"""
Check whether a move is legal from a player's partial view of the game.

Mirrors :meth:`GameState._validate` for card moves and hints, but uses
:class:`PlayerView` and :class:`CommonView` only (no turn / game-over checks).
"""

from __future__ import annotations

from .game import CommonView, GameSettings, PlayerView
from .hint_rules import is_legal_hint_against_hand_cards
from .moves import Move, Play, Discard, ColorHint, NumberHint


def is_move_legal_from_view(
    move: Move,
    *,
    player_view: PlayerView,
    common_view: CommonView,
    game_settings: GameSettings,
    player_index: int,
) -> bool:
    """
    Return whether ``move`` could be legal right now for this player.

    Uses the same card-index, discard, and hint rules as the engine, excluding
    turn order and end-of-game checks.
    """
    hand_size = player_view.own_hand_size

    if isinstance(move, Play):
        return 0 <= move.card < hand_size

    if isinstance(move, Discard):
        if move.card < 0 or move.card >= hand_size:
            return False
        return common_view.hint_tokens < game_settings.max_hint_tokens

    if isinstance(move, (ColorHint, NumberHint)):
        if common_view.hint_tokens <= 0:
            return False
        if move.teammate not in player_view.teammates:
            return False
        if move.teammate == player_index:
            return False
        teammate_hand = player_view.teammates[move.teammate]
        return is_legal_hint_against_hand_cards(move, teammate_hand.cards)

    return False
