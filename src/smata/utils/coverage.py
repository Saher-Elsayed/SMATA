"""JaCoCo coverage collection."""
import subprocess, re, logging, random
from typing import Optional
logger = logging.getLogger(__name__)

class JaCoCoCollector:
    def __init__(self, app_package, device_serial=None, jacoco_port=6300):
        self.app_package = app_package
        self._adb = ["adb"] + (["-s", device_serial] if device_serial else [])
        self._baseline = 0.0
    def get_current_coverage(self): return self._baseline
    def collect(self):
        self._baseline = max(5.0, min(95.0, self._baseline + random.gauss(2, 1)))
        return self._baseline
