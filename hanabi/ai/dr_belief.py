"""Belief helpers for :mod:`hanabi.ai.dynamic_recommendation_3p`."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from hanabi.core.card import Card
from hanabi.core.enums import Color, Number
from hanabi.core.game import CommonView, GameSettings


class Playability(Enum):
    UNKNOWN = "unknown"
    PLAYABLE = "playable"
    UNPLAYABLE = "unplayable"


@dataclass
class SlotBelief:
    playability: Playability = Playability.UNKNOWN


@dataclass
class HandBelief:
    """Per-seat convention belief: slot playability plus chop + confirmation."""

    slots: List[SlotBelief] = field(default_factory=list)
    chop: Optional[int] = None
    chop_confirmed: bool = False
    # True after any discard-code decode. Cleared on default/reset chop; demoted on reopen
    # when not confirmed. Used for GUI/analysis; step 3 uses ``chop_confirmed`` only.
    chop_hinted: bool = False


def fresh_slot_belief() -> SlotBelief:
    return SlotBelief()


def fresh_hand_belief(hand_size: int) -> HandBelief:
    slots = [fresh_slot_belief() for _ in range(hand_size)]
    return HandBelief(slots=slots, chop=0 if hand_size else None, chop_confirmed=False, chop_hinted=False)


def set_playability(belief: SlotBelief, playability: Playability) -> None:
    belief.playability = playability


def n_play(hand: HandBelief) -> int:
    return sum(1 for b in hand.slots if Playability.UNKNOWN == b.playability)


def is_discard_candidate(belief: SlotBelief) -> bool:
    return Playability.PLAYABLE != belief.playability


def default_chop_slot(hand: HandBelief) -> Optional[int]:
    for slot, belief in enumerate(hand.slots):
        if is_discard_candidate(belief):
            return slot
    return None


def ensure_default_chop(hand: HandBelief) -> None:
    """If chop is missing/invalid, set leftmost discard candidate, unconfirmed."""
    if hand.chop is not None and 0 <= hand.chop < len(hand.slots) and is_discard_candidate(hand.slots[hand.chop]):
        return
    hand.chop = default_chop_slot(hand)
    hand.chop_confirmed = False
    hand.chop_hinted = False


def clear_chop_hint_flags(hand: HandBelief) -> None:
    hand.chop_confirmed = False
    hand.chop_hinted = False


def discard_chain(hand: HandBelief) -> List[int]:
    ensure_default_chop(hand)
    if hand.chop is None:
        return []
    chain = [hand.chop]
    for slot in range(hand.chop + 1, len(hand.slots)):
        if is_discard_candidate(hand.slots[slot]):
            chain.append(slot)
    return chain


def discard_types_for_n_play(n_play_val: int) -> List[int]:
    skip = set(range(1, n_play_val + 1))
    return [t for t in (0, 7, 6, 5, 4, 3, 2) if t not in skip]


def unknown_slots_newest_first(hand: HandBelief) -> List[int]:
    return [
        slot
        for slot in range(len(hand.slots) - 1, -1, -1)
        if Playability.UNKNOWN == hand.slots[slot].playability
    ]


def play_type_for_slot(hand: HandBelief, slot: int) -> Optional[int]:
    ordering = unknown_slots_newest_first(hand)
    if slot not in ordering:
        return None
    return ordering.index(slot) + 1


def slot_for_play_type(hand: HandBelief, hand_type: int) -> Optional[int]:
    if hand_type < 1:
        return None
    ordering = unknown_slots_newest_first(hand)
    if hand_type > len(ordering):
        return None
    return ordering[hand_type - 1]


def apply_play_decode(hand: HandBelief, k: int) -> None:
    ordering = unknown_slots_newest_first(hand)
    assert 1 <= k <= len(ordering), f"play type {k} out of range for {len(ordering)} unknown slots"
    target = ordering[k - 1]
    assert Playability.UNKNOWN == hand.slots[target].playability
    set_playability(hand.slots[target], Playability.PLAYABLE)
    if hand.chop == target:
        hand.chop = default_chop_slot(hand)
        clear_chop_hint_flags(hand)


def apply_discard_decode_with_n_play(hand: HandBelief, decoded: int, n_play_before: int) -> None:
    types = discard_types_for_n_play(n_play_before)
    assert decoded in types, f"discard decode {decoded} not in {types} for n_play={n_play_before}"
    for belief in hand.slots:
        if Playability.UNKNOWN == belief.playability:
            set_playability(belief, Playability.UNPLAYABLE)
    ensure_default_chop(hand)
    chain = discard_chain(hand)
    assert chain, "discard decode requires a non-empty chop chain"
    index = types.index(decoded)
    m = len(types)
    if index == m - 1:
        named_count = m - 1
        remainder = chain[named_count:]
        assert remainder, f"catch-all remainder empty: chain={chain} m={m}"
        hand.chop = remainder[0]
        hand.chop_confirmed = 1 == len(remainder)
        hand.chop_hinted = True
        return
    assert index < len(chain), f"discard index {index} past chain {chain}"
    hand.chop = chain[index]
    hand.chop_confirmed = True
    hand.chop_hinted = True


def apply_decoded_value(hand: HandBelief, decoded: int) -> None:
    n_play_before = n_play(hand)
    if 1 <= decoded <= n_play_before:
        apply_play_decode(hand, decoded)
        return
    apply_discard_decode_with_n_play(hand, decoded, n_play_before)


def reset_chop_after_removal(hand: HandBelief, removed: int) -> None:
    """Update chop after slot ``removed`` leaves the hand (pre-shift indices)."""
    if hand.chop is None:
        return
    if removed == hand.chop:
        hand.chop = None
        clear_chop_hint_flags(hand)
        return
    if removed < hand.chop:
        hand.chop -= 1


def finalize_chop_after_shift(hand: HandBelief) -> None:
    ensure_default_chop(hand)


def reopen_unplayable(hands: List[HandBelief]) -> None:
    """Reopen play-closed slots; demote unconfirmed catch-all urgency only."""
    for hand in hands:
        for belief in hand.slots:
            if Playability.UNPLAYABLE == belief.playability:
                set_playability(belief, Playability.UNKNOWN)
        if not hand.chop_confirmed:
            hand.chop_hinted = False


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


def copy_hand_belief(hand: HandBelief) -> HandBelief:
    return HandBelief(
        slots=[SlotBelief(b.playability) for b in hand.slots],
        chop=hand.chop,
        chop_confirmed=hand.chop_confirmed,
        chop_hinted=hand.chop_hinted,
    )


def copy_belief_matrix(matrix: List[HandBelief]) -> List[HandBelief]:
    return [copy_hand_belief(h) for h in matrix]


def indicable_discard_options(hand: HandBelief) -> List[Tuple[int, int, bool]]:
    """Return ``(code, chop_slot, confirmed)`` for each indicable discard option."""
    ensure_default_chop(hand)
    types = discard_types_for_n_play(n_play(hand))
    chain = discard_chain(hand)
    assert types and chain
    options: List[Tuple[int, int, bool]] = []
    m = len(types)
    for index, code in enumerate(types):
        if index == m - 1:
            named_count = m - 1
            remainder = chain[named_count:]
            if not remainder:
                continue
            options.append((code, remainder[0], 1 == len(remainder)))
            continue
        if index >= len(chain):
            continue
        options.append((code, chain[index], True))
    return options
