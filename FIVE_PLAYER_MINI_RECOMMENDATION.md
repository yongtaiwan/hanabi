# Five-player mini recommendation bot (`FivePlayerRecommendationPlayer`)

This note summarizes the **5p Mini Rec** AI (`hanabi.ai.five_player_recommendation`), a batch simulation we ran on it, how its **hint encoding** relates to the Hanabi hint types in this codebase, and how **move vs AI reasoning** appears in the GUI and console.

Implementation lives in `hanabi/ai/five_player_recommendation.py`.

---

## Role

- **Players:** exactly **5**, standard settings from `create_standard_game_settings(5)`.
- **Idea:** Extension of the 4p mini-rec bot: teammates share a **modular code** over visible recommendations with **16 physical channels** (mod **16**), using **index-based** left number, left color, right number, and right color hints toward **next**, **next+1**, **next+2**, or **next+3** (global seat indices `0`–`4`; **next+3** is the previous seat in 5p).

---

## Simulation batch (500 games)

All seats used `FivePlayerRecommendationPlayer`; `seed=42` per batch (`deck_seed = 42 + run_id`).

| Metric | Value |
|--------|--------|
| Completed | 500 / 500 |
| Failures | 0 |
| Score min / max | 17 / 25 |
| Mean score | 23.03 |
| Std dev | 1.77 |
| Perfect (25) | 105 games (21.0%) |

Command:

```bash
python3 run_ai_experiments.py --players 5 --runs 500 --seed 42 --ais five_player_recommendation
```

Recent improvements (same seed scheme):

| Change | Mean | Perfects | Worst |
|---|---:|---:|---:|
| Initial 5p port (mod-16, loose play-follow gate) | 22.32 | 86 | 16 |
| + default **paper** play-follow gate (`PlayFollowGate.paper()`) | 23.03 | 105 | 17 |

Hint scoring (`strong` / `weak` gates, same thresholds as 4p) was grid-validated at 5p before the play-follow change; thresholds were already optimal (`np≥2 | nd≥1 | saves≥1` strong, `total≥1` weak).

Tuning tools: `tools/hint_threshold_grid_5p.py`, `tools/play_follow_gate_grid_5p.py`.

---

## Seat rotation

For hinter `H` and hint target `T`:

`pos = (T - H - 1) % 5` ∈ {0, 1, 2, 3}

- `pos == 0` → **next** player clockwise from `H`.
- `pos == 1` → **next+1**.
- `pos == 2` → **next+2**.
- `pos == 3` → **next+3** (the previous seat in 5p).

Channel `c` uses `direction = c % 4` and `hint_kind = c // 4`.

---

## The sixteen channels (encoding)

Hints are real **number** or **color** moves (`NumberHint` / `ColorHint`). **Left / right** are **index-based** (hand slots `0..n-1`, C1 = index `0`).

| Channels | Hint type | Directions |
|----------|-----------|------------|
| 0–3 | Left number | next / next+1 / next+2 / next+3 |
| 4–7 | Left color | next / next+1 / next+2 / next+3 |
| 8–11 | Right number | next / next+1 / next+2 / next+3 |
| 12–15 | Right color | next / next+1 / next+2 / next+3 |

- **Left number / color:** rank or color of the card at **index 0**; touch all matching cards.
- **Right number / color:** rank or color of the **rightmost** card whose rank/color ≠ slot-0's; touch all matching cards. Unbuildable when the hand is all one rank (right number) or all one color (right color).

The hinter sums visible peers’ recommendation codes (mod 16) and emits channel **`sum_mod` only** (exact channel, no shift). If that channel cannot be built, the hinter skips hinting and falls through to discard / last-resort play.

---

## Peer recommendation codes (what gets summed)

Same rules as 4p (codes **0–8** on the wire):

| Code | Meaning |
|------|---------|
| 0 | No info (fallback) |
| 1–4 | Play slot `code - 1` (playable 5, else lowest-rank playable) |
| 5–8 | Slot `code - 5` is **most useless** (prefer chop if useless/dispensable, else earliest non-chop slot) |

Mod-16 decode values **9–15** are inert (normalized to `0`).

---

## Decoding (observers that are not the hinter)

Non-hinters update a decoded recommendation for themselves:

`(channel_id - sum_of_other_peers) % 16`

In 5p, **three** other peers’ codes are summed (all other hands visible in `PlayerView`).

Each seat keeps at most **one** queued recommendation (`set_latest` on each hint — single-rec semantics).

**Decoded value** (receiver action):

| Code | Meaning |
|------|---------|
| 0 | No info → fall through to default discard (C1) |
| 1–4 | Play slot `code - 1` |
| 5–8 | Discard slot `code - 5` (most useless), unless hint tokens allow hinting first |

---

## Receiver without own card faces (`PlayerView`)

When the observer **is** the hint target, channel inference uses public fields only: number vs color, direction from `pos`, and whether slot **0** is in the touched set (left vs right approximation). Same caveats as 3p/4p mini-rec.

---

## Move selection order inside `play`

The bot tries, in order:

1. **Follow play** from decoded recommendation (when `plays_since_hint` and error count allow — **paper gate** by default).
2. **Strong hint** — encoded hint only if scoring says it helps teammates enough (`new_plays ≥ 2`, or `new_discards ≥ 1`, or `saves ≥ 1`).
3. **Follow most-useless-slot discard** (codes 5–8).
4. **Weak hint** — encoded hint if the candidate has any non-zero effect (`total ≥ 1`).
5. **Fallback:** discard **C1** (oldest), index `0`.
6. **Last-resort play of newest slot** when none of the above is legal — only reached at max hint tokens with an unbuildable exact channel.

### Play-follow gate (**paper**, default)

Configured via `PlayFollowGate` (constructor arg `play_follow_gate`; default `PlayFollowGate.paper()`).

Follow a decoded **play** code (`1`–`4`) only when:

- `plays_since_hint == 0`, **or**
- `plays_since_hint == 1` **and** fewer than 2 bombs so far (`errors < 2`).

If two or more **Play** moves have happened since the hint, skip follow and fall through.

This matches 3p mini-rec and Cox et al. The previous **loose** default (`PlayFollowGate()` with no `max_plays_since_hint` cap) allowed follow whenever `errors < 2`, even after many team Plays — that cost ~0.7 mean on 500-game batches at 5p. Legacy loose gate is still available for experiments:

```python
FivePlayerRecommendationPlayer(i, play_follow_gate=PlayFollowGate())
```

### Hint thresholds

Configured via `HintThresholds` (constructor arg `hint_thresholds`; default grid winner). See `tools/hint_threshold_grid_5p.py`.

**Note on dispatch order:** same as 3p/4p — hint (strong/weak) stays **before** discard-follow so teammates receive fresh codes before the team spends another turn on blind discards.

---

## Hint system in this repo (move objects)

- **Number hint:** `NumberHint(teammate, cards, number)` — `cards` are **0-based** indices.
- **Color hint:** `ColorHint(teammate, cards, color)` — same index convention.

The bot only chooses moves that pass `is_move_legal` from its partial view.

---

## What you see in GUI / console

### Startup (5p + this AI)

- **Console:** Bright blue banner — mod-16 decode, channels 0–15.
- **GUI:** Similar banner when starting a one-player game with this AI.

### After each AI move

1. **Move line:** `[HH:MM:SS T##] …` — play / discard / hint.
2. **Reasoning line (if present):** `FivePlayerRecommendationPlayer:` summary, prefixed with **`[5p mod-16]`** (channel, peer sum, follow-play/discard, strong/weak hint score).

---

## Related classes

- **3p mini-rec:** `ThreePlayerRecommendationPlayer` (`hanabi/ai/three_player_recommendation.py`).
- **4p mini-rec:** `FourPlayerRecommendationPlayer` (`hanabi/ai/four_player_recommendation.py`).
- **5-player paper strategy:** `RecommendationPlayer` (`hanabi/ai/recommendation_player.py`).
- **Tests:** `test/ai/test_five_player_recommendation.py`.
- **Experiments:** `run_ai_experiments.py` key `five_player_recommendation` (5p only).
