"""
Player classes for Hanabi game.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import random
from typing import TYPE_CHECKING, List, Dict, Optional, Union

if TYPE_CHECKING:
    from .game import PlayerView
    from .moves import Move
    from .observer import Observer
    from .game import GameSettings, CommonView

from .observer import Observer
from .game import PlayerView
from .moves import Move, Play, Discard, ColorHint, NumberHint, CardMove, Hint
from .enums import Color, Number


class Player(ABC):
    """Interface for a player in Hanabi."""

    @abstractmethod
    def play(self, player_view: PlayerView) -> Move:
        """
        Make a move based on the current player view.

        Args:
            player_view: The current view of the game from this player's perspective

        Returns:
            The move to make
        """
        pass


class BasePlayer(Observer, Player):
    """Base class for players that implements both Observer and Player."""

    def __init__(self, player_index: int):
        """
        Initialize a base player.

        Args:
            player_index: The index of this player
        """
        self._player_index = player_index
        self._game_settings = None
        self._common_view = None

    @property
    def playerIndex(self) -> int:
        """Get the player index."""
        return self._player_index

    @property
    def gameSettings(self) -> GameSettings:
        """Get the game settings."""
        if self._game_settings is None:
            raise ValueError("Game settings not set")
        return self._game_settings

    @property
    def commonView(self) -> CommonView:
        """Get the common view of the game state."""
        if self._common_view is None:
            raise ValueError("Common view not set")
        return self._common_view

    def set_game_settings(self, game_settings: GameSettings) -> None:
        """Set the game settings."""
        self._game_settings = game_settings

    def set_common_view(self, common_view: CommonView) -> None:
        """Set the common view (all players share the same reference)."""
        self._common_view = common_view

    def observe(self, player_index: int, move: Move, **kwargs) -> None:
        """
        Observe a move made by a player.

        Args:
            player_index: Index of the player who made the move
            move: The move that was made
            **kwargs: Optional context (e.g. game= for strategies that need hint-time state)
        """
        # Base implementation - can be overridden by subclasses
        pass

    @abstractmethod
    def play(self, player_view: PlayerView) -> Move:
        """
        Make a move based on the current player view.

        Args:
            player_view: The current view of the game from this player's perspective

        Returns:
            The move to make
        """
        pass


class HintTrackingPlayer(BasePlayer):
    """Base class for players that track hints about their own hand."""

    def __init__(self, player_index: int):
        """
        Initialize a hint-tracking player.

        Args:
            player_index: The index of this player
        """
        super().__init__(player_index)
        self._hints: Dict[int, Dict[str, Optional[Union[Color, Number]]]] = {}

    def observe(self, player_index: int, move: Move, **kwargs) -> None:
        """
        Observe a move and update hint tracking if it affects this player.

        Args:
            player_index: Index of the player who made the move
            move: The move that was made
        """
        super().observe(player_index, move, **kwargs)

        # If this player received a hint
        if isinstance(move, Hint) and move.teammate == self._player_index:
            self._updateHintsFromHint(move)

        # If this player played/discarded a card
        elif isinstance(move, CardMove) and player_index == self._player_index:
            self._updateHintsFromCardMove(move)

    def _updateHintsFromHint(self, hint: Hint) -> None:
        """Update hints when receiving a hint."""
        # Get current hand size from game settings
        hand_size = self.gameSettings.maxCardsInHand

        for card_idx in hint.cards:
            # Validate card index is within bounds
            if card_idx < 0 or card_idx >= hand_size:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"[HintTrackingPlayer {self._player_index}] Received hint with invalid card index {card_idx} "
                    f"(hand size: {hand_size}). Ignoring this index."
                )
                continue

            if card_idx not in self._hints:
                self._hints[card_idx] = {"color": None, "number": None}

            if isinstance(hint, ColorHint):
                self._hints[card_idx]["color"] = hint.color
            elif isinstance(hint, NumberHint):
                self._hints[card_idx]["number"] = hint.number

    def _updateHintsFromCardMove(self, move: CardMove) -> None:
        """Update hints when playing/discarding a card."""
        card_index = move.card

        # Remove hints for the card being played/discarded
        if card_index in self._hints:
            del self._hints[card_index]

        # Shift remaining hints to new indices
        # When a card is played/discarded:
        # 1. The card at card_index is removed (cards at positions > card_index shift left by 1)
        # 2. A new card is drawn and inserted at position 0 (all cards shift right by 1)
        # Net effect:
        # - Cards at indices < card_index: shift right by 1 (from insertion at 0)
        # - Cards at indices > card_index: shift left by 1 (from removal), then right by 1 (from insertion) = no net change
        # Special case: when card_index = 0, card removed and new card fills position 0, so no net change for other cards
        new_hints = {}
        for old_idx, hint_data in self._hints.items():
            if old_idx < card_index:
                # Card shifted right by 1 due to new card insertion at position 0
                new_hints[old_idx + 1] = hint_data
            elif old_idx > card_index:
                # Card shifted left by 1 from removal, then right by 1 from insertion = no net change
                # This includes the special case when card_index = 0 (all remaining cards have old_idx > 0)
                new_hints[old_idx] = hint_data
        self._hints = new_hints

    def getHints(self) -> Dict[int, Dict[str, Optional[Union[Color, Number]]]]:
        """
        Get hints for this player's hand.

        Returns:
            Dictionary mapping card index to hint data (color and/or number)
        """
        return {
            idx: {
                "color": h.get("color"),
                "number": h.get("number")
            }
            for idx, h in self._hints.items()
        }


class HumanPlayer(HintTrackingPlayer):
    """Human player that requires manual input."""

    def __init__(self, player_index: int, input_handler=None):
        """
        Initialize a human player.

        Args:
            player_index: The index of this player
            input_handler: Optional function to get input (for testing)
        """
        super().__init__(player_index)
        self._input_handler = input_handler

    def play(self, player_view: PlayerView) -> Move:
        """
        Make a move (requires human input).

        Args:
            player_view: The current view of the game

        Returns:
            The move to make
        """
        pass

    def get_decision_summary(self) -> Optional[str]:
        """
        Get a summary of the last decision made.

        Returns:
            "human decision" for human players
        """
        return "human decision"

class StrategyAlphaPlayer(BasePlayer):
    """Strategy player implementing Alpha strategy."""

    def play(self, player_view: PlayerView) -> Move:
        """
        Make a move using the Alpha strategy.

        Args:
            player_view: The current view of the game

        Returns:
            A move based on the Alpha strategy
        """
        # Placeholder for Alpha strategy implementation
        # This would contain the actual strategy logic
        common_view = self.commonView

        # Simple strategy: try to play if we have hint tokens, otherwise discard
        if common_view.hintTokens < self.gameSettings.maxHintTokens:
            # Prefer discarding to gain hint tokens
            return Discard(0)  # Simplified - would need actual strategy
        else:
            # Try to play a card
            return Play(0)  # Simplified - would need actual strategy


class PlayerTeam:
    """Represents a team of players (all players are BasePlayer instances and observe all moves)."""

    def __init__(self, players: List[BasePlayer]):
        """
        Initialize a player team.

        Args:
            players: List of BasePlayer instances in the team (all observe all moves)
        """
        self._players = players.copy()

    @property
    def players(self) -> List[BasePlayer]:
        """Get the list of players in the team."""
        return self._players.copy()

    def name(self) -> str:
        """
        Get the name of the team.

        Returns:
            The team name as a string
        """
        # Default implementation - can be overridden or extended
        return f"Team({len(self._players)} players)"

    def __repr__(self) -> str:
        return f"PlayerTeam(players={len(self._players)})"

