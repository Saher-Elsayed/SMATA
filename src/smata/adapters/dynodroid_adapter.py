"""
SMATA Dynodroid Adapter
=======================
ITestAdapter wrapper for the Dynodroid event-driven testing framework.
Implements the observe-select-execute cycle as an SMATA adapter.

Author: Saher Elsayed
"""
import time
import random
from typing import Optional, List, Dict, Any

from smata.core.interfaces import (
    ITestAdapter, AdapterConfig, TestRunResult, InputEvent, EventType
)
from smata.monitors.input_monitor import InputMonitor
from smata.utils.logger import SMATALogger

logger = SMATALogger.get_logger(__name__)


class DynodroidAdapter(ITestAdapter):
    """
    SMATA adapter wrapping Dynodroid event-driven testing.

    Dynodroid's observe-select-execute cycle is exposed through the
    ITestAdapter interface, allowing the SMATA Driver to orchestrate it
    alongside Monkey, Espresso, and other back-ends.
    """

    ADAPTER_NAME = "dynodroid"

    def __init__(self, input_monitor: Optional[InputMonitor] = None):
        self._input_monitor = input_monitor
        self._app_package: Optional[str] = None
        self._config: Optional[AdapterConfig] = None
        self._event_count = 0
        self._running = False
        self._visited_activities: List[str] = []
        self._current_coverage = 0.0
        self._event_weights: Dict[str, float] = {
            "touch": 0.40,
            "text_input": 0.15,
            "scroll": 0.20,
            "back": 0.10,
            "long_press": 0.10,
            "key_event": 0.05,
        }

    def initialize(self, app_package: str, config: AdapterConfig) -> None:
        self._app_package = app_package
        self._config = config
        self._event_count = 0
        self._visited_activities = []
        self._current_coverage = 0.0
        logger.info(f"DynodroidAdapter initialized | app={app_package}")

    def execute(self, duration_seconds: int) -> TestRunResult:
        """
        Execute Dynodroid observe-select-execute cycle for duration_seconds.
        In production: launches Dynodroid process and parses output.
        """
        if not self._app_package:
            raise RuntimeError("Not initialized.")

        self._running = True
        start_time = time.time()
        start_coverage = self._current_coverage
        crash_count = anr_count = 0

        # Simulate event generation loop
        throttle = (self._config.throttle_ms if self._config else 50) / 1000.0
        while time.time() - start_time < duration_seconds:
            if not self._running:
                break

            # Observe: get current UI state
            ui_state = self._observe()

            # Select: weighted random event from available events
            event_type = self._select_event(ui_state)

            # Execute: generate and log the event
            event = self._execute_event(event_type)
            if event and self._input_monitor:
                self._input_monitor.log_event(event)

            self._event_count += 1

            # Simulate coverage growth (logarithmic saturation)
            elapsed = time.time() - start_time
            self._current_coverage = start_coverage + (
                (45.0 - start_coverage) *
                (1 - 2.718 ** (-0.02 * elapsed))
            )
            self._current_coverage = max(0, min(95, self._current_coverage))

            time.sleep(throttle)

        self._running = False
        elapsed = time.time() - start_time
        delta = self._current_coverage - start_coverage

        result = TestRunResult(
            adapter_name=self.ADAPTER_NAME,
            coverage=self._current_coverage,
            coverage_delta=delta,
            event_count=self._event_count,
            crash_count=crash_count,
            anr_count=anr_count,
            unique_activities=list(set(self._visited_activities)),
            execution_time_s=elapsed,
        )

        logger.info(f"DynodroidAdapter run complete | "
                    f"events={self._event_count} | "
                    f"coverage={self._current_coverage:.1f}% (delta={delta:+.1f}%)")
        return result

    def _observe(self) -> Dict[str, Any]:
        """Observe current UI state. In production: queries UIAutomator."""
        return {
            "screen": f"screen_{random.randint(1, 10)}",
            "clickable_views": random.randint(3, 15),
            "text_fields": random.randint(0, 3),
            "has_scroll": random.random() > 0.5,
        }

    def _select_event(self, ui_state: Dict) -> str:
        """Select the next event type using frequency-based weighting."""
        weights = dict(self._event_weights)
        if ui_state.get("text_fields", 0) == 0:
            weights["text_input"] = 0.0
        if not ui_state.get("has_scroll", False):
            weights["scroll"] = 0.0
        total = sum(weights.values())
        if total == 0:
            return "touch"
        r = random.uniform(0, total)
        cumulative = 0.0
        for etype, w in weights.items():
            cumulative += w
            if r <= cumulative:
                return etype
        return "touch"

    def _execute_event(self, event_type: str) -> Optional[InputEvent]:
        """Generate an InputEvent for the selected event type."""
        type_map = {
            "touch": EventType.TOUCH,
            "text_input": EventType.TEXT_INPUT,
            "scroll": EventType.SCROLL,
            "back": EventType.BACK,
            "long_press": EventType.LONG_PRESS,
            "key_event": EventType.KEY_EVENT,
        }
        etype = type_map.get(event_type, EventType.TOUCH)
        return InputEvent(
            event_type=etype,
            x=random.uniform(0, 1080),
            y=random.uniform(0, 1920),
            adapter_provenance=self.ADAPTER_NAME,
        )

    def update_event_weights(self, weights: Dict[str, float]) -> None:
        """Update the event selection weights (adapts to app behavior)."""
        self._event_weights.update(weights)

    def get_adapter_name(self) -> str:
        return self.ADAPTER_NAME

    def get_event_count(self) -> int:
        return self._event_count

    def get_current_coverage(self) -> float:
        return self._current_coverage

    def get_visited_activities(self) -> List[str]:
        return list(set(self._visited_activities))

    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        self._running = False
        logger.debug("DynodroidAdapter stopped")
