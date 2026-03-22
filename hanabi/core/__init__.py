"""
Core game engine for Hanabi.
Contains all game logic without UI dependencies.
"""

from .enums import Color, Number, CardKind
from .card import Card, Suit
from .moves import Move, Hint, CardMove, Play, Discard, ColorHint, NumberHint
from .game import (
    Hand,
    GameSettings,
    CommonView,
    PlayerView,
    GameState,
    Game,
    create_standard_game_settings,
    StartPosition,
    Deck,
)
from .game_field import GameField
from .player import Player, BasePlayer, HintTrackingPlayer, HumanPlayer, StrategyAlphaPlayer, PlayerTeam

# RandomPlayer is in hanabi.ai, not core.player
from .observer import Observer
from .game_history import GameHistory
from .move_generation import generate_all_valid_moves
from .move_validation import is_move_legal_from_view
from .hint_rules import (
    indices_matching_color,
    indices_matching_number,
    is_legal_hint_against_hand_cards,
)

__all__ = [
    # Enums
    "Color",
    "Number",
    "CardKind",
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
    "StartPosition",
    "Deck",
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
    "Player",
    "BasePlayer",
    "HintTrackingPlayer",
    "HumanPlayer",
    "StrategyAlphaPlayer",
    "PlayerTeam",
    # Note: RandomPlayer is in hanabi.ai, not here
    # Observer
    "Observer",
    # History
    "GameHistory",
    # Move generation utilities
    "generate_all_valid_moves",
    "is_move_legal_from_view",
    "indices_matching_color",
    "indices_matching_number",
    "is_legal_hint_against_hand_cards",
]
