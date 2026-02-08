#!/usr/bin/env python3
"""
Statistical Analysis for SMATA Evaluation

Performs all statistical tests reported in the paper:
- Shapiro-Wilk normality tests
- Mann-Whitney U tests (non-parametric pairwise comparisons)
- Bonferroni correction for multiple comparisons
- Cliff's delta effect size
- Descriptive statistics

Usage: python scripts/statistical_analysis.py
"""

import numpy as np
import pandas as pd
from scipy import stats
import json
import os
import warnings
warnings.filterwarnings('ignore')


def cliffs_delta(x, y):
    """
    Calculate Cliff's delta effect size (non-parametric).

    Interpretation:
      |d| < 0.147: negligible
      0.147 <= |d| < 0.33: small
      0.33 <= |d| < 0.474: medium
      |d| >= 0.474: large
    """
    n_x, n_y = len(x), len(y)
    more = sum(1 for xi in x for yi in y if xi > yi)
    less = sum(1 for xi in x for yi in y if xi < yi)
    d = (more - less) / (n_x * n_y)
    return d


def interpret_cliffs_delta(d):
    """Interpret Cliff's delta magnitude."""
    ad = abs(d)
    if ad < 0.147:
        return "negligible"
    elif ad < 0.33:
        return "small"
    elif ad < 0.474:
        return "medium"
    else:
        return "large"


def mannwhitney_with_bonferroni(groups, alpha=0.05):
    """
    Perform Mann-Whitney U tests between SMATA and all baselines
    with Bonferroni correction.
    """
    results = []
    smata_data = groups["SMATA"]
    baselines = [k for k in groups.keys() if k != "SMATA"]
    n_comparisons = len(baselines)
    corrected_alpha = alpha / n_comparisons

    for baseline in baselines:
        baseline_data = groups[baseline]
        u_stat, p_value = stats.mannwhitneyu(
            smata_data, baseline_data, alternative='two-sided'
        )
        d = cliffs_delta(smata_data.values, baseline_data.values)

        results.append({
            "comparison": f"SMATA vs {baseline}",
            "U_statistic": round(u_stat, 1),
            "p_value": p_value,
            "p_value_str": f"{p_value:.2e}" if p_value < 0.001 else f"{p_value:.4f}",
            "bonferroni_alpha": corrected_alpha,
            "significant": p_value < corrected_alpha,
            "cliffs_delta": round(d, 3),
            "effect_size": interpret_cliffs_delta(d),
            "smata_mean": round(smata_data.mean(), 2),
            "baseline_mean": round(baseline_data.mean(), 2),
        })

    return results


def normality_tests(groups):
    """Run Shapiro-Wilk normality tests for each group."""
    results = []
    for name, data in groups.items():
        if len(data) >= 3:
            w_stat, p_value = stats.shapiro(data)
            results.append({
                "group": name,
                "W_statistic": round(w_stat, 4),
                "p_value": round(p_value, 4),
                "normal": p_value > 0.05
            })
    return results


def analyze_metric(df, metric_col, metric_name):
    """Full analysis pipeline for one metric."""
    print(f"\n{'='*60}")
    print(f"  {metric_name}")
    print(f"{'='*60}")

    # Descriptive stats
    desc = df.groupby("approach")[metric_col].agg(["mean", "std", "median", "min", "max"])
    print(f"\nDescriptive Statistics:")
    print(desc.round(2).to_string())

    # Normality tests
    groups = {name: group[metric_col] for name, group in df.groupby("approach")}
    norm = normality_tests(groups)
    print(f"\nShapiro-Wilk Normality Tests:")
    for r in norm:
        status = "NORMAL" if r["normal"] else "NON-NORMAL"
        print(f"  {r['group']:12s}: W={r['W_statistic']:.4f}, p={r['p_value']:.4f} [{status}]")

    # Mann-Whitney U with Bonferroni
    if "SMATA" in groups:
        mw_results = mannwhitney_with_bonferroni(groups)
        print(f"\nMann-Whitney U Tests (Bonferroni corrected, alpha/3 = {0.05/3:.4f}):")
        for r in mw_results:
            sig = "***" if r["significant"] else "n.s."
            print(f"  {r['comparison']:25s}: U={r['U_statistic']:8.1f}, "
                  f"p={r['p_value_str']:10s}, d={r['cliffs_delta']:+.3f} "
                  f"({r['effect_size']}) {sig}")
    else:
        mw_results = []

    return {
        "metric": metric_name,
        "descriptive": desc.round(2).to_dict(),
        "normality": norm,
        "mann_whitney": mw_results
    }


def run_analysis():
    """Run complete statistical analysis."""
    print("=" * 60)
    print("SMATA Statistical Analysis")
    print("=" * 60)

    # Load data
    df_cov = pd.read_csv("data/raw/coverage_data.csv")
    df_det = pd.read_csv("data/raw/detection_data.csv")
    df_repro = pd.read_csv("data/raw/reproducibility_data.csv")
    df_debug = pd.read_csv("data/raw/debug_time_data.csv")
    df_setup = pd.read_csv("data/raw/setup_time_data.csv")

    # Filter setup to main 4 approaches
    df_setup_main = df_setup[df_setup["approach"].isin(
        ["Monkey", "Dynodroid", "Ad-hoc", "SMATA"]
    )]

    all_results = {}

    # Analyze each metric
    all_results["coverage"] = analyze_metric(df_cov, "coverage_pct", "Code Coverage (%)")
    all_results["detection"] = analyze_metric(df_det, "detection_pct", "Fault Detection Rate (%)")
    all_results["reproducibility"] = analyze_metric(df_repro, "reproducibility_pct", "Bug Reproducibility (%)")
    all_results["debug_time"] = analyze_metric(df_debug, "debug_time_min", "Debug Time (min/bug)")
    all_results["setup_time"] = analyze_metric(df_setup_main, "setup_time_hours", "Setup Time (hours)")

    # SMATA-Reuse vs Ad-hoc comparison
    print(f"\n{'='*60}")
    print(f"  SMATA-Reuse vs Ad-hoc Setup Time")
    print(f"{'='*60}")
    smata_reuse = df_setup[df_setup["approach"] == "SMATA-Reuse"]["setup_time_hours"]
    adhoc_setup = df_setup[df_setup["approach"] == "Ad-hoc"]["setup_time_hours"]
    u, p = stats.mannwhitneyu(smata_reuse, adhoc_setup, alternative='two-sided')
    d = cliffs_delta(smata_reuse.values, adhoc_setup.values)
    reduction = (1 - smata_reuse.mean() / adhoc_setup.mean()) * 100
    print(f"  SMATA-Reuse mean: {smata_reuse.mean():.2f} hours")
    print(f"  Ad-hoc mean:      {adhoc_setup.mean():.2f} hours")
    print(f"  Reduction:        {reduction:.1f}%")
    print(f"  U={u:.1f}, p={p:.2e}, Cliff's d={d:.3f} ({interpret_cliffs_delta(d)})")

    # Save full results
    os.makedirs("data/processed", exist_ok=True)

    # Convert results to JSON-serializable format
    json_results = {}
    for key, val in all_results.items():
        json_results[key] = {
            "metric": val["metric"],
            "normality": val["normality"],
            "mann_whitney": val["mann_whitney"]
        }

    json_results["smata_reuse_vs_adhoc"] = {
        "U_statistic": round(u, 1),
        "p_value": float(p),
        "cliffs_delta": round(d, 3),
        "effect_size": interpret_cliffs_delta(d),
        "reduction_percent": round(reduction, 1)
    }

    with open("data/processed/statistical_results.json", "w") as f:
        json.dump(json_results, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print("Analysis complete. Results saved to data/processed/statistical_results.json")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_analysis()
