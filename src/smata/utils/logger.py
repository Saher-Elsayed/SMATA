"""SMATA centralized logging."""
import logging, sys
from typing import Optional

class SMATALogger:
    _configured = False
    @classmethod
    def configure(cls, level=logging.INFO, log_file=None):
        if cls._configured: return
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        handlers = [logging.StreamHandler(sys.stdout)]
        if log_file: handlers.append(logging.FileHandler(log_file))
        logging.basicConfig(level=level, format=fmt, handlers=handlers)
        cls._configured = True
    @classmethod
    def get_logger(cls, name):
        cls.configure()
        return logging.getLogger(name)
