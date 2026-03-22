"""
Enumerations for Hanabi game.
"""

from enum import Enum


class Color(Enum):
    """Card colors in Hanabi."""

    MULTI = "MULTI"

    WHITE = "WHITE"

    RED = "RED"

    YELLOW = "YELLOW"

    GREEN = "GREEN"

    BLUE = "BLUE"


class Number(Enum):
    """Card numbers in Hanabi."""

    ONE = 1

    TWO = 2

    THREE = 3

    FOUR = 4

    FIVE = 5


class CardKind(Enum):
    """Full-information bucket for a card (mutually exclusive)."""

    USELESS = "useless"

    PLAYABLE = "playable"

    CRITICAL = "critical"

    DISPENSABLE = "dispensable"
