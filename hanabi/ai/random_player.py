"""
Random AI player for Hanabi game.
"""

import random
from typing import List, TYPE_CHECKING

from hanabi.core.player import BasePlayer
from hanabi.core.game import PlayerView
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number
from hanabi.core.move_generation import generate_all_valid_moves

if TYPE_CHECKING:
    pass


class RandomPlayer(BasePlayer):
    """
    AI player that makes random moves from all legitimate moves.

    IMPORTANT: This player relies on the Game to update its commonView reference
    after each move (via Game._set_common_view_for_players()). This ensures players
    always see the current state's CommonView, not a stale one.

    The player validates all moves before returning them using
    :meth:`hanabi.core.player.BasePlayer.is_move_legal`, which matches engine
    hint and card-index rules using only ``commonView``, ``gameSettings``, and
    ``playerView``.
    """

    def __init__(self, player_index: int):
        """
        Initialize a random AI player.

        Args:
            player_index: The index of this player
        """
        super().__init__(player_index)

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
            hand_size = player_view.ownHandSize
            return Play(0) if hand_size > 0 else Play(0)

        # Filter moves to only include valid ones RIGHT NOW
        # This is critical because the commonView is shared and can change
        valid_moves = []
        for move in potential_moves:
            if self.is_move_legal(player_view, move):
                valid_moves.append(move)

        # If filtering removed all moves, fall back to play moves only
        if not valid_moves:
            # Generate play moves as fallback (these should always be valid)
            hand_size = player_view.ownHandSize
            for card_index in range(hand_size):
                play_move = Play(card_index)
                if self.is_move_legal(player_view, play_move):
                    valid_moves.append(play_move)

            # If still no valid moves, return a play move anyway (game will validate)
            if not valid_moves:
                return Play(0) if hand_size > 0 else Play(0)

        # Randomly select from validated moves
        selected = random.choice(valid_moves)

        # Only do a final check for hint moves to ensure tokens are still available
        # This is the only case where state can change between validation and selection
        if isinstance(selected, (ColorHint, NumberHint)):
            # Read hintTokens directly from commonView RIGHT NOW
            tokens = self.commonView.hintTokens
            if tokens <= 0:
                # Tokens are 0 - find another valid move from our list
                # Prefer non-play moves if available
                other_moves = [m for m in valid_moves if not isinstance(m, (ColorHint, NumberHint))]
                if other_moves:
                    selected = random.choice(other_moves)
                else:
                    # Only plays available, use one of them
                    play_moves = [m for m in valid_moves if isinstance(m, Play)]
                    if play_moves:
                        selected = random.choice(play_moves)
                    else:
                        # Last resort
                        hand_size = player_view.ownHandSize
                        selected = Play(0) if hand_size > 0 else Play(0)

        return selected

    def _generate_all_valid_moves(self, player_view: PlayerView) -> List[Move]:
        """
        Generate all legitimate moves for the current player.

        Args:
            player_view: The current view of the game from this player's perspective

        Returns:
            List of all potential moves (game will validate them)
        """
        # Use the utility function to generate moves
        common_view = self.commonView
        game_settings = self.gameSettings

        return generate_all_valid_moves(
            player_view=player_view,
            common_view=common_view,
            game_settings=game_settings,
            player_index=self._player_index
        )

