"""
SMATA Statistical Analysis
===========================
Full statistical analysis of SMATA vs. baseline experimental results.
Implements Mann-Whitney U tests, Cohen's d effect sizes, 95% bootstrap
confidence intervals, and Bonferroni correction.

Reproduces all statistical results reported in the paper.

Author: Saher Elsayed
"""

import json
import numpy as np
from scipy import stats
from scipy.stats import mannwhitneyu
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")


# ──────────────────────────────────────────────────────────────────
# Statistical Functions
# ──────────────────────────────────────────────────────────────────

def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Compute Cohen's d effect size between two groups."""
    pooled_std = np.sqrt((np.std(a, ddof=1)**2 + np.std(b, ddof=1)**2) / 2)
    if pooled_std == 0:
        return 0.0
    return (np.mean(a) - np.mean(b)) / pooled_std


def bootstrap_ci(a: np.ndarray, b: np.ndarray,
                 n_bootstrap: int = 2000,
                 ci: float = 0.95,
                 seed: int = 42) -> Tuple[float, float]:
    """
    Compute bootstrap confidence interval for the difference in means (a - b).
    Returns (lower, upper) bounds.
    """
    rng = np.random.default_rng(seed)
    diffs = []
    n_a, n_b = len(a), len(b)
    for _ in range(n_bootstrap):
        sample_a = rng.choice(a, size=n_a, replace=True)
        sample_b = rng.choice(b, size=n_b, replace=True)
        diffs.append(np.mean(sample_a) - np.mean(sample_b))

    alpha = 1 - ci
    lo = np.percentile(diffs, 100 * alpha / 2)
    hi = np.percentile(diffs, 100 * (1 - alpha / 2))
    return float(lo), float(hi)


def rank_biserial(u_stat: float, n1: int, n2: int) -> float:
    """Compute rank-biserial correlation from Mann-Whitney U statistic."""
    return 1 - (2 * u_stat) / (n1 * n2)


def effect_size_label(d: float) -> str:
    """Classify Cohen's d into small/medium/large/very large."""
    d = abs(d)
    if d < 0.2:
        return "negligible"
    elif d < 0.5:
        return "small"
    elif d < 0.8:
        return "medium"
    elif d < 1.2:
        return "large"
    else:
        return "very large"


def bonferroni_threshold(alpha: float, n_comparisons: int) -> float:
    return alpha / n_comparisons


# ──────────────────────────────────────────────────────────────────
# Pairwise Comparison
# ──────────────────────────────────────────────────────────────────

def compare_pair(smata: np.ndarray, baseline: np.ndarray,
                 baseline_name: str,
                 metric_name: str,
                 higher_is_better: bool = True,
                 alpha: float = 0.05,
                 bonferroni_n: int = 3) -> Dict:
    """
    Perform a full pairwise comparison between SMATA and a baseline.

    Returns a dictionary with all statistical measures.
    """
    if higher_is_better:
        u_stat, p_value = mannwhitneyu(smata, baseline, alternative="greater")
        d = cohens_d(smata, baseline)
    else:
        # For metrics where lower is better (e.g., debug time)
        u_stat, p_value = mannwhitneyu(baseline, smata, alternative="greater")
        d = cohens_d(baseline, smata)

    corrected_alpha = bonferroni_threshold(alpha, bonferroni_n)
    significant = p_value < corrected_alpha

    d_abs = abs(d)
    r_rb = rank_biserial(u_stat, len(smata), len(baseline))
    ci_lo, ci_hi = bootstrap_ci(smata, baseline)

    if higher_is_better:
        improvement_pct = (np.mean(smata) - np.mean(baseline)) / max(0.001, np.mean(baseline)) * 100
        improvement_abs = np.mean(smata) - np.mean(baseline)
    else:
        improvement_pct = (np.mean(baseline) - np.mean(smata)) / max(0.001, np.mean(baseline)) * 100
        improvement_abs = np.mean(baseline) - np.mean(smata)

    return {
        "metric": metric_name,
        "baseline": baseline_name,
        "smata_mean": round(float(np.mean(smata)), 2),
        "smata_std": round(float(np.std(smata, ddof=1)), 2),
        "baseline_mean": round(float(np.mean(baseline)), 2),
        "baseline_std": round(float(np.std(baseline, ddof=1)), 2),
        "improvement_abs": round(improvement_abs, 2),
        "improvement_pct": round(improvement_pct, 1),
        "u_statistic": float(u_stat),
        "p_value": float(p_value),
        "p_value_corrected_alpha": corrected_alpha,
        "significant": significant,
        "cohens_d": round(d_abs, 3),
        "effect_size_label": effect_size_label(d_abs),
        "rank_biserial_r": round(r_rb, 3),
        "ci_95_lo": round(ci_lo, 2),
        "ci_95_hi": round(ci_hi, 2),
    }


# ──────────────────────────────────────────────────────────────────
# Full Analysis Pipeline
# ──────────────────────────────────────────────────────────────────

def run_full_analysis(data_path: str = "data/experiment_data.json",
                      output_path: str = "data/processed/statistical_results.json") -> Dict:
    """
    Run the complete statistical analysis pipeline on experimental data.

    Computes all pairwise comparisons for all metrics with full
    statistical reporting.
    """
    print("=" * 70)
    print("SMATA Statistical Analysis")
    print("=" * 70)

    with open(data_path) as f:
        data = json.load(f)

    results = {}
    BONFERRONI_N = 3  # 3 comparisons per metric (vs Monkey, Dynodroid, Ad-hoc)
    ALPHA = 0.05

    # ── Coverage Analysis ────────────────────────────────────────
    print("\n[RQ1] Code Coverage Analysis")
    print("-" * 50)

    coverage = data["coverage"]
    smata_cov = np.array(coverage["smata"])
    monkey_cov = np.array(coverage["monkey"])
    dynodroid_cov = np.array(coverage["dynodroid"])
    adhoc_cov = np.array(coverage["adhoc"])

    cov_results = []
    for baseline_name, baseline_arr in [
        ("Monkey", monkey_cov),
        ("Dynodroid", dynodroid_cov),
        ("Ad-hoc", adhoc_cov),
    ]:
        r = compare_pair(smata_cov, baseline_arr, baseline_name,
                        "Coverage (%)", higher_is_better=True,
                        bonferroni_n=BONFERRONI_N)
        cov_results.append(r)
        sig_marker = "***" if r["p_value"] < 0.001 else "**" if r["p_value"] < 0.01 else "*" if r["significant"] else "ns"
        print(f"  SMATA vs {baseline_name:12s}: "
              f"mean_diff={r['improvement_abs']:+.1f}pp | "
              f"p={r['p_value']:.2e} {sig_marker} | "
              f"d={r['cohens_d']:.2f} ({r['effect_size_label']}) | "
              f"95%CI=[{r['ci_95_lo']:.1f},{r['ci_95_hi']:.1f}]")
    results["coverage"] = cov_results

    print(f"\n  SMATA: {np.mean(smata_cov):.1f}% +/- {np.std(smata_cov, ddof=1):.1f}%")
    print(f"  Monkey: {np.mean(monkey_cov):.1f}%, Dynodroid: {np.mean(dynodroid_cov):.1f}%, "
          f"Ad-hoc: {np.mean(adhoc_cov):.1f}%")

    # ── Fault Detection Analysis ──────────────────────────────────
    print("\n[RQ2a] Fault Detection Rate Analysis")
    print("-" * 50)

    fd = data["fault_detection"]
    smata_fd = np.array(fd["smata"]) * 100
    monkey_fd = np.array(fd["monkey"]) * 100
    dynodroid_fd = np.array(fd["dynodroid"]) * 100
    adhoc_fd = np.array(fd["adhoc"]) * 100

    fd_results = []
    for baseline_name, baseline_arr in [
        ("Monkey", monkey_fd),
        ("Dynodroid", dynodroid_fd),
        ("Ad-hoc", adhoc_fd),
    ]:
        r = compare_pair(smata_fd, baseline_arr, baseline_name,
                        "Fault Detection (%)", bonferroni_n=BONFERRONI_N)
        fd_results.append(r)
        sig_marker = "***" if r["p_value"] < 0.001 else "**" if r["p_value"] < 0.01 else "*" if r["significant"] else "ns"
        print(f"  SMATA vs {baseline_name:12s}: "
              f"mean_diff={r['improvement_abs']:+.1f}pp | "
              f"p={r['p_value']:.2e} {sig_marker} | "
              f"d={r['cohens_d']:.2f} ({r['effect_size_label']})")
    results["fault_detection"] = fd_results

    # ── Reproducibility Analysis ──────────────────────────────────
    print("\n[RQ2b] Bug Reproducibility Analysis")
    print("-" * 50)

    rp = data["reproducibility"]
    smata_rp = np.array(rp["smata"]) * 100
    monkey_rp = np.array(rp["monkey"]) * 100
    dynodroid_rp = np.array(rp["dynodroid"]) * 100
    adhoc_rp = np.array(rp["adhoc"]) * 100

    rp_results = []
    for baseline_name, baseline_arr in [
        ("Monkey", monkey_rp),
        ("Dynodroid", dynodroid_rp),
        ("Ad-hoc", adhoc_rp),
    ]:
        r = compare_pair(smata_rp, baseline_arr, baseline_name,
                        "Reproducibility (%)", bonferroni_n=BONFERRONI_N)
        rp_results.append(r)
        improvement_x = np.mean(smata_rp) / max(0.001, np.mean(baseline_arr))
        sig_marker = "***" if r["p_value"] < 0.001 else "**" if r["p_value"] < 0.01 else "*" if r["significant"] else "ns"
        print(f"  SMATA vs {baseline_name:12s}: "
              f"{improvement_x:.2f}x improvement | "
              f"p={r['p_value']:.2e} {sig_marker} | "
              f"d={r['cohens_d']:.2f} ({r['effect_size_label']})")
    results["reproducibility"] = rp_results

    # ── Debug Time Analysis ───────────────────────────────────────
    print("\n[RQ2c] Debugging Time Analysis")
    print("-" * 50)

    dt = data["debug_time_min"]
    smata_dt = np.array(dt["smata"])
    monkey_dt = np.array(dt["monkey"])
    dynodroid_dt = np.array(dt["dynodroid"])
    adhoc_dt = np.array(dt["adhoc"])

    dt_results = []
    for baseline_name, baseline_arr in [
        ("Monkey", monkey_dt),
        ("Dynodroid", dynodroid_dt),
        ("Ad-hoc", adhoc_dt),
    ]:
        r = compare_pair(smata_dt, baseline_arr, baseline_name,
                        "Debug Time (min/bug)", higher_is_better=False,
                        bonferroni_n=BONFERRONI_N)
        dt_results.append(r)
        reduction_pct = r["improvement_pct"]
        sig_marker = "***" if r["p_value"] < 0.001 else "**" if r["p_value"] < 0.01 else "*" if r["significant"] else "ns"
        print(f"  SMATA vs {baseline_name:12s}: "
              f"{reduction_pct:.1f}% reduction | "
              f"p={r['p_value']:.2e} {sig_marker} | "
              f"d={r['cohens_d']:.2f} ({r['effect_size_label']})")
    results["debug_time"] = dt_results

    # ── Setup Time Analysis ───────────────────────────────────────
    print("\n[RQ3] Setup Time Analysis")
    print("-" * 50)

    st = data["setup_time_hr"]
    smata_st_reuse = np.array(st["smata_reuse"])
    adhoc_st = np.array(st["adhoc"])

    reduction_pct = (np.mean(adhoc_st) - np.mean(smata_st_reuse)) / np.mean(adhoc_st) * 100
    _, p_setup = mannwhitneyu(adhoc_st, smata_st_reuse, alternative="greater")
    d_setup = cohens_d(adhoc_st, smata_st_reuse)

    print(f"  SMATA-Reuse vs Ad-hoc: {reduction_pct:.1f}% reduction | "
          f"p={p_setup:.2e} | d={d_setup:.2f}")
    print(f"  Ad-hoc: {np.mean(adhoc_st):.1f}h +/- {np.std(adhoc_st, ddof=1):.1f}h")
    print(f"  SMATA-Reuse: {np.mean(smata_st_reuse):.1f}h +/- {np.std(smata_st_reuse, ddof=1):.1f}h")

    results["setup_time"] = {
        "smata_reuse_mean": round(float(np.mean(smata_st_reuse)), 2),
        "adhoc_mean": round(float(np.mean(adhoc_st)), 2),
        "reduction_pct": round(reduction_pct, 1),
        "p_value": float(p_setup),
        "cohens_d": round(d_setup, 2),
    }

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)
    print(f"{'Metric':<20} {'Monkey':>12} {'Dynodroid':>12} {'Ad-hoc':>12} {'SMATA':>12}")
    print("-" * 70)

    metrics_data = [
        ("Coverage (%)",    monkey_cov, dynodroid_cov, adhoc_cov, smata_cov),
        ("Fault Det. (%)",  monkey_fd,  dynodroid_fd,  adhoc_fd,  smata_fd),
        ("Reprod. (%)",     monkey_rp,  dynodroid_rp,  adhoc_rp,  smata_rp),
        ("Debug (min/bug)", monkey_dt,  dynodroid_dt,  adhoc_dt,  smata_dt),
    ]

    for name, m, d, a, s in metrics_data:
        print(f"{name:<20} "
              f"{np.mean(m):>7.1f}+/-{np.std(m,ddof=1):<4.1f} "
              f"{np.mean(d):>7.1f}+/-{np.std(d,ddof=1):<4.1f} "
              f"{np.mean(a):>7.1f}+/-{np.std(a,ddof=1):<4.1f} "
              f"{np.mean(s):>7.1f}+/-{np.std(s,ddof=1):<4.1f}")

    # Save results
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")

    return results


if __name__ == "__main__":
    import sys
    data_path = sys.argv[1] if len(sys.argv) > 1 else "data/experiment_data.json"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "data/processed/statistical_results.json"
    run_full_analysis(data_path, output_path)
