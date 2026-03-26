"""SMATA timing utilities."""
import time
class Timer:
    def __init__(self): self.elapsed = 0.0; self._start = 0.0
    def __enter__(self): self._start = time.time(); return self
    def __exit__(self, *a): self.elapsed = time.time() - self._start
    def current(self): return time.time() - self._start
