"""
SMATA Experiment Runner
=======================
Main entry point for running a full SMATA testing session on a target app.
Coordinates all components: Sequencer, Driver, Monitors, Observer, SanityChecker.

Usage:
    python run_experiment.py --app com.fsck.k9 --duration 3600 --adapters monkey dynodroid
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from smata.driver.driver import Driver, DriverConfig, SwitchStrategy
from smata.monitors.input_monitor import InputMonitor, MonitorConfig
from smata.monitors.output_monitor import OutputMonitor
from smata.observer.observer import Observer, ObserverConfig
from smata.checker.sanity_checker import SanityChecker, SanityCheckerConfig
from smata.sequencer.sequencer import InitializationSequencer
from smata.adapters.monkey_adapter import MonkeyAdapter, MonkeyAdapterConfig
from smata.adapters.dynodroid_adapter import DynodroidAdapter
from smata.core.interfaces import AdapterConfig, Platform


def run(app_package: str,
        duration_s: int = 3600,
        adapters: list = None,
        init_script: str = None,
        output_dir: str = "smata_output",
        device_serial: str = None) -> dict:
    """
    Run a full SMATA session on the target app.

    Args:
        app_package: Android app package name (e.g. com.fsck.k9)
        duration_s: Total testing budget in seconds
        adapters: List of adapter names ["monkey", "dynodroid"]
        init_script: Path to initialization script library JSON
        output_dir: Directory for output artifacts
        device_serial: ADB device serial (None = default device)

    Returns:
        Session result dictionary
    """
    print(f"[SMATA] Starting session")
    print(f"  App     : {app_package}")
    print(f"  Budget  : {duration_s}s ({duration_s//60}min)")
    print(f"  Adapters: {adapters or ['monkey']}")
    print(f"  Output  : {output_dir}")
    print()

    # ── Initialize components ────────────────────────────────────
    monitor_config = MonitorConfig(
        persist_to_disk=True,
        output_path=f"{output_dir}/event_log.jsonl",
    )
    input_monitor = InputMonitor(config=monitor_config)
    output_monitor = OutputMonitor(device_serial=device_serial)

    observer_config = ObserverConfig(
        coverage_delta_threshold=2.0,
        stagnation_window=3,
    )
    observer = Observer(config=observer_config)

    checker_config = SanityCheckerConfig(
        verify_reproduction=True,
        output_dir=f"{output_dir}/bug_reports",
    )
    checker = SanityChecker(input_monitor, output_monitor, config=checker_config)

    driver_config = DriverConfig(
        total_budget_seconds=duration_s,
        slice_seconds=max(60, duration_s // 6),
        switch_strategy=SwitchStrategy.OBSERVER_DRIVEN,
        output_dir=output_dir,
    )
    driver = Driver(
        config=driver_config,
        input_monitor=input_monitor,
        observer=observer,
    )

    # ── Register adapters ────────────────────────────────────────
    adapter_list = adapters or ["monkey"]

    if "monkey" in adapter_list:
        monkey_cfg = MonkeyAdapterConfig(
            event_count=10000,
            throttle_ms=50,
            device_serial=device_serial,
        )
        driver.register_adapter(MonkeyAdapter(
            input_monitor=input_monitor,
            monkey_config=monkey_cfg,
        ))

    if "dynodroid" in adapter_list:
        driver.register_adapter(DynodroidAdapter(input_monitor=input_monitor))

    # ── Initialization Sequencer ─────────────────────────────────
    sequencer = InitializationSequencer(platform=Platform.ANDROID)
    if init_script:
        n = sequencer.load_script_library(init_script)
        print(f"[SMATA] Loaded {n} initialization scripts")
        success = sequencer.initialize(app_package)
        print(f"[SMATA] Initialization: {'OK' if success else 'skipped'}")

    # ── Start monitoring ─────────────────────────────────────────
    output_monitor.start_recording()
    checker.start_monitoring()

    # ── Run session ──────────────────────────────────────────────
    adapter_config = AdapterConfig(device_serial=device_serial)
    result = driver.run_session(app_package, adapter_config=adapter_config)

    # ── Stop and finalize ────────────────────────────────────────
    checker.stop_monitoring()
    output_monitor.stop_recording()

    # Attach bug reports to result
    bug_reports = checker.get_bug_reports()
    result.bug_reports = bug_reports

    # ── Print summary ────────────────────────────────────────────
    print()
    print("[SMATA] Session complete")
    print(f"  Events       : {result.total_events}")
    print(f"  Max coverage : {result.max_coverage:.1f}%")
    print(f"  Crashes      : {result.total_crashes}")
    print(f"  ANRs         : {result.total_anrs}")
    print(f"  Bug reports  : {len(bug_reports)}")
    print(f"  Duration     : {result.total_duration_s:.0f}s")

    checker_summary = checker.get_summary()
    print(f"  Reproducibility: {checker_summary['reproducibility_rate']*100:.1f}%")

    return result.to_dict()


def main():
    parser = argparse.ArgumentParser(
        description="SMATA: Structured Mobile Application Testing Architecture")
    parser.add_argument("--app", required=True, help="App package name")
    parser.add_argument("--duration", type=int, default=3600,
                        help="Testing budget in seconds (default: 3600)")
    parser.add_argument("--adapters", nargs="+", default=["monkey"],
                        choices=["monkey", "dynodroid", "espresso"],
                        help="Test adapters to use")
    parser.add_argument("--init-script", help="Path to initialization script JSON")
    parser.add_argument("--output-dir", default="smata_output",
                        help="Output directory for artifacts")
    parser.add_argument("--device", help="ADB device serial")
    parser.add_argument("--output-json", help="Path to write result JSON")
    args = parser.parse_args()

    result = run(
        app_package=args.app,
        duration_s=args.duration,
        adapters=args.adapters,
        init_script=args.init_script,
        output_dir=args.output_dir,
        device_serial=args.device,
    )

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nResult written to {args.output_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
