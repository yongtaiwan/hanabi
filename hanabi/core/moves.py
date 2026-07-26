"""
Move classes for Hanabi game actions.
"""

from abc import ABC
from typing import List, Optional, Protocol, TypeAlias, runtime_checkable

from .card import Card
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
        # TODO: Rename ``card`` / ``_card`` to ``card_index`` (slot in hand). Observer-facing
        # identity already lives on :class:`FinishedPlay` / :class:`FinishedDiscard` as
        # ``moved_card``.
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


class FinishedPlay(Play):
    """Observer-facing play after the engine applies it (intent :class:`Play` + outcome)."""

    def __init__(self, card: int, moved_card: Card, *, successful: bool) -> None:
        """
        Args:
            card: Hand slot index (same as :class:`Play`).
            moved_card: Public identity of the card that left the hand.
            successful: True if the pile advanced; False if the play bombed (card discarded).
        """
        super().__init__(card)
        # TODO: After ``CardMove.card`` → ``card_index``, consider renaming ``moved_card`` to
        # ``card: Card`` (slot stays ``card_index``).
        self._moved_card = moved_card
        self._successful = successful

    def __repr__(self) -> str:
        return (
            f"FinishedPlay(card={self._card}, moved_card={self._moved_card!r}, "
            f"successful={self._successful})"
        )

    @property
    def moved_card(self) -> Card:
        """Card that left the hand (public after the play attempt)."""
        return self._moved_card

    @property
    def successful(self) -> bool:
        """True when the play advanced a firework pile."""
        return self._successful


class FinishedDiscard(Discard):
    """Observer-facing discard after the engine applies it (intent :class:`Discard` + card)."""

    def __init__(self, card: int, moved_card: Card) -> None:
        """
        Args:
            card: Hand slot index (same as :class:`Discard`).
            moved_card: Public identity of the discarded card.
        """
        super().__init__(card)
        # TODO: After ``CardMove.card`` → ``card_index``, consider renaming ``moved_card`` to
        # ``card: Card`` (slot stays ``card_index``).
        self._moved_card = moved_card

    def __repr__(self) -> str:
        return f"FinishedDiscard(card={self._card}, moved_card={self._moved_card!r})"

    @property
    def moved_card(self) -> Card:
        """Card that left the hand (public after the discard)."""
        return self._moved_card


# Every legal engine move is one of these leaf types. Use with exhaustive dispatch +
# ``typing.assert_never`` (or a final ``case _: assert False``) so new move kinds are caught.
# Subclasses such as :class:`ExplainedPlay` / :class:`FinishedPlay` are still :class:`Play`
# for ``isinstance``.
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


def move_with_why(move: Move, why: str) -> Move:
    """
    Return ``move`` with a :meth:`~HasWhy.why` string attached.

    If ``move`` already implements :class:`HasWhy`, returns ``move`` unchanged.
    """
    if isinstance(move, HasWhy):
        return move
    assert not isinstance(move, (FinishedPlay, FinishedDiscard)), (
        "move_with_why is for intent moves; FinishedPlay/FinishedDiscard are engine observe events"
    )
    if isinstance(move, Play):
        return ExplainedPlay(move.card, why=why)
    if isinstance(move, Discard):
        return ExplainedDiscard(move.card, why=why)
    if isinstance(move, ColorHint):
        return ExplainedColorHint(move.teammate, move.cards, move.color, why=why)
    if isinstance(move, NumberHint):
        return ExplainedNumberHint(move.teammate, move.cards, move.number, why=why)
    assert False, f"unexpected move for move_with_why: {type(move).__name__}"


def ensure_concrete_move(move: Move) -> ConcreteMove:
    """Return ``move`` narrowed to the closed set of concrete move classes (including explained subclasses)."""
    if isinstance(move, (Play, Discard, ColorHint, NumberHint)):
        return move
    assert False, f"unexpected Move subclass (add to ConcreteMove / dispatch): {type(move).__name__}"


def finished_card_move_for_observer(
    move: Play | Discard,
    moved_card: Card,
    *,
    successful: Optional[bool] = None,
) -> FinishedPlay | FinishedDiscard:
    """Build the observer-facing play/discard event from an intent move + public outcome."""
    if isinstance(move, Play):
        assert successful is not None, "FinishedPlay requires successful="
        return FinishedPlay(move.card, moved_card, successful=successful)
    assert isinstance(move, Discard)
    assert successful is None, "FinishedDiscard does not take successful="
    return FinishedDiscard(move.card, moved_card)
