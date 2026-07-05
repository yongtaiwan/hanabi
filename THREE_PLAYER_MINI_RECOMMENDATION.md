# Three-player mini recommendation bot (`ThreePlayerRecommendationPlayer`)

This note summarizes the **3p Mini Rec** AI (`hanabi.ai.three_player_recommendation`), a batch simulation we ran on it, how its **hint encoding** relates to the Hanabi hint types in this codebase, and how **move vs AI reasoning** appears in the GUI and console.

Implementation lives in `hanabi/ai/three_player_recommendation.py`.

---

## Role

- **Players:** exactly **3**, standard settings from `create_standard_game_settings(3)`.
- **Idea:** Like the 5-player paper **RecommendationPlayer**, teammates share a **modular code** over visible recommendations, but here the alphabet has **7 physical channels** (mod **7**), chosen by **index-based** “left / right” number and color hints to the **next** or **previous** seat (global indices `0`, `1`, `2`).

---

## Simulation batch (500 games)

All seats used `ThreePlayerRecommendationPlayer`; `seed=42` per batch (`deck_seed = 42 + run_id`).

| Metric | Value |
|--------|--------|
| Completed | 500 / 500 |
| Failures | 0 |
| Score min / max | 16 / 25 |
| Mean score | 23.52 |
| Std dev | 1.62 |
| Perfect (25) | 178 games (35.6%) |

Command:

```bash
python3 run_ai_experiments.py --players 3 --runs 500 --seed 42 --ais three_player_recommendation
```

History of recent improvements (same seed scheme, same 500-game batch):

| Change | Mean | Perfects | Worst |
|---|---:|---:|---:|
| Pre-tweaks (May baseline) | 22.16 | 65 | 15 |
| + consume-on-follow (clear rec after acting on it) | 22.55 | 82 | 16 |
| + "rightmost non-left" right-number/right-color spec | 22.86 | 115 | 16 |
| + removed shifted-hint mode (replace with play-slot-0 fallback) | 22.86 | 115 | 16 |
| + strong/weak hint scoring (ported from 4p mini-rec) | 23.52 | 178 | 16 |

(The shifted-hint removal and right-spec rows ship together: with the new right-spec, the exact channel is unbuildable only on all-one-rank / all-one-color hands — fewer than 1 occurrence per 500 games — so the shifted-hint branch is no longer needed and was removed in favour of a safer single-seat fallback.)

---

## Seat rotation (same spirit as `RecommendationPlayer`)

For hinter `H` and hint target `T`:

`pos = (T - H - 1) % 3`

- `pos == 0` → `T` is the **next** player clockwise from `H`.
- `pos == 1` → `T` is the **previous** player.

Channels **0–6** combine this **next vs previous** choice with **which physical hint shape** (left/right number or color) was sent; see below.

---

## The seven channels (encoding)

Hints are real **number** or **color** moves (`NumberHint` / `ColorHint`) built from the target hand. **Left / right** are **index-based** (reading hand slots `0..n-1` left to right, C1 = index `0`).

| Channel | Hint type | Target | Definition (brief) |
|--------|-----------|--------|-------------------|
| 0 | Left number | Next | Rank of card at **index 0**; touch **all** cards of that rank. |
| 1 | Left number | Previous | Same as 0, to previous teammate. |
| 2 | Left color | Next | **Color** of card at **index 0**; touch all cards of that color. |
| 3 | Left color | Previous | Same as 2, to previous teammate. |
| 4 | Right number | Next | Rank of the **rightmost** card whose rank ≠ slot-0's rank; touch all cards of that rank on the **full** hand. |
| 5 | Right number | Previous | Same as 4, to previous teammate. |
| 6 | Right color | **Next only** | Color of the **rightmost** card whose color ≠ slot-0's color; touch all cards of that color. No “right color to previous” channel. |

Examples (indices `0`–`4`):
- `R2 Y3 B4 R1 Y2` → **left number** = `2`'s at `[0, 4]`; **right number** = rightmost non-`2` rank, i.e. `R1` at slot `3` → `1`'s at `[3]`.
- `R3 R3 G3 B4 B5` → **left number** = `3`'s at `[0, 1, 2]`; **right number** = rightmost non-`3` = `B5` → `5`'s at `[4]`.

The right-number / right-color channel is **unbuildable** only when every card in the hand shares the same rank (channels 4, 5) or color (channel 6) — in a 5-card hand that needs all 5 cards to be the same rank / color, which is rare (≤ 1 hand per 500-game batch in measured runs).

Modular **payload:** the hinter sums teammates’ recommendation codes (mod 7) and emits **only** the exact channel `cid == sum_mod7`. If that channel can’t be built on the target hand (the all-one-rank / all-one-color corner case above), the hint branch abstains and the dispatch chain falls through. There is no shifted-channel fallback: shifted hints would force every receiver to decode a wrong code at once, so they were removed.

---

## Decoding (observers that are not the hinter)

Non-hinters update a **decoded recommendation** for themselves:

`(channel_id - peer_rec) % 7`

where `peer_rec` is the **other** non-hinter peer’s recommendation code (the hand visible in `PlayerView`, excluding the hinter).

**Decoded value** (what the receiver is told to do):

| Code | Meaning |
|------|---------|
| 0 | Chop is safe to discard. |
| 1–5 | Play slot `code - 1` (1-based slot numbering in summaries). |
| 6 | Do **not** discard chop; discard elsewhere if following discard advice. |

**Chop** = rightmost slot, index `hand_size - 1`.

---

## Receiver without own card faces (`PlayerView`)

`PlayerView` does **not** list your own hand. For observers who **are** the hint target, channel **cannot** be recomputed with full hand geometry. The code falls back to **public** classification: number vs color, next vs previous, and whether slot **0** appears among touched indices (approximation of left vs right). This can **misclassify** rare layouts where a **left** hint’s touched set does not include index `0`. When the hint target is **another** seat, full lists are used and inference matches the encoder.

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

This matches Cox et al. / the 5-player `RecommendationPlayer` timing rules. It is **stricter** than the **loose** gate used on 4p (see `FOUR_PLAYER_MINI_RECOMMENDATION.md`).

**Note on dispatch order:** keeping hint **before** discard-follow is intentional. A hint isn't just spending a token — it also broadcasts the **next round of play/discard codes to every teammate** via the encoded channel. An earlier experiment that put `_try_follow_chop_and_discard_recommendation` before `_try_give_encoded_hint` cratered the 500-game numbers (3p: 22.86 → 20.31, perfects 115 → 12, worst 16 → 3) because teammates were left without fresh codes long enough to bomb on stale play recommendations.

**Consume-on-follow:** whenever step 1 or step 3 returns a move, `self._my_decoded_recommendation` is cleared. The decoded recommendation is otherwise sticky (only overwritten when a *new* encoded hint is observed), and the global `_plays_since_hint` counter still permits a second “follow” if only one teammate has played since the last hint. Together those would re-fire the same slot recommendation on the next own-turn even though the originally indicated card has already been played and the hand shifted — that is exactly the failure mode seen in debug-replay logs (e.g. P3 re-playing slot 0 after only discards in between, then bombing). Clearing on consume makes the second own-turn after a hint fall through to discard / hint instead.

---

## Hint system in this repo (move objects)

- **Number hint:** `NumberHint(teammate, cards, number)` — `cards` are **0-based** indices into that teammate’s hand.
- **Color hint:** `ColorHint(teammate, cards, color)` — same index convention.

The engine applies normal Hanabi legality (hint tokens, touching rules). The mini-rec bot only chooses among moves that pass `is_move_legal` from its partial view.

---

## What you see in GUI / console (order and styling)

### Startup (3p + this AI)

- **Console:** After the welcome line, a **bright blue** line explains mini-rec (mod-7, channels 0–6).
- **GUI (one-player mode with this AI):** Similar **blue** banner is printed when the game starts (terminal side).

### After each AI move (terminal mirror)

Both **GUI** (`gui_game.py` **on_move** path) and **console** (`console_game.py`) print:

1. **First line:** `[HH:MM:SS T##] …` — human-readable **move** (play/discard/hint), with console colorization on keywords where implemented. Hint lines look like `Pα hints Pβ: <rank or color> at <1-based slots>`.
2. **Second line (when the returned move implements `HasWhy`, i.e. `move.why()` is available):**  
   **`ThreePlayerRecommendationPlayer:` `<summary>`**  
   The mini-rec bot wraps its chosen move with `move_with_why(...)` in `play()`, so the standard GUI/console rendering picks the rationale up automatically. Summaries are prefixed with **`[3p mod-7]`** and describe the chosen channel, peer sum mod 7, follow-play / follow-discard rules, etc.

So the **action** is always shown **before** the **AI explanation** on the terminal trace. The **canvas** game UI updates from the same move callback; the pattern above is the **copy/paste terminal log** order.

---

## Related classes

- **4p mini-rec:** `FourPlayerRecommendationPlayer` (`hanabi/ai/four_player_recommendation.py`).
- **5p mini-rec:** `FivePlayerRecommendationPlayer` (`hanabi/ai/five_player_recommendation.py`).
- **5-player paper strategy:** `RecommendationPlayer` (`hanabi/ai/recommendation_player.py`).
- **Tests:** `test/ai/test_three_player_recommendation.py`.
