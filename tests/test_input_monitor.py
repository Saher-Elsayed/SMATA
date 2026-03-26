"""Tests for SMATA InputMonitor component."""
import time
import pytest
import sys
sys.path.insert(0, "src")

from smata.monitors.input_monitor import InputMonitor, MonitorConfig
from smata.core.interfaces import InputEvent, EventType


class TestInputMonitor:

    def setup_method(self):
        config = MonitorConfig(persist_to_disk=False)
        self.monitor = InputMonitor(config=config)

    def test_start_stop_recording(self):
        self.monitor.start_recording()
        assert self.monitor._recording is True
        self.monitor.stop_recording()
        assert self.monitor._recording is False

    def test_log_event_basic(self):
        self.monitor.start_recording()
        event = InputEvent(event_type=EventType.TOUCH, x=100, y=200)
        seq = self.monitor.log_event(event)
        assert seq == 0
        assert self.monitor.get_event_count() == 1
        self.monitor.stop_recording()

    def test_log_multiple_events(self):
        self.monitor.start_recording()
        for i in range(100):
            self.monitor.log_event(InputEvent(EventType.TOUCH, x=float(i), y=float(i)))
        assert self.monitor.get_event_count() == 100
        self.monitor.stop_recording()

    def test_sequence_numbers_are_sequential(self):
        self.monitor.start_recording()
        seqs = []
        for _ in range(10):
            event = InputEvent(EventType.TOUCH)
            seqs.append(self.monitor.log_event(event))
        assert seqs == list(range(10))
        self.monitor.stop_recording()

    def test_get_event_log_from(self):
        self.monitor.start_recording()
        for i in range(20):
            self.monitor.log_event(InputEvent(EventType.TOUCH))
        log = self.monitor.get_event_log_from(10)
        assert len(log) == 10
        assert all(e.sequence_number >= 10 for e in log)
        self.monitor.stop_recording()

    def test_get_events_by_type(self):
        self.monitor.start_recording()
        for _ in range(5):
            self.monitor.log_event(InputEvent(EventType.TOUCH))
        for _ in range(3):
            self.monitor.log_event(InputEvent(EventType.KEY_EVENT))
        touches = self.monitor.get_events_by_type(EventType.TOUCH)
        keys = self.monitor.get_events_by_type(EventType.KEY_EVENT)
        assert len(touches) == 5
        assert len(keys) == 3
        self.monitor.stop_recording()

    def test_event_not_logged_when_not_recording(self):
        event = InputEvent(EventType.TOUCH)
        seq = self.monitor.log_event(event)
        assert seq == -1
        assert self.monitor.get_event_count() == 0

    def test_convenience_log_touch(self):
        self.monitor.start_recording()
        self.monitor.log_touch(100.0, 200.0, view_id="btn_ok", adapter="monkey")
        log = self.monitor.get_event_log()
        assert len(log) == 1
        assert log[0].event_type == EventType.TOUCH
        assert log[0].target_view_id == "btn_ok"
        assert log[0].adapter_provenance == "monkey"
        self.monitor.stop_recording()

    def test_stats_tracking(self):
        self.monitor.start_recording()
        for _ in range(10):
            self.monitor.log_event(InputEvent(EventType.TOUCH))
        for _ in range(5):
            self.monitor.log_event(InputEvent(EventType.KEY_EVENT))
        stats = self.monitor.get_stats()
        assert stats["total_events"] == 15
        assert stats["event_types"]["touch"] == 10
        assert stats["event_types"]["key_event"] == 5
        self.monitor.stop_recording()

    def test_clear(self):
        self.monitor.start_recording()
        for _ in range(50):
            self.monitor.log_event(InputEvent(EventType.TOUCH))
        self.monitor.clear()
        assert self.monitor.get_event_count() == 0
        assert len(self.monitor.get_event_log()) == 0
        self.monitor.stop_recording()
