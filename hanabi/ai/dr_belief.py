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
    # True after any discard-code decode. Cleared only when chop resets to default
    # (opening repair / chop leaves or is play-marked — §8.2 / play decode).
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
    """Wrapped discard order from chop: newer, then older. Skips identified playables (§5.2)."""
    ensure_default_chop(hand)
    if hand.chop is None:
        return []
    chain: List[int] = []
    for slot in range(hand.chop, len(hand.slots)):
        if is_discard_candidate(hand.slots[slot]):
            chain.append(slot)
    for slot in range(0, hand.chop):
        if is_discard_candidate(hand.slots[slot]):
            chain.append(slot)
    return chain


def discard_code_candidates(hand: HandBelief) -> List[int]:
    """First ``m = 8 - N_play`` discard-chain slots (never identified playables)."""
    types = discard_types_for_n_play(n_play(hand))
    candidates = discard_chain(hand)[: len(types)]
    assert all(is_discard_candidate(hand.slots[slot]) for slot in candidates), (
        f"discard candidates must skip playables: {candidates}"
    )
    return candidates


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
    # Newer unknowns (ordering[0 : k-1]) are unplayable: encode always picks newest playable.
    for slot in ordering[: k - 1]:
        set_playability(hand.slots[slot], Playability.UNPLAYABLE)
    set_playability(hand.slots[target], Playability.PLAYABLE)
    if hand.chop == target:
        _advance_chop_past_slot(hand, target)


def apply_discard_decode_with_n_play(hand: HandBelief, decoded: int, n_play_before: int) -> None:
    types = discard_types_for_n_play(n_play_before)
    assert decoded in types, f"discard decode {decoded} not in {types} for n_play={n_play_before}"
    for belief in hand.slots:
        if Playability.UNKNOWN == belief.playability:
            set_playability(belief, Playability.UNPLAYABLE)
    ensure_default_chop(hand)
    m = len(types)
    candidates = discard_chain(hand)[:m]
    assert candidates, "discard decode requires a non-empty candidate list"
    index = types.index(decoded)
    assert index < len(candidates), (
        f"discard index {index} past candidates {candidates} (m={m})"
    )
    hand.chop = candidates[index]
    hand.chop_confirmed = True
    hand.chop_hinted = True


def apply_decoded_value(hand: HandBelief, decoded: int) -> None:
    n_play_before = n_play(hand)
    if 1 <= decoded <= n_play_before:
        apply_play_decode(hand, decoded)
        return
    apply_discard_decode_with_n_play(hand, decoded, n_play_before)


def apply_physical_channel_decode(hand: HandBelief, decoded: int) -> None:
    """Apply a channel value encoded against :func:`fresh_hand_belief` of the same size.

    Peer codes use a blank hand belief, so play/discard type boundaries follow
    ``n_play == hand_size``. Interpreting with the seat's current ``n_play`` would
    desync and can assert.
    """
    assert 0 <= decoded <= 7, f"decoded value {decoded} out of range"
    ref = fresh_hand_belief(len(hand.slots))
    n_play_encode = n_play(ref)
    if 1 <= decoded <= n_play_encode:
        ordering = unknown_slots_newest_first(ref)
        target = ordering[decoded - 1]
        for slot in ordering[: decoded - 1]:
            if Playability.UNKNOWN == hand.slots[slot].playability:
                set_playability(hand.slots[slot], Playability.UNPLAYABLE)
        if Playability.UNKNOWN == hand.slots[target].playability:
            set_playability(hand.slots[target], Playability.PLAYABLE)
            if hand.chop == target:
                _advance_chop_past_slot(hand, target)
        return
    apply_discard_decode_with_n_play(hand, decoded, n_play_encode)


def reset_chop_after_removal(hand: HandBelief, removed: int) -> None:
    """Update chop after slot ``removed`` leaves the hand (pre-shift indices).

    When the chop card leaves: prefer the next newer discard candidate (sticky §8.2),
    adjusting the index for the forthcoming left shift. If none, clear chop and let
    :func:`finalize_chop_after_shift` / :func:`ensure_default_chop` fall back to leftmost.
    """
    if hand.chop is None:
        return
    if removed == hand.chop:
        next_slot = _next_newer_discard_candidate(hand, removed)
        clear_chop_hint_flags(hand)
        # ``next_slot`` is pre-shift; after removing ``removed`` it becomes ``next_slot - 1``.
        hand.chop = next_slot - 1 if next_slot is not None else None
        return
    if removed < hand.chop:
        hand.chop -= 1


def finalize_chop_after_shift(hand: HandBelief) -> None:
    ensure_default_chop(hand)


def _next_newer_discard_candidate(hand: HandBelief, after_slot: int) -> Optional[int]:
    """First discard candidate strictly newer than ``after_slot``, or ``None``."""
    for slot in range(after_slot + 1, len(hand.slots)):
        if is_discard_candidate(hand.slots[slot]):
            return slot
    return None


def _advance_chop_past_slot(hand: HandBelief, slot: int) -> None:
    """Move chop past ``slot`` (no hand shift): next newer candidate, else leftmost default."""
    next_slot = _next_newer_discard_candidate(hand, slot)
    clear_chop_hint_flags(hand)
    if next_slot is not None:
        hand.chop = next_slot
        return
    hand.chop = default_chop_slot(hand)


def reopen_unplayable(hands: List[HandBelief]) -> None:
    """Reopen play-closed slots. Chop fields are unchanged (§8.1)."""
    for hand in hands:
        for belief in hand.slots:
            if Playability.UNPLAYABLE == belief.playability:
                set_playability(belief, Playability.UNKNOWN)


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
    """Return ``(code, chop_slot, confirmed)`` for each of the first ``m`` chain slots."""
    ensure_default_chop(hand)
    types = discard_types_for_n_play(n_play(hand))
    candidates = discard_code_candidates(hand)
    assert types and candidates
    options: List[Tuple[int, int, bool]] = []
    for index, code in enumerate(types):
        if index >= len(candidates):
            continue
        options.append((code, candidates[index], True))
    return options
