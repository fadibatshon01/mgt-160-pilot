"""
MGT 160 Pilot — OLS Regression with Demographic Controls
========================================================
DV: hlxe_allocation (0..1000, $ allocated to the risky HLXE ETF)
Treatments (dummies):
    hyped              = 1 if headline_type == "hyped"        (base: neutral)
    social_proof_yes   = 1 if social_proof == "yes"           (base: no)
    hyped_x_sp         = hyped * social_proof_yes             (interaction)
Demographic controls (dummies, baseline in parens):
    prior_investor_yes        (no)
    age                       (continuous)
    gender_*                  (man)
    year_*                    (freshman)
    major_*                   (business_econ)

SEs: HC1 robust (per Prof. Johnson's spec).
Sample: attention filter time_on_page in [10, 600].

Outputs (analysis/outputs/):
    fig_regression_coefs.png   forest plot of all coefficients (95% CI)
    tab_regression.csv         full coefficient table
    regression_report.md       written explanation
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import statsmodels.api as sm

HERE = Path(__file__).resolve().parent
CSV = HERE / "data" / "Pilot results.csv"
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)

ATTN_LOWER, ATTN_UPPER = 10, 600


def load() -> pd.DataFrame:
    df = pd.read_csv(CSV)
    mask = df["time_on_page_seconds"].between(ATTN_LOWER, ATTN_UPPER)
    return df.loc[mask].copy()


def build_design(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    x = pd.DataFrame(index=df.index)

    # Treatment dummies
    x["hyped"] = (df["headline_type"] == "hyped").astype(int)
    x["social_proof_yes"] = (df["social_proof"] == "yes").astype(int)
    x["hyped_x_sp"] = x["hyped"] * x["social_proof_yes"]

    # Demographic dummies (drop_first to avoid the dummy trap)
    x["prior_investor_yes"] = (df["prior_investor"] == "yes").astype(int)
    x["age"] = df["age"].astype(float)

    for col, base in [
        ("gender", "man"),
        ("year_in_school", "freshman"),
        ("major_area", "business_econ"),
    ]:
        dummies = pd.get_dummies(df[col], prefix=col, dtype=int)
        if f"{col}_{base}" in dummies.columns:
            dummies = dummies.drop(columns=[f"{col}_{base}"])
        x = pd.concat([x, dummies], axis=1)

    x = sm.add_constant(x, has_constant="add")
    y = df["hlxe_allocation"].astype(float)
    return x, y


def main() -> None:
    df = load()
    x, y = build_design(df)
    model = sm.OLS(y, x.astype(float)).fit(cov_type="HC1")

    # --- coefficient table ---
    ci = model.conf_int(alpha=0.05)
    ci.columns = ["ci_low", "ci_high"]
    table = pd.DataFrame({
        "coef": model.params,
        "std_err": model.bse,
        "t": model.tvalues,
        "p_value": model.pvalues,
        "ci_low": ci["ci_low"],
        "ci_high": ci["ci_high"],
    })
    table.to_csv(OUT / "tab_regression.csv", index_label="term")

    # --- plot just the 3 treatment effects (demographics are controls, not the story) ---
    treatment_terms = ["hyped", "social_proof_yes", "hyped_x_sp"]
    labels = ["Hyped headline", "Social proof (peer banner)", "Hyped × Social proof"]
    plot_df = table.loc[treatment_terms]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    y_pos = np.arange(len(plot_df))[::-1]  # first row on top
    errs = np.vstack([plot_df["coef"] - plot_df["ci_low"], plot_df["ci_high"] - plot_df["coef"]])
    colors = ["#d62728" if p < 0.05 else "#1f77b4" for p in plot_df["p_value"]]
    ax.errorbar(plot_df["coef"], y_pos, xerr=errs, fmt="none", ecolor="gray",
                elinewidth=1.5, capsize=4, zorder=2)
    for yi, (coef, color) in enumerate(zip(plot_df["coef"], colors)):
        ax.plot(coef, y_pos[yi], "o", color=color, markersize=9, zorder=3)
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Effect on HLXE allocation ($), 95% CI")
    ax.set_title("Treatment effects on risky-ETF allocation\n(OLS, HC1 robust SEs, controlling for demographics)")
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    plt.tight_layout()
    fig.savefig(OUT / "fig_regression_coefs.png", dpi=160)
    plt.close(fig)

    # --- written explanation ---
    r2 = model.rsquared
    r2a = model.rsquared_adj
    f_p = model.f_pvalue

    def fmt(term: str) -> str:
        r = table.loc[term]
        return (f"β = {r['coef']:+.2f}, SE = {r['std_err']:.2f}, "
                f"95% CI [{r['ci_low']:+.2f}, {r['ci_high']:+.2f}], p = {r['p_value']:.3f}")

    md = []
    md.append("# OLS Regression: Treatment Effects on HLXE Allocation\n")
    md.append(f"**DV:** HLXE allocation ($, 0–1000)  ")
    md.append(f"**Model:** treatment dummies + demographic controls, HC1 robust SEs  ")
    md.append(f"**Controls included** (not shown): `prior_investor`, `age`, `gender`, `year_in_school`, `major_area` — see `tab_regression.csv` for the full table.\n")
    md.append("## Treatment effects\n")
    md.append(f"- **Hyped headline** (vs. neutral): {fmt('hyped')}")
    md.append(f"- **Social proof banner** (vs. none): {fmt('social_proof_yes')}")
    md.append(f"- **Hyped × Social proof** (interaction): {fmt('hyped_x_sp')}\n")
    md.append("## Fit\n")
    md.append(f"R² = {r2:.3f} · Adjusted R² = {r2a:.3f} · F-test p = {f_p:.3f}\n")
    md.append("## Interpretation\n")
    coef_h = table.loc["hyped", "coef"]
    coef_sp = table.loc["social_proof_yes", "coef"]
    coef_int = table.loc["hyped_x_sp", "coef"]
    md.append(
        f"Holding demographics constant, switching from a *neutral* to a *hyped* headline "
        f"(with no peer banner) is associated with a {coef_h:+.1f}-dollar change in HLXE allocation; "
        f"adding the peer-investor banner (under a neutral headline) is associated with a "
        f"{coef_sp:+.1f}-dollar change. The interaction term ({coef_int:+.1f}) tells us whether the "
        f"two manipulations combine super-additively (positive) or cancel (negative). "
        f"Statistical significance is read off the 95% CIs above: any CI that does **not** cross zero "
        f"is significant at α = 0.05 (those rows are colored red in `fig_regression_coefs.png`)."
    )
    md.append(
        f"\n\nThe overall model F-test (p = {f_p:.3f}) and R² = {r2:.3f} indicate "
        f"{'a' if f_p < 0.05 else 'no'} jointly significant relationship between the full predictor "
        f"set and HLXE allocation. With a clumpy bounded DV (mass at $0/$500/$1000), "
        f"these estimates are noisy — consistent with the pilot's role of variance estimation rather "
        f"than confirmation (see power table in `report.md`)."
    )
    (OUT / "regression_report.md").write_text("\n".join(md) + "\n")

    print(f"OLS fit.  R²={r2:.3f}  F p={f_p:.3f}")
    print(f"  hyped:            {fmt('hyped')}")
    print(f"  social_proof_yes: {fmt('social_proof_yes')}")
    print(f"  hyped_x_sp:       {fmt('hyped_x_sp')}")
    print(f"\nWrote:")
    print(f"  {OUT/'fig_regression_coefs.png'}")
    print(f"  {OUT/'tab_regression.csv'}")
    print(f"  {OUT/'regression_report.md'}")


if __name__ == "__main__":
    main()
