"""
GUI Observer implementation for Hanabi game.
"""

from typing import Optional
from hanabi.core.observer import Observer
from hanabi.core.game import GameSettings, CommonView, PlayerView
from hanabi.core.moves import Move


class GUIObserver(Observer):
    """Observer for GUI that handles display updates."""

    def __init__(self, display=None):
        """
        Initialize a GUI observer.

        Args:
            display: The GUIDisplay instance to use for rendering
        """
        self._display = display
        self._game_settings: Optional[GameSettings] = None
        self._common_view: Optional[CommonView] = None

    @property
    def gameSettings(self) -> GameSettings:
        """Get the game settings."""
        assert self._game_settings is not None, "Game settings not set"
        return self._game_settings

    @property
    def commonView(self) -> CommonView:
        """Get the common view of the game state."""
        assert self._common_view is not None, "Common view not set"
        return self._common_view

    def set_game_settings(self, game_settings: GameSettings) -> None:
        """Set the game settings."""
        self._game_settings = game_settings

    def set_common_view(self, common_view: CommonView) -> None:
        """Set the common view."""
        self._common_view = common_view

    def set_display(self, display) -> None:
        """Set the GUIDisplay instance."""
        self._display = display

    def observe(
        self,
        player_index: int,
        move: Move,
        observer_view: PlayerView,
    ) -> None:
        """
        Observe a move made by a player and update the display.

        Args:
            player_index: Index of the player who made the move
            move: The move that was made
            observer_view: This observer's view after the move (from the engine).
        """
        if self._display:
            # Update display when a move is observed
            # The display will handle the rendering
            pass

