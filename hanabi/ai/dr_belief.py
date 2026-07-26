"""Inferred-hand helpers for :mod:`hanabi.ai.dynamic_recommendation_3p`."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from hanabi.core.card import Card
from hanabi.core.enums import Number
from hanabi.core.game import CommonView, GameSettings


class Playability(Enum):
    UNKNOWN = "unknown"
    PLAYABLE = "playable"
    UNPLAYABLE = "unplayable"


@dataclass
class InferredSlot:
    """Convention inference for one hand slot (not card identity)."""

    playability: Playability = Playability.UNKNOWN
    # Set when a public number-5 hint touches this slot (all observers agree).
    known_five: bool = False


@dataclass
class InferredHand:
    """Per-seat convention inferences from past hints: per-slot playability plus chop."""

    cards: List[InferredSlot] = field(default_factory=list)
    chop: Optional[int] = None
    chop_confirmed: bool = False


def fresh_inferred_slot() -> InferredSlot:
    return InferredSlot()


def fresh_inferred_hand(hand_size: int) -> InferredHand:
    cards = [fresh_inferred_slot() for _ in range(hand_size)]
    return InferredHand(cards=cards, chop=0 if hand_size else None, chop_confirmed=False)


def set_playability(belief: InferredSlot, playability: Playability) -> None:
    belief.playability = playability


def any_five_possibly_playable(common_view: CommonView, settings: GameSettings) -> bool:
    """True iff some color pile has top 4, so a 5 could be playable right now (public)."""
    return any(Number.FOUR == common_view.cards_played.get(color) for color in settings.cards)


def is_play_unknown(belief: InferredSlot, fives_possible: bool) -> bool:
    """Counts for play codes / ``N_play``. Known 5s are excluded while no pile is at 4."""
    if Playability.UNKNOWN != belief.playability:
        return False
    return fives_possible or not belief.known_five


def n_play(hand: InferredHand, fives_possible: bool) -> int:
    return sum(1 for b in hand.cards if is_play_unknown(b, fives_possible))


def is_discard_candidate(belief: InferredSlot) -> bool:
    """Playables and known 5s are never discard-chain / chop candidates."""
    return Playability.PLAYABLE != belief.playability and not belief.known_five


def default_chop_slot(hand: InferredHand) -> Optional[int]:
    for slot, belief in enumerate(hand.cards):
        if is_discard_candidate(belief):
            return slot
    return None


def ensure_default_chop(hand: InferredHand) -> None:
    """If chop is missing/invalid, set leftmost discard candidate, unconfirmed."""
    if hand.chop is not None and 0 <= hand.chop < len(hand.cards) and is_discard_candidate(hand.cards[hand.chop]):
        return
    hand.chop = default_chop_slot(hand)
    hand.chop_confirmed = False


def clear_chop_confirmation(hand: InferredHand) -> None:
    hand.chop_confirmed = False


def discard_chain(hand: InferredHand) -> List[int]:
    """Wrapped discard order from chop: newer, then older. Skips playables and known 5s (§5.2)."""
    ensure_default_chop(hand)
    if hand.chop is None:
        return []
    chain: List[int] = []
    for slot in range(hand.chop, len(hand.cards)):
        if is_discard_candidate(hand.cards[slot]):
            chain.append(slot)
    for slot in range(0, hand.chop):
        if is_discard_candidate(hand.cards[slot]):
            chain.append(slot)
    return chain


def discard_code_candidates(hand: InferredHand, fives_possible: bool) -> List[int]:
    """First ``m = 8 - N_play`` discard-chain slots (never identified playables / known 5s)."""
    types = discard_types_for_n_play(n_play(hand, fives_possible))
    candidates = discard_chain(hand)[: len(types)]
    assert all(is_discard_candidate(hand.cards[slot]) for slot in candidates), (
        f"discard candidates must skip playables and known 5s: {candidates}"
    )
    return candidates


def discard_types_for_n_play(n_play_val: int) -> List[int]:
    skip = set(range(1, n_play_val + 1))
    return [t for t in (0, 7, 6, 5, 4, 3, 2) if t not in skip]


def unknown_slots_newest_first(hand: InferredHand, fives_possible: bool) -> List[int]:
    return [
        slot
        for slot in range(len(hand.cards) - 1, -1, -1)
        if is_play_unknown(hand.cards[slot], fives_possible)
    ]


def play_type_for_slot(hand: InferredHand, slot: int, fives_possible: bool) -> Optional[int]:
    ordering = unknown_slots_newest_first(hand, fives_possible)
    if slot not in ordering:
        return None
    return ordering.index(slot) + 1


def slot_for_play_type(hand: InferredHand, hand_type: int, fives_possible: bool) -> Optional[int]:
    if hand_type < 1:
        return None
    ordering = unknown_slots_newest_first(hand, fives_possible)
    if hand_type > len(ordering):
        return None
    return ordering[hand_type - 1]


def apply_play_decode(hand: InferredHand, k: int, fives_possible: bool) -> None:
    ordering = unknown_slots_newest_first(hand, fives_possible)
    assert 1 <= k <= len(ordering), f"play type {k} out of range for {len(ordering)} unknown slots"
    target = ordering[k - 1]
    assert Playability.UNKNOWN == hand.cards[target].playability
    # Newer play-unknowns (ordering[0 : k-1]) are unplayable: encode always picks newest playable.
    for slot in ordering[: k - 1]:
        set_playability(hand.cards[slot], Playability.UNPLAYABLE)
    set_playability(hand.cards[target], Playability.PLAYABLE)
    if hand.chop == target:
        _advance_chop_past_slot(hand, target)


def apply_discard_decode_with_n_play(hand: InferredHand, decoded: int, n_play_before: int) -> None:
    types = discard_types_for_n_play(n_play_before)
    assert decoded in types, f"discard decode {decoded} not in {types} for n_play={n_play_before}"
    for belief in hand.cards:
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


def apply_decoded_value(hand: InferredHand, decoded: int, fives_possible: bool) -> None:
    n_play_before = n_play(hand, fives_possible)
    if 1 <= decoded <= n_play_before:
        apply_play_decode(hand, decoded, fives_possible)
        return
    apply_discard_decode_with_n_play(hand, decoded, n_play_before)


def decoded_value_is_applicable(hand: InferredHand, decoded: int, fives_possible: bool) -> bool:
    """True when :func:`apply_decoded_value` would not assert on ``decoded`` for ``hand``."""
    if not 0 <= decoded <= 7:
        return False
    n_play_before = n_play(hand, fives_possible)
    if 1 <= decoded <= n_play_before:
        return slot_for_play_type(hand, decoded, fives_possible) is not None
    types = discard_types_for_n_play(n_play_before)
    if decoded not in types:
        return False
    # Mirror apply_discard_decode_with_n_play: close unknowns, then chop/candidates.
    probe = copy_inferred_hand(hand)
    for belief in probe.cards:
        if Playability.UNKNOWN == belief.playability:
            set_playability(belief, Playability.UNPLAYABLE)
    ensure_default_chop(probe)
    candidates = discard_chain(probe)[: len(types)]
    if not candidates:
        return False
    return types.index(decoded) < len(candidates)


def reset_chop_after_removal(hand: InferredHand, removed: int) -> None:
    """Update chop after slot ``removed`` leaves the hand (pre-shift indices).

    When the chop card leaves: prefer the next newer discard candidate (sticky §8.2),
    adjusting the index for the forthcoming left shift. If none, clear chop and let
    :func:`finalize_chop_after_shift` / :func:`ensure_default_chop` fall back to leftmost.
    """
    if hand.chop is None:
        return
    if removed == hand.chop:
        next_slot = _next_newer_discard_candidate(hand, removed)
        clear_chop_confirmation(hand)
        # ``next_slot`` is pre-shift; after removing ``removed`` it becomes ``next_slot - 1``.
        hand.chop = next_slot - 1 if next_slot is not None else None
        return
    if removed < hand.chop:
        hand.chop -= 1


def finalize_chop_after_shift(hand: InferredHand) -> None:
    ensure_default_chop(hand)


def _next_newer_discard_candidate(hand: InferredHand, after_slot: int) -> Optional[int]:
    """First discard candidate strictly newer than ``after_slot``, or ``None``."""
    for slot in range(after_slot + 1, len(hand.cards)):
        if is_discard_candidate(hand.cards[slot]):
            return slot
    return None


def _advance_chop_past_slot(hand: InferredHand, slot: int) -> None:
    """Move chop past ``slot`` (no hand shift): next newer candidate, else leftmost default."""
    next_slot = _next_newer_discard_candidate(hand, slot)
    clear_chop_confirmation(hand)
    if next_slot is not None:
        hand.chop = next_slot
        return
    hand.chop = default_chop_slot(hand)


def reopen_unplayable(hands: List[InferredHand]) -> None:
    """Reopen play-closed slots. Chop fields are unchanged (§8.1)."""
    for hand in hands:
        for belief in hand.cards:
            if Playability.UNPLAYABLE == belief.playability:
                set_playability(belief, Playability.UNKNOWN)


def play_reopens_playability(
    card: Card,
    common_view: CommonView,
    settings: GameSettings,
) -> bool:
    """True when a successful play of ``card`` newly opens the next rank with copies left (§8.1)."""
    if Number.FIVE == card.number:
        return False
    after_top = common_view.cards_played.get(card.color)
    if after_top != card.number:
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


def copy_inferred_hand(hand: InferredHand) -> InferredHand:
    return InferredHand(
        cards=[InferredSlot(b.playability, b.known_five) for b in hand.cards],
        chop=hand.chop,
        chop_confirmed=hand.chop_confirmed,
    )


def mark_known_fives(hand: InferredHand, slots: Sequence[int]) -> None:
    """Record public number-5 touches; known 5s leave the discard chain."""
    for slot in slots:
        assert 0 <= slot < len(hand.cards), f"known-five slot {slot} out of hand"
        hand.cards[slot].known_five = True
        if hand.chop == slot:
            _advance_chop_past_slot(hand, slot)
    ensure_default_chop(hand)


def indicable_discard_options(hand: InferredHand, fives_possible: bool) -> List[Tuple[int, int, bool]]:
    """Return ``(code, chop_slot, confirmed)`` for each of the first ``m`` chain slots."""
    ensure_default_chop(hand)
    types = discard_types_for_n_play(n_play(hand, fives_possible))
    candidates = discard_code_candidates(hand, fives_possible)
    assert types and candidates
    options: List[Tuple[int, int, bool]] = []
    for index, code in enumerate(types):
        if index >= len(candidates):
            continue
        options.append((code, candidates[index], True))
    return options
