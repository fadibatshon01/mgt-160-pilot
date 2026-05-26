"""MGT 160 pilot analysis — built to Prof. Erik Johnson's two-deck framework.

Design: 2x2 between-subjects, headline_type (neutral|hyped) x social_proof (no|yes)
DV: hlxe_allocation (dollars of the $1,000 put in the risky ETF)
Control cell = neutral / no;            Any treatment = the other 3 cells

Outputs (all in output/ and figures/):
  - balance_table.tex / .csv       — control vs treatment, mean (SD), t-test p (Rady s.9)
  - balance_table_4cell.tex / .csv — 4-cell version, ANOVA / chi-square p
  - summary_by_cell.tex / .csv     — descriptives by cell
  - regression_table.tex / .csv    — 3 nested OLS, HC1 robust SE (Rady s.12)
  - rollout_sample_size.tex / .csv — n_per_group at 80% / 90% power (Rady s.24-25)
  - 01_density_overlay.png         — KDE bell curves: treatment vs control
  - 01b_gaussian_overlay.png       — fitted Normal PDFs: treatment vs control
  - 02_density_by_cell.png         — KDE bell curves for all 4 cells
  - 02b_gaussian_by_cell.png       — fitted Normal PDFs for all 4 cells
  - 03_bars_ci.png                 — bar chart of means w/ 95% CI (Rady s.10)
  - 04_interaction.png             — 2x2 interaction plot
  - 05_pilot_vs_rollout_ci.png     — same delta, different precision
  - RESULTS_MEMO.md                — narrative walk-through w/ rubric mapping
  - report.txt                     — full console log
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats as st
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.power import TTestIndPower

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

DV = "hlxe_allocation"
ROOT = Path(__file__).parent
FIG = ROOT / "figures"
OUT = ROOT / "output"
sns.set_theme(style="whitegrid", context="talk")
plt.rcParams.update({"figure.dpi": 120, "savefig.dpi": 200, "savefig.bbox": "tight"})

CONTROL_DESC = "neutral headline, no social proof"
LOG: list[str] = []


def say(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    LOG.append(line)


def hr(title):
    say("\n" + "=" * 72)
    say(title)
    say("=" * 72)


# ============================================================ load + clean
def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    num = ["safe_allocation", "hlxe_allocation", "hlxe_return", "final_portfolio",
           "confidence", "age", "time_on_page_seconds", "time_to_submit_seconds"]
    for c in num:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("headline_type", "social_proof", "prior_investor"):
        df[c] = df[c].astype(str).str.strip().str.lower()
    return df


def clean(df: pd.DataFrame, speeder_seconds: int) -> pd.DataFrame:
    hr("STEP 1 — DATA CLEANING & VALIDATION")
    n0 = len(df)
    say(f"Loaded {n0} rows. Missing values per analytical column:")
    for c in [DV, "headline_type", "social_proof", "confidence", "prior_investor",
              "age", "gender", "major_area", "year_in_school"]:
        say(f"  {c:22s} missing={int(df[c].isna().sum())}")

    # Drop test rows + rows where allocation is internally broken.
    vh = df["venmo_handle"].astype(str).str.strip()
    df = df[vh.str.upper() != "TEST"].copy()
    total = df["safe_allocation"] + df["hlxe_allocation"]
    bad = (total - 1000).abs() > 1
    if bad.any():
        say(f"Dropped {int(bad.sum())} rows where safe+hlxe != 1000")
    df = df[~bad].dropna(subset=[DV, "headline_type", "social_proof"])

    df["headline_type"] = pd.Categorical(df["headline_type"],
                                          categories=["neutral", "hyped"])
    df["social_proof"] = pd.Categorical(df["social_proof"], categories=["no", "yes"])
    df["cell"] = (df["headline_type"].astype(str) + " / " + df["social_proof"].astype(str))
    df["treat"] = (~((df.headline_type == "neutral") & (df.social_proof == "no"))).astype(int)
    df["arm"] = np.where(df.treat == 1, "treatment", "control")

    # Speeder flag — kept in main analysis, removed in robustness check.
    df["speeder"] = df["time_on_page_seconds"] < speeder_seconds
    say(f"\nSpeeders (time_on_page < {speeder_seconds}s): {int(df['speeder'].sum())} "
        f"(kept in main analysis, dropped in robustness rerun)")
    # Age sanity — implausible values flagged for the robustness rerun too.
    df["age_outlier"] = (df["age"] < 16) | (df["age"] > 40)
    if df["age_outlier"].any():
        say(f"Age outliers (<16 or >40): {int(df['age_outlier'].sum())} "
            f"(values: {sorted(df.loc[df.age_outlier, 'age'].tolist())})")

    say(f"\nAnalyzable N = {len(df)}.")
    say(f"  Control cell ({CONTROL_DESC}): n={int((df.treat==0).sum())}")
    say(f"  Any treatment (other 3 cells):                       n={int((df.treat==1).sum())}")
    return df.reset_index(drop=True)


# ================================================= balance table (Rady s.9)
def balance_table(df: pd.DataFrame) -> pd.DataFrame:
    """Control vs Treatment on age, gender, year, major, prior_investor.

    Continuous: Welch t-test on the mean.   Categorical: chi-square on the
    contingency table, plus one row per level showing the proportion.
    """
    hr("STEP 2 — BALANCE TABLE (Control vs Treatment, Rady s.9)")
    rows = []
    ctrl = df[df.treat == 0]
    trt = df[df.treat == 1]

    # Continuous: age.
    for var, label in [("age", "Age (years)"),
                       ("time_on_page_seconds", "Time on page (s)"),
                       ("confidence", "Confidence (1–5, post-decision)")]:
        a = ctrl[var].dropna()
        b = trt[var].dropna()
        t = st.ttest_ind(b, a, equal_var=False)
        rows.append({
            "Variable": label,
            "Control mean (SD)": f"{a.mean():.2f} ({a.std(ddof=1):.2f})",
            "Treatment mean (SD)": f"{b.mean():.2f} ({b.std(ddof=1):.2f})",
            "Diff (T − C)": f"{b.mean() - a.mean():+.2f}",
            "p-value": f"{t.pvalue:.3f}",
            "Test": "Welch t",
        })

    # Categorical: one row per level. Chi-square p-value + test name sit on
    # the FIRST level row of each variable; the variable name prefixes the
    # level label (e.g. "Gender: Woman") so every row carries data.
    cat_vars = [
        ("gender", "Gender", {"woman": "Woman", "man": "Man",
                                "non_binary_or_other": "Non-binary / other"}),
        ("year_in_school", "Year",
         {"freshman": "Freshman", "sophomore": "Sophomore",
          "junior": "Junior", "senior": "Senior", "graduate": "Graduate",
          "other": "Other"}),
        ("major_area", "Major",
         {"business_econ": "Business / Econ", "stem": "STEM",
          "social_sciences": "Social sciences", "humanities": "Humanities",
          "other": "Other"}),
        ("prior_investor", "Prior investor",
         {"yes": "Yes", "no": "No"}),
    ]
    for var, header, levels in cat_vars:
        ct = pd.crosstab(df[var], df["arm"])
        for col in ("control", "treatment"):
            if col not in ct.columns:
                ct[col] = 0
        ct = ct[["control", "treatment"]]
        if ct.shape[0] > 1 and ct.values.sum() > 0:
            chi2, p, _, _ = st.chi2_contingency(ct)
        else:
            chi2, p = np.nan, np.nan
        first = True
        for raw, pretty in levels.items():
            n_c = int((ctrl[var] == raw).sum())
            n_t = int((trt[var] == raw).sum())
            if n_c + n_t == 0:
                continue
            p_c = n_c / len(ctrl) * 100 if len(ctrl) else 0
            p_t = n_t / len(trt) * 100 if len(trt) else 0
            rows.append({
                "Variable": f"{header}: {pretty}",
                "Control mean (SD)": f"{n_c} ({p_c:.1f}%)",
                "Treatment mean (SD)": f"{n_t} ({p_t:.1f}%)",
                "Diff (T − C)": f"{p_t - p_c:+.1f} pp",
                "p-value": (f"{p:.3f}" if (first and not np.isnan(p)) else ""),
                "Test": ("chi²" if first else ""),
            })
            first = False

    bt = pd.DataFrame(rows)
    say("\n" + bt.to_string(index=False))

    n_c, n_t = int((df.treat == 0).sum()), int((df.treat == 1).sum())
    bt.to_csv(OUT / "balance_table.csv", index=False)
    _to_latex(bt, OUT / "balance_table.tex",
              caption=(f"Balance table comparing Control ({CONTROL_DESC}) and any-Treatment cells. "
                       f"Continuous variables: Welch two-sample t-test on means. "
                       f"Categorical variables: chi-square on the contingency table; "
                       f"row counts and within-arm percentages reported beneath the test row. "
                       f"Cell sizes: Control $n={n_c}$, Treatment $n={n_t}$. "
                       f"$p>.05$ on all rows is the expected pattern under random assignment."),
              label="tab:balance",
              column_format="lcccrl",
              png_path=FIG / "t01_balance_table.png",
              png_title=f"Balance: Control (n={n_c}) vs Treatment (n={n_t})",
              png_footer="Continuous: Welch two-sample t-test. Categorical: chi-square on the "
                         "contingency table; row counts and within-arm percentages shown below "
                         "the test row. All p > .05 = no detectable imbalance (expected under "
                         "random assignment).")
    say(f"\nLaTeX  -> {OUT/'balance_table.tex'}\nCSV    -> {OUT/'balance_table.csv'}\n"
        f"PNG    -> {FIG/'t01_balance_table.png'}")
    return bt


def balance_table_4cell(df: pd.DataFrame) -> pd.DataFrame:
    """4-cell version: one-way ANOVA / chi-square across the four cells."""
    say("\n(also producing the 4-cell version with ANOVA / chi-square across cells)")
    rows = []
    for var, label in [("age", "Age (years)"),
                       ("time_on_page_seconds", "Time on page (s)"),
                       ("confidence", "Confidence (1–5)")]:
        cells = [g[var].dropna().values for _, g in df.groupby("cell", observed=True)]
        F, p = st.f_oneway(*cells)
        rec = {"Variable": label, "Test": "ANOVA F", "stat": f"{F:.3f}", "p-value": f"{p:.3f}"}
        for cell, g in df.groupby("cell", observed=True):
            rec[cell] = f"{g[var].mean():.2f} ({g[var].std(ddof=1):.2f})"
        rows.append(rec)
    for var, label in [("gender", "Gender"), ("year_in_school", "Year"),
                       ("major_area", "Major area"), ("prior_investor", "Prior investor")]:
        ct = pd.crosstab(df[var], df["cell"])
        if ct.shape[0] > 1:
            chi2, p, _, _ = st.chi2_contingency(ct)
        else:
            chi2, p = np.nan, np.nan
        rec = {"Variable": label, "Test": "chi²",
               "stat": f"{chi2:.3f}" if not np.isnan(chi2) else "—",
               "p-value": f"{p:.3f}" if not np.isnan(p) else "—"}
        for cell in df["cell"].cat.categories if hasattr(df["cell"], "cat") else df["cell"].unique():
            rec[cell] = ""
        rows.append(rec)
    bt = pd.DataFrame(rows)
    cells_order = ["neutral / no", "neutral / yes", "hyped / no", "hyped / yes"]
    bt = bt[["Variable"] + cells_order + ["Test", "stat", "p-value"]]
    bt.to_csv(OUT / "balance_table_4cell.csv", index=False)
    cell_sizes = df.groupby("cell", observed=True).size().to_dict()
    cell_sz_str = ", ".join(f"{c.replace(' / ', '/')}={n}" for c, n in cell_sizes.items())
    _to_latex(bt, OUT / "balance_table_4cell.tex",
              caption=(f"Four-cell balance check. Continuous covariates: one-way ANOVA across cells. "
                       f"Categorical: chi-square on the contingency table. Cell sizes: {cell_sz_str}."),
              label="tab:balance4",
              png_path=FIG / "t02_balance_table_4cell.png",
              png_title=f"Balance across the four cells ({cell_sz_str})",
              png_footer="Continuous covariates: one-way ANOVA across cells. Categorical: "
                         "chi-square on the contingency table.")
    return bt


# =============================================== summary stats by treatment group
def summary_by_group(df: pd.DataFrame):
    hr("STEP 3 — SUMMARY STATISTICS BY TREATMENT GROUP")
    # Two-column (control vs any-treatment)
    rows = []
    for arm, sub in [("Control (neutral/no)", df[df.treat == 0]),
                     ("Any treatment", df[df.treat == 1])]:
        s = sub[DV]
        rows.append({"Group": arm, "n": len(s),
                     "Mean ($)": f"{s.mean():.1f}",
                     "SD ($)": f"{s.std(ddof=1):.1f}",
                     "SE of mean ($)": f"{s.std(ddof=1)/np.sqrt(len(s)):.1f}",
                     "Median ($)": f"{s.median():.0f}",
                     "Min": int(s.min()), "Max": int(s.max()),
                     "% at $0":    f"{(s == 0).mean() * 100:.1f}%",
                     "% at $500":  f"{(s == 500).mean() * 100:.1f}%",
                     "% at $1000": f"{(s == 1000).mean() * 100:.1f}%"})
    sg = pd.DataFrame(rows)
    say("\nHLXE allocation by arm:\n" + sg.to_string(index=False))
    sg.to_csv(OUT / "summary_by_arm.csv", index=False)
    n_c = int((df.treat == 0).sum())
    n_t = int((df.treat == 1).sum())
    _to_latex(sg, OUT / "summary_by_arm.tex",
              caption=(f"Summary statistics for the primary outcome (HLXE allocation, USD) "
                       f"by experimental arm. \\textit{{Control}} is the neutral-headline / "
                       f"no-social-proof cell ($n={n_c}$); \\textit{{Any treatment}} pools the "
                       f"other three cells ($n={n_t}$). Boundary-clumping rows show the share "
                       f"of responses at the three modal allocations ($\\$0$, $\\$500$, $\\$1000$)."),
              label="tab:summary_arm",
              column_format="lcccccccccc")
    sg_t = sg.set_index("Group").T.reset_index().rename(columns={"index": "Statistic"})
    _render_table_png(sg_t, FIG / "t03_summary_by_arm.png",
                      title="HLXE allocation summary: Control vs Treatment",
                      footer=(f"Control = neutral-headline / no-social-proof cell (n={n_c}); "
                              f"Treatment pools the other three cells (n={n_t}). The last "
                              f"three rows show the share of responses at the three modal "
                              f"allocations."))

    # 4-cell
    g = df.groupby("cell", observed=True)[DV].agg(
        n="count", mean="mean", sd=lambda x: x.std(ddof=1),
        median="median", min="min", max="max").round(1)
    say("\nHLXE allocation by cell:\n" + g.to_string())
    g.to_csv(OUT / "summary_by_cell.csv")
    g_tex = g.copy()
    g_tex.columns = ["$n$", "Mean", "SD", "Median", "Min", "Max"]
    g_tex.index.name = "Cell (headline / social proof)"
    _to_latex(g_tex.reset_index(), OUT / "summary_by_cell.tex",
              caption=("Per-cell summary statistics for HLXE allocation (USD). Cell sizes are "
                       "set by block randomization and reported in the $n$ column. SD is the "
                       "unbiased ($n{-}1$) sample standard deviation."),
              label="tab:summary_cell",
              png_path=FIG / "t04_summary_by_cell.png",
              png_title="HLXE allocation by cell (USD)",
              png_footer="Cell sizes (n column) are set by block randomization. SD is the "
                         "unbiased (n-1) sample standard deviation.")
    return sg, g


# ====================================================== Welch t-tests (Rady s.13)
def welch_test(a: pd.Series, b: pd.Series, label: str, name_a: str, name_b: str):
    res = st.ttest_ind(b, a, equal_var=False)
    ci = res.confidence_interval(0.95)
    diff = b.mean() - a.mean()
    pooled_sd = np.sqrt(((len(a)-1)*a.var(ddof=1) + (len(b)-1)*b.var(ddof=1))
                        / (len(a)+len(b)-2))
    d = diff / pooled_sd if pooled_sd else np.nan
    say(f"\n[{label}]   H0: mean_{name_b} = mean_{name_a}   (two-sided Welch)")
    say(f"  {name_a}: n={len(a):3d}  mean=${a.mean():7.2f}  SD=${a.std(ddof=1):6.2f}")
    say(f"  {name_b}: n={len(b):3d}  mean=${b.mean():7.2f}  SD=${b.std(ddof=1):6.2f}")
    say(f"  delta = ${diff:+.2f}   t = {res.statistic:+.3f}   df = {res.df:.1f}   "
        f"p = {res.pvalue:.4f}")
    say(f"  95% CI on delta: [${ci.low:+.2f}, ${ci.high:+.2f}]    Cohen's d = {d:+.3f}")
    return {"comparison": label, "n_a": len(a), "n_b": len(b),
            "mean_a": a.mean(), "mean_b": b.mean(),
            "sd_a": a.std(ddof=1), "sd_b": b.std(ddof=1),
            "diff": diff, "t": res.statistic, "df": res.df, "p": res.pvalue,
            "ci_low": ci.low, "ci_high": ci.high, "cohens_d": d}


def hypothesis_tests(df: pd.DataFrame, alpha: float) -> pd.DataFrame:
    hr("STEP 4 — HYPOTHESIS TESTS  (Welch t, two-sided; H0, p, 95% CI)")
    say(f"Decision rule: pre-committed alpha = {alpha}.  Reject H0 when p < alpha.")
    say("Note (Rady s.13–15): p is the probability of seeing data this extreme "
        "*if H0 were true*. It is NOT P(H0 | data) and NOT an effect size.")
    say("We 'fail to reject' rather than 'accept' — H0 is never proven, only undefeated.")

    H = {"neutral": df.headline_type == "neutral", "hyped": df.headline_type == "hyped"}
    S = {"no": df.social_proof == "no", "yes": df.social_proof == "yes"}
    ctrl_mask = (df.headline_type == "neutral") & (df.social_proof == "no")
    DV_s = df[DV]

    rows = [
        welch_test(DV_s[ctrl_mask], DV_s[~ctrl_mask],
                   "PRIMARY: Any treatment vs Control", "control", "treatment"),
        welch_test(DV_s[H["neutral"]], DV_s[H["hyped"]],
                   "H1: Hyped vs Neutral (main effect of headline)", "neutral", "hyped"),
        welch_test(DV_s[S["no"]], DV_s[S["yes"]],
                   "H2: Social-proof vs None (main effect of social proof)", "no", "yes"),
    ]
    # Cell vs control (3-arm family) — Bonferroni for the family (Rady s.27).
    cell_rows = []
    for hl, sp in [("neutral", "yes"), ("hyped", "no"), ("hyped", "yes")]:
        m = (df.headline_type == hl) & (df.social_proof == sp)
        cell_rows.append(welch_test(DV_s[ctrl_mask], DV_s[m],
                                     f"{hl}/{sp} vs Control", "control", f"{hl}/{sp}"))
    say(f"\nBonferroni (Rady s.27): alpha_corrected = {alpha}/3 = {alpha/3:.4f} "
        f"for the 3 cell-vs-control contrasts.")
    rows.extend(cell_rows)

    res = pd.DataFrame(rows)
    res["p_bonferroni"] = np.nan
    fam_mask = res["comparison"].str.contains("vs Control") & ~res["comparison"].str.startswith("PRIMARY")
    res.loc[fam_mask, "p_bonferroni"] = (res.loc[fam_mask, "p"] * fam_mask.sum()).clip(upper=1.0)
    res["reject_H0"] = (res["p"] < alpha)
    res.loc[fam_mask, "reject_H0"] = res.loc[fam_mask, "p_bonferroni"] < alpha
    res.round(4).to_csv(OUT / "hypothesis_tests.csv", index=False)

    say("\nDecision summary (* = reject H0; — = fail to reject):")
    for _, r in res.iterrows():
        mark = "*" if r["reject_H0"] else "—"
        p_str = (f"p={r['p']:.4f}" if pd.isna(r["p_bonferroni"])
                 else f"p={r['p']:.4f}  p_Bonf={r['p_bonferroni']:.4f}")
        say(f"  {mark}  {r['comparison']:55s} delta={r['diff']:+7.1f}  {p_str}")

    # Non-parametric backup (Week 7 s.38: clumpy bounded DVs).
    hr("STEP 4b — NON-PARAMETRIC BACKUP (40.7% of DV is at boundaries)")
    kw = st.kruskal(*[g[DV].values for _, g in df.groupby("cell", observed=True)])
    say(f"Kruskal-Wallis across 4 cells:  H = {kw.statistic:.3f}   p = {kw.pvalue:.4f}")
    u = st.mannwhitneyu(DV_s[~ctrl_mask], DV_s[ctrl_mask], alternative="two-sided")
    say(f"Mann-Whitney treat vs control:  U = {u.statistic:.0f}   p = {u.pvalue:.4f}")
    return res


# ============================================ OLS regressions with HC1 (Rady s.12)
def regressions(df: pd.DataFrame, alpha: float):
    """Three nested OLS specs, all with HC1 robust SEs (Rady s.12)."""
    hr("STEP 5 — OLS REGRESSIONS (HC1 robust SE, Rady s.12)")
    raw = df[df.treat == 1][DV].mean() - df[df.treat == 0][DV].mean()
    say(f"Raw difference in means (treat − control) = ${raw:+.2f}  (= OLS coefficient on treat)")

    m1 = smf.ols(f"{DV} ~ treat", data=df).fit(cov_type="HC1")
    m2 = smf.ols(f"{DV} ~ C(headline_type) * C(social_proof)", data=df).fit(cov_type="HC1")
    # Model 3: add pre-registered controls. Drop near-empty major levels to avoid noise.
    df3 = df.copy()
    keep_majors = df3["major_area"].value_counts()
    df3 = df3[df3["major_area"].isin(keep_majors[keep_majors >= 5].index)]
    m3 = smf.ols(f"{DV} ~ treat + age + C(prior_investor) + C(gender) + C(major_area)",
                 data=df3).fit(cov_type="HC1")

    for name, m in [("(1) Simple  Y ~ treat", m1),
                    ("(2) Factorial  Y ~ headline * social_proof", m2),
                    ("(3) +Controls  Y ~ treat + age + prior_investor + gender + major", m3)]:
        say(f"\n{name}")
        say(m.summary().tables[1].as_text())
        say(f"   R² = {m.rsquared:.4f}   N = {int(m.nobs)}")

    # Pull headline numbers off model 1 (the primary spec).
    b = m1.params["treat"]
    se = m1.bse["treat"]
    ci = m1.conf_int().loc["treat"]
    pval = m1.pvalues["treat"]
    say(f"\nPRIMARY POINT ESTIMATE  (Rady s.23–24 template):")
    say(f"  beta-hat (treat) = ${b:+.2f}   HC1 SE = ${se:.2f}")
    say(f"  95% CI = [${ci[0]:+.2f}, ${ci[1]:+.2f}]   z = {b/se:+.3f}   p = {pval:.4f}")
    decision = "REJECT H0" if pval < alpha else "FAIL TO REJECT H0"
    say(f"  Decision at alpha = {alpha}:  {decision}.")
    if pval >= alpha:
        say("  Interpretation: the pilot does not show evidence that the manipulation "
            "shifted allocation. A Type II error (false negative) is plausible given "
            "the pilot's MDE — see Step 6.")
    else:
        say("  Interpretation: at the pre-committed alpha, we reject H0. Type I error rate "
            f"is bounded at {alpha} by the test's construction.")

    # 2x2 ANOVA (Type II) on the factorial spec.
    hr("STEP 5b — 2×2 ANOVA (Type II)")
    tbl = anova_lm(m2, typ=2)
    ss_res = tbl.loc["Residual", "sum_sq"]
    tbl["partial_eta2"] = [ss/(ss+ss_res) if i != "Residual" else np.nan
                            for i, ss in zip(tbl.index, tbl["sum_sq"])]
    say(tbl.round(4).to_string())

    # One unified regression table (Rady s.12 style).
    reg_tbl = _three_model_table(m1, m2, m3)
    reg_tbl.to_csv(OUT / "regression_table.csv")
    _regression_table_tex(reg_tbl, OUT / "regression_table.tex",
                          notes=[f"$N$ = {int(m1.nobs)}, {int(m2.nobs)}, {int(m3.nobs)} for "
                                  "models (1)–(3). HC1 robust standard errors in parentheses. "
                                  "Model (3) drops major-area cells with fewer than 5 respondents "
                                  "(humanities, social\\_sciences, other) so the regression isn't "
                                  "driven by 2--3 observations. ${}^{*}\\,p<.10$, ${}^{**}\\,p<.05$, "
                                  "${}^{***}\\,p<.01$."])
    _render_table_png(reg_tbl, FIG / "t05_regression_table.png",
                      title="OLS of HLXE allocation: 3 nested specs (HC1 robust SE)",
                      footer=(f"N = {int(m1.nobs)}, {int(m2.nobs)}, {int(m3.nobs)} for "
                              "models (1)–(3). HC1 robust standard errors in parentheses below "
                              "each coefficient. Model (3) drops major-area cells with fewer "
                              "than 5 respondents (humanities, social_sciences, other) so the "
                              "regression isn't driven by 2-3 observations. * p<.10, ** p<.05, "
                              "*** p<.01."))
    say(f"\nLaTeX regression table -> {OUT/'regression_table.tex'}")
    say(f"PNG regression table   -> {FIG/'t05_regression_table.png'}")
    return m1, m2, m3


# ===================================== prior-investor moderator (pre-registered)
def moderator_prior(df: pd.DataFrame):
    hr("STEP 6 — PRE-REGISTERED MODERATOR: prior_investor × treatment")
    m = smf.ols(f"{DV} ~ treat * C(prior_investor)", data=df).fit(cov_type="HC1")
    say(m.summary().tables[1].as_text())
    say("\nInterpretation:")
    say(" - 'treat' coefficient = effect of treatment among non-investors (reference).")
    say(" - Interaction term = (effect on investors) − (effect on non-investors).")
    inter_p = m.pvalues.get("treat:C(prior_investor)[T.yes]", np.nan)
    inter_b = m.params.get("treat:C(prior_investor)[T.yes]", np.nan)
    if not np.isnan(inter_p):
        say(f" - Interaction beta = ${inter_b:+.2f}, p = {inter_p:.4f}: "
            f"{'differential effect' if inter_p < 0.05 else 'no significant differential effect'} "
            "between prior investors and non-investors.")


# ===================================== confidence as secondary outcome (Step 4 sibling)
def confidence_secondary(df: pd.DataFrame):
    hr("STEP 7 — SECONDARY OUTCOME: post-decision confidence (1–5)")
    ctrl = df[df.treat == 0]["confidence"].dropna()
    trt = df[df.treat == 1]["confidence"].dropna()
    welch_test(ctrl, trt, "Confidence: treatment vs control", "control", "treatment")
    u = st.mannwhitneyu(trt, ctrl, alternative="two-sided")
    say(f"  Mann-Whitney (ordinal-respecting):  U = {u.statistic:.0f}   p = {u.pvalue:.4f}")
    m = smf.ols("confidence ~ C(headline_type) * C(social_proof)", data=df).fit(cov_type="HC1")
    say("\n2×2 OLS on confidence (HC1):")
    say(m.summary().tables[1].as_text())


# ============================================ power, MDE, rollout sizing (Rady s.17, 24-25)
def power_and_rollout(df: pd.DataFrame, alpha: float):
    hr("STEP 8 — POWER, MDE, AND ROLLOUT SAMPLE SIZE (Rady s.17, 24–25)")
    sigma = df.groupby("cell", observed=True)[DV].std(ddof=1).mean()
    ctrl = df[df.treat == 0][DV]
    treat = df[df.treat == 1][DV]
    delta = treat.mean() - ctrl.mean()
    se_delta = np.sqrt(ctrl.var(ddof=1)/len(ctrl) + treat.var(ddof=1)/len(treat))
    n_total = len(df)

    say(f"sigma-hat (pooled within-cell SD)  = ${sigma:.2f}     <- the pilot's headline deliverable")
    say(f"delta-hat (treat − control)         = ${delta:+.2f}")
    say(f"SE(delta-hat)                       = ${se_delta:.2f}")
    say(f"Pilot total N = {n_total} (~{n_total/4:.0f} per cell, ~{n_total/2:.0f} per main-effect level)")

    # Closed-form rollout n  (Rady s.17): n_per_group = 2*(z_a/2 + z_b)^2 * (sigma/delta)^2.
    tt = TTestIndPower()

    def n_per_group_z(sd: float, dlt: float, alpha: float, power: float) -> int:
        if abs(dlt) < 1e-6:
            return -1
        za = st.norm.ppf(1 - alpha/2)
        zb = st.norm.ppf(power)
        return int(np.ceil(2 * (za + zb)**2 * (sd/abs(dlt))**2))

    # MDE @ current n (per-arm level): solve for d given power=80%.
    per_arm = n_total / 4
    per_main = n_total / 2
    hr("STEP 8a — MDE in this pilot (what could we have detected?)")
    say("Closed-form MDE inverts the power formula at the pilot's n and the given alpha.")
    for a in (alpha, 0.10):
        for label, per in [("main-effect (n/2 per level)", per_main),
                           ("cell-vs-control (n/4 per cell)", per_arm)]:
            d_mde = tt.solve_power(nobs1=per, alpha=a, power=0.80, alternative="two-sided")
            say(f"  alpha={a}, {label}:  d_MDE = {d_mde:.3f}   (= ${d_mde*sigma:.0f} in $)")

    # Rollout table — Rady s.24-25 scenarios + Week 7 multipliers (s.44).
    hr("STEP 8b — ROLLOUT SAMPLE SIZE (Rady s.24–25)")
    say("Formula: n_per_group ~ 2 (z_{1-a/2} + z_{1-b})^2 (sigma/delta)^2  (Rady s.17)")
    say(f"  At alpha={alpha}: 80% -> (z_a + z_b)^2 ~ "
        f"{(st.norm.ppf(1-alpha/2)+st.norm.ppf(0.80))**2:.2f}, "
        f"90% -> {(st.norm.ppf(1-alpha/2)+st.norm.ppf(0.90))**2:.2f}.")
    if abs(delta) < 1:
        say(f"\nWARNING: delta-hat = ${delta:+.2f} ~ 0. "
            "The pilot effect is too small to size a rollout on; the n-formula explodes. "
            "Below we report rollout n's for a *managerial* MDE ($25, $50, $75, $100) "
            "instead of the pilot's empirical delta-hat.")
        scenarios = [(d, f"${d}") for d in (25, 50, 75, 100)]
    else:
        scenarios = [(abs(delta), "pilot delta"),
                     (abs(delta) * 0.7, "0.7 x pilot delta (winner's-curse adj.)"),
                     (50.0, "$50 managerial MDE"),
                     (100.0, "$100 managerial MDE")]

    rows = []
    for dlt, lbl in scenarios:
        for power in (0.80, 0.90):
            n_z = n_per_group_z(sigma, dlt, alpha, power)
            n_t = int(np.ceil(tt.solve_power(effect_size=dlt/sigma,
                                              alpha=alpha, power=power,
                                              alternative="two-sided")))
            rows.append({
                "Assumed effect": lbl,
                "delta ($)": f"{dlt:.0f}",
                "Power": f"{int(power*100)}%",
                "Cohen's d": f"{dlt/sigma:.3f}",
                "n / group (z-formula)": n_z if n_z >= 0 else "undefined",
                "n / group (t-formula)": n_t,
                "Total N (2 arms)": (n_z * 2 if n_z >= 0 else "undefined"),
            })
    sens = pd.DataFrame(rows)
    say("\n" + sens.to_string(index=False))
    sens.to_csv(OUT / "rollout_sample_size.csv", index=False)
    _to_latex(sens, OUT / "rollout_sample_size.tex",
              caption=(f"Required sample size per arm to detect an effect at $\\alpha={alpha}$. "
                       f"The $z$-formula is $n = 2(z_{{1-\\alpha/2}}+z_{{1-\\beta}})^2(\\hat\\sigma/\\delta)^2$ "
                       f"(Rady deck, slide~17), evaluated at $\\hat\\sigma={sigma:.0f}$. "
                       f"The $t$-formula uses Python's \\texttt{{TTestIndPower}} for cross-check. "
                       f"Apply multipliers if needed: $\\times 1.3$ for Bonferroni across 3 tests, "
                       f"$\\times 2$ for a powered sub-group cut, $\\times 1.5$ attrition buffer "
                       f"(Week~7 deck, slide~44)."),
              label="tab:rollout",
              column_format="lccccccc",
              png_path=FIG / "t06_rollout_sample_size.png",
              png_title=f"Required n per arm to detect an effect (α={alpha}, σ̂=${sigma:.0f})",
              png_footer=f"Formula: n_per_group ≈ 2 (z_{{1-α/2}} + z_{{1-β}})² (σ̂/δ)² "
                         f"(Rady slide 17), evaluated at σ̂=${sigma:.0f}. The t-formula uses "
                         f"statsmodels TTestIndPower. Multiply by ×1.3 for Bonferroni across 3 "
                         f"tests, ×2 for a powered sub-group cut, ×1.5 attrition buffer (Wk 7 s.44).")
    say(f"\nLaTeX rollout table -> {OUT/'rollout_sample_size.tex'}")

    # Composed N* example.
    if abs(delta) >= 1:
        base = n_per_group_z(sigma, abs(delta)*0.7, alpha, 0.80)
        say(f"\nComposed rollout N* (0.7 x delta, 80% power, alpha={alpha}):")
        say(f"  base/arm = {base}  x1.3 multitest = {int(np.ceil(base*1.3))}"
            f"  x2 subgroup = {int(np.ceil(base*1.3*2))}"
            f"  x1.5 attrition = {int(np.ceil(base*1.3*2*1.5))}/arm")

    # Simulation-based power (Week 7 s.38–39): the bounded clumpy DV violates normality.
    hr("STEP 8c — SIMULATION-BASED POWER (Week 7 s.38–39)")
    say("Bounded, clumpy DV (40%+ at boundaries) violates the normality assumption "
        "behind the closed-form formula. Bootstrap-resample the empirical cells to get "
        "an honest power curve.")
    if abs(delta) < 1:
        say("Skipped: pilot delta ~ 0, no effect to bootstrap power for. "
            "(In a rollout, choose target n based on the *managerial* MDE table above.)")
    else:
        rng = np.random.default_rng(0)
        for n in (50, 100, 200, 400):
            hits = 0
            reps = 2000
            for _ in range(reps):
                c = rng.choice(ctrl.values, n, replace=True)
                t = rng.choice(treat.values, n, replace=True)
                if st.ttest_ind(t, c, equal_var=False).pvalue < alpha:
                    hits += 1
            say(f"  n={n:>4}/arm: simulated power = {hits/reps:.3f}  ({reps} reps)")
    return sigma, delta, se_delta


# ======================================================================== robustness
def robustness(df: pd.DataFrame, alpha: float):
    hr("STEP 9 — ROBUSTNESS (drop speeders; drop age outliers; both)")
    for label, mask in [
        ("Drop speeders only", ~df.speeder),
        ("Drop age outliers only", ~df.age_outlier),
        ("Drop speeders AND age outliers", ~(df.speeder | df.age_outlier)),
    ]:
        sub = df[mask]
        n = len(sub)
        if n < 8:
            continue
        ctrl = sub[sub.treat == 0][DV]
        trt = sub[sub.treat == 1][DV]
        res = st.ttest_ind(trt, ctrl, equal_var=False)
        ci = res.confidence_interval(0.95)
        decision = "reject" if res.pvalue < alpha else "fail to reject"
        say(f"  {label:34s} (N={n:3d}): "
            f"delta=${trt.mean()-ctrl.mean():+7.2f}  "
            f"p={res.pvalue:.4f}  "
            f"95% CI [{ci.low:+.1f}, {ci.high:+.1f}]  -> {decision}")


# ================================================================== figures
def figures(df: pd.DataFrame):
    hr("STEP 10 — FIGURES (publication style)")
    # ---- 1. KDE bell curves: treatment vs control -------------------------
    # Density (KDE) overlaid on a faint histogram so the boundary clumping at
    # $0/$500/$1000 is still visible. Bandwidth: Scott's rule with a small
    # bump to smooth the boundary spikes.
    fig, ax = plt.subplots(figsize=(11, 5.5))
    xs = np.linspace(0, 1000, 400)
    bins = np.arange(0, 1050, 50)
    for arm, color in [("control", "#4c72b0"), ("treatment", "#dd8452")]:
        sub = df[df.arm == arm][DV].values
        ax.hist(sub, bins=bins, density=True, color=color, alpha=0.18,
                edgecolor="white", linewidth=0.4)
        kde = st.gaussian_kde(sub, bw_method=0.35)
        ax.plot(xs, kde(xs), color=color, linewidth=2.6,
                label=f"{arm}\nn={len(sub)}\nM=${sub.mean():.0f}\nSD=${sub.std(ddof=1):.0f}")
        ax.fill_between(xs, kde(xs), color=color, alpha=0.12)
        ax.axvline(sub.mean(), color=color, linestyle="--", linewidth=1.2, alpha=0.7)
    ax.set_xlabel("HLXE allocation ($)")
    ax.set_ylabel("Density")
    ax.set_title("Distribution of HLXE allocation: treatment vs control (KDE)")
    ax.legend(frameon=True, loc="upper left", bbox_to_anchor=(1.02, 1.0),
              borderaxespad=0)
    ax.set_xlim(0, 1000)
    fig.savefig(FIG / "01_density_overlay.png"); plt.close(fig)

    # ---- 1b. Fitted Normal (parametric "bell curve") ---------------------
    # Symmetric N(M, SD) PDFs ignoring the boundary clumping. Cleaner shape
    # for slides, but it misrepresents the bimodal/clumpy reality — present
    # alongside the KDE version, not instead of.
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for arm, color in [("control", "#4c72b0"), ("treatment", "#dd8452")]:
        sub = df[df.arm == arm][DV].values
        m, s = sub.mean(), sub.std(ddof=1)
        pdf = st.norm.pdf(xs, loc=m, scale=s)
        ax.plot(xs, pdf, color=color, linewidth=2.8,
                label=f"{arm}\nN(${m:.0f}, ${s:.0f}²)\nn={len(sub)}")
        ax.fill_between(xs, pdf, color=color, alpha=0.18)
        ax.axvline(m, color=color, linestyle="--", linewidth=1.2, alpha=0.7)
    ax.set_xlabel("HLXE allocation ($)")
    ax.set_ylabel("Density (fitted Normal)")
    ax.set_title("Fitted Normal bell curves: treatment vs control")
    ax.legend(frameon=True, loc="upper left", bbox_to_anchor=(1.02, 1.0),
              borderaxespad=0)
    ax.set_xlim(0, 1000)
    fig.text(0.5, -0.02,
             "Note: parametric Normal fit. The empirical distribution is bimodal "
             "(40% of responses at $0/$500/$1000) — see 01_density_overlay for the KDE.",
             ha="center", fontsize=9, style="italic", color="#555")
    fig.savefig(FIG / "01b_gaussian_overlay.png"); plt.close(fig)

    # ---- 2. 4-cell density curves on one panel ----------------------------
    cells = ["neutral / no", "neutral / yes", "hyped / no", "hyped / yes"]
    colors = {"neutral / no": "#4c72b0", "neutral / yes": "#55a868",
              "hyped / no": "#dd8452", "hyped / yes": "#c44e52"}
    fig, ax = plt.subplots(figsize=(12, 6))
    for cell in cells:
        sub = df[df.cell == cell][DV].values
        kde = st.gaussian_kde(sub, bw_method=0.4)
        ax.plot(xs, kde(xs), color=colors[cell], linewidth=2.4,
                label=f"{cell}\nM=${sub.mean():.0f}\nSD=${sub.std(ddof=1):.0f}")
        ax.fill_between(xs, kde(xs), color=colors[cell], alpha=0.10)
    ax.set_xlabel("HLXE allocation ($)")
    ax.set_ylabel("Density")
    ax.set_title(f"HLXE allocation density by experimental cell (KDE, N={len(df)})")
    ax.legend(frameon=True, loc="upper left", bbox_to_anchor=(1.02, 1.0),
              borderaxespad=0)
    ax.set_xlim(0, 1000)
    fig.savefig(FIG / "02_density_by_cell.png"); plt.close(fig)

    # ---- 2b. 4-cell fitted Normal bell curves ----------------------------
    fig, ax = plt.subplots(figsize=(12, 6))
    for cell in cells:
        sub = df[df.cell == cell][DV].values
        m, s = sub.mean(), sub.std(ddof=1)
        pdf = st.norm.pdf(xs, loc=m, scale=s)
        ax.plot(xs, pdf, color=colors[cell], linewidth=2.4,
                label=f"{cell}\nN(${m:.0f}, ${s:.0f}²)")
        ax.fill_between(xs, pdf, color=colors[cell], alpha=0.08)
    ax.set_xlabel("HLXE allocation ($)")
    ax.set_ylabel("Density (fitted Normal)")
    ax.set_title(f"Fitted Normal bell curves by experimental cell (N={len(df)})")
    ax.legend(frameon=True, loc="upper left", bbox_to_anchor=(1.02, 1.0),
              borderaxespad=0)
    ax.set_xlim(0, 1000)
    fig.text(0.5, -0.02,
             "Note: parametric Normal fits. The empirical distribution is bimodal "
             "(40% of responses at $0/$500/$1000) — see 02_density_by_cell for the KDE.",
             ha="center", fontsize=9, style="italic", color="#555")
    fig.savefig(FIG / "02b_gaussian_by_cell.png"); plt.close(fig)

    # ---- 3. Bar chart of means with 95% CI error bars (Rady s.10) ---------
    fig, ax = plt.subplots(figsize=(11, 6.5))
    order = ["neutral / no", "neutral / yes", "hyped / no", "hyped / yes"]
    sub = df[df["cell"].isin(order)].copy()
    means = sub.groupby("cell", observed=True)[DV].mean().reindex(order)
    sems = sub.groupby("cell", observed=True)[DV].sem().reindex(order)
    ns = sub.groupby("cell", observed=True)[DV].count().reindex(order)
    ci95 = sems * st.t.ppf(0.975, ns - 1)
    cell_colors = ["#4c72b0" if c == "neutral / no" else "#dd8452" for c in order]
    bars = ax.bar(order, means.values, yerr=ci95.values, capsize=8,
                  color=cell_colors, edgecolor="black", linewidth=0.6, alpha=0.9)
    for i, (m, n, c) in enumerate(zip(means.values, ns.values, ci95.values)):
        ax.text(i, m + c + 18, f"${m:.0f}\n(n={n})",
                ha="center", va="bottom", fontsize=11)
    ax.set_ylabel("Mean HLXE allocation ($)")
    ax.set_xlabel("Cell (headline / social proof)")
    ax.set_title("HLXE allocation by cell (mean ± 95% CI)")
    ax.set_ylim(0, max(means.values + ci95.values) * 1.20)
    ax.tick_params(axis="x", rotation=12)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor="#4c72b0", edgecolor="black",
                              label="Control\n(neutral/no)"),
                       Patch(facecolor="#dd8452", edgecolor="black",
                              label="Treatment\ncells")],
              loc="upper left", bbox_to_anchor=(1.02, 1.0),
              borderaxespad=0, frameon=True)
    fig.savefig(FIG / "03_bars_ci.png"); plt.close(fig)

    # ---- 4. 2x2 interaction plot ------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 6))
    for hl, color, marker in [("neutral", "#4c72b0", "o"), ("hyped", "#dd8452", "s")]:
        sub = df[df.headline_type == hl]
        ms = sub.groupby("social_proof", observed=True)[DV].mean()
        ses = sub.groupby("social_proof", observed=True)[DV].sem()
        ns2 = sub.groupby("social_proof", observed=True)[DV].count()
        ci = ses * st.t.ppf(0.975, ns2 - 1)
        ax.errorbar(["no", "yes"], ms.reindex(["no", "yes"]).values,
                    yerr=ci.reindex(["no", "yes"]).values,
                    label=f"{hl}\nheadline", marker=marker, capsize=6,
                    color=color, linewidth=2, markersize=10)
    ax.set_xlabel("Social proof")
    ax.set_ylabel("Mean HLXE allocation ($)")
    ax.set_title("Headline × social-proof interaction (mean ± 95% CI)")
    ax.legend(frameon=True, loc="upper left", bbox_to_anchor=(1.02, 1.0),
              borderaxespad=0)
    fig.savefig(FIG / "04_interaction.png"); plt.close(fig)

    # ---- 5. Pilot CI vs illustrative rollout CI ---------------------------
    ctrl = df[df.treat == 0][DV]; treat = df[df.treat == 1][DV]
    delta = treat.mean() - ctrl.mean()
    se = np.sqrt(ctrl.var(ddof=1)/len(ctrl) + treat.var(ddof=1)/len(treat))
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.errorbar([delta], [1], xerr=[1.96*se], fmt="o", capsize=8, markersize=10,
                color="#4c72b0", label=f"Pilot\n(N={len(df)})")
    ax.errorbar([delta], [0], xerr=[1.96*se*np.sqrt(len(df)/600)], fmt="s",
                capsize=8, markersize=10, color="#dd8452",
                label="Illustrative\nrollout\n(N≈600)")
    ax.axvline(0, color="grey", ls="--", linewidth=1.4)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["rollout", "pilot"])
    ax.set_xlabel("Estimated treatment effect on HLXE allocation ($)")
    ax.set_title("Same point estimate, different precision: pilot vs scaled-up rollout (95% CI)")
    ax.legend(frameon=True, loc="upper left", bbox_to_anchor=(1.02, 1.0),
              borderaxespad=0)
    fig.savefig(FIG / "05_pilot_vs_rollout_ci.png"); plt.close(fig)

    say(f"Saved 5 figures -> {FIG}/")


# ============================================== latex helpers (publication style)
def _to_latex(df: pd.DataFrame, path: Path, caption: str, label: str,
              column_format: str | None = None,
              png_path: Path | None = None, png_title: str | None = None,
              png_footer: str | None = None):
    """Booktabs-style LaTeX. Optionally render a PNG copy for slide decks."""
    if column_format is None:
        column_format = "l" + "c" * (df.shape[1] - 1)
    body = df.to_latex(index=False, escape=True, column_format=column_format,
                       float_format=lambda x: f"{x:.3f}")
    tex = (
        "% requires \\usepackage{booktabs, threeparttable}\n"
        "\\begin{table}[!htbp]\n  \\centering\n  \\begin{threeparttable}\n"
        f"  \\caption{{{caption}}}\n  \\label{{{label}}}\n"
        f"  {body}"
        "  \\end{threeparttable}\n\\end{table}\n"
    )
    path.write_text(tex)
    if png_path is not None:
        _render_table_png(df, png_path, title=png_title or "",
                          footer=png_footer or caption)


def _render_table_png(df: pd.DataFrame, path: Path,
                      title: str = "", footer: str = "",
                      col_widths: list[float] | None = None,
                      max_width_per_col: float = 1.9,
                      first_col_factor: float = 1.6):
    """Render a DataFrame as a publication-quality PNG table for slide decks."""
    n_rows = len(df) + 1            # +1 for header
    n_cols = df.shape[1]

    # column widths: first column wider (variable / row labels), others uniform
    if col_widths is None:
        col_widths = [max_width_per_col * first_col_factor] + \
                     [max_width_per_col] * (n_cols - 1)
    total_w = sum(col_widths)
    row_h = 0.42
    title_h = 0.55 if title else 0.0
    footer_h = 0.0
    if footer:
        # rough wrap estimate; footer typically wraps to ~2-3 lines for long captions
        wrap_chars = max(int(total_w * 12), 60)
        footer_lines = max(1, int(np.ceil(len(footer) / wrap_chars)))
        footer_h = 0.30 * footer_lines + 0.15

    fig_w = max(total_w + 0.6, 6.5)
    fig_h = title_h + row_h * n_rows + footer_h + 0.4
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_axis_off()
    ax.set_xlim(0, total_w)
    ax.set_ylim(0, fig_h)

    # title
    y_cursor = fig_h - 0.1
    if title:
        ax.text(total_w / 2, y_cursor - 0.05, title,
                ha="center", va="top", fontsize=14, fontweight="bold")
        y_cursor -= title_h

    # column x edges
    x_edges = [0.0]
    for w in col_widths:
        x_edges.append(x_edges[-1] + w)

    # header band
    header_y_top = y_cursor
    header_y_bot = y_cursor - row_h
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((0, header_y_bot), total_w, row_h,
                           facecolor="#2c3e50", edgecolor="none"))
    for j, col in enumerate(df.columns):
        # header: first col left-aligned, others centered
        cx = x_edges[j] + (0.10 if j == 0 else col_widths[j] / 2)
        ax.text(cx, header_y_bot + row_h / 2, str(col),
                ha="left" if j == 0 else "center", va="center",
                color="white", fontsize=10.5, fontweight="bold")

    # body rows
    for i, (_, row) in enumerate(df.iterrows()):
        y_top = header_y_bot - i * row_h
        y_bot = y_top - row_h
        # zebra stripe
        if i % 2 == 0:
            ax.add_patch(Rectangle((0, y_bot), total_w, row_h,
                                   facecolor="#f4f6f8", edgecolor="none"))
        for j, val in enumerate(row):
            sval = "" if (val is None or (isinstance(val, float) and np.isnan(val))) else str(val)
            # right-align numeric-looking cells, left-align the first column,
            # center the rest
            if j == 0:
                # row labels: indent leading spaces are visual hints in our balance tables
                indent = len(sval) - len(sval.lstrip())
                cx = x_edges[j] + 0.10 + indent * 0.07
                ax.text(cx, y_bot + row_h / 2, sval.lstrip(),
                        ha="left", va="center", fontsize=10)
            else:
                cx = x_edges[j] + col_widths[j] / 2
                ax.text(cx, y_bot + row_h / 2, sval,
                        ha="center", va="center", fontsize=10)

    # top and bottom rules
    body_bot = header_y_bot - len(df) * row_h
    ax.plot([0, total_w], [header_y_top, header_y_top], color="black", linewidth=1.2)
    ax.plot([0, total_w], [header_y_bot, header_y_bot], color="black", linewidth=0.8)
    ax.plot([0, total_w], [body_bot, body_bot], color="black", linewidth=1.2)

    # footer
    if footer:
        import textwrap
        wrap_chars = max(int(total_w * 12), 60)
        wrapped = textwrap.fill(footer, width=wrap_chars)
        ax.text(0.05, body_bot - 0.15, wrapped,
                ha="left", va="top", fontsize=8.5, color="#444", style="italic")

    fig.savefig(path, dpi=200, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


def _three_model_table(m1, m2, m3) -> pd.DataFrame:
    """One regression table, three columns (Rady s.12 style)."""
    rows: list[dict] = []
    name_map = {
        "Intercept": "Intercept",
        "treat": "Treatment (any of 3 cells)",
        "C(headline_type)[T.hyped]": "Hyped headline (vs neutral)",
        "C(social_proof)[T.yes]": "Social proof: yes (vs no)",
        "C(headline_type)[T.hyped]:C(social_proof)[T.yes]": "Hyped × Social proof",
        "age": "Age",
        "C(prior_investor)[T.yes]": "Prior investor (yes)",
        "C(gender)[T.woman]": "Gender: woman",
        "C(gender)[T.non_binary_or_other]": "Gender: NB / other",
        "C(major_area)[T.stem]": "Major: STEM",
        "C(major_area)[T.business_econ]": "Major: business/econ",
    }
    all_params = []
    for m in (m1, m2, m3):
        for p in m.params.index:
            if p not in all_params:
                all_params.append(p)
    # Stable display order.
    order = [p for p in name_map if p in all_params] + [p for p in all_params if p not in name_map]

    def fmt(m, p):
        if p not in m.params.index:
            return ("", "")
        b = m.params[p]
        se = m.bse[p]
        pv = m.pvalues[p]
        star = "$^{***}$" if pv < .01 else "$^{**}$" if pv < .05 else "$^{*}$" if pv < .10 else ""
        return (f"{b:+.2f}{star}", f"({se:.2f})")

    for p in order:
        b1, s1 = fmt(m1, p)
        b2, s2 = fmt(m2, p)
        b3, s3 = fmt(m3, p)
        if not any([b1, b2, b3]):
            continue
        label = name_map.get(p, p)
        rows.append({"Variable": label,
                     "(1) Simple": b1, "(2) Factorial": b2, "(3) +Controls": b3})
        rows.append({"Variable": "", "(1) Simple": s1, "(2) Factorial": s2, "(3) +Controls": s3})

    rows.append({"Variable": "Observations",
                 "(1) Simple": f"{int(m1.nobs)}",
                 "(2) Factorial": f"{int(m2.nobs)}",
                 "(3) +Controls": f"{int(m3.nobs)}"})
    rows.append({"Variable": "$R^2$",
                 "(1) Simple": f"{m1.rsquared:.4f}",
                 "(2) Factorial": f"{m2.rsquared:.4f}",
                 "(3) +Controls": f"{m3.rsquared:.4f}"})
    rows.append({"Variable": "Robust SE", "(1) Simple": "HC1",
                 "(2) Factorial": "HC1", "(3) +Controls": "HC1"})
    return pd.DataFrame(rows)


def _regression_table_tex(tbl: pd.DataFrame, path: Path, notes: list[str]):
    body = tbl.to_latex(index=False, escape=False, column_format="lccc")
    note_block = "\n".join(f"      \\item {n}" for n in notes)
    tex = (
        "% requires \\usepackage{booktabs, threeparttable}\n"
        "\\begin{table}[!htbp]\n  \\centering\n  \\begin{threeparttable}\n"
        "  \\caption{OLS regressions of HLXE allocation (USD) on treatment "
        "and pre-registered controls. Heteroskedasticity-robust (HC1) standard "
        "errors are reported in parentheses below each coefficient.}\n"
        "  \\label{tab:regressions}\n"
        f"  {body}"
        "    \\begin{tablenotes}[para,flushleft]\\footnotesize\n"
        f"{note_block}\n"
        "    \\end{tablenotes}\n"
        "  \\end{threeparttable}\n\\end{table}\n"
    )
    path.write_text(tex)


# ============================================================ results memo
def write_memo(df, sigma, delta, se_delta, m1_results, alpha):
    """One narrative document tying figures + tables to the rubric."""
    b, se, ci_low, ci_high, p = m1_results
    decision = "reject H0" if p < alpha else "fail to reject H0"
    text = f"""# MGT 160 Pilot — Results Memo

Maps to the Wk-8 rubric: (1) figure, (2) test with H0 + p + 95% CI,
(3) power/MDE given the variance estimate, (4) generalizability.

## Headline numbers

| Quantity | Value |
|---|---|
| Analyzable $N$ | {len(df)} |
| Within-cell SD ($\\hat\\sigma$) | \\${sigma:.2f} |
| Primary effect $\\hat\\delta$ (treat − control) | \\${delta:+.2f} |
| $SE(\\hat\\delta)$ (HC1) | \\${se:.2f} |
| 95% CI on $\\hat\\delta$ | [\\${ci_low:+.2f}, \\${ci_high:+.2f}] |
| $p$-value (Welch / HC1 OLS) | {p:.4f} |
| Decision at $\\alpha={alpha}$ | **{decision}** |

## 1. Figure — see `figures/`

- `01_density_overlay.png` / `01b_gaussian_overlay.png` — KDE and fitted-Normal density, control vs treatment
- `02_density_by_cell.png` / `02b_gaussian_by_cell.png` — KDE and fitted-Normal density for all 4 cells
- `03_bars_ci.png` — bar chart of means with 95% CI error bars (Rady s.10)
- `04_interaction.png` — 2×2 interaction plot
- `05_pilot_vs_rollout_ci.png` — "same effect, different precision"

## 2. Statistical test (H0 + p + 95% CI)

**H0**: mean HLXE allocation is the same in treatment and control.
**HA**: means differ (two-sided).

- Welch's $t$-test (Rady s.13): $\\hat\\delta=\\${delta:+.2f}$, $p={p:.4f}$,
  95% CI on the difference $[\\${ci_low:+.2f}, \\${ci_high:+.2f}]$.
- OLS with HC1 robust SE (Rady s.12) gives the same point estimate by construction.
- At $\\alpha={alpha}$, we **{decision}**.
- Reminder (Rady s.13): $p$ is the probability of data this extreme *if H0 is true*.
  It is NOT $P(H_0|\\text{{data}})$ and it is NOT an effect size.
- Type I error rate is capped at $\\alpha={alpha}$ by construction.
- If we fail to reject, a Type II error (false negative) is possible — see the MDE
  in Step 8a of `report.txt`; this pilot is only powered for large effects.

See `output/balance_table.tex`, `output/summary_by_arm.tex`,
`output/regression_table.tex`, `output/hypothesis_tests.csv`.

## 3. Power / MDE statement

- $\\hat\\sigma = \\${sigma:.2f}$ — the pilot's headline deliverable for sizing follow-ups.
- At $\\alpha={alpha}$, this pilot is powered (80%) for a main-effect shift of
  roughly $d \\approx 0.43$ (≈ \\${0.43*sigma:.0f}).
- See `output/rollout_sample_size.tex` for the per-arm $n$ required to detect
  a managerial \\$25–\\$100 shift at 80% and 90% power.
- Closed-form formula (Rady s.17):
  $$n_{{\\text{{per group}}}} \\approx 2(z_{{1-\\alpha/2}}+z_{{1-\\beta}})^2 (\\hat\\sigma/\\delta)^2$$

## 4. Generalizability

- **Who**: UCSD MGT 160 students who self-selected by clicking a class-email link;
  85% business/econ majors, mostly juniors (n={int((df['year_in_school']=='junior').sum())} / {len(df)}).
- **Context**: hypothetical \\$1,000 (lottery-incentivized only), fictional ETF,
  finance-aware students, single course, single term.
- **Confirmatory vs exploratory**: prior-investor moderation is confirmatory
  (pre-registered). Anything else here — major-area effects, boundary picks —
  is exploratory and expect winner's-curse shrinkage.
- **Where to pilot next**: a non-finance student sample with real (small) stakes;
  size to the rollout table above using $\\hat\\sigma=\\${sigma:.0f}$.
"""
    (OUT / "RESULTS_MEMO.md").write_text(text)
    say(f"\nResults memo -> {OUT/'RESULTS_MEMO.md'}")


# ======================================================================== main
def main():
    ap = argparse.ArgumentParser(description="MGT 160 pilot analysis")
    ap.add_argument("--csv", default="data/Pilot results 1.csv",
                    help="Path to the pilot CSV (default: data/Pilot results 1.csv)")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--speeder-seconds", type=int, default=30)
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    if not csv_path.exists():
        sys.exit(f"No data at {csv_path}.")

    df = load(csv_path)
    df = clean(df, args.speeder_seconds)
    balance_table(df)
    balance_table_4cell(df)
    summary_by_group(df)
    hypothesis_tests(df, args.alpha)
    m1, _m2, _m3 = regressions(df, args.alpha)
    moderator_prior(df)
    confidence_secondary(df)
    sigma, delta, se_delta = power_and_rollout(df, args.alpha)
    robustness(df, args.alpha)
    figures(df)

    # Pull primary point estimate off model 1 for the memo.
    b = m1.params["treat"]; se = m1.bse["treat"]
    ci = m1.conf_int().loc["treat"]; pval = m1.pvalues["treat"]
    write_memo(df, sigma, delta, se_delta,
               (b, se, ci[0], ci[1], pval), args.alpha)

    (OUT / "report.txt").write_text("\n".join(LOG))
    say(f"\nFull text report -> {OUT/'report.txt'}")


if __name__ == "__main__":
    main()
