"""
Utility functions for generating valid moves in Hanabi.

This module provides functions to generate all possible moves for a player
given their current view of the game state.
"""

from typing import List
from .game import PlayerView, CommonView, GameSettings
from .hint_rules import indices_matching_color, indices_matching_number
from .moves import Move, Play, Discard, ColorHint, NumberHint
from .enums import Color, Number


def generate_all_valid_moves(
    player_view: PlayerView,
    common_view: CommonView,
    game_settings: GameSettings,
    player_index: int
) -> List[Move]:
    """
    Generate all legitimate moves for a player given their current view.

    This function generates all possible moves (Play, Discard, ColorHint, NumberHint)
    that could be valid for the current game state. The moves still need to be
    validated by GameState._validate() before being executed.

    Args:
        player_view: The current view of the game from the player's perspective
        common_view: The common view of the game state (for hint tokens, etc.)
        game_settings: The game settings (for max hint tokens, etc.)
        player_index: The index of the player (to avoid hinting themselves)

    Returns:
        List of all potential moves (game will validate them)
    """
    valid_moves: List[Move] = []

    # Get player's hand size from player view
    hand_size = player_view.ownHandSize

    # ALWAYS generate play moves first (these are always valid)
    for card_index in range(hand_size):
        valid_moves.append(Play(card_index))

    # Generate all Discard moves (only if hint tokens are not at maximum)
    # Cannot discard if hint tokens are already at maximum
    if common_view.hintTokens < game_settings.maxHintTokens:
        # Can discard to gain a hint token
        for card_index in range(hand_size):
            valid_moves.append(Discard(card_index))

    # Generate all Hint moves (only if hint tokens available and we have teammates)
    # We'll generate all possible hints, and validation will filter out invalid ones
    if len(player_view.teammates) > 0:
        teammates = player_view.teammates

        for teammate_index, teammate_hand in teammates.items():
            # Skip if teammate has no cards
            if not teammate_hand.cards:
                continue

            # Can't hint yourself
            if teammate_index == player_index:
                continue

            # Generate all ColorHint moves
            for color in Color:
                if color == Color.MULTI:
                    continue  # Skip MULTI color (not used in standard game)
                matching_indices = indices_matching_color(teammate_hand.cards, color)
                # Hint must include ALL matching cards (rule requirement)
                if matching_indices:
                    valid_moves.append(ColorHint(teammate_index, matching_indices, color))

            # Generate all NumberHint moves
            for number in Number:
                matching_indices = indices_matching_number(teammate_hand.cards, number)
                # Hint must include ALL matching cards (rule requirement)
                if matching_indices:
                    valid_moves.append(NumberHint(teammate_index, matching_indices, number))

    return valid_moves
