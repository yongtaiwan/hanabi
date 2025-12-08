"""
Console Observer implementation for Hanabi game.
"""

from typing import Optional
from hanabi.core.observer import Observer
from hanabi.core.game import GameSettings, CommonView
from hanabi.core.moves import Move
from .console_display import ConsoleDisplay


class ConsoleObserver(Observer):
    """Observer for console that handles display updates."""

    def __init__(self, display: Optional[ConsoleDisplay] = None):
        """
        Initialize a console observer.

        Args:
            display: The ConsoleDisplay instance to use for rendering
        """
        self._display = display
        self._game_settings: Optional[GameSettings] = None
        self._common_view: Optional[CommonView] = None

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
        """Set the common view."""
        self._common_view = common_view

    def set_display(self, display: ConsoleDisplay) -> None:
        """Set the ConsoleDisplay instance."""
        self._display = display

    def observe(self, player_index: int, move: Move) -> None:
        """
        Observe a move made by a player and update the display.

        Args:
            player_index: Index of the player who made the move
            move: The move that was made
        """
        if self._display:
            # The display will be updated by the game engine
            # This observer just tracks the move
            pass

