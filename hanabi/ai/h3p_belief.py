"""Convention belief types and pure helpers for :mod:`hanabi.ai.hint_hand_subtype_3p`."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence

from hanabi.core.card import Card
from hanabi.core.enums import CardKind, Color, Number
from hanabi.core.game import CommonView, GameSettings


class Playability(Enum):
    UNKNOWN = "unknown"
    PLAYABLE = "playable"
    UNPLAYABLE = "unplayable"


class LegacyDiscardKind(Enum):
    UNKNOWN = "unknown"
    USELESS = "useless"
    SAFE = "safe"
    CRITICAL = "critical"


class RecState(Enum):
    UNKNOWN = "unknown"
    RECOMMENDED = "recommended"


class HandEncodingMode(Enum):
    LEGACY = "legacy"
    RECOMMENDATION = "recommendation"


@dataclass
class SlotBelief:
    playability: Playability = Playability.UNKNOWN
    legacy_kind: LegacyDiscardKind = LegacyDiscardKind.UNKNOWN
    rec_state: RecState = RecState.UNKNOWN


def fresh_slot_belief() -> SlotBelief:
    return SlotBelief()


def set_playability(belief: SlotBelief, playability: Playability) -> None:
    belief.playability = playability


def needs_discard_info(belief: SlotBelief) -> bool:
    """True when the slot still needs a discard-kind message (legacy ``0``/``6``/``7`` / rec).

    ``playable``, ``useless``, and ``critical`` are exempt: playable is not a discard
    candidate for encoding, useless is fully identified for discard, and critical is
    known not to be the preferred discard until nothing else remains.
    """
    if Playability.PLAYABLE == belief.playability:
        return False
    if LegacyDiscardKind.USELESS == belief.legacy_kind:
        return False
    if LegacyDiscardKind.CRITICAL == belief.legacy_kind:
        return False
    return True


def n_play(row: Sequence[SlotBelief]) -> int:
    return sum(1 for b in row if Playability.UNKNOWN == b.playability)


def n_disc(row: Sequence[SlotBelief]) -> int:
    return sum(1 for b in row if needs_discard_info(b))


def hand_encoding_mode(row: Sequence[SlotBelief]) -> HandEncodingMode:
    if n_play(row) + n_disc(row) > 8:
        return HandEncodingMode.LEGACY
    return HandEncodingMode.RECOMMENDATION


def is_discard_candidate(belief: SlotBelief) -> bool:
    return Playability.PLAYABLE != belief.playability


def discard_priority_tier(belief: SlotBelief) -> Optional[int]:
    if not is_discard_candidate(belief):
        return None
    if LegacyDiscardKind.USELESS == belief.legacy_kind:
        return 1
    if RecState.RECOMMENDED == belief.rec_state:
        return 2
    if LegacyDiscardKind.SAFE == belief.legacy_kind:
        return 3
    if LegacyDiscardKind.UNKNOWN == belief.legacy_kind:
        return 4
    if LegacyDiscardKind.CRITICAL == belief.legacy_kind:
        return 5
    assert False, f"unexpected discard belief {belief!r}"


def discard_anchor_slot(row: Sequence[SlotBelief]) -> Optional[int]:
    for slot, belief in enumerate(row):
        if needs_discard_info(belief):
            return slot
    return None


def chop_slot(row: Sequence[SlotBelief]) -> Optional[int]:
    best_tier: Optional[int] = None
    best_slot: Optional[int] = None
    for slot, belief in enumerate(row):
        tier = discard_priority_tier(belief)
        if tier is None:
            continue
        if best_slot is None or tier < best_tier or (tier == best_tier and slot < best_slot):
            best_tier = tier
            best_slot = slot
    return best_slot


def unknown_slots_newest_first(row: Sequence[SlotBelief]) -> List[int]:
    return [slot for slot in range(len(row) - 1, -1, -1) if Playability.UNKNOWN == row[slot].playability]


def chop_chain_newer_from_chop(row: Sequence[SlotBelief], chop: int) -> List[int]:
    chain = [chop]
    for slot in range(chop + 1, len(row)):
        if is_discard_candidate(row[slot]):
            chain.append(slot)
    return chain


def discard_types_for_n_play(n_play: int) -> List[int]:
    skip = set(range(1, n_play + 1))
    return [t for t in (0, 7, 6, 5, 4, 3, 2) if t not in skip]


def slot_for_play_type(row: Sequence[SlotBelief], hand_type: int) -> Optional[int]:
    if not 1 <= hand_type <= 5:
        return None
    ordering = unknown_slots_newest_first(row)
    if hand_type > len(ordering):
        return None
    return ordering[hand_type - 1]


def slot_for_discard_type(row: Sequence[SlotBelief], discard_type: int) -> Optional[int]:
    n_play_val = n_play(row)
    types = discard_types_for_n_play(n_play_val)
    if discard_type not in types:
        return None
    chop = chop_slot(row)
    if chop is None:
        return None
    chain = chop_chain_newer_from_chop(row, chop)
    index = types.index(discard_type)
    if index >= len(chain):
        return None
    return chain[index]


def play_type_for_slot(row: Sequence[SlotBelief], slot: int) -> Optional[int]:
    ordering = unknown_slots_newest_first(row)
    if slot not in ordering:
        return None
    return ordering.index(slot) + 1


def discard_type_for_slot(row: Sequence[SlotBelief], slot: int) -> Optional[int]:
    chop = chop_slot(row)
    if chop is None:
        return None
    chain = chop_chain_newer_from_chop(row, chop)
    if slot not in chain:
        return None
    types = discard_types_for_n_play(n_play(row))
    index = chain.index(slot)
    if index >= len(types):
        return None
    return types[index]


def legacy_kind_to_card_kind(belief: SlotBelief) -> Optional[CardKind]:
    if Playability.PLAYABLE == belief.playability:
        return CardKind.PLAYABLE
    if LegacyDiscardKind.USELESS == belief.legacy_kind:
        return CardKind.USELESS
    if LegacyDiscardKind.SAFE == belief.legacy_kind:
        return CardKind.DISPENSABLE
    if LegacyDiscardKind.CRITICAL == belief.legacy_kind:
        return CardKind.CRITICAL
    return None


def slot_belief_from_legacy_kind(kind: Optional[CardKind]) -> SlotBelief:
    if kind is None:
        return fresh_slot_belief()
    if CardKind.PLAYABLE == kind:
        return SlotBelief(playability=Playability.PLAYABLE)
    if CardKind.USELESS == kind:
        return SlotBelief(playability=Playability.UNPLAYABLE, legacy_kind=LegacyDiscardKind.USELESS)
    if CardKind.DISPENSABLE == kind:
        return SlotBelief(playability=Playability.UNPLAYABLE, legacy_kind=LegacyDiscardKind.SAFE)
    if CardKind.CRITICAL == kind:
        return SlotBelief(playability=Playability.UNPLAYABLE, legacy_kind=LegacyDiscardKind.CRITICAL)
    assert False, f"unexpected legacy CardKind {kind!r}"


def legacy_kind_row(row: Sequence[SlotBelief]) -> List[Optional[CardKind]]:
    return [legacy_kind_to_card_kind(b) for b in row]


_MIDDLE_DISCARD_RANKS = frozenset({Number.TWO, Number.THREE, Number.FOUR})


def play_reopens_playability(
    card: Card,
    cards_played_before: dict[Color, Number],
    common_view: CommonView,
    settings: GameSettings,
) -> bool:
    if Number.FIVE == card.number:
        return False
    before_top = cards_played_before.get(card.color)
    after_top = common_view.cards_played.get(card.color)
    if after_top != card.number:
        return False
    if before_top is not None and before_top.value >= card.number.value:
        return False
    next_number = Number(card.number.value + 1)
    return _copies_of_card_remain(Card(card.color, next_number), common_view, settings)


def _copies_of_card_remain(card: Card, common_view: CommonView, settings: GameSettings) -> bool:
    suit = settings.cards.get(card.color)
    if suit is None:
        return False
    total = suit.cards.get(card.number, 0)
    discarded = 0
    disc = common_view.cards_discarded.get(card.color)
    if disc is not None:
        discarded = disc.cards.get(card.number, 0)
    played_top = common_view.cards_played.get(card.color)
    on_pile = 1 if played_top is not None and played_top.value >= card.number.value else 0
    return total - discarded - on_pile > 0


def reopen_unplayable_after_play(matrix: List[List[SlotBelief]]) -> None:
    for row in matrix:
        for belief in row:
            if Playability.UNPLAYABLE == belief.playability:
                set_playability(belief, Playability.UNKNOWN)


def apply_play_decode_to_row(
    row: List[SlotBelief],
    k: int,
    *,
    mark_newer_unplayable: bool = True,
) -> None:
    """Mark the ``k``-th unknown-from-newest slot playable.

    When ``mark_newer_unplayable`` is true (legacy play types), newer unknowns become
    ``unplayable`` — honest only if encoding chose the newest physical playable.
    Recommendation play encoding may prefer a five / low rank that is *not* newest, so
    callers must pass ``mark_newer_unplayable=False`` in recommendation mode.
    """
    ordering = unknown_slots_newest_first(row)
    assert 1 <= k <= len(ordering), f"play type {k} out of range for {len(ordering)} unknown slots"
    target = ordering[k - 1]
    if mark_newer_unplayable:
        for slot in ordering[: k - 1]:
            assert Playability.UNKNOWN == row[slot].playability, (
                f"newer-than-target slot {slot} must be unknown before play decode k={k}"
            )
            set_playability(row[slot], Playability.UNPLAYABLE)
    assert Playability.UNKNOWN == row[target].playability, (
        f"play decode target slot {target} must be unknown"
    )
    set_playability(row[target], Playability.PLAYABLE)


def apply_legacy_no_playable_decode(row: List[SlotBelief], hand_type: int) -> None:
    assert hand_type in (0, 6, 7), f"unexpected no-playable type {hand_type}"
    for belief in row:
        if Playability.UNKNOWN == belief.playability:
            set_playability(belief, Playability.UNPLAYABLE)
    anchor = discard_anchor_slot(row)
    if anchor is None:
        return
    if 0 == hand_type:
        row[anchor].legacy_kind = LegacyDiscardKind.SAFE
    elif 6 == hand_type:
        row[anchor].legacy_kind = LegacyDiscardKind.CRITICAL
    else:
        row[anchor].legacy_kind = LegacyDiscardKind.USELESS


def set_recommended(row: List[SlotBelief], slot: int) -> None:
    for idx, belief in enumerate(row):
        if idx == slot:
            belief.rec_state = RecState.RECOMMENDED
        elif RecState.RECOMMENDED == belief.rec_state:
            belief.rec_state = RecState.UNKNOWN


def apply_decoded_value(row: List[SlotBelief], decoded: int) -> None:
    assert 0 <= decoded <= 7, f"decoded value {decoded} out of range"
    mode = hand_encoding_mode(row)
    if HandEncodingMode.LEGACY == mode:
        if 1 <= decoded <= 5:
            apply_play_decode_to_row(row, decoded, mark_newer_unplayable=True)
        else:
            apply_legacy_no_playable_decode(row, decoded)
        return
    n_play_val = n_play(row)
    if 1 <= decoded <= n_play_val:
        # Rec play picks by rank heuristic, not newest playable — do not infer newer unplayable.
        apply_play_decode_to_row(row, decoded, mark_newer_unplayable=False)
        return
    slot = slot_for_discard_type(row, decoded)
    assert slot is not None, f"recommendation discard decode {decoded} did not map to a slot"
    set_recommended(row, slot)


def clear_legacy_safe(matrix: List[List[SlotBelief]]) -> None:
    for row in matrix:
        for belief in row:
            if LegacyDiscardKind.SAFE == belief.legacy_kind:
                belief.legacy_kind = LegacyDiscardKind.UNKNOWN
