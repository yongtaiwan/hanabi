# Four-player mini recommendation bot (`FourPlayerRecommendationPlayer`)

This note summarizes the **4p Mini Rec** AI (`hanabi.ai.four_player_recommendation`), a batch simulation we ran on it, how its **hint encoding** relates to the Hanabi hint types in this codebase, and how **move vs AI reasoning** appears in the GUI and console.

Implementation lives in `hanabi/ai/four_player_recommendation.py`.

---

## Role

- **Players:** exactly **4**, standard settings from `create_standard_game_settings(4)` (hands of **4** cards).
- **Idea:** Extension of the 3p mini-rec bot: teammates share a **modular code** over visible recommendations with **9 physical channels** (mod **9**), using **index-based** left number, left color, and right number hints toward **next**, **next+1**, or **next+2** (global seat indices `0`–`3`). **Right color is not used** so six channels (left number / left color × three directions) are always buildable on every hand.

---

## Simulation batch (500 games)

All seats used `FourPlayerRecommendationPlayer`; `seed=42` per batch (`deck_seed = 42 + run_id`).

| Metric | Value |
|--------|--------|
| Completed | 500 / 500 |
| Failures | 0 |
| Score min / max | 17 / 25 |
| Mean score | 22.93 |
| Std dev | 1.87 |
| Perfect (25) | 124 games (24.8%) |

Recent improvements (same seed scheme):

| Change | Mean | Perfects | Worst |
|---|---:|---:|---:|
| Pre-tweaks (May baseline) | 22.77 | 110 | 17 |
| + "rightmost non-left" right-number spec | 22.93 | 124 | 17 |
| + removed shifted-hint mode (replace with play-slot-0 fallback) | 22.93 | 124 | 17 |

(The last two ship together: with the new right-number spec, the exact channel is unbuildable only on all-one-rank hands — 0 occurrences per 500 games in measured runs — so the shifted-hint branch is no longer needed and was removed in favour of a safer single-seat fallback.)

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

## The nine channels (encoding)

Hints are real **number** or **color** moves (`NumberHint` / `ColorHint`). **Left / right** are **index-based** (hand slots `0..n-1`, C1 = index `0`).

| Channels | Hint type | Directions |
|----------|-----------|------------|
| 0–2 | Left number | next / next+1 / next+2 |
| 3–5 | Left color | next / next+1 / next+2 |
| 6–8 | Right number | next / next+1 / next+2 |

- **Left number / color:** rank or color of the card at **index 0**; touch all matching cards.
- **Right number:** rank of the **rightmost** card whose rank ≠ slot-0's rank; touch all cards of that rank on the full hand. Unbuildable **only** when every card in the hand shares the same rank (very rare in a 5-card hand).

The hinter sums visible peers’ recommendation codes (mod 9) and emits channel **`sum_mod` only** (no `delta` shift). If that channel cannot be built on the target hand (the all-one-rank corner case above), the hinter **skips hinting** and falls through to discard so receivers never decode a wrong value. There is no shifted-channel fallback: shifted hints would force every receiver to decode a wrong code at once, so they were removed.

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

`(channel_id - sum_of_other_peers) % 9`

In 4p, **two** other peers’ codes are summed (both hands visible in `PlayerView`).

**Decoded value** (receiver action):

| Code | Meaning |
|------|---------|
| 0 | No info → fall through to default discard (C1) |
| 1–4 | Play slot `code - 1` |
| 5–8 | Discard slot `code - 5` (most useless), unless hint tokens allow hinting first |

---

## Receiver without own card faces (`PlayerView`)

When the observer **is** the hint target, channel inference uses public fields only: number vs color, direction from `pos`, and for numbers whether slot **0** is in the touched set (left vs right approximation). Color hints map to **left color** (`3 + pos`) because right color is unused.

---

## Move selection order inside `play`

The bot tries, in order:

1. **Follow play** from decoded recommendation (when `plays_since_hint` and error count allow).
2. **Give** an exact-channel encoded hint at `sum_mod` (spend a hint token when legal).
3. **Follow most-useless-slot discard** (codes 5–8).
4. **Fallback:** discard **C1** (oldest), index `0`.
5. **Last-resort play of slot 0** when none of the above is legal — only reached at max hint tokens with an unbuildable exact channel (all-one-rank teammate hand). Caps the damage to at most one bomb on this seat instead of broadcasting a wrong-channel code to every teammate, which is what the previous shifted-hint branch did.

Play follow timing:

- `plays_since_hint == 0`, or
- `plays_since_hint == 1` and fewer than 2 bombs so far.

**Note on dispatch order:** keeping hint **before** discard-follow is intentional. A hint isn't just spending a token — it also broadcasts the **next round of play/discard codes to every teammate** via the encoded channel. An earlier experiment that swapped these (`_try_follow_useless_slot_discard` before `_try_give_encoded_hint`) cratered the 500-game numbers (4p: 22.93 → 21.18, perfects 124 → 21, worst 17 → 1) because teammates were left without fresh codes long enough to bomb on stale play recommendations.

---

## Hint system in this repo (move objects)

- **Number hint:** `NumberHint(teammate, cards, number)` — `cards` are **0-based** indices.
- **Color hint:** `ColorHint(teammate, cards, color)` — same index convention.

The bot only chooses moves that pass `is_move_legal` from its partial view.

---

## What you see in GUI / console

### Startup (4p + this AI)

- **Console:** Bright blue banner — mod-9 decode, channels 0–8.
- **GUI:** Similar banner when starting a one-player game with this AI.

### After each AI move

1. **Move line:** `[HH:MM:SS T##] …` — play / discard / hint.
2. **Reasoning line (if present):** `FourPlayerRecommendationPlayer ·` summary in yellow/cyan, prefixed with **`[4p mod-9]`** (channel, peer sum, exact vs shifted hint, follow-play/discard).

---

## Loss analysis (500-game batch, move logs)

All **390** non-perfect games in this batch ended with **`deck_exhausted`** (not lives lost). The deck ran out before every color reached 5.

| Points short of 25 | Games |
|--------------------|-------|
| 1 | 109 |
| 2 | 90 |
| 3 | 74 |
| 4 | 44 |
| 5+ | 77 |

**Most common problem: tempo — too few cards played onto stacks before the deck ends.**

Compared to perfect games (sample of 40 each from the same batch):

| Per game (mean) | Imperfect | Perfect |
|-----------------|-----------|---------|
| Plays | ~23 | ~26 |
| Discards | ~13 | ~9 |
| Hints | ~23 | ~20 |
| Total moves | ~59 | ~55 |

Imperfect games are slightly **longer** but score lower because they **play less and discard more**: the team spends moves on the hint/discard cycle without converting enough into stacked cards. The narrow **play-follow window** (`plays_since_hint` gating) often defers plays until the next hint cycle. Dispatch-order tweaks have been measured: swapping the order so the bot follows a discard recommendation **before** giving a hint cratered scores (124 → 21 perfect games, worst 17 → 1) because hint payloads also carry the next round of codes to teammates, so withholding hints starves the protocol. The current order (hint before discard-follow) is the one that preserved the most plays-per-game while still letting follow-discard refill the hint bank when an exact channel was available.

Bombs are **not** the main loss mode after the strict-encoding fix (no 0-score games in this batch; worst score 17).

Optional tooling: `python3 tools/analyze_4p_losses.py` (reads `statistics.json` and game records under `game_records/exp_ai_comparison/`).

---

## Related classes

- **3p mini-rec:** `ThreePlayerRecommendationPlayer` (`hanabi/ai/three_player_recommendation.py`).
- **5-player paper strategy:** `RecommendationPlayer` (`hanabi/ai/recommendation_player.py`).
- **Tests:** `test/ai/test_four_player_recommendation.py`.
- **Experiments:** `run_ai_experiments.py` key `four_player_recommendation` (4p only).
