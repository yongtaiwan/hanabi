"""
Observer interface for Hanabi game.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game import GameSettings, CommonView, PlayerView
    from .moves import Move


class Observer(ABC):
    """Observer interface for observing game state."""

    @abstractmethod
    def observe(
        self,
        player_index: int,
        move: Move,
        observer_view: PlayerView,
    ) -> None:
        """
        Observe a move made by a player.

        Args:
            player_index: Index of the player who made the move
            move: The move that was made
            observer_view: This observer's :class:`PlayerView` after the move (same model as
                :meth:`Player.play`). Observers that do not use it may ignore the argument.
        """
        pass

    @property
    @abstractmethod
    def gameSettings(self) -> GameSettings:
        """Get the game settings."""
        pass

    @property
    @abstractmethod
    def commonView(self) -> CommonView:
        """Get the common view of the game state."""
        pass

