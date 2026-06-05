# OLS Regression: Treatment Effects on HLXE Allocation

**DV:** HLXE allocation ($, 0–1000)  
**Model:** treatment dummies + demographic controls, HC1 robust SEs  
**Controls included** (not shown): `prior_investor`, `age`, `gender`, `year_in_school`, `major_area` — see `tab_regression.csv` for the full table.

## Treatment effects

- **Hyped headline** (vs. neutral): β = -19.09, SE = 68.84, 95% CI [-154.01, +115.84], p = 0.782
- **Social proof banner** (vs. none): β = -35.39, SE = 65.96, 95% CI [-164.66, +93.89], p = 0.592
- **Hyped × Social proof** (interaction): β = +48.74, SE = 99.57, 95% CI [-146.41, +243.89], p = 0.624

## Fit

R² = 0.061 · Adjusted R² = -0.036 · F-test p = 0.000

## Interpretation

Holding demographics constant, switching from a *neutral* to a *hyped* headline (with no peer banner) is associated with a -19.1-dollar change in HLXE allocation; adding the peer-investor banner (under a neutral headline) is associated with a -35.4-dollar change. The interaction term (+48.7) tells us whether the two manipulations combine super-additively (positive) or cancel (negative). Statistical significance is read off the 95% CIs above: any CI that does **not** cross zero is significant at α = 0.05 (those rows are colored red in `fig_regression_coefs.png`).


The overall model F-test (p = 0.000) and R² = 0.061 indicate a jointly significant relationship between the full predictor set and HLXE allocation. With a clumpy bounded DV (mass at $0/$500/$1000), these estimates are noisy — consistent with the pilot's role of variance estimation rather than confirmation (see power table in `report.md`).
