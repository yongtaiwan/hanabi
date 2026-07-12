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
| `chop_confirmed` | `true` iff chop was set by a discard decode (each of the `m` codes names one candidate) |

**Discard candidate:** any slot with `playability != playable`.

**Default chop** (deal, and when chop must be chosen with no newer sticky target):

- `chop` = **leftmost** discard candidate
- `chop_confirmed` = `false`
- `chop_hinted` = `false`

After a **recommended** chop leaves the hand, chop advances to the next newer discard candidate when one exists (§8.2), rather than jumping back to leftmost. Older-than-chop cards remain reachable as **later** discard-chain positions via wrap (§5.2).

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

Among slots with `playability == unknown`, order **newest first** (rightmost = type `1`). Type `k` marks the `k`-th slot **`playable`**.

**Negative inference:** every **newer** unknown (types `1 .. k-1`, i.e. strictly right of the marked slot) becomes **`unplayable`**. Older unknowns are unchanged. Discard chop fields are unchanged (except §8.2 if the marked slot was chop).

**Encode:** among physically playable unknowns, always choose the **newest** such card, then emit its from-new index `k`. Receivers may therefore treat “type `k`” as “newest playable is here; nothing newer is playable.”

### 5.2 Discard types

Discard codes = `{0,1,…,7} \ {1,…,N}`, ordered:

```
0, 7, 6, 5, 4, 3, 2   (skip any value that is a play code)
```

Let that list be `D[0], D[1], …, D[m-1]` (`m = 8 - N`).

Build the **discard chain** from current belief (skip every slot with `playability == playable`):

1. Start at **current chop** (default leftmost discard candidate if needed).
2. Then each **newer** discard candidate (`chop+1 … n-1`), in order.
3. Then **wrap** to older-than-chop discard candidates (`0 … chop-1`), oldest first.

**Discard codes only see the first `m = 8 - N` slots of that chain** (the code candidates).
Identified playables never occupy a candidate slot. Deeper chain slots are not indicable until
chop advances. Example with `m = 3` and chop on W3 in hand `[B2, Y5, W3, Y2, W1]`: candidates
are **W3 / Y2 / W1** (not B2). If Y5 were already `playable`, it would be skipped in the chain.

| Code | Meaning |
|------|---------|
| `D[0]` = usually `0` | Set chop to candidate `[0]` (current chop); `chop_confirmed = true` |
| `D[1]` = usually `7` | Set chop to candidate `[1]`; `chop_confirmed = true` |
| … | … |
| `D[m-1]` = usually last of `0,7,6,…` | Set chop to candidate `[m-1]`; `chop_confirmed = true` |

Each of the `m` codes uniquely names one candidate when at least `m` discard candidates exist.
If fewer than `m` candidates exist, only that many codes are usable.

**Every discard decode also play-closes the hand:**

- Every `unknown` → `unplayable`
- Existing `playable` slots unchanged

Rationale: discard info is sent only when the hinter has **no new playable** to identify on that hand (§6), so receivers may treat remaining unknowns as unplayable.

### 5.3 Indicable discard set

Exactly the first `m` wrapped-chain slots (§5.2). A card past position `m - 1` on the chain
**cannot** be indicated on this hint.

---

## 6. Encoding (peer code)

Computed per visible teammate hand, then summed mod 8.

**Order:** always encode **next** (`hinter+1`), then **previous** (`hinter+2`). Belief snapshot is still taken before either decode mutates state (§4.2); only the **encoder’s ranking** for prev may depend on next’s chosen discard identity (§6.4).

### 6.1 Prefer play

If there is at least one physically playable card among `playability == unknown` slots (after the usual duplicate-collapse / masks the bot already uses for honesty):

- Choose the **newest** such play slot (§5.1).
- Peer code = play type `k` for that slot.

### 6.2 Else discard — only among indicable options

If no new playable to identify, choose a discard recommendation **only** from the discrete indicable set:

| Option | Code | Implied chop after decode |
|--------|------|---------------------------|
| Candidate `[0]` (current chop) | `D[0]` | that slot, confirmed |
| Candidate `[j]` for `j = 1 .. m-1` | `D[j]` | that slot, confirmed |

Pick the **best** option in that set by the bot’s discard-quality heuristic (physical card kind / rank — encoder-only; receivers learn position only). Emit the matching code.

If the preferred physical discard is not in the indicable set, pick the best **indicable** alternative.

### 6.3 Recompute on each convention hint

Each convention hint **freshly** computes both peer codes from the current snapshot. Do not re-apply a stored relative discard instruction between hints beyond ordinary chop maintenance (§8).

### 6.4 Double-discard guard

When encoding a peer, treat these physical card identities as **almost-critical** on the
**other** peer (do not treat them as safe cross-hand trash):

1. If that peer’s code on **this** hint is a discard recommendation — the card at that implied chop.
2. If that peer already has a convention chop with `chop_hinted` or `chop_confirmed` from an
   **earlier** discard decode — that chop card, even when this hint gives them a **play** code.

Apply (2) in **both** directions (next↔prev). Apply (1) for prev after next is encoded (next is
encoded first).

Encoder discard ranking (lower = better to recommend):

`useless > in-hand duplicate > cross-hand duplicate > dispensable > soon-playable > almost-critical > critical > playable`

- **In-hand duplicate:** same identity ≥2 times in that hand. Among tied in-hand dups, prefer the
  **newest** copy (sticky chop then advances into later candidates).
- **Cross-hand duplicate:** same identity also appears in the other visible teammate hand, **and**
  that identity is **not** almost-critical (the other seat was not already told to discard it).
- **Soon-playable:** not yet playable, but every rank from the pile top+1 through this card appears
  somewhere in the hinter’s **visible** hands (the scored hand plus the other teammate). If those
  cards are never misdiscarded, this card can be played in sequence soon — prefer not discarding it
  vs ordinary dispensable trash.
- **Almost-critical** overrides cross-hand preference: if the other seat holds a recommended
  discard of that identity, the remaining copy is protected (worse than normal dispensable, better
  than a true singleton critical).
- **Critical tie-break:** among true criticals, prefer fewest fireworks points lost (still-reachable
  ranks from that card up to 5; already-dead higher ranks do not count — e.g. both 4s gone ⇒
  discarding a 3 loses 1). If equal loss, prefer **lower rank** (keep 5s for the play hint-token
  bonus), then older slot.
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

1. Prefer the **next newer** discard candidate (first slot `> chop` with `playability != playable`).
2. If none exists, fall back to the **leftmost** remaining discard candidate (or `None`).
3. Set `chop_confirmed = false` and `chop_hinted = false` (chop class `default` — keep position, drop urgency).

This keeps chop moving right after a recommended discard is spent. Older-than-chop cards stay
reachable later in the wrapped discard chain (§5.2), so they remain indicable when `m` allows.

### 8.3 Hand shifts

Play/discard shifts slots left; drawn cards append as `unknown` playability. Adjust `chop` index with the hand the same way other slot-indexed belief does. If the chop card is gone, §8.2 applies.

### 8.4 No safe-invalidation layer

With no legacy `safe` kind, middle-rank discard-pile invalidation of “safe” is **removed**.

---

## 9. Play strategy (`DynamicRecommendation3P`)

1. **Play** oldest (leftmost) `playable` if any.
2. Otherwise choose **hint vs discard chop** from hint quality × chop class (below).
3. If somehow no chop remains, discard slot `0`.

### 9.1 Chop class (own hand; mutually exclusive)

| Class | Definition |
|-------|------------|
| `confirmed` | `chop_confirmed` (set by any discard-code decode) |
| `default` | chop exists but not confirmed: opening leftmost, or the next chop after the previous one was spent (played/discarded / play-marked) |

### 9.2 Hint quality (would-be convention channel)

Evaluated only when a convention hint is **buildable**. If the type is unbuildable, treat quality as `mediocre` and use literal fallback when the matrix says hint.

| Class | Definition |
|-------|------------|
| `good` | Newly identifies a playable for the **next** player (exclusions: no topping-up; identity not already `playable` on a visible seat; not the same identity newly marked on both peers), **or** recommends **useless/duplicate** trash discard for next **and** a new playable for **prev** (no topping-up on prev; same identity exclusions) |
| `bad` | Channel would newly mark the **same** playable identity on both peers (**double-play**) |
| `mediocre` | Buildable convention hint that is neither `good` nor `bad` (or unbuildable → literal) |

### 9.3 Decision matrix

When **both** hint and discard are legal:

| hint \\ chop | confirmed | default |
|--------------|-----------|---------|
| **good** | Hint | Hint |
| **mediocre** | Discard | Hint |
| **bad** | Discard | Hint |

Guards outside the matrix:

- No hint tokens → discard (by chop / oldest)
- Discard illegal (max hints) → hint anyway (even `bad`)

Reading the matrix:

- `good` always beats chop (tempo: playable for next, or trash for next + playable for prev).
- `confirmed` beats non-good hints (trust prior discard recommendation).
- `bad` / `mediocre` with `default` still hint (avoid burning criticals / playables on unhinted chop).

---

## 10. Worked examples

### 10.1 Opening deal

- `N_play = 5` → play codes `1..5`, discard codes `D = [0, 7, 6]` (`m = 3`).
- Chop = slot `0`, unconfirmed → chop class `default`.
- Named discard options: `D[0]`/`D[1]`/`D[2]` → chain candidates `[0]`/`[1]`/`[2]` (slots `0`/`1`/`2`), each confirmed.

### 10.2 Confirm chop

Hinter encodes discard `0` for a peer with no playable to mark.

- Decode: all unknowns → unplayable; `chop_confirmed = true` → chop class `confirmed`.
- That player’s turn: matrix discards on any non-`good` hint.

### 10.3 Last discard code (`D[m-1]`)

`N_play = 5`, `m = 3`, chop on slot `2` with wrap chain `[2,3,4,0,1]`.

Candidates = first `m` = `[2,3,4]`. Code `6` (`D[2]`) sets chop to slot `4`, **confirmed**.
Slots `0`/`1` are not indicable on this hint.

### 10.4 After discarding confirmed chop

Chop card gone → new chop = **next newer** discard candidate if any, else leftmost; `confirmed = false`, `hinted = false` → chop class `default` until a new discard hint confirms again.

---

## 11. Decisions locked (design log)

| Topic | Decision |
|-------|----------|
| Mode switch | Removed; always §5 partition |
| Legacy kinds | Removed |
| `N` | `N_play` = count of `unknown` playability |
| Play codes | `1..N`; `0` never a play type |
| Play encode | Newest physically playable unknown; decode marks newer unknowns unplayable |
| Discard when | Only if no new playable to encode on that hand |
| Discard ⇒ play-close | Yes (`unknown` → `unplayable`) |
| Discard candidates | First `m = 8 - N` slots of wrapped chain; each `D[i]` names candidate `[i]`, confirmed |
| Type `0` | Candidate `[0]` = current chop |
| Chop after chop leaves | Next newer discard candidate if any, else leftmost; unconfirmed / unhinted |
| Encode discard choice | Best among **indicable** (first `m`) options only; prev sees next’s discard id as almost-critical |
| Encode order | Next peer code, then previous |
| Recompute | Fresh peer codes on each convention hint |
| Dispatch | Play leftmost playable, then hint×chop matrix (§9) |
| Mod-8 wire | Unchanged |
| Bot name | `DynamicRecommendation3P` (leave `DynamicHandType3P` untouched) |

---

## 12. Implementation checklist

- [x] New module/player `DynamicRecommendation3P` (do **not** modify `DynamicHandType3P`)
- [x] Belief: playability + `chop` + `chop_confirmed` only
- [x] Encode/decode per §5–§6 (first `m` wrapped-chain candidates)
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
| **Chop confirmed** | Chop set by a discard decode (each of `m` codes names one candidate) |
| **Discard chain** | Chop, then newer, then wrap older; codes use first `m = 8−N` only |
| **Peer code** | `0`–`7` one hand contributes to the mod-8 sum |
| **Channel** | `(peer + peer) mod 8` |

---

*Spec version: 2026-07-11 (`DynamicRecommendation3P` implemented).*
