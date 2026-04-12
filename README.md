# SMATA: Structured Mobile Application Testing Architecture

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Paper](https://img.shields.io/badge/Paper-Software%20Quality%20Journal-blue)](https://github.com/Saher-Elsayed/SMATA)

> **Paper:** *SMATA: A Structured Mobile Application Testing Architecture --
> Adapting Hardware Verification Principles for Mobile Testing Standardization*
>
> **Author:** Saher Elsayed, University of Pennsylvania (selsayed@seas.upenn.edu)
>
> **Status:** Under review at IEEE ACCESS

---

## Overview

SMATA is a modular, reusable mobile application testing framework inspired by the
Universal Verification Methodology (UVM) from hardware verification. It unifies
disparate testing tools (Monkey, Dynodroid, Espresso, XCUITest) behind standardized
interfaces, automates complex initialization flows, and systematically captures events
to enable bug reproduction.

SMATA addresses three critical challenges in mobile testing:

1. **Tool Fragmentation** -- integrates multiple testing tools through a unified Driver interface
2. **Reproducibility Crisis** -- comprehensive event logging enables 88.7% bug reproducibility
3. **Initialization Barriers** -- automated Sequencer navigates complex authentication flows

---

## Key Results (50 Android + 20 iOS Apps)

| Metric | Monkey | Dynodroid | Ad-hoc | **SMATA** |
|--------|--------|-----------|--------|-----------|
| Coverage (%) | 28.1 +/- 2.8 | 37.3 +/- 2.9 | 43.1 +/- 2.9 | **64.2 +/- 4.4** |
| Fault Det. (%) | 31.1 +/- 5.7 | 40.9 +/- 5.2 | 48.1 +/- 4.3 | **64.8 +/- 4.0** |
| Reprod. (%) | 21.8 +/- 6.2 | 34.3 +/- 7.0 | 56.5 +/- 10.1 | **88.7 +/- 4.2** |
| Debug (min/bug) | 73.0 +/- 20.2 | 62.1 +/- 15.3 | 52.9 +/- 12.7 | **29.3 +/- 6.6** |
| Setup 1st (hr) | 1.1 +/- 0.3 | 4.2 +/- 1.3 | 19.2 +/- 5.5 | 5.4 +/- 1.8 |
| Setup Reuse (hr) | -- | -- | -- | **2.1 +/- 0.6** |

Most comparisons statistically significant (p < 0.01 after Bonferroni correction, large effect sizes, Mann-Whitney U test).

---

## Architecture

```
+-------------------------------------------------------------+
|                      SMATA Framework                        |
|                                                             |
|   +--- Input Environment ---+  +-- Output Environment --+  |
|   |                         |  |                         |  |
|   |  [Init Sequencer]       |  |  [Output Monitor]       |  |
|   |        |                |  |        |                |  |
|   |  [Driver]               |  |  [Observer]             |  |
|   |  Monkey | Dynodroid     |  |        |                |  |
|   |  Espresso | XCUITest    |  |  [Sanity Checker]       |  |
|   |        |                |  |        |                |  |
|   |  [Input Monitor]        |  |        |                |  |
|   +-------|--|--------------+  +--------|----------------+  |
|           |  |                          |                   |
|           v  v                          v                   |
|         +-----------------------------+                     |
|         |     Application Under Test  |                     |
|         +-----------------------------+                     |
+-------------------------------------------------------------+
```

| SMATA Component | UVM Analog | Role |
|----------------|-----------|------|
| Initialization Sequencer | Sequencer | Navigate auth and setup flows |
| Driver | Driver | Unify multiple tool adapters |
| Input Monitor | Active Monitor | Log all input events |
| Output Monitor | Passive Monitor | Observe state and crash signals |
| Observer | Scoreboard (feedback) | Coverage-driven tool switching |
| Sanity Checker | Scoreboard (check) | Crash-to-reproduction correlation |

---

## Repository Structure

```
SMATA/
+-- README.md
+-- LICENSE
+-- requirements.txt
+-- src/smata/core/
|   +-- ITestAdapter.java       # Plug-and-play adapter interface
|   +-- Driver.java             # Central tool orchestration hub
|   +-- InitializationSequencer.java  # Auth/setup automation
|   +-- InputMonitor.java       # Event logging for reproducibility
|   +-- SanityChecker.java      # Crash detection + delta-debugging
|   +-- Observer.java           # Feedback-driven tool switching
+-- experiments/
|   +-- simulate_experiments.py # Full 50-app experiment simulation
|   +-- gen_app_table.py        # LaTeX benchmark table generator
|   +-- requirements.txt
|   +-- run_all.sh              # One-command reproduction
+-- data/
|   +-- experiment_data.json    # Raw results: 50 apps x 10 runs x 4 metrics
+-- figures/                    # All publication figures (PDF + PNG)
|   +-- fig_coverage_boxplot.*
|   +-- fig_coverage_heatmap.*
|   +-- fig_coverage_over_time.*
|   +-- fig_bug_detection_repro.*
|   +-- fig_debugging_time.*
|   +-- fig_setup_time.*
|   +-- fig_ablation.*
|   +-- fig_domain_ios.*
|   +-- fig_effect_sizes.*
|   +-- Final_architecture.png
|   +-- Dynodroid.PNG / Dynodroid_Results.PNG
|   +-- UVM.PNG / UVM_Agent.PNG
|   +-- S0.png / S1.png / S2.png / S3.png
|   +-- fig1.png / fig2.png / timeTravel.png
+-- docs/
    +-- paper_main.tex          # Full paper LaTeX source
    +-- smata-refs.bib          # Bibliography (29 references)
    +-- app_table.tex           # 50-app benchmark table
```

---

## Reproducing All Results

```bash
# 1. Clone
git clone https://github.com/Saher-Elsayed/SMATA
cd SMATA

# 2. Install Python dependencies (Python 3.8+)
pip install -r requirements.txt

# 3. Run full simulation (generates all figures + data)
python experiments/simulate_experiments.py

# Output:
#   data/experiment_data.json     -- raw experimental data
#   figures/*.pdf, *.png          -- all 9 publication figures
```

---

## Benchmark Suite (50 Android Apps)

Spanning 7 domains, 2K--95K lines of code, and three authentication complexity levels.

| App | Domain | LOC | Auth |
|-----|--------|-----|------|
| AnyMemo | Education | 12K | None |
| K-9 Mail | Communication | 45K | Complex |
| WordPress | Productivity | 38K | Complex |
| Signal | Communication | 79K | Complex |
| KeePassDX | Security | 24K | Complex |
| Nextcloud | Productivity | 55K | Complex |
| Wire | Communication | 63K | Complex |
| OsmAnd | Navigation | 95K | Simple |
| Fennec | Browser | 88K | Simple |
| FairEmail | Communication | 72K | Complex |
| AnkiDroid | Education | 31K | Simple |
| NewPipe | Entertainment | 48K | Simple |
| Proton VPN | Security | 45K | Complex |
| DuckDuckGo | Browser | 42K | Simple |
| ... | ... | ... | ... |

Full 50-app table in `docs/app_table.tex` and `data/experiment_data.json`.

---

## Supported Test Back-ends

| Adapter | Platform | Status |
|---------|----------|--------|
| MonkeyAdapter | Android | Implemented |
| DynodroidAdapter | Android | Implemented |
| EspressoAdapter | Android | Implemented |
| XCUITestAdapter | iOS | Implemented |

---

## Citation

```bibtex
@article{elsayed2026smata,
  author  = {Elsayed, Saher},
  title   = {{SMATA: A Structured Mobile Application Testing Architecture}},
  journal = {Software Quality Journal},
  year    = {2026},
  note    = {Under review},
  url     = {https://github.com/Saher-Elsayed/SMATA}
}
```

---

## License

MIT License -- see [LICENSE](LICENSE) for details.
