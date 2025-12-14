"""
Random AI player for Hanabi game.
"""

import random
from typing import List, TYPE_CHECKING

from hanabi.core.player import BasePlayer
from hanabi.core.game import PlayerView, Game
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number

if TYPE_CHECKING:
    pass


class RandomPlayer(BasePlayer):
    """AI player that makes random moves from all legitimate moves."""

    def __init__(self, player_index: int, game: Game):
        """
        Initialize a random AI player.

        Args:
            player_index: The index of this player
            game: The game instance (needed to access game state for move generation)
        """
        super().__init__(player_index)
        self._game = game

    def play(self, player_view: PlayerView) -> Move:
        """
        Make a random move from all legitimate moves.

        Args:
            player_view: The current view of the game from this player's perspective

        Returns:
            A randomly selected legitimate move
        """
        # Generate all legitimate moves
        valid_moves = self._generate_all_valid_moves(player_view)

        if not valid_moves:
            # No valid moves available (shouldn't happen in normal play, but handle gracefully)
            # Try to find any valid move as a last resort
            state = self._game.state
            player_index = self._player_index
            hand_size = len(state.playerHands[player_index].cards)

            # Try play moves
            for card_index in range(hand_size):
                move = Play(card_index)
                if state._validate(player_index, move):
                    return move

            # Try hint moves
            if state.commonView.hintTokens > 0:
                for teammate_index in player_view.teammates.keys():
                    teammate_hand = state.playerHands[teammate_index]
                    for color in Color:
                        if color == Color.MULTI:
                            continue
                        matching_indices = [
                            idx for idx, card in enumerate(teammate_hand.cards)
                            if card.color == color
                        ]
                        if matching_indices:
                            move = ColorHint(teammate_index, matching_indices, color)
                            if state._validate(player_index, move):
                                return move

            # If we still have no valid moves, something is wrong
            # Return a play move that will fail validation but at least won't crash
            return Play(0)

        # Randomly select one move and validate it one more time before returning
        # This ensures the move is still valid at the moment we return it
        selected_move = random.choice(valid_moves)
        state = self._game.state

        # Final validation check
        if state._validate(self._player_index, selected_move):
            return selected_move

        # If the selected move is no longer valid, try to find any valid move
        for move in valid_moves:
            if state._validate(self._player_index, move):
                return move

        # Last resort: regenerate moves and try again
        valid_moves = self._generate_all_valid_moves(player_view)
        if valid_moves:
            return random.choice(valid_moves)

        # Final fallback
        return Play(0)

    def _generate_all_valid_moves(self, player_view: PlayerView) -> List[Move]:
        """
        Generate all legitimate moves for the current player.

        Args:
            player_view: The current view of the game from this player's perspective

        Returns:
            List of all valid moves
        """
        valid_moves: List[Move] = []
        state = self._game.state
        player_index = self._player_index

        # Check if it's this player's turn
        if state.currentPlayer != player_index:
            return valid_moves

        # Check if game is over
        if state.turnsLeft == 0:
            return valid_moves

        # Get player's hand size
        player_hand = state.playerHands[player_index]
        hand_size = len(player_hand.cards)
        common_view = state.commonView

        # Generate all Play moves (all cards in hand can be played)
        for card_index in range(hand_size):
            move = Play(card_index)
            # Always validate - this checks card index validity
            if state._validate(player_index, move):
                valid_moves.append(move)

        # Generate all Discard moves
        # IMPORTANT: Always validate each discard move individually
        # The validation will check if hint tokens are at max
        for card_index in range(hand_size):
            move = Discard(card_index)
            # Validate will return False if hint tokens are at maximum
            if state._validate(player_index, move):
                valid_moves.append(move)

        # Generate all Hint moves (only if hint tokens available)
        if common_view.hintTokens > 0:
            # Get all teammates
            teammates = list(player_view.teammates.keys())

            for teammate_index in teammates:
                teammate_hand = state.playerHands[teammate_index]

                # Generate all ColorHint moves
                for color in Color:
                    if color == Color.MULTI:
                        continue  # Skip MULTI color (not used in standard game)
                    # Find all cards matching this color
                    matching_indices = [
                        idx for idx, card in enumerate(teammate_hand.cards)
                        if card.color == color
                    ]
                    # Hint must include ALL matching cards (rule requirement)
                    if matching_indices:
                        move = ColorHint(teammate_index, matching_indices, color)
                        if state._validate(player_index, move):
                            valid_moves.append(move)

                # Generate all NumberHint moves
                for number in Number:
                    # Find all cards matching this number
                    matching_indices = [
                        idx for idx, card in enumerate(teammate_hand.cards)
                        if card.number == number
                    ]
                    # Hint must include ALL matching cards (rule requirement)
                    if matching_indices:
                        move = NumberHint(teammate_index, matching_indices, number)
                        if state._validate(player_index, move):
                            valid_moves.append(move)

        # Final safety check: double-validate all moves before returning
        # This ensures no invalid moves slip through due to state changes
        validated_moves = []
        for move in valid_moves:
            if state._validate(player_index, move):
                validated_moves.append(move)

        return validated_moves

