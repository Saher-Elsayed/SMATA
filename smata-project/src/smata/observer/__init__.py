"""
SMATA Observer Component

Implements intelligent analysis of application behavior, providing
feedback to the Driver for adaptive test generation. Analogous to
UVM's functional coverage collector and analysis components.
"""

import time
import logging
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ActivityCoverage:
    """Coverage information for a single activity."""
    activity_name: str
    visit_count: int = 0
    unique_actions: Set[str] = field(default_factory=set)
    transitions_out: Set[str] = field(default_factory=set)
    time_spent_seconds: float = 0.0
    last_visited: float = 0.0


class Observer:
    """
    Analyzes application behavior and provides adaptive feedback.

    The Observer tracks:
    1. Activity/screen coverage and transition patterns
    2. UI element interaction coverage
    3. Unexplored regions of the application
    4. Coverage velocity and plateau detection

    It feeds recommendations back to the Driver to guide tool switching
    and test generation strategy.
    """

    def __init__(self):
        self._activity_coverage: Dict[str, ActivityCoverage] = {}
        self._transition_graph: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._current_activity: Optional[str] = None
        self._element_interactions: Dict[str, Set[str]] = defaultdict(set)
        self._coverage_samples: List[Dict] = []
        self._start_time = time.time()

    def observe_state(self, activity: str, visible_elements: List[str] = None,
                      interacted_elements: List[str] = None) -> None:
        """
        Record an observation of the current application state.

        Args:
            activity: Current activity/screen name
            visible_elements: List of visible UI element IDs
            interacted_elements: List of elements that were interacted with
        """
        now = time.time()

        # Track activity coverage
        if activity not in self._activity_coverage:
            self._activity_coverage[activity] = ActivityCoverage(
                activity_name=activity
            )

        cov = self._activity_coverage[activity]
        cov.visit_count += 1
        cov.last_visited = now

        # Track transitions
        if self._current_activity and self._current_activity != activity:
            self._transition_graph[self._current_activity][activity] += 1
            cov_prev = self._activity_coverage.get(self._current_activity)
            if cov_prev:
                cov_prev.transitions_out.add(activity)

        self._current_activity = activity

        # Track element interactions
        if visible_elements:
            self._element_interactions[activity].update(visible_elements)
        if interacted_elements:
            cov.unique_actions.update(interacted_elements)

    def get_coverage_recommendation(self) -> Dict:
        """
        Analyze current coverage and recommend testing strategy adjustments.

        Returns:
            Dictionary with recommendations for the Driver:
            - underexplored_activities: Activities that need more testing
            - suggested_strategy: Recommended tool/approach
            - coverage_velocity: Current rate of new coverage
            - estimated_remaining: Estimated remaining uncovered percentage
        """
        underexplored = []
        for name, cov in self._activity_coverage.items():
            if cov.visit_count < 3:
                underexplored.append(name)
            elif len(cov.unique_actions) < 5:
                underexplored.append(name)

        # Determine strategy based on coverage state
        total_activities = len(self._activity_coverage)
        explored_well = sum(
            1 for c in self._activity_coverage.values()
            if c.visit_count >= 3 and len(c.unique_actions) >= 5
        )

        if total_activities == 0:
            strategy = "monkey"  # Broad exploration first
        elif explored_well / max(total_activities, 1) < 0.5:
            strategy = "dynodroid"  # Targeted exploration
        else:
            strategy = "monkey"  # Random to find edge cases

        # Calculate coverage velocity
        velocity = 0.0
        if len(self._coverage_samples) >= 2:
            recent = self._coverage_samples[-5:]
            if len(recent) >= 2:
                time_delta = recent[-1]["timestamp"] - recent[0]["timestamp"]
                cov_delta = recent[-1]["coverage"] - recent[0]["coverage"]
                velocity = cov_delta / max(time_delta, 1) * 60  # per minute

        return {
            "underexplored_activities": underexplored,
            "suggested_strategy": strategy,
            "coverage_velocity": velocity,
            "total_activities": total_activities,
            "well_explored": explored_well,
            "exploration_ratio": explored_well / max(total_activities, 1)
        }

    def record_coverage_sample(self, coverage_percent: float) -> None:
        """Record a coverage measurement for velocity tracking."""
        self._coverage_samples.append({
            "timestamp": time.time(),
            "coverage": coverage_percent
        })

    def get_activity_graph(self) -> Dict:
        """Return the activity transition graph for visualization."""
        return {
            "nodes": [
                {
                    "id": name,
                    "visits": cov.visit_count,
                    "actions": len(cov.unique_actions)
                }
                for name, cov in self._activity_coverage.items()
            ],
            "edges": [
                {"from": src, "to": dst, "count": count}
                for src, dsts in self._transition_graph.items()
                for dst, count in dsts.items()
            ]
        }

    def get_summary(self) -> Dict:
        """Return a summary of observed behavior."""
        return {
            "total_activities": len(self._activity_coverage),
            "total_transitions": sum(
                count
                for dsts in self._transition_graph.values()
                for count in dsts.values()
            ),
            "total_unique_actions": sum(
                len(cov.unique_actions)
                for cov in self._activity_coverage.values()
            ),
            "coverage_samples": len(self._coverage_samples),
            "observation_duration_seconds": time.time() - self._start_time
        }

    def reset(self) -> None:
        self._activity_coverage = {}
        self._transition_graph = defaultdict(lambda: defaultdict(int))
        self._current_activity = None
        self._element_interactions = defaultdict(set)
        self._coverage_samples = []
        self._start_time = time.time()
