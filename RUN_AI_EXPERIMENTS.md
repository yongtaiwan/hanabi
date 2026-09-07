# Running AI comparison experiments

This guide covers `run_ai_experiments.py`, the batch runner that compares AIs on the same shuffled decks and writes results under `game_records/exp_ai_comparison/`.

For low-level directory layout (`games/all-games/`, symlinks, etc.), see [EXPERIMENTS.md](EXPERIMENTS.md).

## Prerequisites

From the repo root (with your venv activated if you use one):

```bash
cd "/path/to/hanabi"
python3 --version   # 3.10+ recommended
```

No extra install is required beyond the project’s normal dependencies (`PyYAML` is optional but recommended for `.yaml` stats files).

---

## Quick start: 500-game 4-player recommendation batch

Copy-paste this to run **500 games** of **4-player Simple Recommendation** only, with base seed **42**:

```bash
python3 run_ai_experiments.py \
  --players 4 \
  --runs 500 \
  --seed 42 \
  --ais four_player_recommendation
```

Typical runtime: on the order of **10–30 seconds** on a modern laptop (≈0.01s per game).

When it finishes, the terminal prints a short summary and paths like:

```text
Experiment ID: 20260602_173418/4p (runs=500, seed=42)
Statistics saved to: game_records/exp_ai_comparison/20260602_173418/4p/statistics.json
Game records saved to: game_records/exp_ai_comparison/20260602_173418/4p/games/all-games
```

Human-readable overview:

```text
game_records/exp_ai_comparison/<timestamp>/summary.md
```

---

## What gets written

Each batch uses a timestamp folder:

```text
game_records/exp_ai_comparison/
  <timestamp>/
    settings.yaml          # batch config (player counts, runs, seed, --ais)
    summary.md             # comparison table + per-AI stats (start here)
    4p/
      settings.yaml        # table rules for 4p (tokens, hand size, …)
      statistics.json      # per-run scores + aggregated summary (or .yaml)
      games/
        all-games/
          run_000_ai_FourPlayerRecommendationPlayer.json
          run_001_ai_FourPlayerRecommendationPlayer.json
          …
```

- **`summary.md`** — quick read: avg / best / worst / perfect %.
- **`statistics.json`** — every run’s score, move count, `end_reason`, `deck_seed`, path to replay file.
- **`games/all-games/`** — full replays for GUI replay or debugging a single run (e.g. `run_158_…`).

Run `N` uses deck seed `base_seed + N` (with `--seed 42`, run 0 → seed 42, run 89 → seed 131).

---

## CLI reference

| Flag | Default | Meaning |
|------|---------|---------|
| `--players N …` | `2 3 4 5` | Player counts to run (space-separated). |
| `--runs N` | `10` | Games per player count **per AI** listed in `--ais`. |
| `--seed N` | `42` | Base deck seed (run *i* uses `seed + i`). |
| `--ais NAME …` | all interactive AIs | Which bots to include (see table below). |
| `--no-outcome-baseline` | off | Skip auto **CommonSenseCheater** on 5p (irrelevant for 4p-only batches). |

### `--ais` names

| CLI name | Class | Valid player count |
|----------|--------|-------------------|
| `random` | RandomPlayer | 2–5 |
| `commonsense` | CommonSensePlayer | 2–5 |
| `montecarlo` | MonteCarloPlayer | 2–5 |
| `recommendation` | RecommendationPlayer (paper) | **5 only** |
| `three_player_recommendation` | ThreePlayerRecommendationPlayer | **3 only** |
| `four_player_recommendation` | FourPlayerRecommendationPlayer | **4 only** |
| `commonsense_cheater` | CommonSenseCheater (benchmark) | 2–5 |
| `paper_cheater` | PaperCheater (benchmark) | 2–5 |

If you pass an AI for the wrong player count, it is **skipped** (not an error). Example: `recommendation` is ignored when `--players 4`.

---

## More copy-paste examples

### Same as above, explicit one-liner

```bash
python3 run_ai_experiments.py --players 4 --runs 500 --seed 42 --ais four_player_recommendation
```

### 4p recommendation vs Common Sense (500 games each, same decks)

Each AI plays the **same 500 shuffles** (paired comparison within the batch):

```bash
python3 run_ai_experiments.py \
  --players 4 \
  --runs 500 \
  --seed 42 \
  --ais four_player_recommendation commonsense
```

Open `summary.md` for the comparison table.

### 3-player Simple Recommendation only (500 games)

```bash
python3 run_ai_experiments.py \
  --players 3 \
  --runs 500 \
  --seed 42 \
  --ais three_player_recommendation
```

### 5p paper recommendation (500 games)

```bash
python3 run_ai_experiments.py \
  --players 5 \
  --runs 500 \
  --seed 42 \
  --ais recommendation
```

### Smaller smoke test (10 games)

```bash
python3 run_ai_experiments.py \
  --players 4 \
  --runs 10 \
  --seed 42 \
  --ais four_player_recommendation
```

### Different seed (another 500-game sample)

```bash
python3 run_ai_experiments.py \
  --players 4 \
  --runs 500 \
  --seed 1000 \
  --ais four_player_recommendation
```

---

## Reading results

### `summary.md`

Example (single AI):

```markdown
| 4p | FourPlayerRecommendationPlayer | 23.48 | 25 | 17 | 35.2% | 54.8 | 0.013 |
```

- **Avg Score** — mean final score (max 25).
- **Win Rate** — fraction of games scoring **25** (perfect).
- **Avg Moves** — mean plies until game end.

### Inspect one bad run

```bash
# List worst scores from statistics.json (replace timestamp)
python3 -c "
import json
from pathlib import Path
p = Path('game_records/exp_ai_comparison/20260602_173418/4p/statistics.json')
rows = [(r['ai_results']['FourPlayerRecommendationPlayer']['score'],
         r['run_id'],
         r['ai_results']['FourPlayerRecommendationPlayer']['end_reason'])
        for r in json.loads(p.read_text())['runs']]
for s, rid, reason in sorted(rows)[:5]:
    print(f'run {rid:03d}: score {s} ({reason})')
"
```

Replay in GUI: **Load replay** → pick  
`game_records/exp_ai_comparison/<timestamp>/4p/games/all-games/run_XXX_ai_FourPlayerRecommendationPlayer.json`  
Turn on **Debug Replay** if you want live bot rationale.

---

## Comparing two batches

There is no separate “compare” script; each invocation creates a new timestamped folder. Compare manually:

1. Run batch A and note `<timestamp_A>/summary.md`.
2. Change code or settings, run batch B → `<timestamp_B>/summary.md`.
3. Diff the summaries:

```bash
diff game_records/exp_ai_comparison/20260602_173418/summary.md \
     game_records/exp_ai_comparison/20260608_195005/summary.md
```

Or compare mean scores only:

```bash
python3 -c "
import json
from pathlib import Path

def mean(batch):
    p = Path(f'game_records/exp_ai_comparison/{batch}/4p/statistics.json')
    scores = [r['ai_results']['FourPlayerRecommendationPlayer']['score'] for r in json.loads(p.read_text())['runs']]
    return sum(scores)/len(scores)

for b in ['20260602_173418', '20260608_195005']:
    print(b, f'mean={mean(b):.2f}')
"
```

(Replace timestamps with your batch IDs.)

---

## Programmatic use (Python)

Same logic as the CLI, inside a script or notebook:

```python
from run_ai_experiments import run_experiments

run_experiments(
    player_counts=(4,),
    num_runs=500,
    base_seed=42,
    enabled_ais=frozenset({"four_player_recommendation"}),
    include_outcome_baseline=False,  # no extra cheater on 5p; harmless for 4p-only
)
```

Lower-level API (single experiment, custom factories):

```python
from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField
from hanabi.ai import FourPlayerRecommendationPlayer

settings = create_standard_game_settings(4)
field = GameField.create_from_settings(settings, seed=42)

results = field.run_experiment(
    ai_factories={
        "FourPlayerRecommendationPlayer": lambda i: FourPlayerRecommendationPlayer(i),
    },
    num_runs=500,
    save_records=True,
    random_seed=42,
    experiment_id="my_custom_4p_test/4p",
)

field.save_statistics(results)
print(results.summary)
```

Records land under `game_records/exp_ai_comparison/my_custom_4p_test/4p/` (or the path implied by `experiment_id`).

---

## Tips

- **Reproducibility:** same `--seed` and `--runs` → same decks for run indices 0…N−1.
- **4p-only batches:** use `--no-outcome-baseline` to avoid ever pulling in cheater logic on mixed player-count runs; for `--players 4` alone it changes nothing.
- **Faster iteration:** use `--runs 50` or `--runs 100` while tuning, then a full `--runs 500` for reporting.
- **Loss analysis (4p):** optional helper `python3 tools/analyze_4p_losses.py` (see [FOUR_PLAYER_MINI_RECOMMENDATION.md](FOUR_PLAYER_MINI_RECOMMENDATION.md)).
