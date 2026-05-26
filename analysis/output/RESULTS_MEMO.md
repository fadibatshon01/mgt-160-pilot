# MGT 160 Pilot — Results Memo

Maps to the Wk-8 rubric: (1) figure, (2) test with H0 + p + 95% CI,
(3) power/MDE given the variance estimate, (4) generalizability.

## Headline numbers

| Quantity | Value |
|---|---|
| Analyzable $N$ | 172 |
| Within-cell SD ($\hat\sigma$) | \$305.59 |
| Primary effect $\hat\delta$ (treat − control) | \$-11.31 |
| $SE(\hat\delta)$ (HC1) | \$50.53 |
| 95% CI on $\hat\delta$ | [\$-110.34, \$+87.72] |
| $p$-value (Welch / HC1 OLS) | 0.8229 |
| Decision at $\alpha=0.05$ | **fail to reject H0** |

## 1. Figure — see `figures/`

- `01_density_overlay.png` / `01b_gaussian_overlay.png` — KDE and fitted-Normal density, control vs treatment
- `02_density_by_cell.png` / `02b_gaussian_by_cell.png` — KDE and fitted-Normal density for all 4 cells
- `03_bars_ci.png` — bar chart of means with 95% CI error bars (Rady s.10)
- `04_interaction.png` — 2×2 interaction plot
- `05_pilot_vs_rollout_ci.png` — "same effect, different precision"

## 2. Statistical test (H0 + p + 95% CI)

**H0**: mean HLXE allocation is the same in treatment and control.
**HA**: means differ (two-sided).

- Welch's $t$-test (Rady s.13): $\hat\delta=\$-11.31$, $p=0.8229$,
  95% CI on the difference $[\$-110.34, \$+87.72]$.
- OLS with HC1 robust SE (Rady s.12) gives the same point estimate by construction.
- At $\alpha=0.05$, we **fail to reject H0**.
- Reminder (Rady s.13): $p$ is the probability of data this extreme *if H0 is true*.
  It is NOT $P(H_0|\text{data})$ and it is NOT an effect size.
- Type I error rate is capped at $\alpha=0.05$ by construction.
- If we fail to reject, a Type II error (false negative) is possible — see the MDE
  in Step 8a of `report.txt`; this pilot is only powered for large effects.

See `output/balance_table.tex`, `output/summary_by_arm.tex`,
`output/regression_table.tex`, `output/hypothesis_tests.csv`.

## 3. Power / MDE statement

- $\hat\sigma = \$305.59$ — the pilot's headline deliverable for sizing follow-ups.
- At $\alpha=0.05$, this pilot is powered (80%) for a main-effect shift of
  roughly $d \approx 0.43$ (≈ \$131).
- See `output/rollout_sample_size.tex` for the per-arm $n$ required to detect
  a managerial \$25–\$100 shift at 80% and 90% power.
- Closed-form formula (Rady s.17):
  $$n_{\text{per group}} \approx 2(z_{1-\alpha/2}+z_{1-\beta})^2 (\hat\sigma/\delta)^2$$

## 4. Generalizability

- **Who**: UCSD MGT 160 students who self-selected by clicking a class-email link;
  85% business/econ majors, mostly juniors (n=91 / 172).
- **Context**: hypothetical \$1,000 (lottery-incentivized only), fictional ETF,
  finance-aware students, single course, single term.
- **Confirmatory vs exploratory**: prior-investor moderation is confirmatory
  (pre-registered). Anything else here — major-area effects, boundary picks —
  is exploratory and expect winner's-curse shrinkage.
- **Where to pilot next**: a non-finance student sample with real (small) stakes;
  size to the rollout table above using $\hat\sigma=\$306$.
