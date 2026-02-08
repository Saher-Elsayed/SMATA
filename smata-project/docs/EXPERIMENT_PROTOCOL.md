# Experiment Protocol

## Overview
This document describes the experimental protocol used to evaluate SMATA against three baselines across 10 Android applications.

## Hardware Setup
- CPU: Intel Core i7-12700K
- RAM: 32 GB DDR4
- Storage: 512 GB NVMe SSD
- Android Emulator: API Level 30 (Android 11)
- Emulator RAM: 4 GB per instance

## Software Versions
- Android SDK: 30.0.3
- JaCoCo: 0.8.7
- Major Mutation Framework: 2.0.0
- Python: 3.9+
- ADB: 31.0.3

## Execution Protocol

### 1. Application Preparation
For each benchmark application:
1. Clone source from F-Droid repository
2. Instrument with JaCoCo for coverage measurement
3. Generate mutants using Major mutation framework
4. Build debug APK with instrumentation
5. Install on emulator

### 2. Baseline Execution
Each approach runs 10 times per application (randomized order):

**Monkey**: `adb shell monkey -p <package> --throttle 100 -v -v 10000`
**Dynodroid**: observe-select-execute cycle, max 10000 events
**Ad-hoc**: JUnit tests + Espresso UI tests + 15-min manual exploration
**SMATA**: Full framework with Driver, Sequencer, Monitors, Checker

### 3. Measurement Collection
After each run:
1. Pull JaCoCo coverage report: `adb pull /data/data/<package>/coverage.ec`
2. Generate coverage report: `java -jar jacococli.jar report ...`
3. Record crash logs: `adb logcat -d *:E`
4. Record setup time from timestamps
5. Attempt bug reproduction and record time

### 4. Statistical Analysis
- Shapiro-Wilk test for normality
- Mann-Whitney U test for pairwise comparisons
- Bonferroni correction (alpha = 0.05/3 = 0.0167)
- Cliff's delta for effect size
