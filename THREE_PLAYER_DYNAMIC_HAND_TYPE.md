# Three-player dynamic hand-type convention (3p DHT)

Human-executable convention for **3-player Hanabi** using **mod-8** hint encoding. This document is the canonical spec for `DynamicHandType3P` (`hanabi/ai/dynamic_hand_type_3p.py`).

**Related (different bots):**

- Pure-recommendation redesign draft: `DynamicRecommendation3P` — `THREE_PLAYER_DYNAMIC_RECOMMENDATION.md`
- 3p mini recommendation (mod 7): `THREE_PLAYER_MINI_RECOMMENDATION.md`
- 4p mini recommendation (mod 9): `FOUR_PLAYER_MINI_RECOMMENDATION.md`
- Legacy gDoc (superseded by this file for the upgraded convention): [hint-hand-type doc](https://docs.google.com/document/d/1KD2ZClK_OgtcjMIiKBMBUuzlSdV7nrGVEp5-n9IoZus/edit)

---

## 1. Overview

### 1.1 Players and hands

- **Players:** exactly **3**, standard settings from `create_standard_game_settings(3)`.
- **Hand size:** up to **5** cards per player.
- **Slot indices:** `0` = **oldest** (left), `hand_size - 1` = **newest** (right). New draws append on the right.

### 1.2 Design principles

1. **Honest belief only** — track information deduced from **convention-encoded** hints, not literal rank/color hints and not “I can see your card.”
2. **Two independent axes** — **playability** and **discard information** are updated separately; within discard, **legacy kind** and **recommendation state** are separate layers (§2.2).
3. **Maximum information per hint** — e.g. play type `3` identifies one playable card *and* proves newer candidates are unplayable.
4. **Two encoding modes per hand** — **legacy** (original hand-type convention) and **recommendation** (play/discard recommendations), chosen independently per hand from belief counts.
5. **Same wire format** — always **mod 8**, same eight physical hint channels as the original 3p DHT convention.

### 1.3 What this convention is not

- Not a full card-identify tracker (`Set[Card]`). Humans memorize **kinds**, not every possible card.
- Not updated by **literal** hints (including the rare “all 1s” fallback when OLD/MID encoding is unbuildable). Those hints may still be played for tempo; they do **not** change convention belief (for now).

---

## 2. Belief state

Each **seat** and **slot** carries:

### 2.1 Playability (exactly one)

| Value | Meaning |
|-------|---------|
| `unknown` | Might still be playable |
| `playable` | Convention-identified playable |
| `unplayable` | Known not playable |

### 2.2 Discard information (two layers)

Discard state is **not** one flat enum. Two layers apply to non-`playable` slots (and are stored per slot; `playable` slots ignore discard for counting — see §3.1).

#### Layer A — legacy discard kind (mutually exclusive)

From the **legacy** convention, when a card is not `playable`, its legacy kind is exactly one of:

| Legacy kind | Meaning |
|-------------|---------|
| `unknown` | No legacy discard kind identified yet |
| `useless` | Identified useless — **exempt** from `N_disc` |
| `safe` | Identified dispensable |
| `critical` | Identified critical — **exempt** from `N_disc` (never preferred discard until last resort) |

Legacy types `0` / `6` / `7` set the legacy kind on the **discard anchor** (§3.3), not on every slot.

#### Layer B — recommendation state (mutually exclusive per hand)

From the **recommendation** convention:

| Rec state | Meaning |
|-----------|---------|
| `unknown` | No active discard recommendation on this slot |
| `recommended` | This slot is the current discard recommendation |

At most **one** slot per hand has rec state `recommended`.

#### Combining layers

Legacy kind and rec state are **partially independent**. Examples:

- `(safe, recommended)` — safe card that is also the current recommended discard (wins dispatch priority over other safe cards).
- `(critical, unknown)` — critical; exempt from `N_disc` (no further discard-kind message needed).
- `(unknown, recommended)` — recommended discard before legacy kind is known.

**Invariants (convention bugs if violated):**

- Legacy kind is exactly one of the four values above.
- Rec state is `unknown` or `recommended`; at most one `recommended` per hand.

### 2.3 Initial state (deal)

Every slot on every seat:

- `playability = unknown`
- legacy discard kind = `unknown`
- rec state = `unknown`

### 2.4 Slot lifecycle (play / discard / draw)

When a card leaves slot `i` (play or discard):

- Remove slot `i` from both axes; shift indices left.
- If the hand refills to max size, the new rightmost slot starts as `unknown` playability, legacy `unknown`, rec `unknown`.

When a slot is **discarded** by the owner:

- That slot’s belief row is gone (shift only).
- If it was `recommended`, the hand has **no** `recommended` until the next rec decode assigns one.

---

## 3. Counts and mode selection (per hand)

Counts are computed **per hand** from convention belief **only** (all three players derive the same values).

### 3.1 Definitions

```
N_play(slot)  := playability == unknown
N_disc(slot)  := needs_discard_info(slot)

needs_discard_info(slot) :=
    playability != playable
    AND legacy_kind != useless
    AND legacy_kind != critical
```

**Important:** `playable`, legacy-`useless`, and legacy-`critical` are exempt. Rec-`recommended` and legacy-`safe` still need discard information — a later hint may confirm or replace the current expected discard (§3.3–§3.4). Known `critical` is skipped by the discard anchor so a later legacy `0`/`6`/`7` can describe the next unsettled slot (usually current chop).

```
N_play  = number of slots with playability == unknown
N_disc  = number of slots with needs_discard_info
```

### 3.2 Mode

| Condition | Mode |
|-----------|------|
| `N_play + N_disc > 8` | **Legacy** |
| `N_play + N_disc ≤ 8` | **Recommendation** |

**Worked examples:**

| Situation | N_play | N_disc | Sum | Mode |
|-----------|--------|--------|-----|------|
| Opening deal (5 unknown) | 5 | 5 | 10 | Legacy |
| After legacy `0`/`6`/`7`, no play since; chop useless, 4 others need discard | 0 | 4 | 4 | Recommendation |
| One playable identified, four still unknown playability | 4 | 4+ | 8+ | Legacy or Rec (depends on discard flags) |

A hand may **re-enter legacy** later if a successful play reopens `unplayable → unknown` and raises `N_play` enough that `N_play + N_disc > 8`.

### 3.3 Discard anchor

**Discard anchor** = **leftmost** (oldest) slot with `needs_discard_info`.

Used only for **legacy** types `0` / `6` / `7` (legacy kind is set on the discard anchor, not on every slot).

### 3.4 Chop (expected discard)

**Chop** = the slot the team **expects to discard next** on this hand, from **convention belief only** (same for all three players).

Among slots with `playability != playable` (**discard candidates**), each slot has a **discard priority tier**:

| Tier | Condition (first match wins) | Notes |
|------|------------------------------|-------|
| **1** | legacy kind `useless` | Highest discard urgency |
| **2** | rec state `recommended` | Beats `safe` / `unknown` / `critical` |
| **3** | legacy kind `safe` | |
| **4** | legacy kind `unknown` | Default when no legacy kind identified |
| **5** | legacy kind `critical` | Discard only when nothing better remains |

**Chop rule:**

1. Find the **best (lowest) tier** present among discard candidates.
2. Among candidates in that tier, chop = **leftmost** (oldest index).

**Examples:**

| Slots (index 0→4) | Chop | Why |
|-------------------|------|-----|
| useless@1, recommended@3 | **1** | Tier 1 beats tier 2 |
| recommended@3, safe@0 | **3** | Tier 2 beats tier 3 |
| safe@0, safe@2 | **0** | Tie-break older |
| critical@0, unknown@2 | **2** | Tier 4 beats tier 5 |

**Chop is not always the `recommended` slot** — e.g. when a legacy-`useless` card exists, chop is the leftmost useless.

**Uses:**

| Mechanism | Target |
|-----------|--------|
| Legacy types `0` / `6` / `7` | Legacy kind on **discard anchor** (§3.3) |
| Recommendation discard type `0` | Discard **chop** |
| Recommendation types `7, 6, 5, …` | Next **newer** **discard candidate** than chop (walk toward index `n-1`; do not wrap to older slots) |

When encoding or decoding discard type `0`, recompute chop from current belief — it may differ from rec `recommended` if tier 1–3 outranks the recommended slot.

---

## 4. Hint wire format (mod 8)

Unchanged from the original 3p DHT convention. Hints are real `NumberHint` / `ColorHint` moves.

### 4.1 Eight channels (encoded type `0`–`7`)

For hinter `H`, target `T`, hand size `n`, `to_next = (T == (H+1) mod 3)`:

| Encoded type | Direction | Shape | Hint kind |
|--------------|-----------|-------|-----------|
| 0 | next | OLD | number |
| 1 | previous | OLD | number |
| 2 | next | OLD | color |
| 3 | previous | OLD | color |
| 4 | next | NEW | number |
| 5 | previous | NEW | number |
| 6 | next | NEW | color |
| 7 | previous | NEW | color |

**Shape (index-based):**

- **OLD** — touches index `0` (and all matching rank/color on the hand); must not include the newest index when that would collapse OLD into NEW.
- **MID** — all touched indices lie strictly between `0` and `n-1`.
- **NEW** — touches index `n-1` (and all matching rank/color).

Types `0`–`3` prefer OLD, then MID, when building the physical hint. Types `4`–`7` always use NEW.

### 4.2 Channel arithmetic

The hinter sees both teammates’ hands and computes a **peer code** for each (see §5). Let `code_A` and `code_B` be those two values (`0`–`7`).

```
channel = (code_A + code_B) mod 8
```

The hinter emits a hint that encodes **`channel`** on the chosen target hand (same channel inference as today: recover type from direction × shape × number/color).

### 4.3 Decoding (non-hinter seats)

Each non-hinter `P` decodes a **hand type / recommendation** for their own hand:

```
decoded_P = (channel - code_peer) mod 8
```

where `code_peer` is the **other** non-hinter’s peer code (computed from public convention state the same way by all observers).

The hinter applies **both** non-hinter decodes when building belief (then propagates the full matrix to all seats, as today).

**Snapshot rule:** when the hinter applies two decodes in one step, peer codes must be computed **before** either decode mutates belief (same as current implementation).

### 4.4 Mixed modes on one hint

`P2` may be in **legacy** while `P3` is in **recommendation** on the same hint cycle. Each peer code uses **that hand’s** encoder (§5). Each decoder uses **that hand’s** decoder (§6–§7). This is intentional: mode depends only on hint-derived belief, which is public to all three players.

---

## 5. Peer codes (what gets summed)

### 5.1 Legacy mode peer code

When a hand is in **legacy** mode, its peer code is the **legacy hand type** `0`–`7` (§6.3 encoding side). This matches the original convention’s hand-type summarization.

**Note:** legacy hand-type **encoding** for the wire uses visible teammate cards and pile state for slots not already fixed by convention belief (same as the current bot). That is **not** convention belief — it is only how the hinter picks a transmittable type. **Mode selection** never uses visible cards.

### 5.2 Recommendation mode peer code

When a hand is in **recommendation** mode, its peer code is that hand’s **recommended action**, expressed as a type `0`–`7` via the dynamic partition (§7.2).

**Choosing the recommended action:** the **hinter** (and any encoder with the hand visible) uses **full rank/color** information plus pile state to pick the best play or discard, then maps it to a type `0`–`7`.

**Discard choice** must match **chop priority** (§3.4) when recommending “discard chop” (type `0`), and use the same tier logic when choosing among alternatives for types `7, 6, …`. For encoding only, the hinter may also use physical card kinds (`common_view.card_kind`) on visible cards to break ties within a tier when belief has not fixed legacy kind yet — receivers still learn **position only**, not rank/color.

**Play choice** uses the same priority heuristics as `RecommendationPlayer` / 4p mini-rec among `playability == unknown` slots (play rank 5, else lowest-rank playable), mapped to types `1`–`N_play`.

**What the receiver learns:** only **position** via decoded type. Rank and color are not part of convention belief.

**Filtering candidates:**

- Play: `playability == unknown`.
- Discard chain: **discard candidates** (`playability != playable`); chop-relative walk for types `7, 6, …`.

---

## 6. Legacy mode semantics

When `decoded` is interpreted in **legacy** mode for a hand:

### 6.1 Play types `1`–`5` — play *k*-th from new

Let `k = decoded` (`1 ≤ k ≤ 5`).

Among slots with `playability == unknown`, order by **newest first** (1st from new = newest index, 2nd from new = next older, …). Let `target` be the `k`-th slot in that order.

| Region (from new) | Playability update |
|-------------------|-------------------|
| Slots **1 … k−1** (newer than `target`) that are `unknown` | → `unplayable` |
| `target` | → `playable` |
| Slots **older than `target`** still `unknown` | **unchanged** (`unknown`) |
| Already `unplayable` / `playable` | unchanged |

Discard traits on all slots: **unchanged**.

**Rationale (honest information):** we learn the newest playable candidate among unknowns and that newer unknowns are not playable; we do **not** infer anything about older unknown slots.

### 6.2 No-playable types `0` / `6` / `7`

**Precondition:** after applying playability rules, the hand should be **play-closed**: no `unknown` and no `playable` on the playability axis — i.e. every slot is `unplayable` except any pre-existing `playable` (edge case; convention bug if `playable` coexists with a no-playable decode).

**Batch playability:**

- Every `unknown` → `unplayable`

**Discard anchor** = leftmost slot with `needs_discard_info` (§3.3). On **discard anchor** only, set legacy kind:

| Decoded type | Legacy kind on discard anchor |
|--------------|-------------------------------|
| `0` | `safe` |
| `6` | `critical` |
| `7` | `useless` |

Other slots’ legacy kinds unchanged. Rec state unchanged.

**Team knowledge:** “This hand has **no** playable cards until a qualifying play reopens playability (§8.1).”

### 6.3 Legacy hand-type encoding (peer code in legacy mode)

When **summing** the channel, legacy mode uses the original hand-type encoder:

- If the hand still has a playable candidate among slots not convention-masked: type `1`–`5` = position of newest such playable from the right (using visible cards + belief masks as today).
- Else: type `0` / `6` / `7` from the **discard anchor**’s physical kind (visible card + pile when legacy kind not belief-fixed).

See existing `dynamic_hand_type_3p.py` (`_encode_hand_type`, `_kinds_for_hand_type_encoding`) for the exact mask/collapse rules until the implementation is upgraded.

---

## 7. Recommendation mode semantics

When `decoded` is interpreted in **recommendation** mode for a hand with current `N_play`:

### 7.1 Play decode — types `1` .. `N_play`

`decoded = k` (`1 ≤ k ≤ N_play`) → among `playability == unknown`, order newest-first; mark the `k`-th slot **`playable`**.

| Region | Playability update |
|--------|-------------------|
| `target` (k-th unknown from new) | → `playable` |
| Newer / older unknowns | **unchanged** (`unknown`) |
| Already `unplayable` / `playable` | unchanged |

Discard traits unchanged.

**Why not the legacy “newer → unplayable” side effect:** recommendation play encoding chooses among physical playables by **rank heuristic** (playable 5 first, else lowest rank), not “newest playable.” A newer unknown may still be playable (e.g. recommend G5 while B2 is newer and playable). Marking newer slots `unplayable` would be dishonest.

### 7.2 Discard decode — types `0, 7, 6, 5, …`

Discard types are the values in `{0, 1, …, 7} \ {1, …, N_play}` ordered as:

```
0, 7, 6, 5, 4, 3, 2   (then skip any value ≤ N_play)
```

Map discard types to the **chop-relative chain** (§3.3):

| Type | Meaning |
|------|---------|
| `0` | discard **chop** (expected discard) |
| `7` | discard next **newer** than chop (still `needs_discard_info`) |
| `6` | next newer still |
| … | continue toward newest |

**Belief update on discard recommendation:**

- Set rec state `recommended` on the target slot.
- Set rec state `unknown` on every other slot (legacy kind unchanged).
- `playability` unchanged.

**Note:** a recommended discard may target a slot that is legacy-`useless`, `safe`, or `critical`. Rec `recommended` drives dispatch; legacy kind is not required to be `unknown`.

### 7.3 Recommendation peer code (encoding)

Compute the hand’s **intended** play or discard recommendation (§5.2), then encode:

- If recommending **play** on the `k`-th from-new unknown slot → peer code `k`.
- If recommending **discard** at chain position `m` (`m = 0` chop, `m = 1` next newer than chop, …) → peer code = the `m`-th value in the type list from §7.2.

---

## 8. Belief updates without convention hints

### 8.1 Successful play — playability reopening

Triggered only on a **successful** `Play` (pile advances).

**No change** when:

- Rank **5** was played (no new rank to open).
- The play did **not** newly open the next rank on that color (already advanced / illegal success path).
- **Suit dead:** after playing `(C, R)` with `R < 5`, every physical copy of `(C, R+1)` is already played or in the discard pile — no hand card can become newly playable because of this play.

**Change** when the play **opens the frontier** (newly makes `(C, R+1)` the next needed card on color `C`, and at least one copy of `(C, R+1)` could still exist in hands or deck):

- On **every seat, every slot** with `playability == unplayable` → `unknown`.
- `playable` slots unchanged.
- **All discard traits unchanged** (play does not affect discardability).

### 8.2 Discard pile — safe invalidation

When a **new** card appears in the discard pile (discard or misplay) and that event would invalidate “safe” under the existing middle-rank rule (`2`/`3`/`4` copies where the remaining copy is playable or critical — see `_pile_add_invalidates_safe_belief` in the current code):

- Clear legacy kind `safe` → `unknown` on **all slots on all seats** (only the legacy layer).
- Do **not** clear rec `recommended`, legacy `critical`, or legacy `useless`.

Rationale: a card we labeled `safe` may no longer be safe; an active discard recommendation should stay until the next rec hint retargets.

### 8.3 One fuse left — duplicate playable collapse

When the team has **one life** remaining and a **successful** play removes the last “extra” copy of a card identity still marked playable elsewhere:

- On **other** players’ hands, matching slots with `playability == playable` → `unknown`.
- Discard traits unchanged.

(Same intent as today’s `_invalidate_playable_matching_card_on_other_players`.)

### 8.4 Literal / fallback hints

If the bot (or human) gives a **non-convention** literal hint (e.g. early-game all-1s when OLD/MID cannot encode the channel):

- **No** convention belief update.
- **No** mod-8 decode for that hint.

---

## 9. Play strategy (`DynamicHandType3P`)

Ordered dispatch (first legal move wins). Discard steps follow **chop priority** (§3.4).

1. **Play** leftmost `playable`
   (FIFO by identification order scored ~+0.01 on a 1000-game A/B but needs remembering which playable was marked first — keep leftmost for humans.)
2. **Hint** if the convention hint would newly identify a playable for the **next** player (with double-play / topping-up exclusions)
3. **Discard** leftmost legacy-`useless` (tier 1 — same as chop when useless exists)
4. **Discard** slot with rec-`recommended` when that discard is legal (tier-2 explicit step; usually matches chop when no useless remains)
5. **Discard chop** when chop has legacy-`safe` (tier 3)
6. **Hint** (convention channel)
7. **Discard chop** (fallback — chop is tier 4 `unknown` or tier 5 `critical`)
8. **Discard** oldest (slot `0`)

Steps 3–5 and 7 all discard **chop** in the common case; they are split so identified useless / recommended / safe are acted on before spending hints or falling through to unknown/critical chop.

**Recommended play** = leftmost `playable` (step 1). Convention hints update belief directly; the player acts on belief flags on their turn.

---

## 10. Worked examples

### 10.1 Opening deal

All seats: five slots `unknown`, no discard flags.

- `N_play = 5`, `N_disc = 5`, sum `10` → **legacy** for every hand.
- First convention hints use legacy hand types; belief may identify first playables or chop kinds.

### 10.2 Transition to recommendation after “no playable”

`P2` receives legacy decode type `0` (chop safe). No successful play since.

- All `unknown` playability → `unplayable` (`N_play = 0`).
- Discard anchor: legacy `safe`; other four slots still need discard info (`N_disc = 4`).
- Sum `4 ≤ 8` → `P2` in **recommendation** mode.
- Next hints can carry discard recommendations on the chop chain for `P2` while `P3` might still be legacy.

### 10.3 Play type `3` side effects

Five-card hand; slots `0..4` all `unknown` playability. Decode play type `3`:

- 1st from new = slot `4`, 2nd = `3`, **3rd = slot `2`** → `playable`
- Slots `4` and `3` → `unplayable`
- Slots `0` and `1` stay **`unknown`**

### 10.4 Useless outranks recommended for chop

Hand: useless@1, rec `recommended`@3, safe@0.

- **Chop** = slot **1** (tier 1 useless), not slot 3.
- Dispatch step **3** discards slot 1 before step 4 would touch slot 3.
- After slot 1 is gone, chop recomputes; if slot 3 is still `recommended`, chop becomes slot 3.

### 10.5 `safe` anchor vs `recommended`

Discard anchor has legacy `safe` from type `0`. Rec `recommended` on slot 2; anchor at slot 0.

- **Chop** = slot **2** (tier 2 beats tier 3), not anchor@0.
- Rec discard type `0` means discard slot 2.

### 10.6 Mixed mode on one channel

- `P2`: legacy, peer code `4` (hand type).
- `P3`: recommendation, peer code `2` (play 2nd-from-new).
- `channel = (4 + 2) mod 8 = 6`.
- `P2` decodes `(6 - 2) mod 8 = 4` with **legacy** rules.
- `P3` decodes `(6 - 4) mod 8 = 2` with **recommendation** rules.

---

## 11. GUI

Convention belief indicators per slot (when implemented):

| State | Suggested indicator |
|-------|---------------------|
| `playable` | existing playable marker |
| legacy `useless` / `safe` / `critical` | existing kind markers |
| rec `recommended` | **trash can** icon (new) |

**Chop** highlight: expected discard slot (§3.4). Optional secondary marker on **discard anchor** (§3.3) when it differs from chop.

---

## 12. Resolved design decisions

| Topic | Decision |
|-------|----------|
| **12.1 Legacy encoding vs belief** | Keep current: mode/counts from belief only; legacy wire encoding may use visible teammate cards + belief masks. |
| **12.2 Clearing `recommended`** | Discarding the recommended card: slot shifts away; no extra step. Discarding a different card: rec `recommended` persists until the next convention hint retargets. |
| **12.3 Mode switching** | **Dynamic, no hysteresis.** Hands switch legacy ↔ recommendation as `N_play + N_disc` crosses `8` (e.g. reopening after a frontier play can return a hand to legacy). |
| **12.4 Encoding vs belief** | Hinter uses **full rank/color** on visible hands to **choose** the recommendation; receiver learns **position only** via decode. |

## 13. Open questions (remaining)

### 13.1 Chop-relative chain (no wrap)

Types `7, 6, …` walk **newer from chop** among discard candidates only; older slots with `needs_discard_info` are not reachable until chop moves (discard, or new `recommended` decode). Confirm in playtesting.

### 13.2 All-critical hands

`critical` slots are exempt from `N_disc` / discard anchor. They remain discard **candidates** at tier 5 so recommendation / fallback chop can still pitch one when nothing better remains.

### 13.3 Strong/weak hint gates

The upgraded bot keeps today’s “hint if identifies new playable” gate, not 4p mini-rec’s scored strong/weak gates. Revisit after experiments.

### 13.4 Literal fallback belief

Early literal 1-hints narrowing playability — **deferred** (no update for now).

---

## Appendix A: Glossary

| Term | Meaning |
|------|---------|
| **Discard anchor** | Leftmost slot with `needs_discard_info` (legacy `0`/`6`/`7` only) |
| **Chop** | Expected next discard: best tier among non-`playable` slots (§3.4), oldest on tie |
| **Discard candidate** | Any slot with `playability != playable` |
| **From new** | Order newest → oldest; 1st from new = rightmost index |
| **Legacy mode** | Original hand-type encode/decode |
| **Recommendation mode** | Dynamic play/discard type partition |
| **Peer code** | Value `0`–`7` one hand contributes to the mod-8 sum |
| **Channel** | `(peer + peer) mod 8`, encoded by the physical hint |
| **Convention belief** | Playability + legacy discard kind + rec state (encoded hints only) |

## Appendix B: Implementation checklist (for developers)

- [ ] Replace `Optional[CardKind]` matrix with playability + discard flags
- [ ] Per-hand mode selection from `N_play`, `N_disc`
- [ ] Dual encode/decode paths (legacy vs rec) with mixed-mode support
- [ ] Play decode side effects (§6.1) in both modes
- [ ] Rec discard chain mapping (§7.2)
- [ ] Play reopening + safe invalidation (§8)
- [ ] Dispatch: insert discard `recommended` (§9)
- [ ] Copy recommendation priority helpers into `dynamic_hand_type_3p.py` only
- [ ] GUI trash-can for `recommended`
- [ ] Tests mirroring §10 examples
- [ ] Module docstring pointer to this file

---

*Spec version: 2026-07-10 (chop priority tiers). Implementation pending sign-off.*
