# Results: Shrewd Step vs Groundwork vs no skill

Each comparison adds one skill to one Uma and leaves the rest of the team unchanged.
Only that Uma is reported: **Taiki Shuttle** on CM18 and CM21, **Oguri Cap** on CM19.

Both teams face identical races: the same seeds, opponents (2 random teams from a 100-team pool) and gates.
Each comparison ran 10,000 trials with `src/compare_teams.py`. All intervals are 95% CIs.

- **No skill**: the `*_no_gw_team.json` baseline
- **Shrewd Step**: baseline + Shrewd Step (`*_shrewd_step_team.json`)
- **Groundwork**: baseline + Groundwork (`*_gw_team.json`)

Each skill was tested in its own run against its own baseline run, so the "No skill" row can differ slightly between the two comparisons for the same CM.
The win % difference is paired (both teams ran the same races), so it is narrower than the two separate win-rate CIs would suggest.

## Summary

| CM | Uma | Shrewd Step win % gain | Groundwork win % gain |
|---|---|---|---|
| CM18 Libra Cup 2 | Taiki Shuttle | **+1.8%** (+0.8 to +2.7) | **+3.5%** (+2.4 to +4.5) |
| CM19 Scorpio Cup 2 | Oguri Cap | +0.3% (−0.5 to +1.1), not significant | **+2.5%** (+1.6 to +3.4) |
| CM21 Capricorn Cup 2 | Taiki Shuttle | **+1.5%** (+0.6 to +2.4) | **+4.1%** (+3.1 to +5.1) |

Groundwork beats no skill on every CM, and its gain is larger than Shrewd Step's on all three.
Where Shrewd Step helped (CM18, CM21), Groundwork's gain was about 2–3× as large. On CM19, Shrewd Step had no measurable effect.

---

## CM18 — Libra Cup 2 (Taiki Shuttle)

| Variant | Team win rate | Avg place | Avg from top |
|---|---|---|---|
| No skill | 39.5% (38.5–40.4) | 3.71 ± 0.04 | 8.79 ± 0.17 m · 0.34 ± 0.01 s |
| Shrewd Step | 41.2% (40.3–42.2) | 3.48 ± 0.04 | 7.89 ± 0.17 m · 0.31 ± 0.01 s |
| | **+1.8%** (+0.8 to +2.7) | −0.23 | −0.90 m · −0.03 s |

| Variant | Team win rate | Avg place | Avg from top |
|---|---|---|---|
| No skill | 38.5% (37.5–39.4) | 3.69 ± 0.04 | 8.77 ± 0.17 m · 0.34 ± 0.01 s |
| Groundwork | 41.9% (40.9–42.9) | 3.33 ± 0.04 | 7.38 ± 0.16 m · 0.29 ± 0.01 s |
| | **+3.5%** (+2.4 to +4.5) | −0.36 | −1.39 m · −0.05 s |

## CM19 — Scorpio Cup 2 (Oguri Cap)

| Variant | Team win rate | Avg place | Avg from top |
|---|---|---|---|
| No skill | 38.9% (37.9–39.8) | 3.25 ± 0.03 | 8.65 ± 0.17 m · 0.35 ± 0.01 s |
| Shrewd Step | 39.2% (38.2–40.1) | 3.20 ± 0.03 | 8.45 ± 0.17 m · 0.34 ± 0.01 s |
| | +0.3% (−0.5 to +1.1), not significant | −0.05 | −0.20 m · −0.01 s |

| Variant | Team win rate | Avg place | Avg from top |
|---|---|---|---|
| No skill | 39.9% (38.9–40.9) | 3.25 ± 0.03 | 8.62 ± 0.17 m · 0.35 ± 0.01 s |
| Groundwork | 42.4% (41.4–43.4) | 3.08 ± 0.03 | 7.91 ± 0.17 m · 0.32 ± 0.01 s |
| | **+2.5%** (+1.6 to +3.4) | −0.17 | −0.71 m · −0.03 s |

## CM21 — Capricorn Cup 2 (Taiki Shuttle)

| Variant | Team win rate | Avg place | Avg from top |
|---|---|---|---|
| No skill | 30.3% (29.4–31.2) | 4.89 ± 0.05 | 10.03 ± 0.17 m · 0.39 ± 0.01 s |
| Shrewd Step | 31.9% (30.9–32.8) | 4.67 ± 0.05 | 9.37 ± 0.16 m · 0.37 ± 0.01 s |
| | **+1.5%** (+0.6 to +2.4) | −0.22 | −0.66 m · −0.02 s |

| Variant | Team win rate | Avg place | Avg from top |
|---|---|---|---|
| No skill | 30.1% (29.2–31.0) | 4.93 ± 0.05 | 10.19 ± 0.17 m · 0.40 ± 0.01 s |
| Groundwork | 34.2% (33.2–35.1) | 4.39 ± 0.05 | 8.64 ± 0.17 m · 0.34 ± 0.01 s |
| | **+4.1%** (+3.1 to +5.1) | −0.54 | −1.55 m · −0.06 s |
