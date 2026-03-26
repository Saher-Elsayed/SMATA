
"""SMATA Output Monitor — observes app state, crashes, ANR, performance."""
import re, time, subprocess, threading
from typing import Optional, List, Dict
from smata.core.interfaces import FailureSignal, FailureType, IMonitor
from smata.utils.logger import SMATALogger
logger = SMATALogger.get_logger(__name__)

class OutputMonitor(IMonitor):
    def __init__(self, device_serial=None):
        self._adb = ["adb"] + (["-s", device_serial] if device_serial else [])
        self._failure_queue = []
        self._state_log = []
        self._recording = False
        self._latest_stack = None
        self._injected = None
        self._event_count = 0
        self._logcat_proc = None
        self._stop = threading.Event()
        self._thread = None

    def start_recording(self):
        self._recording = True
        self._stop.clear()
        try:
            subprocess.run(self._adb + ["logcat", "-c"], capture_output=True, timeout=3)
            self._logcat_proc = subprocess.Popen(
                self._adb + ["logcat", "-v", "threadtime", "AndroidRuntime:E", "*:S"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        except Exception as e:
            logger.warning(f"Logcat unavailable: {e}")
        logger.info("OutputMonitor: started")

    def stop_recording(self):
        self._recording = False
        self._stop.set()
        if self._logcat_proc:
            try: self._logcat_proc.terminate()
            except: pass
        if self._thread: self._thread.join(timeout=3)
        logger.info(f"OutputMonitor: stopped | failures={len(self._failure_queue)}")

    def _loop(self):
        if not self._logcat_proc: return
        crash_re = re.compile(r"FATAL EXCEPTION|AndroidRuntime")
        anr_re   = re.compile(r"ANR in|Not Responding")
        for line in self._logcat_proc.stdout:
            if self._stop.is_set(): break
            self._event_count += 1
            if crash_re.search(line):
                self._failure_queue.append(FailureSignal(
                    failure_type=FailureType.CRASH, message=line[:200],
                    timestamp=time.time()))
                logger.warning(f"Crash: {line[:80]}")
            if anr_re.search(line):
                self._failure_queue.append(FailureSignal(
                    failure_type=FailureType.ANR, message=line[:200],
                    timestamp=time.time()))

    def get_latest_failure_signal(self):
        if self._injected:
            s = self._injected; self._injected = None; return s
        return self._failure_queue.pop(0) if self._failure_queue else None

    def get_crash_stack_trace(self): return self._latest_stack
    def get_visited_activities(self): return [s["activity"] for s in self._state_log]
    def get_event_count(self): return self._event_count
    def _inject_failure(self, signal): self._injected = signal
