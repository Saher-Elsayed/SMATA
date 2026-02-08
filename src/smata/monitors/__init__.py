"""
SMATA Monitor Components

Input Monitor: Tracks all input events and tool activities, forming the
foundation for coverage analysis and test reproduction.

Output Monitor: Observes all application state changes and responses,
monitoring UI transitions, performance metrics, and crash events.

Analogous to UVM monitors that observe interface activity without
modifying the transaction flow.
"""

import time
import json
import hashlib
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class EventSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MonitorEvent:
    """A monitored event with full context for reproduction."""
    timestamp: float
    event_id: str
    source: str
    event_type: str
    details: Dict[str, Any] = field(default_factory=dict)
    severity: EventSeverity = EventSeverity.INFO
    screenshot_path: Optional[str] = None


class InputMonitor:
    """
    Records all input events for coverage analysis and reproduction.

    The Input Monitor provides:
    1. Comprehensive event recording with precise timestamps
    2. Event sequence hashing for reproduction verification
    3. Coverage correlation (events → code paths)
    4. Export to multiple formats (JSON, CSV) for analysis
    """

    def __init__(self, log_dir: str = "data/raw"):
        self._events: List[MonitorEvent] = []
        self._log_dir = log_dir
        self._session_id = str(int(time.time()))
        self._sequence_hash = hashlib.md5()

    def record_events(self, events: List) -> None:
        """Record a batch of test events from a tool adapter."""
        for event in events:
            monitored = MonitorEvent(
                timestamp=getattr(event, 'timestamp', time.time()),
                event_id=f"input_{len(self._events):06d}",
                source=getattr(event, 'tool', 'unknown'),
                event_type=getattr(event, 'event_type', 'unknown'),
                details={
                    "target": getattr(event, 'target', ''),
                    "parameters": getattr(event, 'parameters', {})
                }
            )
            self._events.append(monitored)

            # Update sequence hash for reproduction verification
            event_str = f"{monitored.event_type}:{monitored.details}"
            self._sequence_hash.update(event_str.encode())

    def record_single(self, source: str, event_type: str,
                      details: Dict = None) -> str:
        """Record a single event and return its ID."""
        event = MonitorEvent(
            timestamp=time.time(),
            event_id=f"input_{len(self._events):06d}",
            source=source,
            event_type=event_type,
            details=details or {}
        )
        self._events.append(event)
        return event.event_id

    def get_sequence_hash(self) -> str:
        """Return hash of the event sequence for reproduction verification."""
        return self._sequence_hash.hexdigest()

    def get_event_count(self) -> int:
        return len(self._events)

    def get_events_by_type(self, event_type: str) -> List[MonitorEvent]:
        return [e for e in self._events if e.event_type == event_type]

    def get_events_in_range(self, start_time: float,
                            end_time: float) -> List[MonitorEvent]:
        return [e for e in self._events
                if start_time <= e.timestamp <= end_time]

    def export_json(self, filepath: str = None) -> str:
        """Export all events to JSON."""
        if filepath is None:
            filepath = f"{self._log_dir}/input_events_{self._session_id}.json"

        data = {
            "session_id": self._session_id,
            "sequence_hash": self.get_sequence_hash(),
            "event_count": len(self._events),
            "events": [
                {
                    "timestamp": e.timestamp,
                    "event_id": e.event_id,
                    "source": str(e.source),
                    "event_type": e.event_type,
                    "details": e.details
                }
                for e in self._events
            ]
        }

        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Exported {len(self._events)} input events to {filepath}")
        except IOError as e:
            logger.error(f"Failed to export: {e}")

        return filepath

    def export_csv(self, filepath: str = None) -> str:
        """Export events to CSV for analysis."""
        if filepath is None:
            filepath = f"{self._log_dir}/input_events_{self._session_id}.csv"

        try:
            with open(filepath, 'w') as f:
                f.write("timestamp,event_id,source,event_type,target,parameters\n")
                for e in self._events:
                    target = e.details.get("target", "")
                    params = json.dumps(e.details.get("parameters", {}))
                    f.write(f"{e.timestamp},{e.event_id},{e.source},"
                            f"{e.event_type},{target},\"{params}\"\n")
            logger.info(f"Exported {len(self._events)} events to {filepath}")
        except IOError as e:
            logger.error(f"Failed to export CSV: {e}")

        return filepath

    def generate_reproduction_script(self) -> str:
        """Generate a script that can reproduce the recorded event sequence."""
        lines = [
            "#!/usr/bin/env python3",
            "\"\"\"Auto-generated reproduction script from SMATA Input Monitor.\"\"\"",
            "import subprocess",
            "import time",
            "",
            f"# Session: {self._session_id}",
            f"# Sequence hash: {self.get_sequence_hash()}",
            f"# Total events: {len(self._events)}",
            "",
            "def reproduce():",
        ]

        prev_time = self._events[0].timestamp if self._events else 0
        for event in self._events:
            delay = event.timestamp - prev_time
            if delay > 0.01:
                lines.append(f"    time.sleep({delay:.3f})")

            if event.event_type == "touch":
                params = event.details.get("parameters", {})
                x = params.get("x", 500)
                y = params.get("y", 500)
                lines.append(f"    subprocess.run(['adb', 'shell', 'input', "
                             f"'tap', '{x}', '{y}'])")
            elif event.event_type == "text_input":
                text = event.details.get("parameters", {}).get("text", "")
                lines.append(f"    subprocess.run(['adb', 'shell', 'input', "
                             f"'text', '{text}'])")
            elif event.event_type == "key":
                key = event.details.get("parameters", {}).get("keycode", "")
                lines.append(f"    subprocess.run(['adb', 'shell', 'input', "
                             f"'keyevent', '{key}'])")

            prev_time = event.timestamp

        lines.extend(["", "if __name__ == '__main__':", "    reproduce()"])
        return "\n".join(lines)

    def reset(self) -> None:
        """Clear all recorded events."""
        self._events = []
        self._sequence_hash = hashlib.md5()
        self._session_id = str(int(time.time()))


class OutputMonitor:
    """
    Monitors application output: UI state, performance, crashes, ANR events.

    The Output Monitor provides:
    1. UI state tracking (activity transitions, view hierarchy changes)
    2. Performance metric collection (memory, CPU, frame rate)
    3. Crash and ANR detection with context capture
    4. Log collection and filtering
    """

    def __init__(self, log_dir: str = "data/raw"):
        self._events: List[MonitorEvent] = []
        self._log_dir = log_dir
        self._session_id = str(int(time.time()))
        self._state_history: List[Dict] = []
        self._performance_samples: List[Dict] = []
        self._crash_count = 0
        self._anr_count = 0

    def record_state_change(self, activity: str, state: str,
                            view_hierarchy: Dict = None) -> None:
        """Record a UI state transition."""
        event = MonitorEvent(
            timestamp=time.time(),
            event_id=f"state_{len(self._events):06d}",
            source="ui_automator",
            event_type="state_change",
            details={
                "activity": activity,
                "state": state,
                "view_hierarchy": view_hierarchy
            }
        )
        self._events.append(event)
        self._state_history.append({
            "timestamp": event.timestamp,
            "activity": activity,
            "state": state
        })

    def record_crash(self, crash_type: str, stack_trace: str,
                     triggering_event_id: str = None) -> str:
        """Record an application crash with context."""
        self._crash_count += 1
        event = MonitorEvent(
            timestamp=time.time(),
            event_id=f"crash_{self._crash_count:04d}",
            source="logcat",
            event_type="crash",
            severity=EventSeverity.CRITICAL,
            details={
                "crash_type": crash_type,
                "stack_trace": stack_trace,
                "triggering_event": triggering_event_id
            }
        )
        self._events.append(event)
        logger.error(f"Crash detected: {crash_type}")
        return event.event_id

    def record_anr(self, details: str,
                   triggering_event_id: str = None) -> str:
        """Record an Application Not Responding event."""
        self._anr_count += 1
        event = MonitorEvent(
            timestamp=time.time(),
            event_id=f"anr_{self._anr_count:04d}",
            source="logcat",
            event_type="anr",
            severity=EventSeverity.ERROR,
            details={
                "details": details,
                "triggering_event": triggering_event_id
            }
        )
        self._events.append(event)
        logger.error(f"ANR detected: {details[:100]}")
        return event.event_id

    def record_performance(self, metrics: Dict) -> None:
        """Record a performance sample."""
        sample = {
            "timestamp": time.time(),
            "memory_mb": metrics.get("memory_mb", 0),
            "cpu_percent": metrics.get("cpu_percent", 0),
            "fps": metrics.get("fps", 0),
            "battery_percent": metrics.get("battery_percent", 100)
        }
        self._performance_samples.append(sample)

    def get_crash_count(self) -> int:
        return self._crash_count

    def get_anr_count(self) -> int:
        return self._anr_count

    def get_unique_activities(self) -> List[str]:
        """Return list of unique activities visited."""
        return list(set(s["activity"] for s in self._state_history))

    def get_state_transitions(self) -> int:
        """Return total number of state transitions."""
        return len(self._state_history)

    def get_performance_summary(self) -> Dict:
        """Return summary statistics of performance metrics."""
        if not self._performance_samples:
            return {}

        import statistics
        memory = [s["memory_mb"] for s in self._performance_samples]
        cpu = [s["cpu_percent"] for s in self._performance_samples]

        return {
            "memory_avg_mb": statistics.mean(memory),
            "memory_max_mb": max(memory),
            "cpu_avg_percent": statistics.mean(cpu),
            "cpu_max_percent": max(cpu),
            "samples": len(self._performance_samples)
        }

    def export_json(self, filepath: str = None) -> str:
        if filepath is None:
            filepath = f"{self._log_dir}/output_events_{self._session_id}.json"

        data = {
            "session_id": self._session_id,
            "event_count": len(self._events),
            "crash_count": self._crash_count,
            "anr_count": self._anr_count,
            "unique_activities": len(self.get_unique_activities()),
            "events": [
                {
                    "timestamp": e.timestamp,
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "severity": e.severity.value,
                    "details": e.details
                }
                for e in self._events
            ],
            "performance": self._performance_samples
        }

        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to export: {e}")

        return filepath

    def reset(self) -> None:
        self._events = []
        self._state_history = []
        self._performance_samples = []
        self._crash_count = 0
        self._anr_count = 0
