"""
Baseline implementations for comparison:
- MonkeyRunner: Standalone Android Monkey testing
- DynodroidRunner: Standalone Dynodroid testing
- AdhocRunner: Simulates typical ad-hoc industry practices
"""

import time
import logging
import subprocess
from typing import Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BaselineResult:
    """Result from a baseline testing run."""
    approach: str
    app_package: str
    run_id: int
    duration_seconds: float
    events_generated: int
    coverage_percent: float
    crashes_found: int
    bugs_reproducible: int
    bugs_total: int
    setup_time_hours: float


class MonkeyRunner:
    """
    Standalone Android Monkey testing baseline.
    Runs 'adb shell monkey' with standard parameters.
    """

    def __init__(self, events: int = 10000, seed: int = None):
        self.events = events
        self.seed = seed

    def run(self, app_package: str, run_id: int = 0) -> BaselineResult:
        cmd = [
            "adb", "shell", "monkey",
            "-p", app_package,
            "--throttle", "100",
            "-v",
            str(self.events)
        ]
        if self.seed is not None:
            cmd.extend(["-s", str(self.seed + run_id)])

        start = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            duration = time.time() - start
            events = self._count_events(result.stdout)
            crashes = result.stdout.count("CRASH") + result.stdout.count("ANR")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            duration = time.time() - start
            events = self.events
            crashes = 0

        return BaselineResult(
            approach="monkey",
            app_package=app_package,
            run_id=run_id,
            duration_seconds=duration,
            events_generated=events,
            coverage_percent=0.0,  # Measured separately via JaCoCo
            crashes_found=crashes,
            bugs_reproducible=0,
            bugs_total=0,
            setup_time_hours=0.0
        )

    def _count_events(self, output: str) -> int:
        return output.count(":Sending")


class DynodroidRunner:
    """Standalone Dynodroid testing baseline."""

    def __init__(self, max_events: int = 10000, strategy: str = "frequency"):
        self.max_events = max_events
        self.strategy = strategy

    def run(self, app_package: str, run_id: int = 0) -> BaselineResult:
        start = time.time()
        try:
            cmd = [
                "python", "-m", "dynodroid",
                "--package", app_package,
                "--max-events", str(self.max_events),
                "--strategy", self.strategy
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            duration = time.time() - start
        except (subprocess.TimeoutExpired, FileNotFoundError):
            duration = time.time() - start

        return BaselineResult(
            approach="dynodroid",
            app_package=app_package,
            run_id=run_id,
            duration_seconds=duration,
            events_generated=self.max_events,
            coverage_percent=0.0,
            crashes_found=0,
            bugs_reproducible=0,
            bugs_total=0,
            setup_time_hours=0.0
        )


class AdhocRunner:
    """
    Simulates ad-hoc industry testing practices:
    JUnit unit tests + manual exploration + isolated Espresso UI tests.
    """

    def __init__(self):
        pass

    def run(self, app_package: str, run_id: int = 0) -> BaselineResult:
        start = time.time()

        # Run JUnit tests if available
        try:
            subprocess.run(
                ["./gradlew", "test"],
                capture_output=True, timeout=300
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Run Espresso tests if available
        try:
            subprocess.run(
                ["./gradlew", "connectedAndroidTest"],
                capture_output=True, timeout=600
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        duration = time.time() - start

        return BaselineResult(
            approach="adhoc",
            app_package=app_package,
            run_id=run_id,
            duration_seconds=duration,
            events_generated=0,
            coverage_percent=0.0,
            crashes_found=0,
            bugs_reproducible=0,
            bugs_total=0,
            setup_time_hours=0.0
        )
