"""
SMATA Observer Component
========================
Analyzes application behavior and test run results to provide adaptive
feedback to the Driver for tool-switching decisions. Prevents state-space
cycling via coverage delta thresholding and activity visit tracking.

Corresponds to UVM Scoreboard (feedback path) adapted for mobile testing.

Author: Saher Elsayed
"""

import time
from collections import deque, Counter
from typing import List, Optional, Dict, Any, Deque
from dataclasses import dataclass, field

from smata.core.interfaces import (
    TestRunResult, ObserverFeedback, InputEvent, EventType
)
from smata.utils.logger import SMATALogger

logger = SMATALogger.get_logger(__name__)


@dataclass
class ObserverConfig:
    """Configuration for the Observer component."""
    coverage_delta_threshold: float = 2.0       # % per slice to continue same tool
    cycle_detection_window: int = 20             # events in cycle detection window
    cycle_similarity_threshold: float = 0.85    # fraction similarity for cycle detection
    min_runs_before_switch: int = 2             # min runs before allowing switch
    activity_coverage_weight: float = 0.3       # weight of activity coverage in feedback
    stagnation_window: int = 3                  # consecutive low-delta runs before switch
    max_adapter_memory: int = 10               # run history kept per adapter


@dataclass
class RunHistory:
    """History of runs for a single adapter."""
    adapter_name: str
    coverage_history: List[float] = field(default_factory=list)
    delta_history: List[float] = field(default_factory=list)
    activity_history: List[List[str]] = field(default_factory=list)
    state_history: List[List[str]] = field(default_factory=list)
    run_count: int = 0

    def add_run(self, result: TestRunResult) -> None:
        self.coverage_history.append(result.coverage)
        if result.coverage_delta is not None:
            self.delta_history.append(result.coverage_delta)
        self.activity_history.append(result.unique_activities)
        self.state_history.append(result.visited_states)
        self.run_count += 1

    @property
    def avg_delta(self) -> float:
        if not self.delta_history:
            return 0.0
        return sum(self.delta_history[-5:]) / min(5, len(self.delta_history))

    @property
    def last_coverage(self) -> float:
        return self.coverage_history[-1] if self.coverage_history else 0.0

    @property
    def all_visited_activities(self) -> set:
        result = set()
        for acts in self.activity_history:
            result.update(acts)
        return result


class StateTracker:
    """Tracks visited application states to detect state-space cycling."""

    def __init__(self, window_size: int = 20, similarity_threshold: float = 0.85):
        self.window_size = window_size
        self.similarity_threshold = similarity_threshold
        self._recent_states: Deque[str] = deque(maxlen=window_size)
        self._state_counts: Counter = Counter()
        self._total_visits = 0

    def update(self, states: List[str]) -> None:
        for state in states:
            self._recent_states.append(state)
            self._state_counts[state] += 1
            self._total_visits += 1

    def has_cycle(self, new_states: List[str]) -> bool:
        """
        Detect whether the new states represent a repeated pattern.

        A cycle is detected when the fraction of new states that are
        already in the recent history exceeds the similarity threshold.
        """
        if not new_states or len(self._recent_states) < self.window_size // 2:
            return False

        recent_set = set(self._recent_states)
        if not recent_set:
            return False

        overlap = sum(1 for s in new_states if s in recent_set)
        similarity = overlap / len(new_states)

        if similarity >= self.similarity_threshold:
            logger.debug(f"Cycle detected: similarity={similarity:.2f} "
                         f"(threshold={self.similarity_threshold})")
            return True
        return False

    def get_unique_state_count(self) -> int:
        return len(self._state_counts)

    def get_most_visited(self, n: int = 5) -> List[tuple]:
        return self._state_counts.most_common(n)

    def reset(self) -> None:
        self._recent_states.clear()
        self._state_counts.clear()
        self._total_visits = 0


class Observer:
    """
    SMATA Observer

    Analyzes coverage feedback from test runs and signals the Driver
    when a tool switch would likely improve coverage. Key heuristics:

    1. Coverage delta below threshold -> signal switch
    2. State cycle detection (repeated state sequences) -> signal switch
    3. Uncovered activity detection -> suggest targeted exploration
    4. Multi-run stagnation tracking -> forced switch after N low-delta runs

    Usage:
        observer = Observer()
        feedback = observer.analyze(run_result)
        if feedback.should_switch_tool:
            driver.switch_adapter()
    """

    def __init__(self, config: Optional[ObserverConfig] = None):
        self.config = config or ObserverConfig()
        self._last_coverage: float = 0.0
        self._state_tracker = StateTracker(
            window_size=self.config.cycle_detection_window,
            similarity_threshold=self.config.cycle_similarity_threshold,
        )
        self._run_history: Dict[str, RunHistory] = {}
        self._consecutive_low_delta: Dict[str, int] = {}
        self._all_seen_activities: set = set()
        self._analysis_log: List[Dict] = []
        self._total_analyses = 0
        logger.info(f"Observer initialized | "
                    f"delta_threshold={self.config.coverage_delta_threshold}% | "
                    f"cycle_window={self.config.cycle_detection_window}")

    def analyze(self, result: TestRunResult) -> ObserverFeedback:
        """
        Analyze a completed test run and return feedback for the Driver.

        Args:
            result: TestRunResult from the most recent adapter time slice.

        Returns:
            ObserverFeedback indicating whether to switch tools and why.
        """
        adapter = result.adapter_name

        # Update history
        if adapter not in self._run_history:
            self._run_history[adapter] = RunHistory(adapter_name=adapter)
            self._consecutive_low_delta[adapter] = 0
        history = self._run_history[adapter]
        history.add_run(result)

        # Coverage delta
        delta = result.coverage - self._last_coverage
        self._last_coverage = result.coverage

        # State cycle detection
        cycle_detected = self._state_tracker.has_cycle(result.visited_states)
        self._state_tracker.update(result.visited_states)

        # Update seen activities
        self._all_seen_activities.update(result.unique_activities)

        # Uncovered activities
        uncovered = result.uncovered_activities

        # Low delta stagnation
        low_delta = delta < self.config.coverage_delta_threshold
        if low_delta:
            self._consecutive_low_delta[adapter] += 1
        else:
            self._consecutive_low_delta[adapter] = 0

        stagnated = (self._consecutive_low_delta[adapter]
                     >= self.config.stagnation_window)

        # Should switch?
        should_switch = (
            cycle_detected or
            stagnated or
            (low_delta and history.run_count >= self.config.min_runs_before_switch)
        )

        # Suggest best alternate adapter
        suggested = self._suggest_adapter(adapter, uncovered)

        # Build reason string
        reasons = []
        if cycle_detected:
            reasons.append(f"cycle(window={self.config.cycle_detection_window})")
        if stagnated:
            reasons.append(f"stagnated({self._consecutive_low_delta[adapter]}x low delta)")
        if low_delta and not stagnated:
            reasons.append(f"low_delta({delta:.1f}%<{self.config.coverage_delta_threshold}%)")

        reason = "|".join(reasons) if reasons else "ok"

        if should_switch:
            logger.info(f"Observer: switch recommended for {adapter} | reason={reason} | "
                        f"suggested={suggested}")
        else:
            logger.debug(f"Observer: continue {adapter} | "
                         f"delta={delta:.1f}% | cycle={cycle_detected}")

        feedback = ObserverFeedback(
            should_switch_tool=should_switch,
            coverage_delta=delta,
            uncovered_activities=uncovered,
            cycle_detected=cycle_detected,
            suggested_adapter=suggested,
            confidence=self._compute_confidence(history, delta, cycle_detected),
            reason=reason,
        )

        # Log analysis
        self._analysis_log.append({
            "timestamp": time.time(),
            "adapter": adapter,
            "coverage": result.coverage,
            "delta": delta,
            "cycle": cycle_detected,
            "should_switch": should_switch,
            "reason": reason,
        })
        self._total_analyses += 1

        return feedback

    def _suggest_adapter(self, current_adapter: str,
                          uncovered: List[str]) -> Optional[str]:
        """
        Suggest the best alternate adapter based on history.

        Prefers adapters with:
        1. Higher average coverage delta in recent history
        2. Ability to reach uncovered activities (heuristic)
        """
        candidates = {
            name: hist for name, hist in self._run_history.items()
            if name != current_adapter
        }

        if not candidates:
            return None

        # Score each candidate by avg delta
        scores = {name: hist.avg_delta for name, hist in candidates.items()}

        # Boost Dynodroid for auth-heavy uncovered activities
        if uncovered and "dynodroid" in scores:
            auth_keywords = {"login", "auth", "signin", "password", "account"}
            if any(any(kw in act.lower() for kw in auth_keywords)
                   for act in uncovered):
                scores["dynodroid"] = scores.get("dynodroid", 0) + 3.0

        # Return highest scoring candidate
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else None

    def _compute_confidence(self, history: RunHistory,
                             delta: float, cycle: bool) -> float:
        """
        Compute confidence in the switch recommendation (0.0 - 1.0).
        Higher = more confident switch is beneficial.
        """
        confidence = 0.5

        # More history = higher confidence
        if history.run_count >= 3:
            confidence += 0.2

        # Cycle detection = high confidence switch is needed
        if cycle:
            confidence += 0.3

        # Sustained low delta = moderate confidence
        consec = self._consecutive_low_delta.get(history.adapter_name, 0)
        confidence += min(0.2, consec * 0.05)

        return min(1.0, confidence)

    def get_coverage_trend(self, adapter_name: str,
                            window: int = 5) -> Optional[float]:
        """Return the coverage trend (slope) for a given adapter."""
        if adapter_name not in self._run_history:
            return None
        hist = self._run_history[adapter_name].coverage_history[-window:]
        if len(hist) < 2:
            return None
        return (hist[-1] - hist[0]) / len(hist)

    def get_global_coverage(self) -> float:
        """Return the maximum coverage achieved across all adapters."""
        if not self._run_history:
            return 0.0
        return max(
            (h.last_coverage for h in self._run_history.values()),
            default=0.0
        )

    def get_analysis_summary(self) -> Dict[str, Any]:
        return {
            "total_analyses": self._total_analyses,
            "unique_states_seen": self._state_tracker.get_unique_state_count(),
            "unique_activities_seen": len(self._all_seen_activities),
            "adapter_histories": {
                name: {
                    "runs": hist.run_count,
                    "avg_delta": round(hist.avg_delta, 2),
                    "last_coverage": round(hist.last_coverage, 2),
                }
                for name, hist in self._run_history.items()
            },
        }

    def reset(self) -> None:
        """Reset the observer state for a new session."""
        self._last_coverage = 0.0
        self._state_tracker.reset()
        self._run_history.clear()
        self._consecutive_low_delta.clear()
        self._all_seen_activities.clear()
        self._analysis_log.clear()
        self._total_analyses = 0
        logger.info("Observer reset")

    def __repr__(self) -> str:
        return (f"Observer(analyses={self._total_analyses}, "
                f"adapters={list(self._run_history.keys())})")
