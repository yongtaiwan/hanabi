# Three-player Simple Recommendation (`ThreePlayerRecommendationPlayer`)

This note summarizes the **3-player Simple Recommendation** AI (`hanabi.ai.three_player_recommendation`), its hint encoding and batch results, and how move reasoning appears in the GUI and console.

Implementation lives in `hanabi/ai/three_player_recommendation.py`.

---

## Role

- **Players:** exactly **3**, standard settings from `create_standard_game_settings(3)`.
- **Idea:** Like the 5-player paper **RecommendationPlayer**, teammates share a **modular code** over visible recommendations, but here the alphabet has **8 hint channels** (mod **8**), chosen by **index-based** “left / right” number and color hints to the **next** or **previous** seat (global indices `0`, `1`, `2`).

---

## Simulation batch (500 games)

All seats used `ThreePlayerRecommendationPlayer`; `seed=42` (`deck_seed = 42 + run_id`).
Results were regenerated on 2026-09-06 from the current code.

| Metric | Value |
|--------|--------|
| Completed | 500 / 500 |
| Failures | 0 |
| Score min / max | 16 / 25 |
| Mean score | 23.55 |
| Std dev | 1.60 |
| Perfect (25) | 182 games (36.4%) |

Command:

```bash
python3 run_ai_experiments.py --players 3 --runs 500 --seed 42 --ais three_player_recommendation
```

---

## Seat rotation (same spirit as `RecommendationPlayer`)

For hinter `H` and hint target `T`:

`pos = (T - H - 1) % 3`

- `pos == 0` → `T` is the **next** player clockwise from `H`.
- `pos == 1` → `T` is the **previous** player.

Channels **0–7** combine this **next vs previous** choice with the **hint direction and type** (left/right number or color); see below.

---

## The eight channels (encoding)

Hints are real **number** or **color** moves (`NumberHint` / `ColorHint`) built from the target hand. **Left / right** are **index-based** (reading hand slots `0..n-1` left to right, C1 = index `0`).

| Channel | Hint type | Target | Definition (brief) |
|--------|-----------|--------|-------------------|
| 0 | Left number | Next | Rank of card at **index 0**; touch **all** cards of that rank. |
| 1 | Left number | Previous | Same as 0, to previous teammate. |
| 2 | Left color | Next | **Color** of card at **index 0**; touch all cards of that color. |
| 3 | Left color | Previous | Same as 2, to previous teammate. |
| 4 | Right number | Next | Rank of the **rightmost** card whose rank ≠ slot-0's rank; touch all cards of that rank on the **full** hand. |
| 5 | Right number | Previous | Same as 4, to previous teammate. |
| 6 | Right color | Next | Color of the **rightmost** card whose color ≠ slot-0's color; touch all cards of that color. |
| 7 | Right color | Previous | Same as 6, to previous teammate. |

Examples (indices `0`–`4`):
- `R2 Y3 B4 R1 Y2` → **left number** = `2`'s at `[0, 4]`; **right number** = rightmost non-`2` rank, i.e. `R1` at slot `3` → `1`'s at `[3]`.
- `R3 R3 G3 B4 B5` → **left number** = `3`'s at `[0, 1, 2]`; **right number** = rightmost non-`3` = `B5` → `5`'s at `[4]`.

The right-number / right-color channel is **unbuildable** only when every card in the hand shares the same rank (channels 4, 5) or color (channels 6, 7) — in a 5-card hand that needs all 5 cards to be the same rank / color, which is rare (≤ 1 hand per 500-game batch in measured runs).

Modular **payload:** the hinter sums teammates’ recommendation codes (mod 8) and emits **only** the exact channel `cid == sum_mod8`. If that channel can’t be built on the target hand (the all-one-rank / all-one-color corner case above), the hint branch abstains and the dispatch chain falls through. There is no shifted-channel fallback: shifted hints would force every receiver to decode a wrong code at once, so they were removed.

---

## Decoding (observers that are not the hinter)

Non-hinters update a **decoded recommendation** for themselves:

`(channel_id - peer_rec) % 8`

where `peer_rec` is the **other** non-hinter peer’s recommendation code (the hand visible in `PlayerView`, excluding the hinter).

**Decoded value** (what the receiver is told to do):

| Code | Meaning |
|------|---------|
| 0 | Chop is safe to discard. |
| 1–5 | Play slot `code - 1` (1-based slot numbering in summaries). |
| 6 | Do **not** discard chop; discard elsewhere if following discard advice. |
| 7 | Inert; no new action. |

**Chop** = rightmost slot, index `hand_size - 1`.

---

## Receiver without own card faces (`PlayerView`)

`PlayerView` does **not** list your own hand. A receiver nevertheless identifies the channel from public information: number versus color, next versus previous, and whether C1 appears among the touched positions. Left directions always touch C1; right directions use an attribute different from C1 and therefore never touch it.

---

## Move selection order inside `play`

The bot tries, in order:

1. **Follow play** from decoded recommendation (when timing / errors allow — **paper gate**, see below).
2. **Strong hint** — encoded hint only if scoring says it helps teammates enough (`new_plays ≥ 2`, or `new_discards ≥ 1`, or `saves ≥ 1`).
3. **Follow chop/discard** recommendation (codes 0 or 6).
4. **Weak hint** — encoded hint if the candidate has any non-zero effect (`total ≥ 1`).
5. **Fallback:** discard **C1** (oldest), index `0`, like the paper bot’s default.
6. **Last-resort play of slot 0** when none of the above is legal — only reached at max hint tokens with an unbuildable exact channel (all-one-rank / all-one-color teammate hand). Caps the damage to at most one bomb on this seat instead of broadcasting a wrong-channel code to every teammate.

### Play-follow gate (**paper**, hardcoded)

`_plays_since_hint` counts **Play** moves by **any** player since the last encoding hint (resets to 0 when a hint is observed).

Follow a decoded **play** code (`1`–`5`) only when:

- `plays_since_hint == 0` (no team play since the hint), **or**
- `plays_since_hint == 1` **and** fewer than 2 bombs so far (`errors < 2`).

If two or more **Play** moves have happened since the hint, skip follow and fall through to hint / discard.

This shared freshness rule is used by the committed 3p, 4p, and 5p Simple strategies.

**Note on dispatch order:** a qualifying hint stays before discard-follow because it broadcasts the next round of recommendations to every teammate.

**Consume-on-follow:** whenever step 1 or step 3 returns a move, the acting seat is removed from the one-record-per-seat ledger. A new hint replaces rather than appends to that seat's entry, and any later play or discard clears the acting seat after its hand shifts. This prevents the same position recommendation from firing again on a different physical card.

---

## Hint system in this repo (move objects)

- **Number hint:** `NumberHint(teammate, cards, number)` — `cards` are **0-based** indices into that teammate’s hand.
- **Color hint:** `ColorHint(teammate, cards, color)` — same index convention.

The engine applies normal Hanabi legality (hint tokens, touching rules). The Simple strategy only chooses among moves that pass `is_move_legal` from its partial view.

---

## What you see in GUI / console (order and styling)

### Startup (3p + this AI)

- **Console:** After the welcome line, a **bright blue** line explains Simple Recommendation (mod-8, channels 0–7).
- **GUI (one-player mode with this AI):** Similar **blue** banner is printed when the game starts (terminal side).

### After each AI move (terminal mirror)

Both **GUI** (`gui_game.py` **on_move** path) and **console** (`console_game.py`) print:

1. **First line:** `[HH:MM:SS T##] …` — human-readable **move** (play/discard/hint), with console colorization on keywords where implemented. Hint lines look like `Pα hints Pβ: <rank or color> at <1-based slots>`.
2. **Second line (when the returned move implements `HasWhy`, i.e. `move.why()` is available):**  
   **`ThreePlayerRecommendationPlayer:` `<summary>`**  
   The Simple strategy wraps its chosen move with `move_with_why(...)` in `play()`, so the standard GUI/console rendering picks the rationale up automatically. Summaries are prefixed with **`[3p mod-8]`** and describe the chosen channel, peer sum mod 8, follow-play / follow-discard rules, etc.

So the **action** is always shown **before** the **AI explanation** on the terminal trace. The **canvas** game UI updates from the same move callback; the pattern above is the **copy/paste terminal log** order.

---

## Related classes

- **4-player Simple Recommendation:** `FourPlayerRecommendationPlayer` (`hanabi/ai/four_player_recommendation.py`).
- **5-player Simple Recommendation:** `FivePlayerRecommendationPlayer` (`hanabi/ai/five_player_recommendation.py`).
- **5-player paper strategy:** `RecommendationPlayer` (`hanabi/ai/recommendation_player.py`).
- **Tests:** `test/ai/test_three_player_recommendation.py`.
