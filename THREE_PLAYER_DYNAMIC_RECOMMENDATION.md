# Three-player dynamic recommendation convention (3p DR)

Human-executable convention for **3-player Hanabi** using **mod-8** hint encoding. This document is the canonical spec for **`DynamicRecommendation3P`**.

**Status:** implemented (`DynamicRecommendation3P`).

**Related (different bots):**

- Dual-mode dynamic hand-type (current bot): `DynamicHandType3P` — `THREE_PLAYER_DYNAMIC_HAND_TYPE.md`
- Classic 3p hint-hand-type: `HintHandSubtype3P` — [gDoc](https://docs.google.com/document/d/1KD2ZClK_OgtcjMIiKBMBUuzlSdV7nrGVEp5-n9IoZus/edit)
- 3p mini recommendation (mod 7): `THREE_PLAYER_MINI_RECOMMENDATION.md`
- 4p mini recommendation (mod 9): `FOUR_PLAYER_MINI_RECOMMENDATION.md`

---

## 1. Overview

### 1.1 Players and hands

- **Players:** exactly **3**, standard settings from `create_standard_game_settings(3)`.
- **Hand size:** up to **5** cards per player.
- **Slot indices:** `0` = **oldest** (left), `hand_size - 1` = **newest** (right). New draws append on the right.

### 1.2 Design principles

1. **Honest belief only** — track information deduced from **convention-encoded** hints, not literal rank/color hints and not “I can see your card.”
2. **One encoding scheme always** — no legacy / recommendation mode switch. Every hand uses the same play / discard code partition from current `N_play`.
3. **Play first, discard second** — a peer code means “play this unknown” when a new playable should be identified; otherwise it means discard guidance.
4. **Single chop + confirmation** — discard belief is one expected discard slot plus whether that slot was uniquely confirmed.
5. **Same wire format** — always **mod 8**, same eight physical hint channels as classic 3p hint-hand-type.

### 1.3 What this convention is not

- Not `DynamicHandType3P` (dual legacy↔recommendation) and not classic `HintHandSubtype3P`.
- Not a full card-identify tracker. No convention-derived `useless` / `safe` / `critical` kinds.
- Not updated by **literal** hints (including fallback when OLD/MID is unbuildable). Those may be played for tempo; they do **not** change convention belief.

---

## 2. Belief state

Each **seat** carries:

### 2.1 Per-slot playability (exactly one)

| Value | Meaning |
|-------|---------|
| `unknown` | Might still be playable |
| `playable` | Convention-identified playable |
| `unplayable` | Known not playable |

### 2.2 Per-hand chop

| Field | Meaning |
|-------|---------|
| `chop` | Expected discard slot, or `None` if no discard candidate |
| `chop_confirmed` | `true` iff chop was uniquely identified (named discard code, or catch-all with a singleton remainder) |

**Discard candidate:** any slot with `playability != playable`.

**Default chop** (deal, and after the chop card is discarded/played away with no fresh discard code):

- `chop` = **leftmost** discard candidate
- `chop_confirmed` = `false`

There is **no** legacy discard-kind layer and **no** per-slot `recommended` flag. Chop + confirmation are the only discard belief.

### 2.3 GUI

- Playable / unplayable overlays from playability.
- **Unconfirmed chop:** icon `/`
- **Confirmed chop:** icon `X`
- These are distinct marks (not the same icon with a modifier).

---

## 3. Counts (no mode switch)

```
N_play  = number of slots with playability == unknown
```

- Play codes use `1 .. N_play` (empty if `N_play = 0`).
- Discard codes are the remaining values in `{0,1,…,7}` (see §5).

Opening deal: `N_play = 5` → **3** discard codes (`0`, `7`, `6`). That is intentional; playtest for tempo impact.

---

## 4. Hint wire format (mod 8)

Unchanged from classic 3p hint-hand-type.

### 4.1 Eight channels (encoded type `0`–`7`)

| Type | Target | Shape preference | Content |
|------|--------|------------------|---------|
| 0 | next | OLD (else MID) | number |
| 1 | previous | OLD (else MID) | number |
| 2 | next | OLD (else MID) | color |
| 3 | previous | OLD (else MID) | color |
| 4 | next | NEW | number |
| 5 | previous | NEW | number |
| 6 | next | NEW | color |
| 7 | previous | NEW | color |

### 4.2 Channel sum

```
channel = (code_A + code_B) mod 8
```

Each non-hinter decodes:

```
decoded_self = (channel - code_peer) mod 8
```

Snapshot rule: when the hinter applies two peer codes, compute **both codes before** either decode mutates belief.

Literal / unbuildable fallbacks: no mod-8 decode (belief unchanged).

---

## 5. Code meanings (always)

Let `N = N_play` at decode/encode time for that hand.

### 5.1 Play types `1 .. N`

Among slots with `playability == unknown`, order **newest first**. Type `k` marks the `k`-th slot **`playable`**.

- Newer / older unknowns: **unchanged**
- Discard chop fields: **unchanged**

Play encoding picks by the usual rank heuristic among physically playable unknowns (prefer playable 5, else lowest rank), then maps that slot to its from-new index `k`.

### 5.2 Discard types

Discard codes = `{0,1,…,7} \ {1,…,N}`, ordered:

```
0, 7, 6, 5, 4, 3, 2   (skip any value that is a play code)
```

Let that list be `D[0], D[1], …, D[m-1]` (`m = 8 - N`).

Build the **discard chain** from current belief:

1. Start at **current chop** (default leftmost discard candidate if needed).
2. Then each **newer** discard candidate (`chop+1 … n-1`), in order.
3. Do **not** wrap to older-than-chop slots.

| Code | Meaning |
|------|---------|
| `D[0]` = usually `0` | **Confirm current chop** → `chop_confirmed = true` (chop slot unchanged) |
| `D[1]` = usually `7` | Set chop to 1st newer chain slot; `chop_confirmed = true` |
| `D[2]` = usually `6` | Set chop to 2nd newer; `chop_confirmed = true` |
| … | … |
| **`D[m-1]` (catch-all, last discard code)** | Only if no earlier discard code applies (§6). Let `R` be the remainder of the chain not named by `D[0]…D[m-2]`. Set `chop` to the **oldest** slot in `R`. If `\|R\| = 1`, `chop_confirmed = true`; otherwise `chop_confirmed = false`. |

**Every discard decode also play-closes the hand:**

- Every `unknown` → `unplayable`
- Existing `playable` slots unchanged

Rationale: discard info is sent only when the hinter has **no new playable** to identify on that hand (§6), so receivers may treat remaining unknowns as unplayable.

### 5.3 Catch-all

Catch-all never names an arbitrary deep card: it only selects the **oldest** slot in the unnamed remainder `R`.

- If `|R| = 1`, that card is uniquely determined → `chop_confirmed = true` (same urgency as a named code).
- If `|R| > 1`, chop moves to oldest of `R` with `chop_confirmed = false`.

A card that is neither current chop, nor a named newer chain slot, nor that oldest remainder **cannot** be indicated.

---

## 6. Encoding (peer code)

Computed **independently per visible teammate hand**, then summed mod 8.

### 6.1 Prefer play

If there is at least one physically playable card among `playability == unknown` slots (after the usual duplicate-collapse / masks the bot already uses for honesty):

- Choose the play slot by rank heuristic (§5.1).
- Peer code = play type `k` for that slot.

### 6.2 Else discard — only among indicable options

If no new playable to identify, choose a discard recommendation **only** from the discrete indicable set:

| Option | Code | Implied chop after decode |
|--------|------|---------------------------|
| Confirm current chop | `D[0]` | same chop, confirmed |
| Each named newer chain slot `j = 1 .. m-2` | `D[j]` | that slot, confirmed |
| Catch-all | `D[m-1]` | oldest of remainder `R`; confirmed iff `|R| = 1` |

Pick the **best** option in that set by the bot’s discard-quality heuristic (physical card kind / rank — encoder-only; receivers learn position only). Emit the matching code.

If the preferred physical discard is not in the indicable set, pick the best **indicable** alternative (possibly catch-all).

### 6.3 Recompute on each convention hint

Each convention hint **freshly** computes both peer codes from the current snapshot. Do not re-apply a stored relative discard instruction between hints beyond ordinary chop maintenance (§8).

---

## 7. Decoding

For each non-hinter hand, with `decoded` and that hand’s current `N_play`:

1. If `1 ≤ decoded ≤ N_play` → play decode (§5.1).
2. Else → discard decode (§5.2): play-close unknowns, then update `chop` / `chop_confirmed`.

---

## 8. Belief updates without convention hints

### 8.1 Successful play — playability reopening

Same frontier rule as before: on a qualifying successful play that newly opens the next rank with copies remaining:

- Every `unplayable` → `unknown` (all seats)
- `playable` unchanged
- **Chop fields unchanged** (discard guidance is not cleared by reopen)

### 8.2 After the chop card leaves the hand

When the chop slot is discarded or played:

- Set `chop` = leftmost remaining discard candidate (or `None`)
- Set `chop_confirmed` = `false`

### 8.3 Hand shifts

Play/discard shifts slots left; drawn cards append as `unknown` playability. Adjust `chop` index with the hand the same way other slot-indexed belief does. If the chop card is gone, §8.2 applies.

### 8.4 No safe-invalidation layer

With no legacy `safe` kind, middle-rank discard-pile invalidation of “safe” is **removed**.

---

## 9. Play strategy (`DynamicRecommendation3P`)

Ordered dispatch (first legal move wins):

1. **Play** leftmost `playable`
2. **Hint** if the convention hint would newly identify a playable for the **next** player (same urgency exclusions as DHT step-2: no topping-up, no double-play identity, etc.)
3. **Discard chop** if `chop_confirmed`
4. **Hint** (convention channel)
5. **Discard chop** if chop exists and not confirmed (default / catch-all / post-chop reset)

If hints are unavailable or unbuildable, fall through to step 5 (or discard slot `0` if somehow no chop).

---

## 10. Worked examples

### 10.1 Opening deal

- `N_play = 5` → play codes `1..5`, discard codes `D = [0, 7, 6]` (`m = 3`).
- Chop = slot `0`, unconfirmed.
- Named discard options: confirm `0`; set chop to 1st newer candidate (`7`); catch-all (`6`) → oldest remainder after those two named positions.

### 10.2 Confirm chop

Hinter encodes discard `0` for a peer with no playable to mark.

- Decode: all unknowns → unplayable; `chop_confirmed = true`.
- That player’s turn: step 3 discards chop before spending a hint.

### 10.3 Catch-all

`N_play = 0`, chain candidates `{0,1,2,3,4}`, `D = [0,7,6,5,4,3,2]`.

If named positions are only chop + several newer slots and the hinter’s best discard is deep:

- Last code catch-all sets chop to oldest slot **not** covered by `D[0]…D[m-2]`’s specific targets.
- If that remainder has one slot → `confirmed = true` (treat like a named confirm); if several → `confirmed = false` and prefer hint (step 4) before discarding (step 5).

### 10.4 After discarding confirmed chop

Chop card gone → new chop = leftmost discard candidate, `confirmed = false` → later turns use step 5 until a new discard hint confirms again.

---

## 11. Decisions locked (design log)

| Topic | Decision |
|-------|----------|
| Mode switch | Removed; always §5 partition |
| Legacy kinds | Removed |
| `N` | `N_play` = count of `unknown` playability |
| Play codes | `1..N`; `0` never a play type |
| Discard when | Only if no new playable to encode on that hand |
| Discard ⇒ play-close | Yes (`unknown` → `unplayable`) |
| Catch-all | Last discard code; oldest of remainder `R`; confirmed iff `|R| = 1` |
| Type `0` | Confirm **current** chop |
| Chop after chop leaves | Leftmost discard candidate, unconfirmed |
| Encode discard choice | Best among **indicable** options only |
| Recompute | Fresh peer codes on each convention hint |
| Dispatch | Play → step-2 hint → confirmed chop → hint → unconfirmed chop |
| Mod-8 wire | Unchanged |
| Bot name | `DynamicRecommendation3P` (leave `DynamicHandType3P` untouched) |

---

## 12. Implementation checklist

- [x] New module/player `DynamicRecommendation3P` (do **not** modify `DynamicHandType3P`)
- [x] Belief: playability + `chop` + `chop_confirmed` only
- [x] Encode/decode per §5–§6 (catch-all last)
- [x] Dispatch per §9
- [x] GUI: `/` unconfirmed chop, `X` confirmed chop (DHT keeps axe)
- [ ] Tests + A/B vs `DynamicHandType3P` / `HintHandSubtype3P`

---

## 13. Glossary

| Term | Meaning |
|------|---------|
| **N_play** | Count of `playability == unknown` |
| **Discard candidate** | `playability != playable` |
| **Chop** | Expected discard slot |
| **Chop confirmed** | Chop uniquely identified (named code, or singleton catch-all) |
| **Discard chain** | Chop, then newer discard candidates |
| **Catch-all** | Last discard code; oldest of remainder `R`; confirmed iff `|R| = 1` |
| **Peer code** | `0`–`7` one hand contributes to the mod-8 sum |
| **Channel** | `(peer + peer) mod 8` |

---

*Spec version: 2026-07-11 (`DynamicRecommendation3P` implemented).*
