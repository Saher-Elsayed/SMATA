"""Tests for SMATA Observer component."""
import pytest
import sys
sys.path.insert(0, "src")

from smata.observer.observer import Observer, ObserverConfig, StateTracker
from smata.core.interfaces import TestRunResult, ObserverFeedback


def make_result(adapter="monkey", coverage=50.0, delta=2.0,
                states=None, activities=None, crashes=0):
    r = TestRunResult(adapter_name=adapter, coverage=coverage,
                      coverage_delta=delta, event_count=100,
                      crash_count=crashes)
    if states: r.visited_states = states
    if activities: r.unique_activities = activities
    return r


class TestStateTracker:

    def test_no_cycle_on_empty(self):
        tracker = StateTracker(window_size=10)
        assert tracker.has_cycle(["state_1", "state_2"]) is False

    def test_cycle_detected_on_repetition(self):
        tracker = StateTracker(window_size=10, similarity_threshold=0.8)
        states = ["s1", "s2", "s3", "s4", "s5"]
        tracker.update(states)
        tracker.update(states)
        assert tracker.has_cycle(states) is True

    def test_no_cycle_on_new_states(self):
        tracker = StateTracker(window_size=10, similarity_threshold=0.8)
        tracker.update(["s1", "s2", "s3"])
        assert tracker.has_cycle(["s4", "s5", "s6"]) is False

    def test_unique_state_count(self):
        tracker = StateTracker()
        tracker.update(["s1", "s2", "s3"])
        tracker.update(["s1", "s4"])
        assert tracker.get_unique_state_count() == 4


class TestObserver:

    def setup_method(self):
        config = ObserverConfig(
            coverage_delta_threshold=2.0,
            stagnation_window=3,
            min_runs_before_switch=1,
        )
        self.observer = Observer(config=config)

    def test_no_switch_on_good_delta(self):
        result = make_result(coverage=55.0, delta=5.0)
        feedback = self.observer.analyze(result)
        assert feedback.should_switch_tool is False

    def test_switch_on_low_delta_sustained(self):
        for _ in range(3):
            result = make_result(coverage=50.0, delta=0.5)
            feedback = self.observer.analyze(result)
        assert feedback.should_switch_tool is True

    def test_switch_on_cycle(self):
        states = ["s1", "s2", "s3", "s4", "s5",
                  "s6", "s7", "s8", "s9", "s10"]
        # Fill state history
        for _ in range(3):
            result = make_result(delta=5.0, states=states)
            self.observer.analyze(result)
        # Now repeat same states — should trigger cycle
        result = make_result(delta=3.0, states=states)
        feedback = self.observer.analyze(result)
        assert feedback.cycle_detected is True
        assert feedback.should_switch_tool is True

    def test_coverage_delta_in_feedback(self):
        self.observer._last_coverage = 40.0
        result = make_result(coverage=47.0, delta=7.0)
        feedback = self.observer.analyze(result)
        assert abs(feedback.coverage_delta - 7.0) < 0.1

    def test_reset_clears_state(self):
        for _ in range(5):
            self.observer.analyze(make_result(delta=0.5))
        self.observer.reset()
        assert self.observer._total_analyses == 0
        assert self.observer._last_coverage == 0.0
