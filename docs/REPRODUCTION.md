# Reproduction Guide

## Quick Reproduction (Analysis + Figures Only)

```bash
# Install dependencies
pip install -r requirements.txt

# Generate simulated experimental data
python scripts/generate_data.py

# Run statistical analysis
python scripts/statistical_analysis.py

# Generate all paper figures
python scripts/generate_figures.py
```

Output:
- `data/raw/` — 6 CSV files with raw experimental data
- `data/processed/` — Summary statistics and statistical test results (JSON)
- `figures/` — 7 figures in PDF and PNG format

## Full Reproduction (Requires Android Environment)

### Prerequisites
1. Android SDK with API Level 30
2. Android Emulator configured (4GB RAM)
3. ADB accessible from PATH
4. JaCoCo CLI (0.8.7+)
5. Major Mutation Framework (2.0.0)

### Steps
1. Install benchmark applications from F-Droid
2. Instrument each app with JaCoCo
3. Run: `python experiments/run_experiment.py --app <name> --approach <approach>`
4. Collect results from `data/raw/`
5. Run analysis: `python scripts/statistical_analysis.py`
6. Generate figures: `python scripts/generate_figures.py`

## File Manifest

| File | Description | Size |
|------|-------------|------|
| data/raw/coverage_data.csv | Coverage per app/approach/run | 400 rows |
| data/raw/detection_data.csv | Fault detection per app/approach/run | 400 rows |
| data/raw/reproducibility_data.csv | Reproducibility per app/approach/run | 400 rows |
| data/raw/debug_time_data.csv | Debug time per app/approach/run | 400 rows |
| data/raw/setup_time_data.csv | Setup time per app/approach/run | 500 rows |
| data/raw/coverage_over_time.csv | Coverage progression (5-min intervals) | 5200 rows |
| data/processed/summary_statistics.json | Aggregated statistics | — |
| data/processed/statistical_results.json | All statistical test results | — |
| data/processed/coverage_heatmap.csv | Per-app average coverage matrix | — |
