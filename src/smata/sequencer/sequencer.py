"""
SMATA Initialization Sequencer
===============================
Automates navigation through complex authentication and multi-step setup flows
before handing control to the Driver. Executes reusable initialization script
libraries defined in JSON/DSL format.

Corresponds to UVM Sequencer adapted for mobile app state initialization.

Author: Saher Elsayed
"""

import json
import time
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable

from smata.core.interfaces import ISequencer, Platform
from smata.utils.logger import SMATALogger

logger = SMATALogger.get_logger(__name__)


@dataclass
class UiAction:
    """A single UI action in an initialization script."""
    action_type: str           # tap, swipe, type_text, wait, scroll, back, assert_text
    target: Optional[str] = None      # view ID, xpath, or content description
    value: Optional[str] = None       # text to type, direction to swipe, etc.
    x: Optional[float] = None
    y: Optional[float] = None
    timeout_ms: int = 5000
    optional: bool = False            # if True, failure does not abort script
    description: str = ""

    def to_dict(self) -> Dict:
        return {
            "action": self.action_type,
            "target": self.target,
            "value": self.value,
            "timeout_ms": self.timeout_ms,
            "optional": self.optional,
        }


@dataclass
class InitScript:
    """A complete initialization script for a specific app state."""
    name: str
    description: str
    state_patterns: List[str]    # regex patterns matching app states where this script applies
    actions: List[UiAction]
    expected_final_state: Optional[str] = None
    platform: str = "any"        # android, ios, any
    app_package: Optional[str] = None
    priority: int = 0            # higher = tried first
    tags: List[str] = field(default_factory=list)

    def matches(self, current_state: str, platform: str = "android") -> bool:
        """Check whether this script applies to the given app state."""
        if self.platform not in ("any", platform):
            return False
        return any(re.search(pat, current_state, re.IGNORECASE)
                   for pat in self.state_patterns)

    def execute(self, bridge: "UiAutomatorBridge") -> bool:
        """Execute the script using the given UI bridge. Returns True on success."""
        logger.info(f"Executing init script: {self.name} ({len(self.actions)} actions)")
        for i, action in enumerate(self.actions):
            logger.debug(f"  Step {i+1}/{len(self.actions)}: {action.action_type} "
                         f"target={action.target} value={action.value}")
            try:
                success = bridge.execute_action(action)
                if not success and not action.optional:
                    logger.error(f"  Step {i+1} failed (non-optional) — aborting script")
                    return False
                elif not success:
                    logger.warning(f"  Step {i+1} failed (optional) — continuing")
            except Exception as e:
                if not action.optional:
                    logger.error(f"  Step {i+1} raised exception: {e}")
                    return False
                logger.warning(f"  Step {i+1} optional exception: {e}")

        if self.expected_final_state:
            actual = bridge.get_current_state()
            if not re.search(self.expected_final_state, actual, re.IGNORECASE):
                logger.warning(f"Final state mismatch: expected={self.expected_final_state}, "
                               f"actual={actual}")
                return False

        logger.info(f"Init script '{self.name}' completed successfully")
        return True

    @staticmethod
    def from_dict(data: Dict) -> "InitScript":
        """Parse an InitScript from a dictionary (JSON config)."""
        actions = []
        for a in data.get("actions", []):
            actions.append(UiAction(
                action_type=a["action"],
                target=a.get("target"),
                value=a.get("value"),
                x=a.get("x"),
                y=a.get("y"),
                timeout_ms=a.get("timeout_ms", 5000),
                optional=a.get("optional", False),
                description=a.get("description", ""),
            ))
        return InitScript(
            name=data["name"],
            description=data.get("description", ""),
            state_patterns=data.get("state_patterns", [".*"]),
            actions=actions,
            expected_final_state=data.get("expected_final_state"),
            platform=data.get("platform", "any"),
            app_package=data.get("app_package"),
            priority=data.get("priority", 0),
            tags=data.get("tags", []),
        )


class UiAutomatorBridge(ABC):
    """Abstract bridge for UI interaction (Android UIAutomator / iOS XCUITest)."""

    @abstractmethod
    def execute_action(self, action: UiAction) -> bool:
        """Execute a UI action. Returns True on success."""
        ...

    @abstractmethod
    def detect_current_screen(self, app_package: str) -> str:
        """Detect the current application screen/state identifier."""
        ...

    @abstractmethod
    def get_current_state(self) -> str:
        """Return a string description of the current application state."""
        ...

    @abstractmethod
    def launch_app(self, package: str) -> bool:
        """Launch the application."""
        ...

    @abstractmethod
    def is_app_running(self, package: str) -> bool:
        """Check if the application is currently running."""
        ...


class AndroidUiAutomatorBridge(UiAutomatorBridge):
    """
    Android-specific UIAutomator bridge.
    Executes actions via ADB commands to UIAutomator2.
    """

    def __init__(self, device_serial: Optional[str] = None, timeout_s: int = 30):
        self.device_serial = device_serial
        self.timeout_s = timeout_s
        self._adb_prefix = ["adb"]
        if device_serial:
            self._adb_prefix += ["-s", device_serial]

    def _adb(self, *args, timeout: int = 10) -> Tuple[str, int]:
        cmd = self._adb_prefix + list(args)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.stdout.strip(), result.returncode
        except subprocess.TimeoutExpired:
            return "", -1
        except Exception as e:
            logger.error(f"ADB error: {e}")
            return "", -1

    def execute_action(self, action: UiAction) -> bool:
        """Execute a UIAutomator action via ADB."""
        at = action.action_type.lower()

        if at == "tap":
            if action.x is not None and action.y is not None:
                out, rc = self._adb("shell", "input", "tap",
                                    str(int(action.x)), str(int(action.y)))
                return rc == 0
            elif action.target:
                return self._tap_by_id(action.target, action.timeout_ms)

        elif at == "type_text":
            if action.value:
                text = action.value.replace(" ", "%s")
                out, rc = self._adb("shell", "input", "text", text)
                return rc == 0

        elif at == "wait":
            wait_ms = int(action.value or "1000")
            time.sleep(wait_ms / 1000.0)
            return True

        elif at == "back":
            out, rc = self._adb("shell", "input", "keyevent", "4")
            return rc == 0

        elif at == "home":
            out, rc = self._adb("shell", "input", "keyevent", "3")
            return rc == 0

        elif at == "scroll":
            direction = action.value or "down"
            coords = {"down": ("540", "1200", "540", "400"),
                      "up":   ("540", "400", "540", "1200"),
                      "left": ("900", "600", "200", "600"),
                      "right":("200", "600", "900", "600")}.get(direction, ("540","1200","540","400"))
            out, rc = self._adb("shell", "input", "swipe", *coords, "500")
            return rc == 0

        elif at == "swipe":
            if all(v is not None for v in [action.x, action.y,
                                            action.action_params.get("x2"),
                                            action.action_params.get("y2")]):
                out, rc = self._adb("shell", "input", "swipe",
                                    str(int(action.x)), str(int(action.y)),
                                    str(int(action.action_params["x2"])),
                                    str(int(action.action_params["y2"])), "500")
                return rc == 0

        elif at == "assert_text":
            out, _ = self._adb("shell", "uiautomator", "dump", "/dev/stdout")
            return action.value in out if action.value else True

        elif at == "clear_field":
            self._adb("shell", "input", "keyevent", "KEYCODE_CTRL_A")
            self._adb("shell", "input", "keyevent", "KEYCODE_DEL")
            return True

        elif at == "launch":
            return self.launch_app(action.target or "")

        logger.warning(f"Unknown action type: {action.action_type}")
        return False

    def _tap_by_id(self, view_id: str, timeout_ms: int = 5000) -> bool:
        """Tap a view by resource ID using UIAutomator."""
        script = f"""
import sys
sys.path.append('/data/local/tmp')
from uiautomator2 import connect
d = connect()
el = d(resourceId='{view_id}')
if el.exists(timeout={timeout_ms/1000}):
    el.click()
    sys.exit(0)
sys.exit(1)
"""
        # Simplified: use uiautomator dump + tap coordinates
        out, _ = self._adb("shell", "uiautomator", "dump", "/dev/stdout")
        match = re.search(rf'resource-id="{re.escape(view_id)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', out)
        if match:
            x = (int(match.group(1)) + int(match.group(3))) // 2
            y = (int(match.group(2)) + int(match.group(4))) // 2
            _, rc = self._adb("shell", "input", "tap", str(x), str(y))
            return rc == 0
        return False

    def detect_current_screen(self, app_package: str) -> str:
        out, _ = self._adb("shell", "dumpsys", "activity", "top")
        match = re.search(r'ACTIVITY (\S+)', out)
        return match.group(1) if match else "unknown"

    def get_current_state(self) -> str:
        return self.detect_current_screen("")

    def launch_app(self, package: str) -> bool:
        out, rc = self._adb("shell", "monkey", "-p", package, "-c",
                            "android.intent.category.LAUNCHER", "1")
        return rc == 0

    def is_app_running(self, package: str) -> bool:
        out, _ = self._adb("shell", "pidof", package)
        return bool(out.strip())


class InitializationSequencer(ISequencer):
    """
    SMATA Initialization Sequencer

    Automates navigation through complex authentication and multi-step setup
    flows before handing control to the Driver.

    Script libraries are loaded from JSON files and matched to the current
    application state by regex pattern matching on screen/activity names.

    Usage:
        sequencer = InitializationSequencer(bridge)
        sequencer.load_script_library("configs/k9mail_init.json")
        success = sequencer.initialize("com.fsck.k9")
    """

    def __init__(self, bridge: Optional[UiAutomatorBridge] = None,
                 platform: Platform = Platform.ANDROID):
        self._bridge = bridge
        self._platform = platform
        self._script_library: List[InitScript] = []
        self._execution_history: List[Dict] = []
        self._init_callbacks: List[Callable] = []
        logger.info(f"InitializationSequencer initialized | platform={platform.value}")

    @property
    def bridge(self) -> Optional[UiAutomatorBridge]:
        return self._bridge

    @bridge.setter
    def bridge(self, b: UiAutomatorBridge) -> None:
        self._bridge = b

    def load_script_library(self, path: str) -> int:
        """
        Load initialization scripts from a JSON file.
        Returns the number of scripts loaded.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Script library not found: {path}")

        with open(p) as f:
            data = json.load(f)

        scripts_data = data if isinstance(data, list) else data.get("scripts", [])
        new_scripts = [InitScript.from_dict(s) for s in scripts_data]
        self._script_library.extend(new_scripts)
        self._script_library.sort(key=lambda s: -s.priority)

        logger.info(f"Loaded {len(new_scripts)} scripts from {path} "
                    f"(total library: {len(self._script_library)})")
        return len(new_scripts)

    def add_step(self, state_pattern: str, action: UiAction,
                 name: str = "inline_step") -> None:
        """Register a single inline initialization step."""
        script = InitScript(
            name=name,
            description=f"Inline step: {action.action_type}",
            state_patterns=[state_pattern],
            actions=[action],
        )
        self._script_library.append(script)

    def add_login_script(self, username: str, password: str,
                         username_id: str = "com.example:id/username",
                         password_id: str = "com.example:id/password",
                         submit_id: str = "com.example:id/login_button",
                         state_pattern: str = "login|signin|auth") -> None:
        """Convenience method to add a standard login sequence."""
        script = InitScript(
            name="standard_login",
            description=f"Login with username and password",
            state_patterns=[state_pattern],
            actions=[
                UiAction("tap", target=username_id, description="Tap username field"),
                UiAction("type_text", value=username, description="Enter username"),
                UiAction("tap", target=password_id, description="Tap password field"),
                UiAction("type_text", value=password, description="Enter password"),
                UiAction("tap", target=submit_id, description="Submit login form"),
                UiAction("wait", value="2000", description="Wait for login completion"),
            ],
            tags=["login", "auth"],
        )
        self._script_library.insert(0, script)

    def initialize(self, app_package: str) -> bool:
        """
        Execute initialization for the target app.

        Detects the current screen and executes the highest-priority
        matching script from the library. If no script matches, proceeds
        without initialization and returns False.

        Args:
            app_package: Target Android/iOS application package.

        Returns:
            True if a matching script was found and executed successfully.
        """
        if self._bridge is None:
            logger.warning("No UI bridge configured — skipping initialization")
            return False

        # Launch app if not running
        if not self._bridge.is_app_running(app_package):
            logger.info(f"Launching {app_package}")
            self._bridge.launch_app(app_package)
            time.sleep(2)

        current_state = self._bridge.detect_current_screen(app_package)
        logger.info(f"Current state: {current_state}")

        # Find matching script
        matching = [s for s in self._script_library
                    if s.matches(current_state, self._platform.value)]

        if not matching:
            logger.info(f"No matching init script for state '{current_state}' — "
                        "proceeding without initialization")
            return False

        # Execute highest-priority match
        script = matching[0]
        logger.info(f"Selected script: '{script.name}' (priority={script.priority})")

        start = time.time()
        success = script.execute(self._bridge)
        duration = time.time() - start

        self._execution_history.append({
            "timestamp": time.time(),
            "app_package": app_package,
            "initial_state": current_state,
            "script_name": script.name,
            "success": success,
            "duration_s": round(duration, 2),
        })

        if success:
            logger.info(f"Initialization complete in {duration:.1f}s")
        else:
            logger.warning(f"Initialization script '{script.name}' failed")

        # Fire callbacks
        for cb in self._init_callbacks:
            try:
                cb(app_package, success, duration)
            except Exception:
                pass

        return success

    def register_callback(self, callback: Callable) -> None:
        """Register a callback invoked after each initialization attempt."""
        self._init_callbacks.append(callback)

    def get_script_library(self) -> List[InitScript]:
        return list(self._script_library)

    def get_execution_history(self) -> List[Dict]:
        return list(self._execution_history)

    def get_script_count(self) -> int:
        return len(self._script_library)

    def clear_library(self) -> None:
        self._script_library.clear()
        logger.info("Script library cleared")

    def __repr__(self) -> str:
        return (f"InitializationSequencer("
                f"scripts={len(self._script_library)}, "
                f"platform={self._platform.value})")


# Re-export for type hints
from typing import Tuple
