# Three-player mini recommendation bot (`ThreePlayerRecommendationPlayer`)

This note summarizes the **3p Mini Rec** AI (`hanabi.ai.three_player_recommendation`), a batch simulation we ran on it, how its **hint encoding** relates to the Hanabi hint types in this codebase, and how **move vs AI reasoning** appears in the GUI and console.

Implementation lives in `hanabi/ai/three_player_recommendation.py`.

---

## Role

- **Players:** exactly **3**, standard settings from `create_standard_game_settings(3)`.
- **Idea:** Like the 5-player paper **RecommendationPlayer**, teammates share a **modular code** over visible recommendations, but here the alphabet has **7 physical channels** (mod **7**), chosen by **index-based** “left / right” number and color hints to the **next** or **previous** seat (global indices `0`, `1`, `2`).

---

## Simulation batch (500 games)

All seats used `ThreePlayerRecommendationPlayer`; before each `Game.create`, `random.seed(10_000 + game_index)` so decks differ per run.

| Metric | Value |
|--------|--------|
| Completed | 500 / 500 |
| Failures | 0 |
| Score min / max | 0 / 25 |
| Mean score | ~18.0 |
| Std dev | ~6.4 |
| Perfect (25) | 33 games |

Rough throughput on the machine used for the run was on the order of **250+ games/s** (engine-only, no UI).

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
| 4 | Right number | Next | **Minimum rank** among cards at indices **1..n-1**; then touch all cards of that rank on the **full** hand. |
| 5 | Right number | Previous | Same as 4, to previous teammate. |
| 6 | Right color | **Next only** | First standard suit (fixed color order) that appears on some slot **≥ 1**; touch all cards of that color. No “right color to previous” channel. |

Example (indices `0`–`4`): `R2 Y3 B4 R1 Y2` → **left number** is **2**’s (slots `0` and `4`); **right number** is **1**’s (slot `3`). If the right-number spec would produce the **same** move as left-number, that channel is **unavailable** for that hand.

Modular **payload:** the hinter sums teammates’ recommendation codes (mod 7), then picks the **smallest** `delta` in `0..6` such that channel `(sum + delta) % 7` yields a **legal** hint.

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

1. **Follow play** from decoded recommendation (when timing / errors allow).
2. **Give** an encoded hint (spend a hint token when legal).
3. **Follow chop/discard** recommendation (codes 0 or 6).
4. **Fallback:** discard **C1** (oldest), index `0`, like the paper bot’s default.

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
2. **Second line (if the mover has `get_decision_summary`):**  
   **`ThreePlayerRecommendationPlayer` ·** `<summary>`  
   - Class name: **bright yellow**  
   - Summary text: **cyan**  
   Summaries for this bot are prefixed with **`[3p mod-7]`** and describe the chosen channel, peer sum mod 7, follow-play/follow-discard rules, etc.

So the **action** is always shown **before** the **AI explanation** on the terminal trace. The **canvas** game UI updates from the same move callback; the pattern above is the **copy/paste terminal log** order.

---

## Related classes

- **5-player paper strategy:** `RecommendationPlayer` (`hanabi/ai/recommendation_player.py`).
- **Tests:** `test/ai/test_three_player_recommendation.py`.
