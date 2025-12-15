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

    The player validates all moves before returning them using _is_move_valid(),
    which replicates GameState._validate() logic using only information available
    to players (commonView, gameSettings, playerView).
    """

    def __init__(self, player_index: int):
        """
        Initialize a random AI player.

        Args:
            player_index: The index of this player
        """
        super().__init__(player_index)

    def _is_move_valid(self, move: Move, player_view: PlayerView) -> bool:
        """
        Check if a move is valid using the same logic as GameState._validate.

        This replicates the validation logic that the game uses, but only using
        information available to players (commonView, gameSettings, playerView).

        Args:
            move: The move to validate
            player_view: The current player view

        Returns:
            True if the move is valid, False otherwise
        """
        try:
            common_view = self.commonView
            hand_size = player_view.ownHandSize
        except (ValueError, AttributeError):
            # Can't validate without commonView, assume invalid
            return False

        # Validate Play moves
        if isinstance(move, Play):
            # Check card index is valid
            if move.card < 0 or move.card >= hand_size:
                return False
            return True

        # Validate Discard moves
        if isinstance(move, Discard):
            # Check card index is valid
            if move.card < 0 or move.card >= hand_size:
                return False
            # Cannot discard if hint tokens are already at maximum
            if common_view.hintTokens >= self.gameSettings.maxHintTokens:
                return False
            return True

        # Validate Hint moves
        if isinstance(move, (ColorHint, NumberHint)):
            # Check if hint tokens available
            # Read hintTokens directly from the shared commonView
            # This is the authoritative source - if it says 0, the move is invalid
            hint_tokens = common_view.hintTokens
            if hint_tokens <= 0:
                return False

            # Check if teammate index is valid
            if move.teammate not in player_view.teammates:
                return False

            # Can't hint yourself
            if move.teammate == self._player_index:
                return False

            # Check if hint has matching cards
            if not move.cards:
                return False

            # Validate that the hint actually matches cards in the hand
            teammate_hand = player_view.teammates[move.teammate]

            if isinstance(move, ColorHint):
                # Find all cards in the hand that match this color
                matching_indices = [
                    idx for idx, card in enumerate(teammate_hand.cards)
                    if card.color == move.color
                ]

                # Check that all card indices in the hint are valid and match the color
                for card_idx in move.cards:
                    if card_idx < 0 or card_idx >= len(teammate_hand.cards):
                        return False
                    if teammate_hand.cards[card_idx].color != move.color:
                        return False

                # CRITICAL RULE: A hint must include ALL matching cards in the hand
                if set(move.cards) != set(matching_indices):
                    return False

            elif isinstance(move, NumberHint):
                # Find all cards in the hand that match this number
                matching_indices = [
                    idx for idx, card in enumerate(teammate_hand.cards)
                    if card.number == move.number
                ]

                # Check that all card indices in the hint are valid and match the number
                for card_idx in move.cards:
                    if card_idx < 0 or card_idx >= len(teammate_hand.cards):
                        return False
                    if teammate_hand.cards[card_idx].number != move.number:
                        return False

                # CRITICAL RULE: A hint must include ALL matching cards in the hand
                if set(move.cards) != set(matching_indices):
                    return False

            return True

        # Unknown move type
        return False

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
            if self._is_move_valid(move, player_view):
                valid_moves.append(move)

        # If filtering removed all moves, fall back to play moves only
        if not valid_moves:
            # Generate play moves as fallback (these should always be valid)
            hand_size = player_view.ownHandSize
            for card_index in range(hand_size):
                play_move = Play(card_index)
                if self._is_move_valid(play_move, player_view):
                    valid_moves.append(play_move)

            # If still no valid moves, return a play move anyway (game will validate)
            if not valid_moves:
                return Play(0) if hand_size > 0 else Play(0)

        # Randomly select from validated moves
        selected = random.choice(valid_moves)

        # Only do a final check for hint moves to ensure tokens are still available
        # This is the only case where state can change between validation and selection
        if isinstance(selected, (ColorHint, NumberHint)):
            try:
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
            except (ValueError, AttributeError):
                # Error accessing commonView - fall back to another move from valid list
                other_moves = [m for m in valid_moves if not isinstance(m, (ColorHint, NumberHint))]
                if other_moves:
                    selected = random.choice(other_moves)
                else:
                    # Fallback to play
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
        try:
            common_view = self.commonView
            game_settings = self.gameSettings
        except (ValueError, AttributeError):
            # If commonView or gameSettings not set, only return play moves
            hand_size = player_view.ownHandSize
            return [Play(card_index) for card_index in range(hand_size)]

        return generate_all_valid_moves(
            player_view=player_view,
            common_view=common_view,
            game_settings=game_settings,
            player_index=self._player_index
        )

