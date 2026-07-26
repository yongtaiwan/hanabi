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
- Not updated by **literal** hints (including fallback when OLD/MID are unbuildable for types
  ``0``–``3``). Those may be played for tempo; they do **not** change convention belief —
  including for the hint target. Bots never emit MID-shaped literals (MID is treated as
  convention by the hint target); OLD/NEW literals are rejected via the touch-set check.
- **Full-hand touch = abandon convention.** A hint that touches **every** slot in the target
  hand is never a mod-8 channel (receivers and observers leave belief unchanged). When the
  would-be type is unbuildable, literal fallback **prefers a full-hand number-1** hint when
  available (e.g. five 1s) — clear tempo and an unmistakable abandon signal.

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

Types `0`–`3` prefer OLD, then MID, when building the physical hint. Types `4`–`7` always use NEW.
Literal fallback never uses a MID-shaped hint (so the hint target can treat MID as convention).
A hint that touches the **entire** target hand is never built as a convention channel (NEW types
that would touch every slot are treated as unbuildable) and is never decoded as one.

### 4.2 Channel sum

```
channel = (code_A + code_B) mod 8
```

Each non-hinter decodes:

```
decoded_self = (channel - code_peer) mod 8
```

Snapshot rule: when the hinter applies two peer codes, compute **both codes before** either decode mutates belief.

Literal / unbuildable fallbacks: no mod-8 decode (belief unchanged). Full-hand touches are
always treated as abandon-convention (same: no decode), including when they would otherwise
match a NEW number/color shape (e.g. hinting five 1s).

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

**Order:** always encode **next** (`hinter+1`), then **previous** (`hinter+2`). Each peer code
uses that hand’s cards, **that seat’s current shared public belief** (chop / playability), and
public piles — independently reconstructible by every observer who sees the hand. Do **not**
wipe belief to a blank row when encoding (sticky chop must remain). Snapshot both peer codes
before either decode mutates state (§4.2).

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

Each convention hint **freshly** computes both peer codes from the **current** shared belief
snapshot (same chop / playability everyone already shares). “Freshly” means re-rank with
current cards + belief — not reset belief to blank. Do not re-apply a stored relative discard
instruction between hints beyond ordinary chop maintenance (§8).

### 6.4 Discard ranking (channel-safe)

Each peer’s discard code is chosen from that hand alone (plus public piles). Do **not** use the
other teammate’s cards or standing chop when picking the code — those inputs are not shared by
every observer who must recompute the same peer code.

Encoder discard ranking (lower = better to recommend):

`useless > in-hand duplicate > dispensable > critical > playable`

- **In-hand duplicate:** same identity ≥2 times in that hand. Among tied in-hand dups, prefer the
  **newest** copy (sticky chop then advances into later candidates).
- **Critical tie-break:** any critical discard already rules out a perfect score, so among
  criticals prefer only the **newest** slot (sticky chop can pivot to later non-criticals on a
  following hint). Do not rank by points lost or by rank.
- **Safe (dispensable) / residual playable:** prefer **higher rank**, then **older** slot.
- **Useless:** prefer **lower rank**, then **older** slot.

Hinter-only hint **quality** (whether to hint vs discard chop, §9) may still look at both visible
hands; that does not change the encoded peer codes.
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
3. Set `chop_confirmed = false` (chop class `default` — keep position, drop urgency).

This keeps chop moving right after a recommended discard is spent. Older-than-chop cards stay
reachable later in the wrapped discard chain (§5.2), so they remain indicable when `m` allows.

### 8.3 Hand shifts

Play/discard shifts slots left; drawn cards append as `unknown` playability. Adjust `chop` index with the hand the same way other slot-indexed belief does. If the chop card is gone, §8.2 applies.

### 8.4 No safe-invalidation layer

With no legacy `safe` kind, middle-rank discard-pile invalidation of “safe” is **removed**.

### 8.5 Full-hand abandon convention

If a hint’s touch set covers **all** slots of the target hand:

- Encode: do **not** emit that physical hint as a mod-8 channel (the corresponding NEW type is
  unbuildable when it would touch the whole hand).
- Decode: every observer (including the hint target) leaves convention belief unchanged.
- Literal fallback: among true non-convention hints, prefer **full-hand number-1**, then any
  other full-hand touch, then remaining OLD/NEW literals. If somehow every non-MID hint would
  still round-trip as convention and no full-hand option exists, a non-MID last resort is
  still emitted so the bot stays legal at max tokens (receivers may mis-decode — rare).

Rationale: a whole-hand 1s hint is obvious tempo and cannot be mistaken for a selective
OLD/MID/NEW band once the full-hand rule is shared.

---

## 9. Play strategy (`DynamicRecommendation3P`)

1. **`_try_protect_next_player`** — if next is about to burn a critical / unique playable,
   save them before cashing own tempo (§9.0).
2. **Play** oldest (leftmost) `playable` if any.
3. Otherwise choose **hint vs discard chop** from hint quality × chop class (below).
4. If somehow no chop remains, discard slot `0`.

### 9.0 Protect next (`_try_protect_next_player`)

Emergency override that runs **before** playing a known playable. Goal: prevent the immediate
next seat from discarding (or being forced to discard) a card that makes a perfect score
impossible — the same notion as experiment outcome “critical lost”: last remaining copy for
fireworks (`CRITICAL`, or unique `PLAYABLE`).

This step is **next-seat only** (the player who acts immediately after us). Prev’s chop danger
is left to next’s own protect step on their turn. Endgame / short-deck exceptions are deferred.

#### 9.0.1 Predicates

| Name | Definition |
|------|------------|
| **Dangerous chop card** | On a visible hand, the physical card at that seat’s current chop is `CRITICAL` or `PLAYABLE` under `common_view.card_kind` (last copy for fireworks). |
| **Next likely good** | Honest approx that next’s turn would produce a §9.2 `good` channel via “playable for their next” (**prev** from us). True when `hint_tokens > 0`, **prev** has **no** convention-`playable` yet, and prev has ≥1 `unknown` slot that is **physically playable**. (Does not assume good via “trash next + playable for us” — that needs our hidden hand. Residual holes: double-play / unbuildable.) |
| **Next would discard** | Next has no convention-`playable`, their chop card is dangerous, and either `hint_tokens == 0` **or** (chop is `confirmed` **and not** next-likely-good). Does **not** fully simulate next as hinter (their channel encodes our invisible hand). With tokens and `default` chop, treat as “would hint” (matrix). |
| **Hint protects next** | The **standard** would-be convention channel (`_project_channel` / §6 peer codes → one `enc_type`) is buildable, and **after** applying its projected decode to both non-hinter rows, “next would discard” is **false**. Typical successes: next newly marks a `playable` (they play), or next’s chop moves to a non-dangerous card. A channel that only helps **prev** does **not** count. Protect does **not** search alternate encodings or use belief-updating literals (literals never update convention belief). |
| **Token gift** | When `hint_tokens == 0`, an action that leaves `hint_tokens ≥ 1` for next’s turn. In this version that means **discard** only (+1 when below max). Ordinary plays do not change the token count unless the card is a **5**, but see §9.0.3 — we usually **cannot** know our playable is a 5. |

#### 9.0.2 Algorithm

When `_try_protect_next_player` runs:

1. If **not** “next would discard” a dangerous chop card → return no move (fall through).
2. **Save-hint:** if `hint_tokens > 0` and the standard convention channel **protects next** → give that hint (same builder as normal convention hints).
   - Precedence vs §9.2 `bad`: **critical save overrides `bad`** (still emit the channel when it protects).
   - If the channel is unbuildable, or buildable but does **not** protect next → do not save-hint (fall through to token gift / no move).
3. **Token gift** (only when `hint_tokens == 0`):
   - First build the **post-gift hypothetical**: same hands and belief, but `hint_tokens == 1`. Token gift is useful **only if** in that hypothetical “next would discard” a dangerous chop card is **false** (they would hint via the matrix, or play a convention-`playable`). If they would still discard danger with one token (typical: `confirmed` + non-`good` channel), token gift cannot save them — return no move.
   - Else, if own chop is **`confirmed`** and discard is legal → discard confirmed chop. Do **not** gift via `default` chop.
   - Do **not** use “play a 5 for refund” unless §9.0.3 says the leftmost playable is **known** to be a 5 (rare). Prefer discard gift when both would work.
4. Otherwise → return no move.

#### 9.0.3 Knowing a playable is a 5

Convention belief stores **playability only** — not rank or color. `DynamicRecommendation3P` does **not** track literal number/color touches on its own hand. So a leftmost `playable` mark does **not**, by itself, mean the card is a 5.

Honest ways we could know (optional; only the first is in scope if implemented later):

| Source | When it works |
|--------|----------------|
| **Public piles** | Every incomplete color already has top **4** (the only currently playable identities are 5s). Then any convention-`playable` must be a 5 → playing it refunds a token. |
| Literal number hint | Touched as 5 **and** marked playable — **out of scope** until/unless DR adopts hint-tracking for own cards. |
| Seeing own card | **Forbidden** (anti-cheat). |

**v1 decision:** token gift = **confirmed-chop discard only**. Skip play-5 refund unless public piles make every playable a 5 (implement that check or defer; do not assume rank from playability alone).

Notes:

- Protect may fire even when we have our own playable: deferring that play is intentional.
- If save-hint is available, it beats token gift and beats playing our own card.
- At 0 tokens with next on `confirmed` + non-`good`, only a prior save-hint (when tokens existed) could have helped; this step correctly no-ops and fallthrough may play.
- Prev-seat critical chop is out of scope for this step.
- Soft endgame exception (defer protect when `turns_left` is tight and the endangered card is not needed for remaining score) is **TODO**.

### 9.1 Chop class (own hand; mutually exclusive)

| Class | Definition |
|-------|------------|
| `confirmed` | `chop_confirmed` (set by any discard-code decode) |
| `default` | chop exists but not confirmed: opening leftmost, or the next chop after the previous one was spent (played/discarded / play-marked) |

### 9.2 Hint quality (would-be convention channel)

Evaluated only when a convention hint is **buildable**. If the type is unbuildable, treat quality as `fine` and use literal fallback when the matrix says hint.

| Class | Definition |
|-------|------------|
| `good` | Newly identifies a playable for the **next** player (exclusions: no topping-up; identity not already `playable` on a visible seat; not the same identity newly marked on both peers), **or** recommends **useless/duplicate** trash discard for next **and** a new playable for **prev** (no topping-up on prev; same identity exclusions) |
| `fine` | Buildable convention hint that is neither `good` nor `bad` (or unbuildable → literal). Includes double-play channels when **more than one life** remains (tempo preferred over bomb risk). |
| `bad` | Channel would recommend discard of the **same** mid-rank identity (`2`/`3`/`4`) on **both** peers (double mid-rank discard; ones excluded), **or** newly mark the **same** playable identity on **both** peers while **only one life** remains (double play would end the game). |

Precedence when classifying: `good` → `bad` → `fine`.

### 9.3 Decision matrix

When **both** hint and discard are legal:

| hint \\ chop | confirmed | default |
|--------------|-----------|---------|
| **good** | Hint | Hint |
| **fine** | Discard | Hint |
| **bad** | Discard | Discard |

Guards outside the matrix:

- No hint tokens → discard (by chop / oldest)
- Discard illegal (max hints) → hint anyway (including `bad`; literal escape for `bad` deferred)
- **TODO (hint-bank):** Avoid filling the bank — at `max-1` tokens, prefer discard unless hint is
  `good` (discard or play-5 both refund to max). At max tokens with no playable, prefer literal
  escape over a `bad` convention channel. Soft caution at `max-2` / endgame exceptions later.

Reading the matrix:

- `good` always beats chop (tempo: playable for next, or trash for next + playable for prev).
- `confirmed` beats non-good / non-bad hints (trust prior discard recommendation).
- `bad` always discards when discard is legal (never schedule both mid-rank discards; never schedule double play on the last life).
- `fine` with `default` still hint (avoid burning criticals / playables on unhinted chop).

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

### 10.5 Protect next (save-hint before own play)

Next’s chop is a physical critical; next has no convention-`playable`; tokens > 0; next’s matrix
would discard (`fine`/`bad` + `confirmed`, or equivalent). We have our own marked playable.

- Without §9.0 we would play and next would burn the critical.
- With §9.0: if a convention hint **protects next** (e.g. marks a playable for them, or moves
  their chop to trash) → hint now; own play waits.

### 10.6 Protect next (token gift at 0 tokens)

Next would discard a dangerous chop **only because** `hint_tokens == 0` (e.g. `default` chop
and a `fine` channel, or `good` available). With a hypothetical `tokens == 1`, matrix/play would
not burn the card.

- Own chop is **`confirmed`** and discard is legal → discard chop (+1 token).
- Play-5 refund only if §9.0.3 public-pile test says every playable is a 5 (otherwise we do
  not know rank).
- If instead next’s chop is `confirmed` and the channel is non-`good`, hypothetical still
  discards danger → token gift is useless; protect returns no move.

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
| Encode discard choice | Best among **indicable** (first `m`) options; single hand + public piles only |
| Encode order | Next peer code, then previous |
| Recompute | Fresh peer codes from current shared belief on each convention hint |
| Dispatch | Protect next (§9.0), then play leftmost playable, then hint×chop matrix (§9) |
| Protect next | Next-seat only; save-hint (bad overridden) before play; “would discard” via confirmed∧¬next-likely-good or 0 tokens (§9.0.1); at 0 tokens gift via confirmed-chop discard only if hypothetical `tokens==1` stops the burn; play-5 only if public piles imply playable≡5 (§9.0.3); no default-chop gift; endgame TODO |
| Mod-8 wire | Unchanged |
| Bot name | `DynamicRecommendation3P` (leave `DynamicHandType3P` untouched) |

---

## 12. Implementation checklist

- [x] New module/player `DynamicRecommendation3P` (do **not** modify `DynamicHandType3P`)
- [x] Belief: playability + `chop` + `chop_confirmed` only
- [x] Encode/decode per §5–§6 (first `m` wrapped-chain candidates)
- [x] Dispatch per §9 (play / hint×chop matrix)
- [x] `_try_protect_next_player` per §9.0
- [x] GUI: `/` unconfirmed chop, `X` confirmed chop (DHT keeps axe)
- [ ] Tests + A/B vs `DynamicHandType3P` / `HintHandSubtype3P` (protect: watch `3.3` critical-lost)

---

## 13. Glossary

| Term | Meaning |
|------|---------|
| **Protect next** | §9.0 emergency: save next from discarding a last-copy critical/playable before own play |
| **N_play** | Count of `playability == unknown` |
| **Discard candidate** | `playability != playable` |
| **Chop** | Expected discard slot |
| **Chop confirmed** | Chop set by a discard decode (each of `m` codes names one candidate) |
| **Discard chain** | Chop, then newer, then wrap older; codes use first `m = 8−N` only |
| **Peer code** | `0`–`7` one hand contributes to the mod-8 sum |
| **Channel** | `(peer + peer) mod 8` |

---

*Spec version: 2026-07-25 (`DynamicRecommendation3P`; §9.0 protect next defined, not yet implemented).*
