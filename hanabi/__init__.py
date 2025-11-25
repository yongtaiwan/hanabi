"""
Hanabi Game Implementation

A Python implementation of the Hanabi card game with strategy support.
"""

__version__ = "0.1.0"

# Import main classes for easy access
from .enums import Color, Number
from .card import Card, Suit
from .game import (
    Hand, GameSettings, CommonView, PlayerView, GameState, Game, GameField,
    create_standard_game_settings
)
from .moves import Move, Hint, CardMove, Play, Discard, ColorHint, NumberHint
from .observer import Observer
from .player import Player, BasePlayer, HumanPlayer, RandomPlayer, StrategyAlphaPlayer, PlayerTeam

__all__ = [
    # Enums
    'Color',
    'Number',
    # Cards
    'Card',
    'Suit',
    # Game state
    'Hand',
    'GameSettings',
    'create_standard_game_settings',
    'CommonView',
    'PlayerView',
    'GameState',
    'Game',
    'GameField',
    # Moves
    'Move',
    'Hint',
    'CardMove',
    'Play',
    'Discard',
    'ColorHint',
    'NumberHint',
    # Players
    'Observer',
    'Player',
    'BasePlayer',
    'HumanPlayer',
    'RandomPlayer',
    'StrategyAlphaPlayer',
    'PlayerTeam',
]
