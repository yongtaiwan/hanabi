"""
GUI Player implementation for Hanabi game.
"""

import threading
from typing import Optional
from hanabi.core.player import HumanPlayer
from hanabi.core.game import PlayerView, Game
from hanabi.core.moves import Move


class GUIPlayer(HumanPlayer):
    """Human player for GUI that gets moves from GUI input and updates display."""

    def __init__(self, player_index: int, game: Optional[Game], display):
        """
        Initialize a GUI player.

        Args:
            player_index: The index of this player
            game: The game instance (can be None initially, set later)
            display: GUIDisplay instance for updating the display
        """
        super().__init__(player_index)
        self._game = game
        self._display = display
        self._pending_move: Optional[Move] = None
        self._move_event = threading.Event()  # Event to signal when move is ready
        self._lock = threading.Lock()  # Lock for thread-safe access

    def set_move(self, move: Move) -> None:
        """
        Set a move from GUI input (called from GUI thread).

        Args:
            move: The move to make
        """
        with self._lock:
            self._pending_move = move
        self._move_event.set()  # Signal that move is ready

    def play(self, player_view: PlayerView) -> Move:
        """
        Get a move from GUI input (blocks until move is set).

        Args:
            player_view: The current view of the game

        Returns:
            The move to make
        """
        # Update display to show current state (schedule on GUI thread)
        # But only if not animating (to prevent premature updates during card animations)
        if self._game:

            def safe_display_update():
                # Check if animating before updating
                if not (self._display._is_animating or self._display._active_animations):
                    self._display.display_game_state(self._game, self.player_index)

            self._display.root.after(0, safe_display_update)

        # Wait for move to be set from GUI
        self._move_event.wait()

        with self._lock:
            move = self._pending_move
            self._pending_move = None
        self._move_event.clear()

        assert move is not None, "Move was set to None"

        return move
