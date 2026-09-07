# Five-player Simple Recommendation (`FivePlayerRecommendationPlayer`)

This note summarizes the **5-player Simple Recommendation** AI (`hanabi.ai.five_player_recommendation`), its hint encoding and batch results, and how move reasoning appears in the GUI and console.

Implementation lives in `hanabi/ai/five_player_recommendation.py`.

---

## Role

- **Players:** exactly **5**, standard settings from `create_standard_game_settings(5)`.
- **Idea:** Extension of the 4-player Simple strategy: teammates share a **modular code** over visible recommendations with **16 hint channels** (mod **16**), using **index-based** left number, left color, right number, and right color hints toward **next**, **next+1**, **next+2**, or **next+3** (global seat indices `0`–`4`; **next+3** is the previous seat in 5p).

---

## Simulation batch (500 games)

All seats used `FivePlayerRecommendationPlayer`; `seed=42` (`deck_seed = 42 + run_id`).
Results were regenerated on 2026-09-06 from the current code.

| Metric | Value |
|--------|--------|
| Completed | 500 / 500 |
| Failures | 0 |
| Score min / max | 17 / 25 |
| Mean score | 23.03 |
| Std dev | 1.79 |
| Perfect (25) | 115 games (23.0%) |

Command:

```bash
python3 run_ai_experiments.py --players 5 --runs 500 --seed 42 --ais five_player_recommendation
```

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

Codes **0–12** are actionable on the wire:

| Code | Meaning |
|------|---------|
| 0 | No info (fallback) |
| 1–4 | Play slot `code - 1` (playable 5, else lowest-rank playable) |
| 5–8 | Slot `code - 5` is **USELESS** |
| 9–12 | Slot `code - 9` is **DISPENSABLE** |

Mod-16 decode values **13–15** are unused.

---

## Decoding (observers that are not the hinter)

Non-hinters update a decoded recommendation for themselves:

`(channel_id - sum_of_other_peers) % 16`

In 5p, **three** other peers’ codes are summed (all other hands visible in `PlayerView`).

Each seat keeps only the latest actionable recommendation. A new hint replaces it, and any play or discard by that seat clears it because positions shift.

**Decoded value** (receiver action):

| Code | Meaning |
|------|---------|
| 0 | No info → fall through to default discard (C1) |
| 1–4 | Play slot `code - 1` |
| 5–8 | Discard slot `code - 5` (USELESS) |
| 9–12 | Discard slot `code - 9` (DISPENSABLE) |
| 13–15 | Inert; no new action |

---

## Receiver without own card faces (`PlayerView`)

When the observer **is** the hint target, channel inference uses public fields only: number versus color, target offset from `pos`, and whether C1 is in the touched set. Left directions touch C1; right directions do not.

---

## Move selection order inside `play`

The bot tries, in order:

1. **Follow play** from decoded recommendation when the shared freshness rule allows.
2. **Strong hint**.
3. **Follow USELESS discard** (codes 5–8).
4. **Medium hint**.
5. **Follow DISPENSABLE discard** (codes 9–12).
6. **Weak hint**.
7. **Fallback:** discard C1.
8. **Last resort:** play the newest slot when no exact hint or discard is legal.

### Play-follow gate (shared)

Follow immediately, or after exactly one intervening team play while fewer than two lives have been lost. This is fixed for all committed Simple strategies; the alternate loose-gate experiment has been removed.

### Hint urgency

The committed paper rule is fixed in the bot rather than exposed as an experimental grid:

- **Strong:** a save, a new useless-discard recommendation, at least two new plays, or at least two combined recommendation changes.
- **Medium:** at least one new dispensable-discard recommendation that did not already qualify as strong.
- **Weak:** any remaining positive change.

The exact dispatch order is the eight-step list above: strong hint precedes both discard bands; the useless-discard band precedes medium; and the dispensable-discard band precedes weak.

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

- **3-player Simple Recommendation:** `ThreePlayerRecommendationPlayer` (`hanabi/ai/three_player_recommendation.py`).
- **4-player Simple Recommendation:** `FourPlayerRecommendationPlayer` (`hanabi/ai/four_player_recommendation.py`).
- **5-player paper strategy:** `RecommendationPlayer` (`hanabi/ai/recommendation_player.py`).
- **Tests:** `test/ai/test_five_player_recommendation.py`.
- **Experiments:** `run_ai_experiments.py` key `five_player_recommendation` (5p only).
