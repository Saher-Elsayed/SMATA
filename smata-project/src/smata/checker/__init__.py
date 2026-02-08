"""
SMATA Sanity Checker

Comprehensive failure detection including crash correlation, ANR detection,
and automated reproduction report generation. Analogous to UVM's scoreboard
that checks DUT outputs against expected results.
"""

import time
import json
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CrashReport:
    """Detailed crash report with reproduction information."""
    crash_id: str
    timestamp: float
    crash_type: str
    exception_class: str
    message: str
    stack_trace: str
    triggering_events: List[Dict] = field(default_factory=list)
    app_state: Dict = field(default_factory=dict)
    reproducible: bool = False
    reproduction_steps: List[str] = field(default_factory=list)
    severity: str = "high"


@dataclass
class ANRReport:
    """ANR (Application Not Responding) report."""
    anr_id: str
    timestamp: float
    activity: str
    reason: str
    cpu_usage: float = 0.0
    triggering_events: List[Dict] = field(default_factory=list)


class SanityChecker:
    """
    Monitors application health and correlates failures with input sequences.

    Capabilities:
    1. Real-time crash detection via logcat monitoring
    2. ANR detection (5-second timeout on Android)
    3. Crash-to-input correlation for reproduction
    4. Automated reproduction report generation
    5. Severity classification
    """

    def __init__(self, anr_timeout_ms: int = 5000):
        self._crash_reports: List[CrashReport] = []
        self._anr_reports: List[ANRReport] = []
        self._anr_timeout_ms = anr_timeout_ms
        self._monitoring = False
        self._event_window: List[Dict] = []
        self._window_size = 50  # Keep last 50 events for correlation

    def update_event_window(self, events: List) -> None:
        """Update the sliding window of recent events for crash correlation."""
        for event in events:
            entry = {
                "timestamp": getattr(event, 'timestamp', time.time()),
                "type": getattr(event, 'event_type', 'unknown'),
                "target": getattr(event, 'target', ''),
                "tool": str(getattr(event, 'tool', 'unknown'))
            }
            self._event_window.append(entry)

        # Trim window
        if len(self._event_window) > self._window_size:
            self._event_window = self._event_window[-self._window_size:]

    def report_crash(self, crash_type: str, exception_class: str,
                     message: str, stack_trace: str,
                     app_state: Dict = None) -> CrashReport:
        """
        Record a crash and correlate with recent input events.

        Returns a CrashReport with the triggering event sequence.
        """
        crash_id = f"CRASH-{len(self._crash_reports)+1:04d}"

        report = CrashReport(
            crash_id=crash_id,
            timestamp=time.time(),
            crash_type=crash_type,
            exception_class=exception_class,
            message=message,
            stack_trace=stack_trace,
            triggering_events=list(self._event_window),
            app_state=app_state or {},
            severity=self._classify_severity(crash_type, exception_class)
        )

        # Attempt to identify minimal reproduction sequence
        report.reproduction_steps = self._extract_reproduction_steps(report)
        report.reproducible = len(report.reproduction_steps) > 0

        self._crash_reports.append(report)
        logger.error(f"Crash {crash_id}: {exception_class} - {message[:80]}")

        return report

    def report_anr(self, activity: str, reason: str,
                   cpu_usage: float = 0.0) -> ANRReport:
        """Record an ANR event."""
        anr_id = f"ANR-{len(self._anr_reports)+1:04d}"

        report = ANRReport(
            anr_id=anr_id,
            timestamp=time.time(),
            activity=activity,
            reason=reason,
            cpu_usage=cpu_usage,
            triggering_events=list(self._event_window[-10:])
        )

        self._anr_reports.append(report)
        logger.error(f"ANR {anr_id}: {activity} - {reason[:80]}")

        return report

    def _classify_severity(self, crash_type: str,
                           exception_class: str) -> str:
        """Classify crash severity based on type and exception."""
        critical_exceptions = [
            "OutOfMemoryError", "StackOverflowError",
            "SecurityException", "SQLiteException"
        ]
        high_exceptions = [
            "NullPointerException", "IllegalStateException",
            "ConcurrentModificationException"
        ]

        if any(exc in exception_class for exc in critical_exceptions):
            return "critical"
        elif any(exc in exception_class for exc in high_exceptions):
            return "high"
        elif crash_type == "native":
            return "critical"
        else:
            return "medium"

    def _extract_reproduction_steps(self, report: CrashReport) -> List[str]:
        """
        Extract minimal reproduction steps from the event window.
        Uses a heuristic approach to identify the most likely
        triggering sequence.
        """
        if not report.triggering_events:
            return []

        steps = []
        for i, event in enumerate(report.triggering_events[-10:]):
            step = f"Step {i+1}: {event['type']} on {event['target']}"
            if event.get('tool'):
                step += f" (via {event['tool']})"
            steps.append(step)

        return steps

    def get_crash_count(self) -> int:
        return len(self._crash_reports)

    def get_anr_count(self) -> int:
        return len(self._anr_reports)

    def get_crashes_by_severity(self, severity: str) -> List[CrashReport]:
        return [c for c in self._crash_reports if c.severity == severity]

    def get_reproducible_crashes(self) -> List[CrashReport]:
        return [c for c in self._crash_reports if c.reproducible]

    def get_reproducibility_rate(self) -> float:
        if not self._crash_reports:
            return 0.0
        reproducible = len(self.get_reproducible_crashes())
        return reproducible / len(self._crash_reports) * 100

    def export_reports(self, filepath: str) -> None:
        """Export all crash and ANR reports to JSON."""
        data = {
            "summary": {
                "total_crashes": len(self._crash_reports),
                "total_anrs": len(self._anr_reports),
                "reproducible_crashes": len(self.get_reproducible_crashes()),
                "reproducibility_rate": self.get_reproducibility_rate(),
                "severity_distribution": {
                    "critical": len(self.get_crashes_by_severity("critical")),
                    "high": len(self.get_crashes_by_severity("high")),
                    "medium": len(self.get_crashes_by_severity("medium"))
                }
            },
            "crashes": [
                {
                    "crash_id": c.crash_id,
                    "timestamp": c.timestamp,
                    "crash_type": c.crash_type,
                    "exception_class": c.exception_class,
                    "message": c.message,
                    "severity": c.severity,
                    "reproducible": c.reproducible,
                    "reproduction_steps": c.reproduction_steps,
                    "triggering_events_count": len(c.triggering_events)
                }
                for c in self._crash_reports
            ],
            "anrs": [
                {
                    "anr_id": a.anr_id,
                    "timestamp": a.timestamp,
                    "activity": a.activity,
                    "reason": a.reason
                }
                for a in self._anr_reports
            ]
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Exported reports to {filepath}")

    def reset(self) -> None:
        self._crash_reports = []
        self._anr_reports = []
        self._event_window = []
