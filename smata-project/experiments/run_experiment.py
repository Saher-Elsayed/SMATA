#!/usr/bin/env python3
"""
SMATA Experiment Runner

Orchestrates the execution of SMATA and baseline approaches
across benchmark applications. Requires Android emulator setup.

Usage:
    python experiments/run_experiment.py --app AnyMemo --approach SMATA --runs 10
    python experiments/run_experiment.py --all
"""

import argparse
import json
import sys
import os
import time
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.smata.driver import SMATADriver, ToolConfig, ToolType
from src.smata.sequencer import InitSequencer
from src.smata.monitors import InputMonitor, OutputMonitor
from src.smata.checker import SanityChecker
from src.baselines import MonkeyRunner, DynodroidRunner, AdhocRunner

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger('experiment')

# Load app configs
with open('configs/app_configs.json') as f:
    APP_CONFIGS = json.load(f)['apps']

APP_NAMES = list(APP_CONFIGS.keys())


def run_smata(app_name, app_config, run_id):
    """Run SMATA framework on one app."""
    package = app_config['package']

    # Initialize components
    driver = SMATADriver(tools=["monkey", "dynodroid"])
    sequencer = InitSequencer(config='configs/app_configs.json')
    input_mon = InputMonitor(log_dir='data/raw')
    output_mon = OutputMonitor(log_dir='data/raw')
    checker = SanityChecker()

    # Phase 1: Initialization
    init_result = sequencer.initialize(package)
    logger.info(f"Init: {init_result['steps_completed']}/{init_result['steps_total']} steps")

    # Phase 2: Coordinated Testing
    results = driver.run(
        app_package=package,
        duration_minutes=60,
        monitors=[input_mon, output_mon],
        switch_interval_seconds=300
    )

    # Phase 3: Collect Results
    events = driver.get_all_events()
    checker.update_event_window(events)

    return {
        'app': app_name,
        'approach': 'SMATA',
        'run': run_id,
        'events': results['total_events'],
        'switches': results['switches'],
        'crashes': output_mon.get_crash_count(),
        'anrs': output_mon.get_anr_count(),
        'init_steps': init_result['steps_completed'],
        'sequence_hash': input_mon.get_sequence_hash(),
    }


def run_baseline(app_name, app_config, approach, run_id):
    """Run a baseline approach on one app."""
    package = app_config['package']

    if approach == 'Monkey':
        runner = MonkeyRunner(events=10000, seed=42)
        result = runner.run(package, run_id)
    elif approach == 'Dynodroid':
        runner = DynodroidRunner(max_events=10000)
        result = runner.run(package, run_id)
    elif approach == 'Ad-hoc':
        runner = AdhocRunner()
        result = runner.run(package, run_id)
    else:
        raise ValueError(f"Unknown approach: {approach}")

    return {
        'app': app_name,
        'approach': approach,
        'run': run_id,
        'events': result.events_generated,
        'duration': result.duration_seconds,
    }


def main():
    parser = argparse.ArgumentParser(description='SMATA Experiment Runner')
    parser.add_argument('--app', type=str, help='App name (e.g., AnyMemo)')
    parser.add_argument('--approach', type=str, choices=['SMATA', 'Monkey', 'Dynodroid', 'Ad-hoc', 'all'],
                        default='SMATA')
    parser.add_argument('--runs', type=int, default=10)
    parser.add_argument('--all', action='store_true', help='Run all apps and approaches')
    args = parser.parse_args()

    os.makedirs('data/raw', exist_ok=True)

    if args.all:
        apps = APP_NAMES
        approaches = ['Monkey', 'Dynodroid', 'Ad-hoc', 'SMATA']
    else:
        apps = [args.app] if args.app else APP_NAMES
        approaches = ['Monkey', 'Dynodroid', 'Ad-hoc', 'SMATA'] if args.approach == 'all' else [args.approach]

    results = []
    for app_name in apps:
        if app_name not in APP_CONFIGS:
            logger.warning(f"Unknown app: {app_name}")
            continue

        app_config = APP_CONFIGS[app_name]
        for approach in approaches:
            for run_id in range(1, args.runs + 1):
                logger.info(f"Running {approach} on {app_name} (run {run_id}/{args.runs})")
                try:
                    if approach == 'SMATA':
                        result = run_smata(app_name, app_config, run_id)
                    else:
                        result = run_baseline(app_name, app_config, approach, run_id)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed: {e}")

    # Save results
    output_file = f'data/raw/experiment_results_{int(time.time())}.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved to {output_file}")


if __name__ == '__main__':
    main()
