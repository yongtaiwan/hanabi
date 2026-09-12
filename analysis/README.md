# Paper statistics

Run from the repository root:

```sh
python analysis/reviewer_stats.py
python -m unittest discover -s analysis -p 'test_*.py'
```

The frozen run in `reviewer-stats-2026-09-12/` uses 500 seeds (42–541) for each
of seven strategy/player-count combinations. The same seed gives the same deck
within each player count. All players use the named strategy. The engine uses
the standard 50-card deck and stops early if no further points are possible.
No bot policy changed for this analysis.

## Figures and editable sources

The `reviewer-stats-2026-09-12/graphics/` folder contains four PNG figures and a
PowerPoint companion with native charts and their embedded data. The figures
cover perfect-game rates, non-perfect outcomes, zero-token frequencies, and
three-player score distributions. The zero-token figure is an optional
companion; the other three are used in the manuscript.

The companion uses the short labels **Simple**, **Dynamic**, and **Cheater**
for Simple Recommendation, Dynamic Recommendation, and CommonSenseCheater.

## Verification status (12 September 2026)

The four analysis checks pass, including independent replay of selected seeds
and every all-lives-lost or final-fallback edge case. Core discovery passes
(118 tests, 9 skipped) and web discovery passes (32 tests). AI discovery runs
342 tests but retains 8 existing failures/errors and 1 skip: seven tests call
outdated RecommendationPlayer helper signatures; one hint-tracking test sends
an unfinished Play event to an observer that expects FinishedPlay. These tests
and production strategy code were not changed for this statistics publication.

The fresh analysis checks do not imply that the entire legacy suite passes.

`summary.json` gives exact counts, denominators, means, standard deviations,
and Wilson 95% intervals for perfect-game rates. `evidence.json.gz` retains every
deck and move, including pre-move hint tokens, lost lives, and explanatory text.
The script writes an uncompressed `evidence.json` when rerun.

## Scoring and outcome definitions

A perfect game scores 25. Following the manuscript's scoring rule, a game that
loses its third life scores zero. Raw engine scores remain in the evidence as
`raw_score`; the paper uses `paper_score`. This distinction affects one
four-player Simple game (seed 131, raw score 4) and one Dynamic game (seed 481,
raw score 23). It does not affect perfect-game rates.

Every non-perfect game belongs to the first applicable category:

1. **All lives lost:** the third unsuccessful play ended the game.
2. **Last needed copy lost:** with lives remaining, a discard or failed play
   removed the last copy of a rank still needed for a firework. This includes
   the last copy of a currently playable card.
3. **Tempo:** neither earlier condition occurred, but the final round ended
   below 25. All games in this category retained a playable card in a hand.

These are descriptive outcome categories, not causal estimates of points lost.
The priority prevents double counting. The main graphic uses all non-perfect
games, not only those where a matched cheater scored 25. The latter subset is
retained separately in the summary for auditability.

Zero-token turn frequency uses **all completed moves** as its denominator and
measures the token bank immediately before each move. Zero-token game frequency
counts games that contain at least one such turn. Turns within a game are
dependent; do not treat each turn as an independent statistical trial.

## Published comparison

Cox et al., *How to Make the Perfect Fireworks Display: Two Strategies for
Hanabi*, Figure 7, label perfect-score frequencies of approximately 0.16, 0.76,
and 0.91 for Recommendation, Information, and Cheating. These are rounded
published histogram labels, not exact counts. Figure 8 reports means of 23.00,
24.68, and 24.87 over one million five-player games. We were unable to fully
replicate their Recommendation result, so those values remain cross-study
context rather than head-to-head results. DOI: https://doi.org/10.4169/math.mag.88.5.323
