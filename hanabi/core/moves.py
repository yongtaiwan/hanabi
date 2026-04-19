"""
Move classes for Hanabi game actions.
"""

from abc import ABC
from typing import List, Protocol, TypeAlias, runtime_checkable

from .enums import Color, Number


@runtime_checkable
class HasWhy(Protocol):
    """Structural type for moves that carry an AI/console narrative (duck typing)."""

    def why(self) -> str:
        """Return a short human-readable reason for this move."""
        ...


class Move(ABC):
    """Base class for all moves in Hanabi."""

    pass


class Hint(Move):
    """Base class for hint moves."""

    def __init__(self, teammate: int, cards: List[int]):
        """
        Initialize a hint move.

        Args:
            teammate: Index of the teammate receiving the hint
            cards: List of card indices in the teammate's hand that match the hint
        """
        self._teammate = teammate
        self._cards = cards.copy()

    def __repr__(self) -> str:
        return f"Hint(teammate={self._teammate}, cards={self._cards})"

    @property
    def teammate(self) -> int:
        """Get the teammate index receiving the hint."""
        return self._teammate

    @property
    def cards(self) -> List[int]:
        """Get the list of card indices matching the hint."""
        return self._cards.copy()


class ColorHint(Hint):
    """Hint indicating a specific color."""

    def __init__(self, teammate: int, cards: List[int], color: Color):
        """
        Initialize a color hint.

        Args:
            teammate: Index of the teammate receiving the hint
            cards: List of card indices matching the color
            color: The color being hinted
        """
        super().__init__(teammate, cards)
        self._color = color

    def __repr__(self) -> str:
        return f"ColorHint(teammate={self._teammate}, color={self._color.name}, cards={self._cards})"

    @property
    def color(self) -> Color:
        """Get the color being hinted."""
        return self._color


class NumberHint(Hint):
    """Hint indicating a specific number."""

    def __init__(self, teammate: int, cards: List[int], number: Number):
        """
        Initialize a number hint.

        Args:
            teammate: Index of the teammate receiving the hint
            cards: List of card indices matching the number
            number: The number being hinted
        """
        super().__init__(teammate, cards)
        self._number = number

    def __repr__(self) -> str:
        return f"NumberHint(teammate={self._teammate}, number={self._number.value}, cards={self._cards})"

    @property
    def number(self) -> Number:
        """Get the number being hinted."""
        return self._number


class CardMove(Move):
    """Base class for moves involving a card."""

    def __init__(self, card: int):
        """
        Initialize a card move.

        Args:
            card: Index of the card in the player's hand
        """
        self._card = card

    def __repr__(self) -> str:
        return f"CardMove(card={self._card})"

    @property
    def card(self) -> int:
        """Get the card index."""
        return self._card


class Play(CardMove):
    """Move to play a card."""

    def __init__(self, card: int):
        """
        Initialize a play move.

        Args:
            card: Index of the card to play
        """
        super().__init__(card)

    def __repr__(self) -> str:
        return f"Play(card={self._card})"


class Discard(CardMove):
    """Move to discard a card."""

    def __init__(self, card: int):
        """
        Initialize a discard move.

        Args:
            card: Index of the card to discard
        """
        super().__init__(card)

    def __repr__(self) -> str:
        return f"Discard(card={self._card})"


# Every legal engine move is one of these leaf types. Use with exhaustive dispatch +
# ``typing.assert_never`` (or a final ``case _: assert False``) so new move kinds are caught.
# Subclasses such as :class:`ExplainedPlay` are still :class:`Play` / etc. for ``isinstance``.
ConcreteMove: TypeAlias = Play | Discard | ColorHint | NumberHint

HintMove: TypeAlias = ColorHint | NumberHint


class ExplainedMixin:
    """Adds :meth:`why` for AI/console narrative; mixed into leaf move subclasses."""

    _why: str

    def why(self) -> str:
        return self._why


class ExplainedPlay(ExplainedMixin, Play):
    """:class:`Play` with a :meth:`why` string (implements :class:`HasWhy`)."""

    def __init__(self, card: int, *, why: str) -> None:
        super().__init__(card)
        self._why = why


class ExplainedDiscard(ExplainedMixin, Discard):
    """:class:`Discard` with a :meth:`why` string (implements :class:`HasWhy`)."""

    def __init__(self, card: int, *, why: str) -> None:
        super().__init__(card)
        self._why = why


class ExplainedColorHint(ExplainedMixin, ColorHint):
    """:class:`ColorHint` with a :meth:`why` string (implements :class:`HasWhy`)."""

    def __init__(self, teammate: int, cards: List[int], color: Color, *, why: str) -> None:
        super().__init__(teammate, cards, color)
        self._why = why


class ExplainedNumberHint(ExplainedMixin, NumberHint):
    """:class:`NumberHint` with a :meth:`why` string (implements :class:`HasWhy`)."""

    def __init__(self, teammate: int, cards: List[int], number: Number, *, why: str) -> None:
        super().__init__(teammate, cards, number)
        self._why = why


def ensure_concrete_move(move: Move) -> ConcreteMove:
    """Return ``move`` narrowed to the closed set of concrete move classes (including explained subclasses)."""
    if isinstance(move, (Play, Discard, ColorHint, NumberHint)):
        return move
    assert False, f"unexpected Move subclass (add to ConcreteMove / dispatch): {type(move).__name__}"
