"""
Hanabi Game Implementation

A Python implementation of the Hanabi card game with strategy support.
"""

__version__ = "0.1.0"

# Import main classes for easy access
from .core.enums import Color, Number
from .core.card import Card, Suit
from .core.game import Hand, GameSettings, CommonView, PlayerView, GameState, Game, create_standard_game_settings
from .core.game_field import GameField
from .core.moves import Move, Hint, CardMove, Play, Discard, ColorHint, NumberHint
from .core.observer import Observer
from .core.player import Player, BasePlayer, HintTrackingPlayer, HumanPlayer, StrategyAlphaPlayer, PlayerTeam
from .ai import RandomPlayer

__all__ = [
    # Enums
    "Color",
    "Number",
    # Cards
    "Card",
    "Suit",
    # Game state
    "Hand",
    "GameSettings",
    "create_standard_game_settings",
    "CommonView",
    "PlayerView",
    "GameState",
    "Game",
    "GameField",
    # Moves
    "Move",
    "Hint",
    "CardMove",
    "Play",
    "Discard",
    "ColorHint",
    "NumberHint",
    # Players
    "Observer",
    "Player",
    "BasePlayer",
    "HintTrackingPlayer",
    "HumanPlayer",
    "RandomPlayer",
    "StrategyAlphaPlayer",
    "PlayerTeam",
]
