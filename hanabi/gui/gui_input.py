"""
GUI input handler for Hanabi game.
Handles click-based interactions for card selection and moves.
"""

import tkinter as tk
from typing import Optional, Callable, Tuple
from hanabi.core.enums import Color, Number
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint
from hanabi.core.game import Game
from .gui_display import GUIDisplay
from .gui_player import GUIPlayer


class GUIInput:
    """Handles GUI-based input for Hanabi moves."""

    def __init__(self, game: Game, display: GUIDisplay):
        """
        Initialize GUI input handler.

        Args:
            game: The game instance
            display: The GUI display
        """
        self._game = game
        self._display = display
        self._pending_move: Optional[Move] = None
        self._move_callback: Optional[Callable[[Move], None]] = None

        # Set up card click handlers
        self._setup_card_clicks()

    def setup_canvas_clicks(self):
        """Set up canvas click handlers (called after display is ready)."""
        # Card clicks are handled via the canvas click handler in display
        # which calls _on_canvas_click here
        pass

    def set_move_callback(self, callback: Callable[[Move], None]):
        """Set callback for when a move is made."""
        self._move_callback = callback

    def get_move(self, player_index: int) -> Optional[Move]:
        """
        Get a move from the player (non-blocking, returns None if no move ready).

        This is called by the game controller to check for moves.
        The actual move is made via callbacks when buttons are clicked.
        """
        # In GUI mode, moves are made via callbacks, not polling
        # This method is kept for interface compatibility
        return None

    def display_prompt(self, player_index: int) -> None:
        """Display input prompt (no-op in GUI mode)."""
        pass

    def _setup_card_clicks(self):
        """Set up card click event handlers."""
        # This will be called after display is set up
        pass

    def _on_canvas_click(self, event):
        """Handle canvas click events - detect card clicks and show action menu."""
        # If game is finished, ignore all clicks
        # But allow clicks when turns_left > 0 (current player still has their final turn)
        if self._game:
            if self._game.state.turns_left is not None:
                # Deck is exhausted - only ignore if 0 == turns_left
                if 0 == self._game.state.turns_left and self._game.is_finished:
                    return
            elif self._game.is_finished:
                # Game finished for other reasons (lives lost, perfect score, etc.)
                return

        # Don't show menu if it's not the GUI player's turn
        if not self._is_gui_player_turn():
            return

        # Check if there's an open menu
        menu_open = hasattr(self._display, "_action_menu") and self._display._action_menu

        # If menu is open, check if click is on the menu itself
        if menu_open:
            try:
                menu_x = self._display._action_menu.winfo_x()
                menu_y = self._display._action_menu.winfo_y()
                menu_width = self._display._action_menu.winfo_width()
                menu_height = self._display._action_menu.winfo_height()
                screen_x = event.x_root
                screen_y = event.y_root
                # Check if click is within menu bounds (in screen coordinates)
                if menu_x <= screen_x <= menu_x + menu_width and menu_y <= screen_y <= menu_y + menu_height:
                    return  # Click is on menu, don't close it
            except:
                pass

        # Check if click is on a card
        clicked_card = None
        if hasattr(self._display, "_card_positions") and self._display._card_positions:
            try:
                for (player_idx, card_idx), position in self._display._card_positions.items():
                    if 4 != len(position):
                        continue
                    x1, y1, x2, y2 = position
                    if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                        clicked_card = (player_idx, card_idx)
                        break
            except (KeyError, ValueError, TypeError) as e:
                # Handle any errors gracefully
                pass

        # If menu is open, close it first
        if menu_open:
            if hasattr(self._display, "_close_action_menu"):
                self._display._close_action_menu()

        # If clicking on a card, open menu for that card (whether menu was open or not)
        if clicked_card:
            player_idx, card_idx = clicked_card
            self._display.show_action_menu(
                player_idx,
                card_idx,
                event.x_root,  # Screen coordinates
                event.y_root,
            )
            return

        # No menu open - check if click is on a card
        if not hasattr(self._display, "_card_positions") or not self._display._card_positions:
            return

        # Check if click is on a card by checking stored positions
        try:
            for (player_idx, card_idx), position in self._display._card_positions.items():
                if 4 != len(position):
                    continue
                x1, y1, x2, y2 = position
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    # Show action menu at cursor position
                    self._display.show_action_menu(
                        player_idx,
                        card_idx,
                        event.x_root,  # Screen coordinates
                        event.y_root,
                    )
                    return
        except (KeyError, ValueError, TypeError) as e:
            # Handle any errors gracefully
            pass

    def _is_gui_player_turn(self) -> bool:
        """
        Check if it's currently a GUI player's turn.

        Returns:
            True if current player is a GUI player, False otherwise
        """
        if not self._game:
            return False

        current_player_idx = self._game.current_player
        if current_player_idx >= len(self._game.team.players):
            return False

        current_player = self._game.team.players[current_player_idx]
        return isinstance(current_player, GUIPlayer)
