"""
SMATA Driver Component
======================
Central integration hub that orchestrates multiple test-generation back-ends
through the ITestAdapter interface. Implements dynamic methodology switching
driven by Observer feedback.

Corresponds to UVM Driver component adapted for mobile testing.

Author: Saher Elsayed
Affiliation: University of Pennsylvania
"""

import time
import logging
import threading
import json
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from smata.core.interfaces import ITestAdapter, AdapterConfig, TestRunResult, SessionResult
from smata.core.interfaces import ObserverFeedback, DriverEvent, DriverState
from smata.monitors.input_monitor import InputMonitor
from smata.observer.observer import Observer
from smata.utils.logger import SMATALogger
from smata.utils.timing import Timer

logger = SMATALogger.get_logger(__name__)


class SwitchStrategy(Enum):
    """Strategy for selecting the next adapter on tool switch."""
    ROUND_ROBIN = "round_robin"
    COVERAGE_DRIVEN = "coverage_driven"
    TIME_BASED = "time_based"
    OBSERVER_DRIVEN = "observer_driven"


@dataclass
class DriverConfig:
    """Configuration for the SMATA Driver."""
    total_budget_seconds: int = 3600
    slice_seconds: int = 300
    switch_strategy: SwitchStrategy = SwitchStrategy.OBSERVER_DRIVEN
    min_coverage_delta: float = 2.0        # % per slice before switch
    max_cycles_before_switch: int = 3      # state cycles before forced switch
    parallel_execution: bool = False
    log_events: bool = True
    checkpoint_interval: int = 60          # seconds between state checkpoints
    retry_on_crash: bool = True
    max_retries: int = 3
    output_dir: str = "smata_output"


@dataclass
class AdapterStats:
    """Runtime statistics for a single adapter."""
    adapter_name: str
    total_runs: int = 0
    total_events: int = 0
    total_coverage: float = 0.0
    crashes_detected: int = 0
    anrs_detected: int = 0
    coverage_deltas: List[float] = field(default_factory=list)
    run_durations: List[float] = field(default_factory=list)
    switch_reasons: List[str] = field(default_factory=list)

    @property
    def avg_coverage(self) -> float:
        return self.total_coverage / self.total_runs if self.total_runs > 0 else 0.0

    @property
    def avg_coverage_delta(self) -> float:
        return sum(self.coverage_deltas) / len(self.coverage_deltas) if self.coverage_deltas else 0.0

    def to_dict(self) -> Dict:
        return {
            "adapter": self.adapter_name,
            "total_runs": self.total_runs,
            "total_events": self.total_events,
            "avg_coverage": round(self.avg_coverage, 2),
            "avg_delta": round(self.avg_coverage_delta, 2),
            "crashes": self.crashes_detected,
            "anrs": self.anrs_detected,
        }


class Driver:
    """
    SMATA Driver — orchestrates multiple ITestAdapter back-ends.

    The Driver maintains a registry of test-generation adapters and coordinates
    their execution according to a configurable switching strategy. It receives
    feedback from the Observer component to make dynamic tool-switching decisions.

    Usage:
        driver = Driver(config=DriverConfig(total_budget_seconds=3600))
        driver.register_adapter(MonkeyAdapter())
        driver.register_adapter(DynodroidAdapter())
        result = driver.run_session(app_package="com.example.app")
    """

    def __init__(self, config: Optional[DriverConfig] = None,
                 input_monitor: Optional[InputMonitor] = None,
                 observer: Optional[Observer] = None):
        self.config = config or DriverConfig()
        self.input_monitor = input_monitor or InputMonitor()
        self.observer = observer or Observer()
        self._adapters: List[ITestAdapter] = []
        self._adapter_stats: Dict[str, AdapterStats] = {}
        self._current_adapter_idx: int = 0
        self._state: DriverState = DriverState.IDLE
        self._session_result: Optional[SessionResult] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._event_log: List[DriverEvent] = []
        self._session_start_time: float = 0.0
        self._checkpoint_data: Dict[str, Any] = {}
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Driver initialized with strategy={self.config.switch_strategy.value}, "
                    f"budget={self.config.total_budget_seconds}s")

    # ──────────────────────────────────────────────────────────────
    # Adapter Registry
    # ──────────────────────────────────────────────────────────────

    def register_adapter(self, adapter: ITestAdapter) -> None:
        """Register a test-generation back-end."""
        if adapter.get_adapter_name() in self._adapter_stats:
            raise ValueError(f"Adapter '{adapter.get_adapter_name()}' already registered.")
        self._adapters.append(adapter)
        self._adapter_stats[adapter.get_adapter_name()] = AdapterStats(
            adapter_name=adapter.get_adapter_name()
        )
        logger.info(f"Registered adapter: {adapter.get_adapter_name()}")

    def unregister_adapter(self, adapter_name: str) -> bool:
        """Remove a registered adapter by name."""
        for i, adapter in enumerate(self._adapters):
            if adapter.get_adapter_name() == adapter_name:
                self._adapters.pop(i)
                del self._adapter_stats[adapter_name]
                logger.info(f"Unregistered adapter: {adapter_name}")
                return True
        return False

    def get_registered_adapters(self) -> List[str]:
        return [a.get_adapter_name() for a in self._adapters]

    # ──────────────────────────────────────────────────────────────
    # Session Execution
    # ──────────────────────────────────────────────────────────────

    def run_session(self, app_package: str,
                    adapter_config: Optional[AdapterConfig] = None) -> SessionResult:
        """
        Orchestrate a full testing session across all registered adapters.

        The session runs within the configured total budget, switching adapters
        according to the configured strategy and Observer feedback.

        Args:
            app_package: Target Android/iOS application package identifier.
            adapter_config: Optional configuration passed to each adapter on init.

        Returns:
            SessionResult containing per-adapter results and aggregate statistics.
        """
        if not self._adapters:
            raise RuntimeError("No adapters registered. Call register_adapter() first.")

        self._state = DriverState.RUNNING
        self._session_start_time = time.time()
        self._stop_event.clear()
        self._session_result = SessionResult(app_package=app_package)
        self._current_adapter_idx = 0

        logger.info(f"Session started | app={app_package} | "
                    f"adapters={self.get_registered_adapters()} | "
                    f"budget={self.config.total_budget_seconds}s")

        self.input_monitor.start_recording()
        self._log_event(DriverEvent.SESSION_START, {"app_package": app_package})

        try:
            self._execute_session(app_package, adapter_config)
        except KeyboardInterrupt:
            logger.warning("Session interrupted by user.")
            self._stop_event.set()
        except Exception as e:
            logger.error(f"Unexpected session error: {e}", exc_info=True)
            self._session_result.add_error(str(e))
        finally:
            self._finalize_session()

        return self._session_result

    def _execute_session(self, app_package: str,
                         adapter_config: Optional[AdapterConfig]) -> None:
        """Internal session execution loop."""
        budget_ms = self.config.total_budget_seconds * 1000
        last_checkpoint = time.time()

        # Initialize current adapter
        current_adapter = self._adapters[self._current_adapter_idx]
        self._initialize_adapter(current_adapter, app_package, adapter_config)

        consecutive_low_delta = 0
        cycle_count = 0

        while not self._stop_event.is_set():
            elapsed_ms = (time.time() - self._session_start_time) * 1000
            if elapsed_ms >= budget_ms:
                logger.info(f"Budget exhausted after {elapsed_ms/1000:.1f}s")
                break

            remaining_s = (budget_ms - elapsed_ms) / 1000
            slice_s = min(self.config.slice_seconds, remaining_s)
            if slice_s < 10:
                logger.info("Less than 10s remaining — ending session.")
                break

            # Execute one time slice
            logger.info(f"Running {current_adapter.get_adapter_name()} "
                        f"for {slice_s:.0f}s | elapsed={elapsed_ms/1000:.0f}s | "
                        f"remaining={remaining_s:.0f}s")

            run_result = self._execute_slice(current_adapter, int(slice_s))
            self._session_result.add_run_result(
                current_adapter.get_adapter_name(), run_result)
            self._update_adapter_stats(current_adapter.get_adapter_name(), run_result)

            # Observer analysis
            feedback: ObserverFeedback = self.observer.analyze(run_result)
            coverage_delta = feedback.coverage_delta

            logger.info(f"Slice complete | coverage_delta={coverage_delta:.2f}% | "
                        f"should_switch={feedback.should_switch_tool}")

            # Checkpoint
            if time.time() - last_checkpoint >= self.config.checkpoint_interval:
                self._save_checkpoint(app_package)
                last_checkpoint = time.time()

            # Tool switch decision
            if feedback.should_switch_tool:
                next_adapter = self._select_next_adapter(feedback)
                if next_adapter is not None and next_adapter != current_adapter:
                    reason = self._determine_switch_reason(feedback, coverage_delta)
                    logger.info(f"Tool switch: {current_adapter.get_adapter_name()} "
                                f"-> {next_adapter.get_adapter_name()} ({reason})")
                    self._adapter_stats[current_adapter.get_adapter_name()].switch_reasons.append(reason)
                    current_adapter.stop()
                    current_adapter = next_adapter
                    self._initialize_adapter(current_adapter, app_package, adapter_config)
                    self._log_event(DriverEvent.TOOL_SWITCH, {
                        "from": self._adapters[self._current_adapter_idx - 1].get_adapter_name()
                            if self._current_adapter_idx > 0 else "none",
                        "to": current_adapter.get_adapter_name(),
                        "reason": reason,
                    })
                    consecutive_low_delta = 0
                    cycle_count = 0
                else:
                    consecutive_low_delta += 1
            else:
                consecutive_low_delta = 0

        # Stop current adapter
        try:
            current_adapter.stop()
        except Exception:
            pass

    def _execute_slice(self, adapter: ITestAdapter, duration_s: int) -> TestRunResult:
        """Execute a single time slice on the given adapter, with retry on crash."""
        retries = 0
        while retries <= self.config.max_retries:
            try:
                with Timer() as t:
                    result = adapter.execute(duration_s)
                result.execution_time_s = t.elapsed
                stats = self._adapter_stats[adapter.get_adapter_name()]
                stats.total_runs += 1
                stats.total_events += result.event_count
                stats.total_coverage += result.coverage
                stats.run_durations.append(t.elapsed)
                if result.coverage_delta is not None:
                    stats.coverage_deltas.append(result.coverage_delta)
                return result
            except Exception as e:
                retries += 1
                logger.warning(f"Adapter {adapter.get_adapter_name()} failed "
                               f"(attempt {retries}/{self.config.max_retries}): {e}")
                if retries > self.config.max_retries:
                    raise
                time.sleep(5)
        # Should never reach here
        raise RuntimeError("Max retries exceeded")

    def _initialize_adapter(self, adapter: ITestAdapter, app_package: str,
                            config: Optional[AdapterConfig]) -> None:
        """Initialize an adapter with the target app and configuration."""
        cfg = config or AdapterConfig()
        logger.debug(f"Initializing {adapter.get_adapter_name()} for {app_package}")
        adapter.initialize(app_package, cfg)

    def _select_next_adapter(self, feedback: ObserverFeedback) -> Optional[ITestAdapter]:
        """Select the next adapter based on the configured strategy."""
        if len(self._adapters) <= 1:
            return None

        if self.config.switch_strategy == SwitchStrategy.ROUND_ROBIN:
            self._current_adapter_idx = (self._current_adapter_idx + 1) % len(self._adapters)
            return self._adapters[self._current_adapter_idx]

        elif self.config.switch_strategy == SwitchStrategy.COVERAGE_DRIVEN:
            # Pick adapter with highest historical avg delta
            best_idx = 0
            best_delta = -1.0
            for i, adapter in enumerate(self._adapters):
                if i == self._current_adapter_idx:
                    continue
                stats = self._adapter_stats[adapter.get_adapter_name()]
                if stats.avg_coverage_delta > best_delta:
                    best_delta = stats.avg_coverage_delta
                    best_idx = i
            self._current_adapter_idx = best_idx
            return self._adapters[best_idx]

        elif self.config.switch_strategy == SwitchStrategy.OBSERVER_DRIVEN:
            # Use Observer's suggestion if available
            if feedback.suggested_adapter is not None:
                for i, adapter in enumerate(self._adapters):
                    if adapter.get_adapter_name() == feedback.suggested_adapter:
                        self._current_adapter_idx = i
                        return adapter
            # Fallback to round robin
            self._current_adapter_idx = (self._current_adapter_idx + 1) % len(self._adapters)
            return self._adapters[self._current_adapter_idx]

        elif self.config.switch_strategy == SwitchStrategy.TIME_BASED:
            self._current_adapter_idx = (self._current_adapter_idx + 1) % len(self._adapters)
            return self._adapters[self._current_adapter_idx]

        return None

    def _determine_switch_reason(self, feedback: ObserverFeedback,
                                  coverage_delta: float) -> str:
        """Generate a human-readable reason for the tool switch."""
        reasons = []
        if feedback.cycle_detected:
            reasons.append(f"state_cycle_detected")
        if coverage_delta < self.config.min_coverage_delta:
            reasons.append(f"low_delta({coverage_delta:.1f}%<{self.config.min_coverage_delta}%)")
        if feedback.uncovered_activities:
            reasons.append(f"uncovered_activities({len(feedback.uncovered_activities)})")
        return "|".join(reasons) if reasons else "observer_signal"

    def _update_adapter_stats(self, adapter_name: str, result: TestRunResult) -> None:
        stats = self._adapter_stats[adapter_name]
        stats.crashes_detected += result.crash_count
        stats.anrs_detected += result.anr_count

    def _save_checkpoint(self, app_package: str) -> None:
        checkpoint = {
            "timestamp": time.time(),
            "app_package": app_package,
            "elapsed_s": time.time() - self._session_start_time,
            "current_adapter": self._adapters[self._current_adapter_idx].get_adapter_name(),
            "adapter_stats": {k: v.to_dict() for k, v in self._adapter_stats.items()},
            "event_count": self.input_monitor.get_event_count(),
        }
        path = Path(self.config.output_dir) / "checkpoint.json"
        with open(path, "w") as f:
            json.dump(checkpoint, f, indent=2)
        logger.debug(f"Checkpoint saved to {path}")

    def _finalize_session(self) -> None:
        """Stop recording, finalize results, write output."""
        self.input_monitor.stop_recording()
        self._state = DriverState.COMPLETED
        if self._session_result:
            self._session_result.total_events = self.input_monitor.get_event_count()
            self._session_result.total_duration_s = time.time() - self._session_start_time
            self._session_result.adapter_stats = {
                k: v.to_dict() for k, v in self._adapter_stats.items()
            }
        self._log_event(DriverEvent.SESSION_END, {
            "duration_s": time.time() - self._session_start_time,
            "total_events": self.input_monitor.get_event_count(),
        })
        self._write_session_report()
        logger.info(f"Session complete | "
                    f"duration={time.time()-self._session_start_time:.0f}s | "
                    f"events={self.input_monitor.get_event_count()}")

    def _write_session_report(self) -> None:
        if not self._session_result:
            return
        report_path = Path(self.config.output_dir) / "session_report.json"
        with open(report_path, "w") as f:
            json.dump(self._session_result.to_dict(), f, indent=2)
        logger.info(f"Session report written to {report_path}")

    def _log_event(self, event_type: DriverEvent, data: Dict) -> None:
        self._event_log.append({
            "timestamp": time.time(),
            "event": event_type.value,
            "data": data,
        })

    def stop(self) -> None:
        """Signal the session to stop gracefully."""
        logger.info("Stop requested.")
        self._stop_event.set()

    @property
    def state(self) -> DriverState:
        return self._state

    @property
    def elapsed_seconds(self) -> float:
        if self._session_start_time == 0:
            return 0.0
        return time.time() - self._session_start_time

    def get_adapter_stats(self) -> Dict[str, Dict]:
        return {k: v.to_dict() for k, v in self._adapter_stats.items()}

    def __repr__(self) -> str:
        return (f"Driver(adapters={self.get_registered_adapters()}, "
                f"state={self._state.value}, "
                f"strategy={self.config.switch_strategy.value})")
