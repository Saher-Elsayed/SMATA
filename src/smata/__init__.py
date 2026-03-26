"""
SMATA: Structured Mobile Application Testing Architecture
=========================================================
A modular, reusable framework for standardizing mobile application testing,
inspired by the Universal Verification Methodology (UVM) from hardware verification.

Author: Saher Elsayed, University of Pennsylvania
"""

__version__ = "2.0.0"
__author__ = "Saher Elsayed"
__email__ = "selsayed@seas.upenn.edu"
__license__ = "MIT"

from smata.driver.driver import Driver, DriverConfig, SwitchStrategy
from smata.core.interfaces import (
    ITestAdapter, AdapterConfig, TestRunResult, SessionResult,
    InputEvent, EventType, FailureSignal, FailureType, BugReport,
    ObserverFeedback, Platform,
)
from smata.monitors.input_monitor import InputMonitor, MonitorConfig
from smata.sequencer.sequencer import InitializationSequencer, InitScript, UiAction
from smata.observer.observer import Observer, ObserverConfig
from smata.checker.sanity_checker import SanityChecker, SanityCheckerConfig

__all__ = [
    "Driver", "DriverConfig", "SwitchStrategy",
    "ITestAdapter", "AdapterConfig", "TestRunResult", "SessionResult",
    "InputEvent", "EventType", "FailureSignal", "FailureType", "BugReport",
    "ObserverFeedback", "Platform",
    "InputMonitor", "MonitorConfig",
    "InitializationSequencer", "InitScript", "UiAction",
    "Observer", "ObserverConfig",
    "SanityChecker", "SanityCheckerConfig",
]
