# MGT 160 Pilot — Experiment Design

## 1. Big Question

Do popularity cues and hype framing cause people to take on more financial risk than they otherwise would, by acting on heuristics instead of evaluating the underlying information?

## 2. Research Question

When UCSD students are shown a realistic online investment listing, does the presence of a popularity signal and hype framing cause them to allocate more of a $1,000 portfolio toward a risky asset rather than a safe one?

## 3. Where & Who

Participants are MGT 160 students recruited online via a single class-wide email containing one link. The experiment runs entirely on a self-built single-page web app deployed to Vercel.

## 4. Stimulus & Treatments

All participants see the same fictional but realistic asset:

**Helix Renewable Energy ETF (HLXE)** — a diversified fund tracking 50 mid-cap renewable energy companies. The listing displays the same six descriptive sections across every condition: historical performance (+14.2% 3-yr, −7.8% worst year, +21.4% best year), expense ratio (0.45%), top holdings (5 fictional companies), risk profile, analyst ratings (6 Buy / 3 Hold / 1 Sell), and management team.

Two factors are manipulated in a 2×2 design: headline framing and popularity badge.

|  | No social proof | Social proof present |
|---|---|---|
| **Neutral headline** | Standard listing, no popularity badge | Standard listing + "Most-bought ETF among college investors this month" |
| **Hyped headline** | "HOT PICK" framing, no badge | "HOT PICK" framing + "Most-bought ETF among college investors this month" |

**Implementation detail:** the manipulation cues are shown in *two* places per screen — at the top of the listing card (large banner / callout) and again as compact tags directly above the "Allocate your $1,000" heading, so participants register the cue both when reading the listing and at the moment of decision. The 6 descriptive sections are byte-identical across conditions.

## 5. Randomization

Random assignment is done **server-side via block randomization** (also called balanced assignment). When the participant clicks Begin, the page issues a GET request to the Google Apps Script Web App. The script reads the Sheet's `condition` column, counts completed responses per cell, and returns whichever condition currently has the fewest entries, with a uniform random tiebreak when several cells are tied. The next participant fills in the smallest cell.

This guarantees the spread across the 4 conditions stays within ±1 throughout data collection, which materially improves statistical power at the pilot's small N (~30–50). If the network request fails, the client falls back to local `Math.floor(Math.random() * 4) + 1` so the experiment still runs for that participant. The assigned condition is logged with the response, eliminating any risk of mis-assignment, sharing, or condition leakage.

A `?condition=N` URL parameter forces a specific condition; used for QA only.

## 6. Primary Behavioral Outcome (Allocation Decision)

Each participant allocates a hypothetical $1,000 portfolio between a **Treasury bond** (guaranteed 5% return, no risk of loss) and **HLXE** (random return drawn uniformly from −25% to +25%). The two amounts must sum to exactly $1,000; the input fields are linked so that typing into one auto-updates the other.

The primary measure is the dollar amount allocated to HLXE.

**Hypothesis:** participants in the social-proof and/or hyped-headline conditions allocate more to HLXE than those in the control (neutral, no social proof) condition.

The 5% Treasury rate is chosen deliberately. A higher safe rate (e.g., 8%) raises the rational floor enough that most participants would pick all-Treasury in baseline regardless of manipulation, leaving no headroom for HOT PICK or social proof to shift behavior. 5% sits closer to real-world Treasury yields, removes the credibility issue that 8% would create for finance-aware participants, and leaves the HLXE bet attractive enough that the manipulation has room to push allocation.

## 7. Real-Money Incentive (How the Decision Becomes Behavioral)

After the participant submits their allocation, the page **immediately draws a random HLXE return and locks the final portfolio value** — but does *not* display it yet. The participant first answers a 1–5 confidence question (see §8), then sees the outcome reveal: HLXE return percentage and final portfolio value (e.g., "HLXE returned +14.20% / Your portfolio is now $1,127.50"), with an animated counter-up presentation. The breakdown shows each asset's contribution: `Treasury: $X × 1.05` and `HLXE: $Y × (1 ± Z%)`.

After data collection closes, the top 3 participants by final portfolio value are paid via Venmo: 1st = $20, 2nd = $15, 3rd = $5. Every allocation affects the chance of placing in the top 3, so each decision carries real expected monetary value. The mechanism (rates, range, prize structure, and that the result is computed immediately on submit) is fully disclosed on the landing page before the participant sees any treatment.

## 8. Secondary Outcomes & Subgroups

**Captured automatically:** timestamp, condition assigned (1–4), `headline_type` (neutral / hyped), `social_proof` (yes / no), Treasury allocation, HLXE allocation, HLXE return drawn, final portfolio value, time on page (sec), time to submit (sec).

**Self-report items:**

- **Confidence in decision (1–5):** asked *between* allocation submit and outcome reveal — i.e., after the participant has committed but before they see the random return. This placement is intentional: asking confidence after the result would contaminate the measure with hindsight bias (a +20% draw inflates retroactive confidence; a −20% draw deflates it). Pre-outcome captures decision-time belief.
- **Demographics (post-outcome):** age, gender (Woman / Man / Non-binary or another gender / Prefer not to say), year in school (Freshman / Sophomore / Junior / Senior / Graduate), major area (Business/Econ / STEM / Humanities / Social Sciences / Other), prior real-money investing experience (yes / no).
- **Venmo handle (optional):** for prize disbursement only.

**Pre-specified subgroups for analysis:**

- **Prior investing experience (yes vs. no)** — primary subgroup. Tests whether participants with real-money exposure are less susceptible to social-proof and hype heuristics.
- **Major area (Business/Econ vs. other)** — secondary. Tests whether finance-adjacent training reduces susceptibility.

## 9. Timeline & To-Dos

| Task | When | Status |
|---|---|---|
| Build single-page web experiment | Pre-pilot week | Done |
| Set up Google Sheet schema (17 columns) | Pre-pilot week | Done |
| Deploy Apps Script endpoint (doPost write + doGet block randomization) | Pre-pilot week | Done |
| Deploy participant page to Vercel | Pre-pilot week | Done |
| Distribute single class link via MGT 160 email | Pilot week | Pending |
| Identify top 3 by portfolio value, pay via Venmo, analyze data | Within 3 days of pilot close | Pending |
| Complete final presentation | 1 week before due date | Pending |

## 10. Participant Flow

1. **Landing.** Page loads. Disclosure tiles show Treasury bond rate (+5% guaranteed, no risk of loss), HLXE range (−25% to +25%), prize tiers ($20 / $15 / $5), and that the result is calculated immediately on submit.
2. **Begin → balanced condition assignment.** Click "Begin study". Page fetches the next condition from the Apps Script `doGet` (block randomization on completed Sheet rows). Brief "Loading…" state on the button while the request is in flight (≈300–700 ms). Falls back to client-side `Math.random()` if the network call fails.
3. **HLXE listing.** Page renders the assigned condition's framing: "HOT PICK" red banner at top of listing card if `headline_type === "hyped"`; amber "Most-bought ETF among college investors" callout below the tagline if `social_proof === "yes"`. The 6 descriptive sections render identically across conditions.
4. **Allocation.** Two linked numeric inputs (Treasury / HLXE) on a separate card below the listing. The same manipulation cues that appeared at the top of the listing reappear as compact tags directly above the heading, so they're visible at the moment of decision. A live split bar visualizes the breakdown. Submit button enables only when the two amounts sum to exactly $1,000.
5. **Allocation submit.** Page draws HLXE return `~ Uniform(−25, +25)` rounded to 2 decimals, computes `final_portfolio = (treasury × 1.05) + (hlxe × (1 + return / 100))`, and locks both values in state. Outcome DOM is pre-rendered but not shown.
6. **Pre-outcome confidence (1–5).** Eyebrow says "Decision locked." Participant rates confidence before seeing the return.
7. **Outcome reveal.** Animated counter-up of return % (gradient green if positive, red if negative) and final portfolio value. Breakdown card shows each asset's contribution.
8. **Demographics.** Age, gender, year in school, major area, prior real-money investing.
9. **Venmo (optional).** Prize-tier visual ($20 / $15 / $5) above an optional handle field. Blank submit is allowed.
10. **POST to Sheet.** All data submitted as a single JSON row to the Apps Script `doPost`, written to row `n+1` of the Sheet.
11. **Thanks.** "You're all set." Confirmation that response was recorded and that top-3 finishers will be paid via Venmo within a week of study close.
