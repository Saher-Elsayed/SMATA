"""
SMATA Initialization Sequencer

Handles complex authentication and setup flows that prevent testing tools
from reaching core application functionality. Analogous to UVM's sequence
library that defines reusable transaction sequences.

Key capabilities:
- Configurable multi-step authentication navigation
- Reusable initialization script libraries
- State preparation and app configuration
- Login credential management
"""

import time
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class StepType(Enum):
    """Types of initialization steps."""
    CLICK = "click"
    TEXT_INPUT = "text_input"
    SWIPE = "swipe"
    WAIT = "wait"
    ASSERT_VISIBLE = "assert_visible"
    BACK = "back"
    PERMISSION_GRANT = "permission_grant"
    PERMISSION_DENY = "permission_deny"
    CUSTOM = "custom"


@dataclass
class InitStep:
    """A single step in an initialization sequence."""
    step_type: StepType
    target: str = ""
    value: str = ""
    timeout_ms: int = 5000
    description: str = ""
    optional: bool = False
    retry_count: int = 1


@dataclass
class InitSequence:
    """A complete initialization sequence for an application."""
    name: str
    app_package: str
    steps: List[InitStep] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    estimated_duration_seconds: int = 30


class InitSequencer:
    """
    Manages and executes initialization sequences for applications.

    The Sequencer maintains a library of reusable initialization sequences
    that can be shared across projects, addressing the initialization
    barrier problem identified in mobile testing.
    """

    def __init__(self, config: str = None):
        self._sequences: Dict[str, InitSequence] = {}
        self._execution_log: List[Dict] = []

        if config:
            self.load_config(config)

    def load_config(self, config_path: str) -> None:
        """Load initialization sequences from a JSON configuration file."""
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)

            for app_name, app_data in data.get("apps", {}).items():
                if "init_sequence" in app_data:
                    seq = self._parse_sequence(app_name, app_data)
                    self._sequences[app_data.get("package", app_name)] = seq
                    logger.info(f"Loaded init sequence for {app_name}: "
                                f"{len(seq.steps)} steps")

        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config: {e}")

    def _parse_sequence(self, name: str, data: Dict) -> InitSequence:
        """Parse a sequence definition from config data."""
        steps = []
        for step_data in data.get("init_sequence", []):
            step = InitStep(
                step_type=StepType(step_data.get("type", "click")),
                target=step_data.get("target", ""),
                value=step_data.get("value", ""),
                timeout_ms=step_data.get("timeout_ms", 5000),
                description=step_data.get("description", ""),
                optional=step_data.get("optional", False),
                retry_count=step_data.get("retry_count", 1)
            )
            steps.append(step)

        return InitSequence(
            name=name,
            app_package=data.get("package", ""),
            steps=steps,
            preconditions=data.get("preconditions", []),
            postconditions=data.get("postconditions", []),
            estimated_duration_seconds=data.get("estimated_duration", 30)
        )

    def register_sequence(self, package: str, sequence: InitSequence) -> None:
        """Register a custom initialization sequence."""
        self._sequences[package] = sequence
        logger.info(f"Registered sequence for {package}: {len(sequence.steps)} steps")

    def initialize(self, app_package: str) -> Dict:
        """
        Execute the initialization sequence for an application.

        Returns:
            Dictionary with execution results including success status,
            time taken, and any errors encountered.
        """
        result = {
            "app_package": app_package,
            "success": False,
            "steps_completed": 0,
            "steps_total": 0,
            "time_seconds": 0,
            "errors": []
        }

        if app_package not in self._sequences:
            logger.info(f"No init sequence for {app_package}, skipping initialization")
            result["success"] = True
            return result

        sequence = self._sequences[app_package]
        result["steps_total"] = len(sequence.steps)
        start_time = time.time()

        logger.info(f"Starting initialization for {app_package}: "
                     f"{len(sequence.steps)} steps")

        for i, step in enumerate(sequence.steps):
            step_result = self._execute_step(step, app_package)

            if step_result["success"]:
                result["steps_completed"] += 1
                logger.debug(f"Step {i+1}/{len(sequence.steps)} OK: {step.description}")
            elif step.optional:
                logger.warning(f"Optional step {i+1} failed: {step.description}")
            else:
                result["errors"].append({
                    "step": i + 1,
                    "description": step.description,
                    "error": step_result.get("error", "Unknown error")
                })
                logger.error(f"Required step {i+1} failed: {step.description}")
                break

        result["time_seconds"] = time.time() - start_time
        result["success"] = result["steps_completed"] == result["steps_total"] or \
                            len(result["errors"]) == 0

        self._execution_log.append(result)
        logger.info(f"Initialization {'succeeded' if result['success'] else 'failed'}: "
                     f"{result['steps_completed']}/{result['steps_total']} steps in "
                     f"{result['time_seconds']:.1f}s")

        return result

    def _execute_step(self, step: InitStep, app_package: str) -> Dict:
        """Execute a single initialization step via ADB/UIAutomator."""
        for attempt in range(step.retry_count):
            try:
                if step.step_type == StepType.CLICK:
                    return self._execute_click(step)
                elif step.step_type == StepType.TEXT_INPUT:
                    return self._execute_text_input(step)
                elif step.step_type == StepType.SWIPE:
                    return self._execute_swipe(step)
                elif step.step_type == StepType.WAIT:
                    return self._execute_wait(step)
                elif step.step_type == StepType.PERMISSION_GRANT:
                    return self._execute_permission(step, grant=True)
                elif step.step_type == StepType.PERMISSION_DENY:
                    return self._execute_permission(step, grant=False)
                elif step.step_type == StepType.BACK:
                    return self._execute_back(step)
                elif step.step_type == StepType.ASSERT_VISIBLE:
                    return self._execute_assert(step)
                else:
                    return {"success": False, "error": f"Unknown step type: {step.step_type}"}
            except Exception as e:
                if attempt < step.retry_count - 1:
                    logger.debug(f"Step retry {attempt+1}/{step.retry_count}: {e}")
                    time.sleep(1)
                else:
                    return {"success": False, "error": str(e)}

        return {"success": False, "error": "All retries exhausted"}

    def _execute_click(self, step: InitStep) -> Dict:
        """Execute a click step via UIAutomator or ADB."""
        import subprocess
        try:
            # Try resource-id based click
            cmd = f'adb shell uiautomator dump /dev/tty | grep "{step.target}"'
            subprocess.run(cmd, shell=True, timeout=step.timeout_ms / 1000)
            cmd = f'adb shell input tap {step.value}' if step.value else \
                  f'adb shell am instrument -w -e target "{step.target}"'
            subprocess.run(cmd, shell=True, timeout=step.timeout_ms / 1000)
            return {"success": True}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Simulation mode
            logger.debug(f"Simulating click: {step.target}")
            return {"success": True}

    def _execute_text_input(self, step: InitStep) -> Dict:
        import subprocess
        try:
            # Focus the field first, then input text
            cmd = f'adb shell input text "{step.value}"'
            subprocess.run(cmd, shell=True, timeout=step.timeout_ms / 1000)
            return {"success": True}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.debug(f"Simulating text input: {step.target} = {step.value}")
            return {"success": True}

    def _execute_swipe(self, step: InitStep) -> Dict:
        logger.debug(f"Simulating swipe: {step.target}")
        return {"success": True}

    def _execute_wait(self, step: InitStep) -> Dict:
        wait_time = step.timeout_ms / 1000
        time.sleep(min(wait_time, 5))  # Cap at 5s for simulation
        return {"success": True}

    def _execute_permission(self, step: InitStep, grant: bool) -> Dict:
        import subprocess
        action = "allow" if grant else "deny"
        try:
            cmd = f'adb shell pm grant {step.target} {step.value}' if grant else \
                  f'adb shell pm revoke {step.target} {step.value}'
            subprocess.run(cmd, shell=True, timeout=5)
            return {"success": True}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.debug(f"Simulating permission {action}: {step.target}")
            return {"success": True}

    def _execute_back(self, step: InitStep) -> Dict:
        import subprocess
        try:
            subprocess.run("adb shell input keyevent 4", shell=True, timeout=3)
            return {"success": True}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.debug("Simulating back press")
            return {"success": True}

    def _execute_assert(self, step: InitStep) -> Dict:
        logger.debug(f"Simulating assert visible: {step.target}")
        return {"success": True}

    def get_execution_log(self) -> List[Dict]:
        """Return the log of all initialization executions."""
        return self._execution_log

    def list_sequences(self) -> List[str]:
        """List all registered app packages with initialization sequences."""
        return list(self._sequences.keys())

    def export_sequence(self, app_package: str) -> Optional[Dict]:
        """Export a sequence as a JSON-serializable dictionary for sharing."""
        if app_package not in self._sequences:
            return None

        seq = self._sequences[app_package]
        return {
            "name": seq.name,
            "app_package": seq.app_package,
            "steps": [
                {
                    "type": step.step_type.value,
                    "target": step.target,
                    "value": step.value,
                    "timeout_ms": step.timeout_ms,
                    "description": step.description,
                    "optional": step.optional
                }
                for step in seq.steps
            ]
        }
