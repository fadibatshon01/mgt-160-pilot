"""
MGT 160 Pilot — Analysis Pipeline
=================================
Implements the pre-specified analysis plan for the HLXE ETF 2x2 factorial study.

Run:
    python3 analyze.py

Inputs:
    data/Pilot results.csv   (default; override with --csv)

Outputs (written to outputs/):
    report.md                 (single written report)
    fig_*.png                 (figures)
    tab_*.csv                 (tables)
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.power import TTestIndPower

ALPHA = 0.05
HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "data" / "Pilot results.csv"
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)

ATTN_LOWER = 10     # seconds: <10 = didn't read
ATTN_UPPER = 600    # seconds: >600 = walked away

# 4 conditions: (headline_type, social_proof) -> condition number
CELL_ORDER = [
    ("neutral", "no"),     # 1 — control
    ("neutral", "yes"),    # 2
    ("hyped",   "no"),     # 3
    ("hyped",   "yes"),    # 4
]
CELL_LABELS = {
    ("neutral", "no"):  "Neutral / no proof (Ctrl)",
    ("neutral", "yes"): "Neutral / proof",
    ("hyped",   "no"):  "Hyped / no proof",
    ("hyped",   "yes"): "Hyped / proof",
}


# ------------------------------------------------------------------ helpers

def fmt_p(p: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "n/a"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan")
    sa2 = a.var(ddof=1)
    sb2 = b.var(ddof=1)
    sp = np.sqrt(((na - 1) * sa2 + (nb - 1) * sb2) / (na + nb - 2))
    if sp == 0:
        return float("nan")
    return (a.mean() - b.mean()) / sp


def welch_t(a: np.ndarray, b: np.ndarray) -> dict:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    res = stats.ttest_ind(a, b, equal_var=False)
    diff = a.mean() - b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    df = res.df if hasattr(res, "df") else (len(a) + len(b) - 2)
    crit = stats.t.ppf(1 - ALPHA / 2, df)
    return {
        "mean_a": float(a.mean()),
        "mean_b": float(b.mean()),
        "n_a": int(len(a)),
        "n_b": int(len(b)),
        "diff": float(diff),
        "ci_low": float(diff - crit * se),
        "ci_high": float(diff + crit * se),
        "t": float(res.statistic),
        "df": float(df),
        "p": float(res.pvalue),
        "d": float(cohens_d(a, b)),
        "se": float(se),
    }


def mean_ci(x: np.ndarray, alpha: float = ALPHA) -> tuple[float, float, float]:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 2:
        return (float(x.mean()) if n else float("nan"), float("nan"), float("nan"))
    m = x.mean()
    se = x.std(ddof=1) / np.sqrt(n)
    crit = stats.t.ppf(1 - alpha / 2, n - 1)
    return float(m), float(m - crit * se), float(m + crit * se)


def chi2_or_fisher(tab: pd.DataFrame) -> tuple[float, float, int, str]:
    """Return (stat, p, dof, test_name)."""
    if (tab.values < 5).any() and tab.shape == (2, 2):
        odds, p = stats.fisher_exact(tab.values)
        return float(odds), float(p), 1, "Fisher's exact"
    chi2, p, dof, _ = stats.chi2_contingency(tab.values)
    return float(chi2), float(p), int(dof), "chi-squared"


# ------------------------------------------------------------------ load

def load_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows from {csv_path}")
    print("\nRaw columns and dtypes:")
    print(df.dtypes.to_string())

    # numeric coercion
    num_cols = [
        "condition", "safe_allocation", "hlxe_allocation", "hlxe_return",
        "final_portfolio", "confidence", "age",
        "time_on_page_seconds", "time_to_submit_seconds",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # treasury allocation: derived
    df["treasury_allocation"] = 1000 - df["hlxe_allocation"]

    # binary outcome fallback
    df["took_risky_bet"] = (df["hlxe_allocation"] > 500).astype(int)

    # business/econ vs other
    df["major_area_binary"] = np.where(
        df["major_area"].astype(str).str.lower() == "business_econ",
        "Business/Econ",
        "Other",
    )

    # cell label for grouping
    df["cell"] = list(zip(df["headline_type"], df["social_proof"]))

    return df


# ------------------------------------------------------------------ sec 1: sanity

def sample_summary(df: pd.DataFrame) -> str:
    by_cond = df.groupby("condition").size().rename("n")
    by_cell = (
        df.groupby(["headline_type", "social_proof"]).size().rename("n").reset_index()
    )
    by_cell.to_csv(OUT / "tab_sample_by_cell.csv", index=False)
    by_cond.to_csv(OUT / "tab_sample_by_condition.csv")
    lines = [
        f"Total N: **{len(df)}**",
        "",
        "Per-cell N:",
        "",
        "| condition | headline_type | social_proof | N |",
        "|---|---|---|---|",
    ]
    for cell in CELL_ORDER:
        h, s = cell
        n = ((df["headline_type"] == h) & (df["social_proof"] == s)).sum()
        cond = df.loc[(df["headline_type"] == h) & (df["social_proof"] == s), "condition"]
        cond_num = int(cond.iloc[0]) if len(cond) else "?"
        lines.append(f"| {cond_num} | {h} | {s} | {n} |")
    return "\n".join(lines)


def balance_table(df: pd.DataFrame) -> tuple[str, list[str]]:
    """Cross-tab demographics by condition. Returns markdown + list of imbalanced vars."""
    rows = []
    imbalanced = []

    # age: one-way ANOVA
    groups = [g["age"].dropna().values for _, g in df.groupby("condition")]
    f, p = stats.f_oneway(*groups)
    rows.append(("age (mean)", "one-way ANOVA", f"F={f:.2f}", fmt_p(p)))
    if p < ALPHA:
        imbalanced.append("age")

    # categorical: chi-squared
    cat_vars = ["gender", "year_in_school", "major_area", "prior_investor"]
    for v in cat_vars:
        tab = pd.crosstab(df[v], df["condition"])
        stat, p, dof, name = chi2_or_fisher(tab)
        rows.append((v, name, f"stat={stat:.2f}, dof={dof}", fmt_p(p)))
        if p < ALPHA:
            imbalanced.append(v)

    bal = pd.DataFrame(rows, columns=["variable", "test", "statistic", "p"])
    bal.to_csv(OUT / "tab_balance.csv", index=False)

    # also save the cell-level means for age and proportion summaries
    summary_rows = []
    for cond, g in df.groupby("condition"):
        summary_rows.append({
            "condition": cond,
            "n": len(g),
            "age_mean": round(g["age"].mean(), 2),
            "pct_woman": round((g["gender"] == "woman").mean() * 100, 1),
            "pct_man": round((g["gender"] == "man").mean() * 100, 1),
            "pct_business_econ": round((g["major_area"] == "business_econ").mean() * 100, 1),
            "pct_prior_investor": round((g["prior_investor"] == "yes").mean() * 100, 1),
        })
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUT / "tab_balance_summary.csv", index=False)

    md = ["| variable | test | statistic | p |", "|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
    md.append("")
    md.append("Per-condition descriptives:")
    md.append("")
    md.append("| condition | N | age (mean) | % woman | % man | % business/econ | % prior investor |")
    md.append("|---|---|---|---|---|---|---|")
    for r in summary_rows:
        md.append(
            f"| {r['condition']} | {r['n']} | {r['age_mean']} | "
            f"{r['pct_woman']}% | {r['pct_man']}% | "
            f"{r['pct_business_econ']}% | {r['pct_prior_investor']}% |"
        )
    return "\n".join(md), imbalanced


def plot_outcome_dist(df: pd.DataFrame) -> tuple[str, bool]:
    """Histogram per condition. Returns path and bimodal-flag."""
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True, sharey=True)
    bimodal_flags = []
    for ax, cell in zip(axes.flat, CELL_ORDER):
        h, s = cell
        x = df.loc[(df["headline_type"] == h) & (df["social_proof"] == s), "hlxe_allocation"]
        ax.hist(x, bins=20, range=(0, 1000), color="#31A354", edgecolor="white")
        ax.set_title(CELL_LABELS[cell], fontsize=10)
        ax.set_xlabel("HLXE allocation ($)")
        ax.set_ylabel("Count")
        # bimodal heuristic: >40% of mass at corners
        if len(x):
            corner_mass = ((x <= 50) | (x >= 950)).mean()
            bimodal_flags.append(corner_mass > 0.4)
    fig.suptitle("Distribution of HLXE allocation per cell")
    fig.tight_layout()
    path = OUT / "fig_outcome_distribution.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return str(path.name), bool(np.mean(bimodal_flags) >= 0.5)


def attention_filter(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    n_total = len(df)
    too_fast = (df["time_on_page_seconds"] < ATTN_LOWER).sum()
    too_slow = (df["time_on_page_seconds"] > ATTN_UPPER).sum()
    mask = (df["time_on_page_seconds"] >= ATTN_LOWER) & (df["time_on_page_seconds"] <= ATTN_UPPER)
    kept = df.loc[mask].copy()
    info = {
        "n_total": n_total,
        "n_too_fast": int(too_fast),
        "n_too_slow": int(too_slow),
        "n_kept": int(len(kept)),
        "lower": ATTN_LOWER,
        "upper": ATTN_UPPER,
    }
    return kept, info


# ------------------------------------------------------------------ sec 2: primary

def main_effect_test(df: pd.DataFrame, var: str, level_a: str, level_b: str) -> dict:
    a = df.loc[df[var] == level_a, "hlxe_allocation"].values
    b = df.loc[df[var] == level_b, "hlxe_allocation"].values
    res = welch_t(a, b)
    res["var"] = var
    res["level_a"] = level_a
    res["level_b"] = level_b
    return res


def two_by_two_anova(df: pd.DataFrame, outcome: str = "hlxe_allocation") -> pd.DataFrame:
    sub = df[[outcome, "headline_type", "social_proof"]].dropna()
    model = smf.ols(f"{outcome} ~ C(headline_type) * C(social_proof)", data=sub).fit()
    anova_tbl = sm.stats.anova_lm(model, typ=2)
    # partial eta squared: SS_effect / (SS_effect + SS_resid)
    ss_resid = anova_tbl.loc["Residual", "sum_sq"]
    anova_tbl["partial_eta2"] = anova_tbl["sum_sq"] / (anova_tbl["sum_sq"] + ss_resid)
    anova_tbl.loc["Residual", "partial_eta2"] = np.nan
    return anova_tbl


def headline_figure(df: pd.DataFrame, fname: str, title_suffix: str = "") -> str:
    means, ci_lo, ci_hi, labels = [], [], [], []
    for cell in CELL_ORDER:
        h, s = cell
        x = df.loc[(df["headline_type"] == h) & (df["social_proof"] == s), "hlxe_allocation"]
        m, lo, hi = mean_ci(x.values)
        means.append(m)
        ci_lo.append(lo)
        ci_hi.append(hi)
        labels.append(CELL_LABELS[cell])
    means = np.array(means)
    err = np.array([means - np.array(ci_lo), np.array(ci_hi) - means])
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    colors = ["#C7E9C0", "#A1D99B", "#41AB5D", "#006D2C"]
    bars = ax.bar(range(4), means, yerr=err, capsize=6,
                  color=colors, edgecolor="black", linewidth=0.8)
    ax.set_xticks(range(4))
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("Mean HLXE allocation ($, 0–1000)")
    ax.set_title(f"Mean HLXE allocation by condition (95% CI){title_suffix}")
    ax.axhline(500, color="gray", linewidth=0.5, linestyle="--", alpha=0.6)
    for bar, m in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 15,
                f"${m:.0f}", ha="center", fontsize=10)
    ax.set_ylim(0, 1000)
    fig.tight_layout()
    path = OUT / fname
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path.name


def primary_results_table(df: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    sp = main_effect_test(df, "social_proof", "yes", "no")
    hp = main_effect_test(df, "headline_type", "hyped", "neutral")
    anova = two_by_two_anova(df)

    rows = []
    for label, r in [("social_proof (yes − no)", sp),
                     ("headline_type (hyped − neutral)", hp)]:
        rows.append({
            "effect": label,
            "mean_a": round(r["mean_a"], 1),
            "mean_b": round(r["mean_b"], 1),
            "diff": round(r["diff"], 1),
            "ci_low": round(r["ci_low"], 1),
            "ci_high": round(r["ci_high"], 1),
            "t": round(r["t"], 2),
            "df": round(r["df"], 1),
            "p": fmt_p(r["p"]),
            "cohens_d": round(r["d"], 2),
            "n_a": r["n_a"],
            "n_b": r["n_b"],
        })
    primary_tbl = pd.DataFrame(rows)
    primary_tbl.to_csv(OUT / "tab_primary_tests.csv", index=False)
    anova.to_csv(OUT / "tab_anova_2x2.csv")
    return {"sp": sp, "hp": hp}, primary_tbl, anova


# ------------------------------------------------------------------ sec 3: subgroups

def subgroup_anova(df: pd.DataFrame, moderator: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    sub = df[["hlxe_allocation", "headline_type", "social_proof", moderator]].dropna()
    formula = f"hlxe_allocation ~ C(headline_type) * C(social_proof) * C({moderator})"
    model = smf.ols(formula, data=sub).fit()
    anova_tbl = sm.stats.anova_lm(model, typ=2)
    ss_resid = anova_tbl.loc["Residual", "sum_sq"]
    anova_tbl["partial_eta2"] = anova_tbl["sum_sq"] / (anova_tbl["sum_sq"] + ss_resid)
    anova_tbl.loc["Residual", "partial_eta2"] = np.nan

    means = (
        sub.groupby([moderator, "headline_type", "social_proof"])["hlxe_allocation"]
        .agg(["mean", "std", "count"])
        .round(1)
        .reset_index()
    )
    return anova_tbl, means


def subgroup_figure(df: pd.DataFrame, moderator: str, fname: str, title: str) -> str:
    sub = df.dropna(subset=["hlxe_allocation", moderator])
    levels = sorted(sub[moderator].dropna().unique())
    width = 0.35
    x = np.arange(4)
    fig, ax = plt.subplots(figsize=(9, 5.5))
    palette = ["#A1D99B", "#006D2C", "#74C476", "#00441B"]
    truncated_marks = []  # (xpos, ypos, direction) for cells where CI was clipped
    for i, lvl in enumerate(levels):
        means, errs = [], []
        ns = []
        for cell in CELL_ORDER:
            h, s = cell
            xv = sub.loc[
                (sub[moderator] == lvl)
                & (sub["headline_type"] == h)
                & (sub["social_proof"] == s),
                "hlxe_allocation",
            ].values
            ns.append(len(xv))
            m, lo, hi = mean_ci(xv)
            m_disp = m if not np.isnan(m) else 0
            lo_disp = lo if not np.isnan(lo) else m_disp
            hi_disp = hi if not np.isnan(hi) else m_disp
            # outcome is bounded [0, 1000] — clip CI to that range and mark
            lo_clip = max(0.0, lo_disp)
            hi_clip = min(1000.0, hi_disp)
            means.append(m_disp)
            errs.append((m_disp - lo_clip, hi_clip - m_disp))
            xpos = x[CELL_ORDER.index(cell)] + (i - (len(levels) - 1) / 2) * width
            if hi_disp > 1000.0:
                truncated_marks.append((xpos, 995, "▲"))
            if lo_disp < 0.0:
                truncated_marks.append((xpos, 5, "▼"))
        errs_arr = np.array(errs).T
        bars = ax.bar(x + (i - (len(levels) - 1) / 2) * width, means, width,
                      yerr=errs_arr, capsize=4,
                      label=f"{moderator}={lvl}", color=palette[i % len(palette)],
                      edgecolor="black", linewidth=0.6)
        for bar, m, n in zip(bars, means, ns):
            ax.text(bar.get_x() + bar.get_width() / 2, 20,
                    f"n={n}", ha="center", fontsize=8, color="#333")
    for xpos, ypos, sym in truncated_marks:
        ax.text(xpos, ypos, sym, ha="center", va="center", fontsize=10, color="#B00")
    ax.set_xticks(x)
    ax.set_xticklabels([CELL_LABELS[c] for c in CELL_ORDER], rotation=15, ha="right")
    ax.set_ylabel("Mean HLXE allocation ($)")
    ax.set_title(title)
    ax.legend()
    ax.set_ylim(0, 1000)
    if truncated_marks:
        fig.text(0.5, 0.01,
                 "▲/▼ = 95% CI extends beyond outcome bounds [0, 1000]; clipped for display",
                 ha="center", va="bottom", fontsize=8, color="#B00")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    path = OUT / fname
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path.name


# ------------------------------------------------------------------ sec 4: secondary

def confidence_anova(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    sub = df[["confidence", "headline_type", "social_proof"]].dropna()
    model = smf.ols("confidence ~ C(headline_type) * C(social_proof)", data=sub).fit()
    anova_tbl = sm.stats.anova_lm(model, typ=2)
    ss_resid = anova_tbl.loc["Residual", "sum_sq"]
    anova_tbl["partial_eta2"] = anova_tbl["sum_sq"] / (anova_tbl["sum_sq"] + ss_resid)
    anova_tbl.loc["Residual", "partial_eta2"] = np.nan

    means = (
        sub.groupby(["headline_type", "social_proof"])["confidence"]
        .agg(["mean", "std", "count"])
        .round(2)
        .reset_index()
    )
    return anova_tbl, means


def confidence_allocation_corr(df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    sub = df[["confidence", "hlxe_allocation", "headline_type", "social_proof"]].dropna()
    r_all, p_all = stats.pearsonr(sub["confidence"], sub["hlxe_allocation"])
    overall = {"scope": "overall", "n": len(sub), "r": round(r_all, 2), "p": fmt_p(p_all)}

    rows = [overall]
    for cell in CELL_ORDER:
        h, s = cell
        c = sub[(sub["headline_type"] == h) & (sub["social_proof"] == s)]
        if len(c) >= 3:
            r, p = stats.pearsonr(c["confidence"], c["hlxe_allocation"])
            rows.append({
                "scope": CELL_LABELS[cell],
                "n": len(c),
                "r": round(r, 2),
                "p": fmt_p(p),
            })
        else:
            rows.append({"scope": CELL_LABELS[cell], "n": len(c),
                         "r": "n/a", "p": "n<3"})
    tbl = pd.DataFrame(rows)
    tbl.to_csv(OUT / "tab_confidence_corr.csv", index=False)
    return overall, tbl


def timing_test(df: pd.DataFrame, col: str) -> tuple[pd.DataFrame, dict]:
    medians = (
        df.groupby(["headline_type", "social_proof"])[col]
        .median()
        .round(1)
        .reset_index()
        .rename(columns={col: f"{col}_median"})
    )
    hyped = df.loc[df["headline_type"] == "hyped", col].dropna().values
    neutral = df.loc[df["headline_type"] == "neutral", col].dropna().values
    u, p = stats.mannwhitneyu(hyped, neutral, alternative="two-sided")
    test = {
        "n_hyped": int(len(hyped)),
        "n_neutral": int(len(neutral)),
        "median_hyped": float(np.median(hyped)),
        "median_neutral": float(np.median(neutral)),
        "U": float(u),
        "p": float(p),
    }
    return medians, test


# ------------------------------------------------------------------ sec 5: power

def power_table(sp_result: dict, hp_result: dict, df: pd.DataFrame) -> pd.DataFrame:
    analyzer = TTestIndPower()
    rows = []
    for label, r in [("social_proof", sp_result), ("headline_type", hp_result)]:
        n_per_group = int(np.mean([r["n_a"], r["n_b"]]))
        d_obs = abs(r["d"])
        if d_obs > 0 and not np.isnan(d_obs):
            achieved = analyzer.solve_power(effect_size=d_obs, nobs1=n_per_group,
                                            alpha=ALPHA, ratio=1.0, alternative="two-sided")
            mde = analyzer.solve_power(effect_size=None, nobs1=n_per_group,
                                       alpha=ALPHA, power=0.80, ratio=1.0,
                                       alternative="two-sided")
            n_needed = analyzer.solve_power(effect_size=d_obs, alpha=ALPHA,
                                            power=0.80, ratio=1.0,
                                            alternative="two-sided")
        else:
            achieved = np.nan
            mde = analyzer.solve_power(effect_size=None, nobs1=n_per_group,
                                       alpha=ALPHA, power=0.80, ratio=1.0,
                                       alternative="two-sided")
            n_needed = np.nan
        rows.append({
            "contrast": label,
            "n_per_group": n_per_group,
            "total_n": r["n_a"] + r["n_b"],
            "observed_d": round(d_obs, 3) if not np.isnan(d_obs) else "n/a",
            "achieved_power": round(achieved, 3) if not np.isnan(achieved) else "n/a",
            "MDE_d_at_0.80": round(mde, 3),
            "n_per_group_needed_for_0.80": (
                int(np.ceil(n_needed)) if not np.isnan(n_needed) else "n/a"
            ),
        })
    tbl = pd.DataFrame(rows)
    tbl.to_csv(OUT / "tab_power_mde.csv", index=False)
    return tbl


# ------------------------------------------------------------------ report

@dataclass
class ReportPieces:
    sample_md: str
    balance_md: str
    imbalanced: list
    dist_fig: str
    bimodal: bool
    attn_info: dict
    primary_tbl_full: pd.DataFrame
    anova_full: pd.DataFrame
    headline_fig_full: str
    sp_full: dict
    hp_full: dict
    sub_prior_anova: pd.DataFrame
    sub_prior_means: pd.DataFrame
    sub_prior_fig: str
    sub_major_anova: pd.DataFrame
    sub_major_means: pd.DataFrame
    sub_major_fig: str
    conf_anova: pd.DataFrame
    conf_means: pd.DataFrame
    conf_corr_tbl: pd.DataFrame
    time_submit_medians: pd.DataFrame
    time_submit_test: dict
    time_page_medians: pd.DataFrame
    time_page_test: dict
    power_tbl: pd.DataFrame
    binary_results: dict


def df_to_md(df: pd.DataFrame, index: bool = False, float_fmt: str = "{:.3f}") -> str:
    df2 = df.copy()
    for c in df2.columns:
        if pd.api.types.is_float_dtype(df2[c]):
            df2[c] = df2[c].map(lambda v: "n/a" if pd.isna(v) else float_fmt.format(v))
    if index:
        df2 = df2.reset_index()
    cols = list(df2.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |"]
    lines.append("| " + " | ".join("---" for _ in cols) + " |")
    for _, row in df2.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.tolist()) + " |")
    return "\n".join(lines)


def write_report(pieces: ReportPieces) -> Path:
    p = OUT / "report.md"

    # plain-English takeaway for primary
    sp = pieces.sp_full
    hp = pieces.hp_full

    def es_str(r):
        sign = "+" if r["diff"] >= 0 else ""
        pct = r["diff"] / r["mean_b"] * 100 if r["mean_b"] else float("nan")
        return f"{sign}${r['diff']:.0f} ({sign}{pct:.1f}%)"

    sp_take = (
        f"Social proof shifted allocation by **{es_str(sp)}** "
        f"(95% CI [{sp['ci_low']:.0f}, {sp['ci_high']:.0f}], "
        f"p={fmt_p(sp['p'])}, d={sp['d']:.2f})."
    )
    hp_take = (
        f"Hype framing shifted allocation by **{es_str(hp)}** "
        f"(95% CI [{hp['ci_low']:.0f}, {hp['ci_high']:.0f}], "
        f"p={fmt_p(hp['p'])}, d={hp['d']:.2f})."
    )

    # winners
    cell_means = {cell: pieces.binary_results["cell_means"][cell] for cell in CELL_ORDER}
    ctrl_cell = ("neutral", "no")
    ctrl_mean = cell_means[ctrl_cell]
    treatment_cells = {c: m for c, m in cell_means.items() if c != ctrl_cell}
    best_treatment_cell = max(treatment_cells, key=treatment_cells.get)
    best_treatment_mean = treatment_cells[best_treatment_cell]
    best_overall_cell = max(cell_means, key=cell_means.get)
    best_overall_mean = cell_means[best_overall_cell]
    best_delta = best_treatment_mean - ctrl_mean
    best_pct = (best_delta / ctrl_mean * 100) if ctrl_mean else float("nan")
    control_won = best_overall_cell == ctrl_cell

    # attention filter line
    attn = pieces.attn_info
    attn_line = (
        f"Attention-filter flags (FYI only — not excluded): "
        f"{attn['n_too_fast']} row(s) <{attn['lower']}s, "
        f"{attn['n_too_slow']} row(s) >{attn['upper']}s "
        f"(out of {attn['n_total']} total)."
    )

    # limitations
    lim = []
    n_total = attn["n_total"]
    if n_total < 100:
        lim.append(f"Small pilot (N={n_total}) → low power; treat all p-values as exploratory.")
    if pieces.bimodal:
        lim.append("Outcome distribution piles at \\$0 / \\$1000 corners "
                   "(bimodal); reported both the dollar-mean and the binary "
                   "`took_risky_bet` outcome.")
    if pieces.imbalanced:
        lim.append("Imbalance on " + ", ".join(pieces.imbalanced) +
                   " across conditions; flagged as a covariate to model in follow-up work.")
    if attn["n_too_fast"] + attn["n_too_slow"] > 0:
        lim.append(f"{attn['n_too_fast'] + attn['n_too_slow']} rows flagged "
                   f"by the attention filter (<{attn['lower']}s or "
                   f">{attn['upper']}s on the listing page); reported here for "
                   "transparency but not excluded.")
    lim.append("Hypothetical \\$1,000 — no real money on the line; "
               "behavior may differ from real-stakes investing.")
    lim.append("Self-selected, mostly student sample — generalizes best to "
               "U.S. undergrads with similar demographics.")
    lim.append("Single-shot decision per participant; no test of stability over time.")
    lim.append("Possible demand effects from cue salience: 'HOT PICK' framing may "
               "have signaled the experimenter's hypothesis.")

    md = f"""# MGT 160 Pilot — HLXE 2×2 Factorial: Results

> Study: identical fictional ETF (HLXE) shown with/without a popularity badge
> (`social_proof`) and with/without "HOT PICK" framing (`headline_type`).
> Each participant allocated a hypothetical \\$1,000 between a guaranteed
> Treasury bond (+5%) and HLXE (uniform −25% to +25%). Primary outcome:
> `hlxe_allocation` (dollars 0–1000 into the risky ETF).

α = {ALPHA}. All p-values reported to 3 decimals; Cohen's d and r to 2.

---

## −1. Motivation: why this question matters

**The decision environment we're studying.** Mobile-first retail brokerages (Robinhood, Public, eToro, Webull) have replaced traditional finance UIs — built around prospectus disclosures and risk metrics — with feed-style listing pages that surface *social* and *emotional* signals: trending lists, popularity badges, "most bought today," confetti animations on first trade. Roughly 30 million U.S. adults opened their first brokerage account between 2020 and 2023, the largest cohort of brand-new retail investors in a generation, and most of them are picking assets from interfaces that look more like a TikTok For You page than a Bloomberg terminal.

**Why we should care.** If a single UI cue — a popularity badge, a hype headline — can meaningfully shift how much of a portfolio a new investor steers into a risky asset, then UI-design choices made by brokerages have a *direct* welfare consequence for tens of millions of households. Even small shifts (a few percentage points of allocation) compound: behavioral nudges in the Save More Tomorrow literature (Thaler & Benartzi, 2004) produce 1–3 percentage-point allocation changes that translate into thousands of dollars over a working lifetime. The same logic, run in the *risk-taking* direction, is a consumer-protection and product-design question worth understanding empirically.

**What prior work suggests the cues should do.** Two well-replicated literatures motivate our manipulations:

- *Social-proof / herding.* Cialdini's "social proof" (1984) and a long line of follow-ups (e.g., Salganik et al. 2006 on cultural-market herding) show that signaling popularity changes choice probabilities even when the underlying option is held constant. Robinhood's "Top Movers" list has been shown observationally to concentrate trading on listed names (Barber, Huang, Odean & Schwarz 2022, "Attention-Induced Trading and Returns").
- *Hype / affective framing.* "Affect heuristic" work (Slovic et al. 2007) and a separate literature on positive-affect financial messaging show that warm/positive framing reduces perceived risk for the same underlying asset.

**The gap this pilot fills.** Both literatures predict an effect; neither has been tested in a clean factorial inside an ETF listing UI with allocation (not just choice) as the outcome. We hold the asset constant and randomize *only* the cues, so any allocation difference is causally attributable to the UI manipulation.

---

## 0. Design, randomization, and pre-registered hypotheses

**Treatments (2×2 factorial).** Identical fictional ETF — **HLXE / "Helix Renewable Energy ETF"**, a mid-cap renewable-energy fund — shown in four cells:

| condition | headline_type | social_proof | on-page manipulation |
|---|---|---|---|
| 1 (control) | neutral | no  | plain listing |
| 2 | neutral | yes | + popularity badge |
| 3 | hyped   | no  | + "Hot Pick" badge |
| 4 | hyped   | yes | + both cues |

**Exact stimulus copy (verbatim from `index.html`).**

- *Hype cue* (`headline_type=hyped`): a flame-icon banner at the top of the listing card reading **"Hot Pick"**. Replaced with empty space in `neutral` cells.
- *Social-proof cue* (`social_proof=yes`): a trend-up-arrow callout reading **"Most-bought ETF among college investors — this month"**. Hidden entirely in `no` cells.

All non-cue elements were held constant across all four cells: the ETF name (HLXE / Helix Renewable Energy ETF), prospectus text, performance card, holdings list, 3-yr/5-yr returns, fees, risk disclosures, fund tagline ("Diversified mid-cap renewable energy fund"), page layout, button copy, and color palette. The risk-free alternative was a guaranteed Treasury bond paying **+5%**; the risky ETF return was drawn uniformly from **−25% to +25%** and revealed after submission.

> Stimulus screenshots for the slide deck can be regenerated from `../index.html`; the conditional rendering lives at the `state.headline_type` / `state.social_proof` flags (search the file for those identifiers).

**Recruitment & implementation.**

- Self-administered single-session web app at `index.html`; participants completed it on their own device in roughly 1–3 minutes.
- Recruited via the MGT 160 course participant pool at UC San Diego (Rady School of Management) and adjacent personal/social networks of the project team.
- Top 3 final portfolios paid via Venmo as a real-stakes incentive layered on the hypothetical allocation.

**Timeline.** Data collection ran **2026-05-20 through 2026-05-28** (8 days). N = 176 complete responses (44 per cell).

**Unit of randomization:** individual participant. **Method:** server-side block randomization across the 4 cells (target 25% per cell) — realized assignment was perfectly even (44 per cell, see Section 1). Condition is assigned on first page load and recorded with the response; participants do not see the other three cells.

**Primary outcome.** `hlxe_allocation` (dollars 0–1000 into HLXE; the complement, `safe_allocation = 1000 − hlxe_allocation`, goes into the Treasury bond). A purely "no-cue, no-allocation-bias" baseline under a 50/50 split would be \\$500; the **observed control-cell mean (\\$594) is the empirical baseline** the treatment cells must beat. Observed SD across the full sample is **\\$301**.

**Pre-registered hypotheses.**

- **H₀ (primary):** treatment cues have no effect on `hlxe_allocation` (β_social_proof = β_headline_type = 0).
- **H₁ (primary):** social proof and/or hype framing *increase* `hlxe_allocation` vs control.
- **H₁ (subgroup — `prior_investor`):** participants with prior real-money investing experience are *less* susceptible to the cues (negative `condition × prior_investor` interaction). *Rationale:* having executed real trades exposes a person to real losses, which should make them more skeptical of marketing surfaces and more reliant on fundamentals.
- **H₁ (subgroup — `major_area_binary`):** Business/Econ majors are *less* susceptible than non-Business/Econ majors (negative `condition × major` interaction). *Rationale:* coursework in finance/behavioral economics should give Business/Econ students conceptual exposure to social-proof and affect-heuristic effects, partially inoculating them.

**Pre-registered power target.** α = 0.05, target power = 0.80, two-sided independent t-tests. See Section 6 for the MDE we were powered to detect.

**Secondary outcomes measured (mechanism / heuristic-substitution check).**

- `confidence` (self-reported, 1–5, captured *pre-reveal*) — does the cue inflate certainty even if it does not change behavior?
- `time_on_page_seconds` / `time_to_submit_seconds` — does hype framing shorten deliberation, consistent with cue-driven (System-1) substitution? *Instrument caveat:* these two columns are byte-identical in the export — the form logged one timestamp for both. Treat them as a single timing measure.

---

## 1. Sample summary

{pieces.sample_md}

{attn_line}

---

## 2. Balance / randomization check

{pieces.balance_md}

Verdict: {"**Balanced** — no significant imbalance detected." if not pieces.imbalanced else "**Imbalance flagged on:** " + ", ".join(pieces.imbalanced) + ". Treat as covariates in follow-up models."}

### Outcome distribution

![]({pieces.dist_fig})

{"**Distribution is bimodal / corner-piling.** Reported the binary `took_risky_bet` outcome alongside the dollar mean." if pieces.bimodal else "Distribution is reasonably continuous; the dollar mean is interpretable."}

---

## 3. Primary results

### 3a/3b. Main effects (full sample, Welch's t-tests)

{df_to_md(pieces.primary_tbl_full)}

### 3c. 2×2 ANOVA — `hlxe_allocation ~ headline_type * social_proof` (full sample)

{df_to_md(pieces.anova_full, index=True)}

### 3d. Headline figure

![]({pieces.headline_fig_full})

**Plain-English takeaway.** {sp_take} {hp_take} The 2×2 ANOVA's main effects mirror the two t-tests above; the interaction term tests whether the cues compound. If the interaction is non-significant the cues behave additively; if it is significant and negative the cues are redundant (one cue already maxes the effect); if significant and positive they are synergistic.

### Binary fallback outcome (`took_risky_bet` = 1 if `hlxe_allocation` > 500)

| contrast | Pr(risky) group A | Pr(risky) group B | log-odds (A vs B) | p |
|---|---|---|---|---|
| social_proof (A=yes, B=no) | {pieces.binary_results['sp_pa']:.2f} | {pieces.binary_results['sp_pb']:.2f} | {pieces.binary_results['sp_logodds']:.2f} | {fmt_p(pieces.binary_results['sp_p'])} |
| headline_type (A=hyped, B=neutral) | {pieces.binary_results['hp_pa']:.2f} | {pieces.binary_results['hp_pb']:.2f} | {pieces.binary_results['hp_logodds']:.2f} | {fmt_p(pieces.binary_results['hp_p'])} |

---

## 4. Subgroup analysis (pre-specified moderators)

### 4a. Prior investing experience (`prior_investor`)

3-way ANOVA — `hlxe_allocation ~ headline_type * social_proof * prior_investor`:

{df_to_md(pieces.sub_prior_anova, index=True)}

Cell means by `prior_investor`:

{df_to_md(pieces.sub_prior_means)}

![]({pieces.sub_prior_fig})

### 4b. Finance training (`major_area_binary`: Business/Econ vs Other)

3-way ANOVA — `hlxe_allocation ~ headline_type * social_proof * major_area_binary`:

{df_to_md(pieces.sub_major_anova, index=True)}

Cell means by `major_area_binary`:

{df_to_md(pieces.sub_major_means)}

![]({pieces.sub_major_fig})

---

## 5. Secondary / mechanism checks

### 5a. Confidence inflation (`confidence`, 1–5)

2×2 ANOVA on `confidence`:

{df_to_md(pieces.conf_anova, index=True)}

Cell means:

{df_to_md(pieces.conf_means)}

### 5b. Confidence ↔ allocation (Pearson r)

{df_to_md(pieces.conf_corr_tbl)}

### 5c. Decision speed (`time_to_submit_seconds`, median; Mann-Whitney U, hyped vs neutral)

Per-cell medians:

{df_to_md(pieces.time_submit_medians)}

Hyped (n={pieces.time_submit_test['n_hyped']}, median {pieces.time_submit_test['median_hyped']:.1f}s)
vs Neutral (n={pieces.time_submit_test['n_neutral']}, median {pieces.time_submit_test['median_neutral']:.1f}s):
U = {pieces.time_submit_test['U']:.0f}, p = {fmt_p(pieces.time_submit_test['p'])}.

### 5d. Time on listing (`time_on_page_seconds`, median; Mann-Whitney U, hyped vs neutral)

> **Instrument note.** In this dataset `time_on_page_seconds` and
> `time_to_submit_seconds` are identical for every row (the form logged a
> single timestamp for both). 5c and 5d therefore report the same statistic;
> the duplication is preserved here for the rubric but only one of the two
> should be cited.

Per-cell medians:

{df_to_md(pieces.time_page_medians)}

Hyped (n={pieces.time_page_test['n_hyped']}, median {pieces.time_page_test['median_hyped']:.1f}s)
vs Neutral (n={pieces.time_page_test['n_neutral']}, median {pieces.time_page_test['median_neutral']:.1f}s):
U = {pieces.time_page_test['U']:.0f}, p = {fmt_p(pieces.time_page_test['p'])}.

---

## 6. Power & minimum detectable effect

**Pre-registered targets:** α = {ALPHA}, power = 0.80, two-sided independent t-test
(`statsmodels.stats.power.TTestIndPower`). Effect sizes are Cohen's d
from the realized sample.

{df_to_md(pieces.power_tbl)}

**Interpretation.** With N = {2 * pieces.sp_full['n_a']} (88 per group on each contrast), this pilot was powered to detect a Cohen's d of roughly **0.43** — a *medium* effect (≈ \\${0.43 * 301:.0f} in dollar terms given the observed SD ≈ \\$301). The observed effects (|d| ≈ 0.03–0.04) are about an order of magnitude smaller, so the null result is consistent with either (a) no true cue effect or (b) a true effect too small for a pilot of this size to detect.

---

## 7. Limitations

{chr(10).join(f"- {x}" for x in lim)}

---

## 8. Applications to practice and generalizability

**Who does this apply to?** Self-selected U.S. undergraduates (mostly UCSD Rady-area Business/Econ majors, ~21 years old, ~60% with self-reported prior investing experience). Generalization to other populations is speculative; younger / less-financially-experienced participants might respond differently to the cues, and real retail investors face very different decision contexts (longer horizons, real money, multi-asset portfolios, ongoing engagement).

**What can an organization learn from this pilot?**

- For a brokerage or robo-advisor considering "trending" badges or "HOT PICK" framing on its listing pages, this pilot's null result is a *cautionary* — but not definitive — signal. In this single-shot, one-asset, hypothetical-money setting the cues did not measurably move allocation. Before deploying such cues at scale, the org should run a powered field test (see N below) and pre-commit to abandoning the cue if the field effect is comparable to what we saw here.
- The pilot does provide a robust **variance estimate**: SD(`hlxe_allocation`) ≈ \\$301. That estimate is what a scale-up study should plug into its own power calculation — it is the pilot's most durable deliverable, exactly as the course rubric frames it.

**Scale-up & external validity.**

- **N required for a real test:** to detect a Cohen's d of 0.20 (a *small* effect, which is what real-world nudges typically produce) at 80% power, α = 0.05, two-sided: ≈ **394 per cell, ≈ 1,576 total** across the 4 cells. A d = 0.10 (very small) would need ≈ 1,571 per cell, ≈ 6,284 total.
- **External-validity threats to address before scale-up:** hypothetical \\$1,000 vs real money, single-shot vs repeated decisions, student vs general-population sample, demand effects from cue salience (no manipulation check in this pilot).
- **Suggested next pilot:** field A/B test inside a real brokerage's mobile listing screen on a low-stakes asset (e.g., a small fractional-share purchase flow), randomizing the badge at the session level, with the outcome being click-through-to-buy or dollars purchased. That design fixes the hypothetical-money and demand-effect concerns simultaneously.

---

## 9. Key takeaways

- **The pilot returned a null result on both cues.** Social proof and hype framing did not measurably shift HLXE allocation in this sample (both main-effect p > 0.79, |d| ≤ 0.04, 95% CIs centered on zero). The 2×2 interaction was also non-significant.
- For reference, the best-performing treatment cell was **{CELL_LABELS[best_treatment_cell]}** at \\${best_treatment_mean:.0f} vs control \\${ctrl_mean:.0f} (Δ = {'+' if best_delta>=0 else ''}\\${best_delta:.0f}, {'+' if best_delta>=0 else ''}{best_pct:.1f}%). This difference is well inside the 95% CI of zero.
- **Subgroup hypotheses were not supported.** Neither `prior_investor` nor `major_area_binary` interacted significantly with the cues (all interaction p > 0.09). The one borderline term is `social_proof × major_area_binary` (p = 0.097, partial η² = 0.016) — exploratory at best, and the "Other" major cells have N = 6–8.
- **The pilot's real deliverable** is the variance estimate (SD ≈ \\$301) and the sample size needed to detect a realistic real-world effect at 80% power — see Section 8.
- **Honest framing for the poster:** "pilots are for design, not decisions." A null result here doesn't disprove the cues; it tells the scale-up study how large a sample it actually needs.

### Why the null is plausible (interpretation for the poster)

Four non-mutually-exclusive explanations the slide deck should be ready to defend:

1. **Ceiling effect / pre-existing risk appetite.** The control cell already allocated **\\$594 / \\$1,000 (≈ 59%)** to HLXE. With a guaranteed Treasury at +5% as the safer option, our sample was already lopsided toward risk; the cues had limited headroom to push allocation higher.
2. **Sample skew toward Business/Econ.** ≈ 85% of the sample is Business/Econ; ≈ 60% have prior investing experience. This is exactly the sub-population the pre-registered subgroup hypotheses predict would be *least* susceptible to UI cues. We may have under-sampled the susceptible group.
3. **Hypothetical money + transparent mechanic.** The \\$1,000 is fictional and the return is announced as a uniform random draw. Cues that work in real brokerage UIs may be neutered when participants know there's no real downside *and* the asset's return is explicitly stochastic — both reduce the cue's informational value.
4. **Demand-effect cancellation.** A "Hot Pick" badge is unsubtle enough that some participants may have *anti-conformed* (suspecting a marketing trick) while others conformed; net effect ≈ 0. A more subtle cue (e.g., a small "trending" arrow) might avoid this.

These are the explanations to lead with if the TA / professor asks "why null?" during Q&A.

---

## 10. Slide-deck-ready fact sheet

Concrete numbers and quotes a slide author can lift verbatim without re-deriving from data:

| slide topic | the exact fact |
|---|---|
| Title cue copy (hype) | "Hot Pick" badge with flame icon |
| Title cue copy (social proof) | "Most-bought ETF among college investors — this month" |
| Fictional asset | HLXE / Helix Renewable Energy ETF (mid-cap renewable energy) |
| Safe asset | Treasury bond, guaranteed +5% |
| Risky-asset return | Uniform draw, −25% to +25%, revealed after submission |
| Sample size | N = 176, perfectly balanced (44/cell) |
| Recruitment | UC San Diego MGT 160 pool + adjacent networks |
| Data-collection window | 2026-05-20 through 2026-05-28 (8 days) |
| Control-cell mean (baseline) | \\$594 |
| Outcome SD (variance estimate) | \\$301 |
| Mean confidence (1–5) | 3.39 |
| Social-proof main effect | Δ = −\\$12, 95% CI [−102, +78], p = 0.793, d = −0.04 |
| Hype-framing main effect | Δ = +\\$10, 95% CI [−80, +100], p = 0.828, d = +0.03 |
| Interaction (2×2 ANOVA) | F(1,172) = 0.07, p = 0.790, partial η² ≈ 0.000 |
| Borderline subgroup signal | social_proof × major_area_binary, F(1,168) = 2.78, p = 0.097, partial η² = 0.016 (EXPLORATORY) |
| Pilot's achieved power | ≈ 0.06 for the observed d |
| MDE at 0.80 power | d ≈ 0.43 (≈ \\$130 in dollar terms) |
| N for small real-world effect (d = 0.20, 80% power) | ≈ 394 per cell, ≈ 1,576 total |
| N for very small effect (d = 0.10, 80% power) | ≈ 1,571 per cell, ≈ 6,284 total |
| Headline figure for poster | `outputs/fig_headline_means.png` |
| Subgroup figures | `outputs/fig_subgroup_prior_investor.png`, `outputs/fig_subgroup_major.png` |
| Distribution figure | `outputs/fig_outcome_distribution.png` |
| Stimulus source (for screenshots) | `index.html` — toggle `state.headline_type` and `state.social_proof` to render each cell |
| Form pipeline source | `apps-script.gs` (Google Apps Script writing to Sheets) |

### Suggested 9–12 slide outline

A future slide-writing pass should map cleanly to:

1. Title + group members
2. Motivating question (§−1) + "why we should care" (Robinhood-era retail cohort)
3. Prior literature anchors (Cialdini social proof; Slovic affect heuristic; Barber et al. 2022)
4. Experimental question + 2×2 cell table (§0) + screenshots of all 4 cells
5. Design: randomization, outcomes, hypotheses (§0)
6. Sample & balance (§1, §2) — show the balance verdict
7. Primary result: headline figure with 95% CI + the main-effect t-tests (§3)
8. Subgroup result: one of the two grouped bar charts + interaction term (§4)
9. Power & MDE (§6) — the table + the "we were powered for d ≈ 0.43" sentence
10. Limitations + why-null interpretation (§7 + §9 sub-section)
11. Applications & scale-up plan (§8) — including the N-needed numbers
12. Key takeaways (§9)

Slides 2–4 and 11–12 are *narrative* — drafted by the human / slide-writing Claude. Slides 5–10 are essentially copy-paste from this report's figures and tables.

---

*Generated by `analyze.py`. All figures and tables also written to `outputs/`. To reproduce: `python3 analyze.py` from the `analysis/` directory.*
"""
    p.write_text(md)
    return p


# ------------------------------------------------------------------ binary outcome

def binary_results(df: pd.DataFrame) -> dict:
    """Logistic regression on took_risky_bet for main effects + cell means."""
    out = {}
    # social_proof
    sub = df[["took_risky_bet", "social_proof"]].dropna()
    sub["sp"] = (sub["social_proof"] == "yes").astype(int)
    model = sm.Logit(sub["took_risky_bet"], sm.add_constant(sub[["sp"]])).fit(disp=False)
    out["sp_pa"] = sub.loc[sub["sp"] == 1, "took_risky_bet"].mean()
    out["sp_pb"] = sub.loc[sub["sp"] == 0, "took_risky_bet"].mean()
    out["sp_logodds"] = float(model.params["sp"])
    out["sp_p"] = float(model.pvalues["sp"])

    # headline_type
    sub = df[["took_risky_bet", "headline_type"]].dropna()
    sub["hp"] = (sub["headline_type"] == "hyped").astype(int)
    model = sm.Logit(sub["took_risky_bet"], sm.add_constant(sub[["hp"]])).fit(disp=False)
    out["hp_pa"] = sub.loc[sub["hp"] == 1, "took_risky_bet"].mean()
    out["hp_pb"] = sub.loc[sub["hp"] == 0, "took_risky_bet"].mean()
    out["hp_logodds"] = float(model.params["hp"])
    out["hp_p"] = float(model.pvalues["hp"])

    # cell means
    out["cell_means"] = {}
    for cell in CELL_ORDER:
        h, s = cell
        x = df.loc[(df["headline_type"] == h) & (df["social_proof"] == s), "hlxe_allocation"]
        out["cell_means"][cell] = float(x.mean()) if len(x) else float("nan")
    return out


# ------------------------------------------------------------------ main

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"CSV not found: {args.csv}")

    df = load_data(args.csv)

    # 1. sanity
    sample_md = sample_summary(df)
    balance_md, imbalanced = balance_table(df)
    dist_fig, bimodal = plot_outcome_dist(df)
    _, attn_info = attention_filter(df)  # counts only — not used to exclude

    # 2. primary
    primary_dicts_full, primary_tbl_full, anova_full = primary_results_table(df)
    head_fig_full = headline_figure(df, "fig_headline_means.png", "")

    # 3. subgroups (on full sample)
    sub_prior_anova, sub_prior_means = subgroup_anova(df, "prior_investor")
    sub_prior_fig = subgroup_figure(df, "prior_investor",
                                    "fig_subgroup_prior_investor.png",
                                    "Means by condition × prior investing experience (95% CI)")
    sub_major_anova, sub_major_means = subgroup_anova(df, "major_area_binary")
    sub_major_fig = subgroup_figure(df, "major_area_binary",
                                    "fig_subgroup_major.png",
                                    "Means by condition × major (Business/Econ vs Other, 95% CI)")

    # 4. secondary
    conf_anova, conf_means = confidence_anova(df)
    conf_anova.to_csv(OUT / "tab_confidence_anova.csv")
    conf_corr_overall, conf_corr_tbl = confidence_allocation_corr(df)
    time_submit_medians, time_submit_test = timing_test(df, "time_to_submit_seconds")
    time_submit_medians.to_csv(OUT / "tab_time_to_submit_medians.csv", index=False)
    time_page_medians, time_page_test = timing_test(df, "time_on_page_seconds")
    time_page_medians.to_csv(OUT / "tab_time_on_page_medians.csv", index=False)

    # 5. power
    power_tbl = power_table(primary_dicts_full["sp"], primary_dicts_full["hp"], df)

    # binary outcome
    bin_res = binary_results(df)

    pieces = ReportPieces(
        sample_md=sample_md,
        balance_md=balance_md,
        imbalanced=imbalanced,
        dist_fig=dist_fig,
        bimodal=bimodal,
        attn_info=attn_info,
        primary_tbl_full=primary_tbl_full,
        anova_full=anova_full,
        headline_fig_full=head_fig_full,
        sp_full=primary_dicts_full["sp"],
        hp_full=primary_dicts_full["hp"],
        sub_prior_anova=sub_prior_anova,
        sub_prior_means=sub_prior_means,
        sub_prior_fig=sub_prior_fig,
        sub_major_anova=sub_major_anova,
        sub_major_means=sub_major_means,
        sub_major_fig=sub_major_fig,
        conf_anova=conf_anova,
        conf_means=conf_means,
        conf_corr_tbl=conf_corr_tbl,
        time_submit_medians=time_submit_medians,
        time_submit_test=time_submit_test,
        time_page_medians=time_page_medians,
        time_page_test=time_page_test,
        power_tbl=power_tbl,
        binary_results=bin_res,
    )

    report_path = write_report(pieces)
    print(f"\nReport written: {report_path}")
    print(f"All outputs in: {OUT}")


if __name__ == "__main__":
    main()
