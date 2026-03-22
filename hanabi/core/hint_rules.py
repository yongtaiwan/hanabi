"""
Shared Hanabi hint rules against a known visible hand.

Used by the engine, move generation, Monte Carlo rollouts, and AI move filtering
so hint legality stays consistent.
"""

from __future__ import annotations

from typing import List, Sequence

from .card import Card
from .enums import Color, Number
from .moves import ColorHint, NumberHint


def indices_matching_color(hand: Sequence[Card], color: Color) -> List[int]:
    """Indices of cards in ``hand`` with the given color."""
    return [idx for idx, card in enumerate(hand) if card.color == color]


def indices_matching_number(hand: Sequence[Card], number: Number) -> List[int]:
    """Indices of cards in ``hand`` with the given number."""
    return [idx for idx, card in enumerate(hand) if card.number == number]


def is_legal_hint_against_hand_cards(
    move: ColorHint | NumberHint,
    hand_cards: Sequence[Card],
) -> bool:
    """
    Whether ``move`` satisfies Hanabi hint rules for the given visible hand.

    The hinted indices must match the hinted color/number, and the set of indices
    must be exactly all matching cards in the hand.
    """
    if not move.cards:
        return False

    if isinstance(move, ColorHint):
        matching = indices_matching_color(hand_cards, move.color)
        for card_idx in move.cards:
            if card_idx < 0 or card_idx >= len(hand_cards):
                return False
            if hand_cards[card_idx].color != move.color:
                return False
        return set(move.cards) == set(matching)

    matching = indices_matching_number(hand_cards, move.number)
    for card_idx in move.cards:
        if card_idx < 0 or card_idx >= len(hand_cards):
            return False
        if hand_cards[card_idx].number != move.number:
            return False
    return set(move.cards) == set(matching)
