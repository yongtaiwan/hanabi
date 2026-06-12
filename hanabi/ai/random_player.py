"""
Random AI player for Hanabi game.
"""

import random
from typing import List, Optional, TYPE_CHECKING

from hanabi.core.player import BasePlayer
from hanabi.core.game import PlayerView
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint, move_with_why
from hanabi.core.enums import Color, Number
from hanabi.core.move_generation import generate_all_valid_moves

if TYPE_CHECKING:
    pass


class RandomPlayer(BasePlayer):
    """
    AI player that makes random moves from all legitimate moves.

    IMPORTANT: This player relies on the Game to update its common_view reference
    after each move (via Game._set_common_view_for_players()). This ensures players
    always see the current state's CommonView, not a stale one.

    The player validates all moves before returning them using
    :meth:`hanabi.core.player.BasePlayer.is_move_legal`, which matches engine
    hint and card-index rules using only ``common_view``, ``game_settings``, and
    ``playerView``.

    Pass a seeded :class:`random.Random` via ``rng`` to make the player reproducible
    (e.g. for debug-replay). Default is the module-level :mod:`random`.
    """

    def __init__(self, player_index: int, *, rng: Optional[random.Random] = None):
        """
        Initialize a random AI player.

        Args:
            player_index: The index of this player
            rng: Optional dedicated random source for reproducibility (default: module ``random``).
        """
        super().__init__(player_index)
        self._rng = rng if rng is not None else random

    def play(self, player_view: PlayerView) -> Move:
        """
        Make a random move from all legitimate moves.

        Args:
            player_view: The current view of the game from this player's perspective

        Returns:
            A randomly selected legitimate move
        """
        # Generate all potential moves
        potential_moves = self._generate_all_valid_moves(player_view)

        if not potential_moves:
            # No moves available - create a play move as fallback
            hand_size = player_view.own_hand_size
            fallback = Play(0) if hand_size > 0 else Play(0)
            return move_with_why(fallback, "random: no valid moves generated (fallback Play(0))")

        # Filter moves to only include valid ones RIGHT NOW
        # This is critical because the common_view is shared and can change
        valid_moves = []
        for move in potential_moves:
            if self.is_move_legal(player_view, move):
                valid_moves.append(move)

        # If filtering removed all moves, fall back to play moves only
        if not valid_moves:
            # Generate play moves as fallback (these should always be valid)
            hand_size = player_view.own_hand_size
            for card_index in range(hand_size):
                play_move = Play(card_index)
                if self.is_move_legal(player_view, play_move):
                    valid_moves.append(play_move)

            # If still no valid moves, return a play move anyway (game will validate)
            if not valid_moves:
                fallback = Play(0) if hand_size > 0 else Play(0)
                return move_with_why(fallback, "random: no legal moves after filter (fallback Play(0))")

        # Randomly select from validated moves
        selected = self._rng.choice(valid_moves)
        candidate_pool_size = len(valid_moves)

        # Only do a final check for hint moves to ensure tokens are still available
        # This is the only case where state can change between validation and selection
        if isinstance(selected, (ColorHint, NumberHint)):
            # Re-read hint tokens at selection time (state may have changed since validation).
            if 0 == self.common_view.hint_tokens:
                # Tokens are 0 - find another valid move from our list
                # Prefer non-play moves if available
                other_moves = [m for m in valid_moves if not isinstance(m, (ColorHint, NumberHint))]
                if other_moves:
                    selected = self._rng.choice(other_moves)
                    candidate_pool_size = len(other_moves)
                else:
                    # Only plays available, use one of them
                    play_moves = [m for m in valid_moves if isinstance(m, Play)]
                    if play_moves:
                        selected = self._rng.choice(play_moves)
                        candidate_pool_size = len(play_moves)
                    else:
                        # Last resort
                        hand_size = player_view.own_hand_size
                        selected = Play(0) if hand_size > 0 else Play(0)
                        candidate_pool_size = 1

        return move_with_why(selected, f"random: uniform pick from {candidate_pool_size} legal move(s)")

    def _generate_all_valid_moves(self, player_view: PlayerView) -> List[Move]:
        """
        Generate all legitimate moves for the current player.

        Args:
            player_view: The current view of the game from this player's perspective

        Returns:
            List of all potential moves (game will validate them)
        """
        return generate_all_valid_moves(
            player_view=player_view,
            common_view=self.common_view,
            game_settings=self.game_settings,
            player_index=self._player_index,
        )
