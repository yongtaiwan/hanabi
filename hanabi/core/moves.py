"""
Move classes for Hanabi game actions.
"""

from abc import ABC
from typing import List, TypeAlias

from .enums import Color, Number


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
    
    @property
    def teammate(self) -> int:
        """Get the teammate index receiving the hint."""
        return self._teammate
    
    @property
    def cards(self) -> List[int]:
        """Get the list of card indices matching the hint."""
        return self._cards.copy()
    
    def __repr__(self) -> str:
        return f"Hint(teammate={self._teammate}, cards={self._cards})"


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
    
    @property
    def color(self) -> Color:
        """Get the color being hinted."""
        return self._color
    
    def __repr__(self) -> str:
        return f"ColorHint(teammate={self._teammate}, color={self._color.name}, cards={self._cards})"


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
    
    @property
    def number(self) -> Number:
        """Get the number being hinted."""
        return self._number
    
    def __repr__(self) -> str:
        return f"NumberHint(teammate={self._teammate}, number={self._number.value}, cards={self._cards})"


class CardMove(Move):
    """Base class for moves involving a card."""
    
    def __init__(self, card: int):
        """
        Initialize a card move.
        
        Args:
            card: Index of the card in the player's hand
        """
        self._card = card
    
    @property
    def card(self) -> int:
        """Get the card index."""
        return self._card
    
    def __repr__(self) -> str:
        return f"CardMove(card={self._card})"


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
ConcreteMove: TypeAlias = Play | Discard | ColorHint | NumberHint


def ensure_concrete_move(move: Move) -> ConcreteMove:
    """Return ``move`` narrowed to the closed set of concrete move classes."""
    if isinstance(move, (Play, Discard, ColorHint, NumberHint)):
        return move
    assert False, f"unexpected Move subclass (add to ConcreteMove / dispatch): {type(move).__name__}"

