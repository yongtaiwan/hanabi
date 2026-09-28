# Hanabi simulation dataset: 500 games per bot configuration

The recorded games used for the paper's simulation results: **3,500 games and
174,132 moves**, covering seven strategy/player-count configurations. These are
the frozen September 12, 2026 runs, not newly simulated or selected examples.
Every configuration contains all 500 seeds from **42 through 541**, inclusive.

## Download and contents

- [games.csv](games.csv): all 3,500 game-level records, one row per game.
- [summary.csv](summary.csv): seven configuration-level result rows.
- [manifest.json](manifest.json): provenance, row counts, and SHA-256 checksums.
- [Full replay evidence (JSON.gz)](../../analysis/reviewer-stats-2026-09-12/evidence.json.gz):
  every shuffled deck and recorded move, including explanations and pre-move state.
- [Detailed original summary](../../analysis/reviewer-stats-2026-09-12/summary.json):
  Wilson 95% intervals, token frequencies, and paired-benchmark subsets.

Separate 500-row files are also available:

| Dataset | Players | Mean score | Sample SD | Perfect games |
| --- | ---: | ---: | ---: | ---: |
| [Simple 3p](simple-3p.csv) | 3 | 23.546 | 1.6003 | 182 / 500 (36.4%) |
| [Simple 4p](simple-4p.csv) | 4 | 23.650 | 1.8608 | 213 / 500 (42.6%) |
| [Simple 5p](simple-5p.csv) | 5 | 23.034 | 1.7853 | 115 / 500 (23.0%) |
| [Dynamic 3p](dynamic-3p.csv) | 3 | 24.590 | 1.3659 | 385 / 500 (77.0%) |
| [Cheater 3p](cheater-3p.csv) | 3 | 24.940 | 0.2767 | 475 / 500 (95.0%) |
| [Cheater 4p](cheater-4p.csv) | 4 | 24.852 | 0.4843 | 448 / 500 (89.6%) |
| [Cheater 5p](cheater-5p.csv) | 5 | 24.786 | 0.5299 | 416 / 500 (83.2%) |

The CSV files are UTF-8 with headers, comma delimiters, and no missing values.
Boolean fields use `0`/`1`. Summary rates are fractions in `[0, 1]`, not percentages.
The combined file and seven separate files contain the **same** games; do not
concatenate them together and double count observations.

## Experimental setup and limitations

All seats in a game use the named bot. `Simple` means Simple Recommendation
(mod 8, 12, or 16 for 3, 4, or 5 players); `Dynamic` means the stateful 3-player
Dynamic Recommendation; `Cheater` means CommonSenseCheater, an **illegal
full-information benchmark** that sees its own hand but not future draws. It is
not a proven optimal strategy or mathematical upper bound.

Games use the standard 50-card, five-color deck: three 1s, two each of 2/3/4,
and one 5 per color. Hands start with five cards for 3 players and four for
4/5 players; the bank has eight hint tokens and three lives. The engine can
stop early when no more points are possible (`auto_end_when_no_points_possible=True`).

Within each player count, strategies use identical decks for the same seed,
allowing paired comparisons. Different player counts change the deal, hand size,
and turn economy; do not interpret their means as a head-to-head bot ranking.
These seeds were used during development, not a held-out validation set. Bot
results do not establish human performance or ease of learning. Cox's published
results are **not rows in this dataset**; they are separate comparison evidence.

## Game-level data dictionary

| Column | Type | Meaning |
| --- | --- | --- |
| `game_id` | string | Unique ID: lowercase strategy, player count, seed. |
| `strategy` | string | `Simple`, `Dynamic`, or `Cheater`. |
| `players` | integer | Number of players: 3, 4, or 5. |
| `seed` | integer | Deck seed, 42–541 inclusive. |
| `paper_score` | integer | Paper score, 0–25; zero after the third failed play. |
| `raw_score` | integer | Engine's final firework total, retained even after all lives are lost. |
| `perfect_game` | boolean | 1 exactly when `paper_score == 25`. |
| `lives_remaining` | integer | Final lives, 0–3. |
| `category` | string | Exclusive outcome category, defined below. |
| `needed_last_copy_lost` | boolean | At any point, a discard/failed play lost a final copy still needed for a firework. |
| `playable_cards_left` | integer | Playable physical cards in all hands at termination. |
| `moves` | integer | Number of completed recorded moves. |
| `hints`, `plays`, `discards` | integer | Move counts; their sum equals `moves`. Plays include failures. |
| `failed_plays` | integer | Unsuccessful plays; equals `3 - lives_remaining`. |
| `zero_hint_moves` | integer | Moves with zero hint tokens immediately before the move. |
| `last_resort_plays` | integer | Play moves whose recorded explanation identifies a "last resort" fallback. |
| `deck_sha256` | string | SHA-256 of the 50 card codes joined by one ASCII space, no trailing newline. |

The natural key is `(strategy, players, seed)`. Join replay evidence using this
key; the JSON archive uses the same fields and preserves their exact values.
Card codes use `R/Y/G/B/W` plus rank 1–5. Replay decoding is implemented in
[`GameHistory`](../../hanabi/core/game_history.py).

### Scoring and outcome categories

Use **`paper_score`** to reproduce the manuscript. Only two games differ from
`raw_score`: Simple 4p seed 131 (raw 4, paper 0) and Dynamic 3p seed 481 (raw 23,
paper 0). Both lost all three lives. No records were excluded.

Categories are assigned in this order, so each game belongs to exactly one:

1. `perfect`: score 25.
2. `all_lives_lost`: the third failed play ended a non-perfect game.
3. `needed_last_copy_lost`: lives remained, but a needed final copy was lost.
4. `tempo`: neither loss category applied, but the final round ended below 25.

Last-copy loss includes a currently playable card's last copy, so it is not
identical to the convention's narrower `critical` card type. These categories
describe outcomes, not causal estimates of points lost. All recorded tempo
games still had a playable card in a hand. Moves within a game are dependent;
do not treat the 174,132 moves as independent trials.

`summary.csv` uses arithmetic means and sample standard deviations (`n - 1`).
Its four outcome columns are counts summing to `games`; `perfect_game_rate`
equals `perfect_games / games`. `perfect` duplicates `perfect_games` so the
exclusive partition can be summed directly.

## Provenance and verification

- Recorded engine revision: [`c516c769e78b341dff6d14e182e7a683dd4f141e`](https://github.com/yongtaiwan/hanabi/commit/c516c769e78b341dff6d14e182e7a683dd4f141e).
- Evidence and original analysis first published in commit
  [`b041097a1c64086460a9b54f11a02e2310ba545a`](https://github.com/yongtaiwan/hanabi/commit/b041097a1c64086460a9b54f11a02e2310ba545a).
  The engine files are unchanged between these revisions.
- [Exporter and validation checks](../../analysis/export_paper_dataset.py) use only
  Python's standard library and the frozen compressed evidence. They do not run bots.
- [Replay checks](../../analysis/test_reviewer_stats.py) independently replay selected
  seeds and every all-lives-lost/final-fallback edge case.

From the repository root, using Python 3.10 or newer:

```sh
# Verify all exported bytes, seeds, paired decks, score rules, and summary values.
python3 analysis/export_paper_dataset.py --check
python3 -m unittest discover -s analysis -p 'test_*.py'

# Regenerate the CSV files from the frozen archive (not new simulations).
python3 analysis/export_paper_dataset.py

# Optional: run new simulations into a SEPARATE directory.
python3 analysis/reviewer_stats.py --games 500 --output /tmp/hanabi-new-run
```

To reproduce the historical simulation code, use revision `b041097` in a separate
checkout. New runs from later revisions must not silently replace this frozen
dataset. For citations, identify this dataset, the repository, frozen run date,
and the exact publication commit through GitHub's permalink feature.
