# Four-player Simple Recommendation (`FourPlayerRecommendationPlayer`)

This note summarizes the **4-player Simple Recommendation** AI (`hanabi.ai.four_player_recommendation`), its hint encoding and batch results, and how move reasoning appears in the GUI and console.

Implementation lives in `hanabi/ai/four_player_recommendation.py`.

---

## Role

- **Players:** exactly **4**, standard settings from `create_standard_game_settings(4)` (hands of **4** cards).
- **Idea:** Extension of the 3-player Simple strategy: teammates share a **modular code** over visible recommendations with **12 hint channels** (mod **12**), using index-based left/right number and color hints toward **next**, **next+1**, or **next+2**.

---

## Simulation batch (500 games)

All seats used `FourPlayerRecommendationPlayer`; `seed=42` (`deck_seed = 42 + run_id`).
Results were regenerated on 2026-09-06 from the current code.

| Metric | Value |
|--------|--------|
| Completed | 500 / 500 |
| Failures | 0 |
| Score min / max | 4 / 25 |
| Mean score | 23.66 |
| Std dev | 1.77 |
| Perfect (25) | 213 games (42.6%) |

Command:

```bash
python3 run_ai_experiments.py --players 4 --runs 500 --seed 42 --ais four_player_recommendation
```

---

## Seat rotation (same spirit as `RecommendationPlayer`)

For hinter `H` and hint target `T`:

`pos = (T - H - 1) % 4` ∈ {0, 1, 2}

- `pos == 0` → **next** player clockwise from `H`.
- `pos == 1` → **next+1**.
- `pos == 2` → **next+2** (the previous seat in 4p).

Channel `c` uses `direction = c % 3` and `hint_kind = c // 3`.

---

## The twelve channels (encoding)

Hints are real **number** or **color** moves (`NumberHint` / `ColorHint`). **Left / right** are **index-based** (hand slots `0..n-1`, C1 = index `0`).

| Channels | Hint type | Directions |
|----------|-----------|------------|
| 0–2 | Left number | next / next+1 / next+2 |
| 3–5 | Left color | next / next+1 / next+2 |
| 6–8 | Right number | next / next+1 / next+2 |
| 9–11 | Right color | next / next+1 / next+2 |

- **Left number / color:** rank or color of the card at **index 0**; touch all matching cards.
- **Right number / color:** the rank or color of the rightmost card that differs from C1; touch all matching cards. A right channel is unbuildable only when the hand is uniform on that attribute.

The hinter sums visible peers’ recommendation codes (mod 12) and emits channel **`sum_mod` only** (no `delta` shift). If that channel cannot be built on the target hand because the required right-number or right-color shape is unavailable, the hinter **skips hinting** and falls through to discard so receivers never decode a wrong value.

---

## Peer recommendation codes (what gets summed)

Per visible hand, first matching rule wins:

| Code | Meaning |
|------|---------|
| 0 | No info (fallback) |
| 1–4 | Play slot `code - 1` (playable 5, else lowest-rank playable) |
| 5–8 | Slot `code - 5` is **most useless** (prefer chop if useless/dispensable, else earliest non-chop slot) |

---

## Decoding (observers that are not the hinter)

Non-hinters update a decoded recommendation for themselves:

`(channel_id - sum_of_other_peers) % 12`

In 4p, **two** other peers’ codes are summed (both hands visible in `PlayerView`).

**Decoded value** (receiver action):

| Code | Meaning |
|------|---------|
| 0 | No info → fall through to default discard (C1) |
| 1–4 | Play slot `code - 1` |
| 5–8 | Discard slot `code - 5` (safe useless/dispensable target), unless hinting takes priority |
| 9–11 | Inert; no new action |

---

## Receiver without own card faces (`PlayerView`)

When the observer **is** the hint target, channel inference uses public fields only: number versus color, direction from `pos`, and whether C1 is in the touched set to distinguish left from right.

---

## Move selection order inside `play`

The bot tries, in order:

1. **Follow play** from decoded recommendation when the shared freshness rule allows.
2. **Strong hint** — encoded hint only if scoring says it helps teammates enough (`new_plays ≥ 2`, or `new_discards ≥ 1`, or `saves ≥ 1`).
3. **Follow most-useless-slot discard** (codes 5–8).
4. **Weak hint** — encoded hint if the candidate has any non-zero effect (`total ≥ 1`).
5. **Fallback:** discard **C1** (oldest), index `0`.
6. **Last-resort play of newest slot** when none of the above is legal — only reached at max hint tokens with an unbuildable exact channel (all-one-rank teammate hand).

### Play-follow gate (shared)

Follow immediately, or after exactly one intervening team play while fewer than two lives have been lost. Two or more intervening plays make the code stale.

**Note on dispatch order:** a qualifying hint stays before discard-follow because it broadcasts the next round of recommendations to every teammate.

---

## Hint system in this repo (move objects)

- **Number hint:** `NumberHint(teammate, cards, number)` — `cards` are **0-based** indices.
- **Color hint:** `ColorHint(teammate, cards, color)` — same index convention.

The bot only chooses moves that pass `is_move_legal` from its partial view.

---

## What you see in GUI / console

### Startup (4p + this AI)

- **Console:** Bright blue banner — mod-12 decode, channels 0–11.
- **GUI:** Similar banner when starting a one-player game with this AI.

### After each AI move

1. **Move line:** `[HH:MM:SS T##] …` — play / discard / hint.
2. **Reasoning line (if present):** `FourPlayerRecommendationPlayer ·` summary in yellow/cyan, prefixed with **`[4p mod-12]`** (channel, peer sum, exact vs shifted hint, follow-play/discard).

---

## Loss analysis

Tempo remains the dominant exclusive non-perfect category in the matched 500-deck comparison. See the project results artifact for the committed category counts and benchmark definition.
