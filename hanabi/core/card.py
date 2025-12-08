"""
Card and Suit classes for Hanabi.
"""

from typing import Dict
from .enums import Color, Number


class Card:
    """Represents a single card in Hanabi."""
    
    def __init__(self, color: Color, number: Number):
        self._color = color
        self._number = number
    
    @property
    def color(self) -> Color:
        """Get the color of the card."""
        return self._color
    
    @property
    def number(self) -> Number:
        """Get the number of the card."""
        return self._number
    
    def __repr__(self) -> str:
        return f"Card({self._color.name}, {self._number.value})"
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Card):
            return False
        return self._color == other._color and self._number == other._number
    
    def __hash__(self) -> int:
        return hash((self._color, self._number))


class Suit:
    """Represents a suit with cards mapping numbers to quantities."""
    
    def __init__(self, cards: Dict[Number, int]):
        """
        Initialize a suit.
        
        Args:
            cards: Dictionary mapping Number to quantity of that number in the suit
        """
        self._cards = cards.copy()
    
    @property
    def cards(self) -> Dict[Number, int]:
        """Get the cards mapping (Number -> quantity)."""
        return self._cards.copy()
    
    def __repr__(self) -> str:
        return f"Suit({self._cards})"

