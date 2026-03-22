"""
GUI display for Hanabi game with round table layout.
Mimics physical game setup with players around a table.
"""

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    raise ImportError(
        "tkinter is not available. On macOS, install it with: brew install python-tk\n"
        "Or use the CLI version: python -m hanabi"
    )
from typing import Dict, Optional, List, Tuple, Callable
from math import cos, sin, pi, radians
import math
from datetime import datetime
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card
from hanabi.core.game import Game, GameState
from hanabi.core.moves import Move, ColorHint, NumberHint


class GUIDisplay:
    """GUI display for Hanabi game with round table layout."""

    # Color mappings for cards (matching PDF style)
    COLOR_COLORS = {
        Color.WHITE: "#F5F5F5",
        Color.RED: "#DC143C",
        Color.YELLOW: "#FFD700",
        Color.GREEN: "#228B22",
        Color.BLUE: "#4169E1",
        Color.MULTI: "#9370DB",  # Purple for multicolor
    }

    COLOR_NAMES = {
        Color.WHITE: "White",
        Color.RED: "Red",
        Color.YELLOW: "Yellow",
        Color.GREEN: "Green",
        Color.BLUE: "Blue",
        Color.MULTI: "Multi",
    }

    def __init__(self, root: tk.Tk):
        """
        Initialize GUI display.

        Args:
            root: Tkinter root window
        """
        self.root = root
        self.root.title("Hanabi - Fireworks Game")
        # Don't set geometry here - let play_gui_game() handle window sizing (maximized)
        self.root.configure(bg="#2C3E50")  # Dark blue-gray background

        # Game state
        self._game: Optional[Game] = None
        self._current_player: int = 0
        self._show_all_cards: bool = False  # For replay mode

        # UI components
        self._canvas: Optional[tk.Canvas] = None
        self._card_widgets: Dict[Tuple[int, int], int] = {}  # (player_idx, card_idx) -> widget_id
        self._card_positions: Dict[Tuple[int, int], Tuple[int, int, int, int]] = {}  # (player_idx, card_idx) -> (x1, y1, x2, y2)
        self._firework_widgets: Dict[Color, List[int]] = {}  # Color -> list of widget IDs
        self._token_widgets: Dict[str, List[int]] = {}  # "hint" or "life" -> list of widget IDs
        self._status_label: Optional[tk.Label] = None
        self._score_label: Optional[tk.Label] = None
        self._action_menu: Optional[tk.Toplevel] = None  # Popup menu for card actions
        self._action_menu_context: Optional[dict] = None  # Context for action menu (player_idx, card_idx, etc.)
        self._move_callback: Optional[Callable] = None
        self._input_handler: Optional[Callable] = None  # Input handler for card clicks
        self._suppress_dialogs: bool = False  # Set to True to disable messageboxes (for testing)

        # Event history
        self._event_history: List[Tuple[str, str]] = []  # List of (timestamp, message) tuples
        self._live_turn_numbers: List[int] = []  # Track turn numbers for each move in live play
        self._history_listbox: Optional[tk.Listbox] = None
        self._history_scrollbar: Optional[ttk.Scrollbar] = None

        # Hint tracking (independent of player implementations)
        # Structure: player_index -> card_index -> {"color": Color or None, "number": Number or None}
        self._hints: Dict[int, Dict[int, Dict[str, Optional[Color | Number]]]] = {}

        # Animation state
        self._animations_enabled: bool = True  # Can be disabled for faster gameplay
        self._active_animations: List[Dict] = []  # List of active animation objects
        self._animation_queue: List[Dict] = []  # Queue of pending animations
        self._animation_duration_ms: int = 100  # Animation duration in milliseconds (0.1 seconds, 5x faster)
        self._animation_fps: int = 60  # Frames per second for animation
        self._is_animating: bool = False  # Track if an animation is currently playing
        self._active_explosions: List[Dict] = []  # List of active explosion effects
        self._pending_game_state: Optional[Game] = None  # Store game state to apply after animation
        self._pending_player_index: Optional[int] = None  # Store player index to apply after animation
        self._frozen_game_state: Optional[Game] = None  # Store old state to use during animation
        self._frozen_state: Optional[GameState] = None  # Store old GameState directly during animation

        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        # Main container with horizontal split
        main_frame = tk.Frame(self.root, bg="#2C3E50")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Top status bar
        status_frame = tk.Frame(main_frame, bg="#34495E", height=40)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        status_frame.pack_propagate(False)

        # Home button (top left, always visible during play/replay)
        self._home_btn = tk.Button(
            status_frame,
            text="🏠 Home",
            command=None,  # Will be set by GUIGame
            bg="#E74C3C",
            fg="black",
            font=("Arial", 9, "bold"),
            highlightthickness=0,
            state=tk.DISABLED  # Disabled until game starts
        )
        self._home_btn.pack(side=tk.LEFT, padx=10, pady=5)

        # Store reference to status frame for later use
        self._status_frame = status_frame

        self._status_label = tk.Label(
            status_frame,
            text="Hanabi - Fireworks Game",
            bg="#34495E",
            fg="white",
            font=("Arial", 14, "bold")
        )
        self._status_label.pack(side=tk.LEFT, padx=10, pady=5)

        # Last turn warning banner (initially hidden)
        self._last_turn_label = tk.Label(
            status_frame,
            text="⚠️ LAST TURN - Deck is empty!",
            bg="#E74C3C",
            fg="white",
            font=("Arial", 12, "bold"),
            padx=15,
            pady=3
        )
        # Will be packed when needed

        self._score_label = tk.Label(
            status_frame,
            text="Score: 0/25",
            bg="#34495E",
            fg="#FFD700",
            font=("Arial", 12)
        )
        self._score_label.pack(side=tk.RIGHT, padx=10, pady=5)

        # Main content area: canvas on left, history panel on right
        content_frame = tk.Frame(main_frame, bg="#2C3E50")
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas for game table (left side)
        self._canvas_frame = tk.Frame(content_frame, bg="#2C3E50")
        self._canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self._canvas = tk.Canvas(
            self._canvas_frame,
            bg="#1A252F",  # Darker background for table
            highlightthickness=0
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        # Bind click to handle card clicks and close action menu
        self._canvas.bind("<Button-1>", self._on_canvas_click)

        # Event history panel (right side) - wider to show full events
        self._history_frame = tk.Frame(content_frame, bg="#34495E", width=550)
        self._history_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        self._history_frame.pack_propagate(False)

        # History label
        history_label = tk.Label(
            self._history_frame,
            text="Game Events",
            bg="#34495E",
            fg="white",
            font=("Arial", 12, "bold")
        )
        history_label.pack(pady=5)

        # History text widget with scrollbar (for colored text)
        listbox_frame = tk.Frame(self._history_frame, bg="#34495E")
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._history_text = tk.Text(
            listbox_frame,
            bg="#2C3E50",
            fg="white",
            font=("Arial", 11),
            wrap=tk.WORD,
            state=tk.DISABLED,  # Make read-only
            selectbackground="#3498DB",
            selectforeground="white"
        )
        self._history_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._history_scrollbar = ttk.Scrollbar(
            listbox_frame,
            orient=tk.VERTICAL,
            command=self._history_text.yview
        )
        self._history_text.config(yscrollcommand=self._history_scrollbar.set)
        self._history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure text tags for colors
        self._history_text.tag_config("player", foreground="#87CEEB")  # Light blue
        self._history_text.tag_config("color_white", foreground="#F5F5F5")  # White
        self._history_text.tag_config("color_red", foreground="#DC143C")  # Red
        self._history_text.tag_config("color_yellow", foreground="#FFD700")  # Yellow
        self._history_text.tag_config("color_green", foreground="#228B22")  # Green
        self._history_text.tag_config("color_blue", foreground="#4169E1")  # Blue
        self._history_text.tag_config("color_multi", foreground="#9370DB")  # Purple
        self._history_text.tag_config("number", foreground="#FFFFFF", font=("Arial", 11, "bold"))
        self._history_text.tag_config("error", foreground="#FF6B6B")  # Light red
        self._history_text.tag_config("timestamp", foreground="#888888")  # Grey
        self._history_text.tag_config("game_end", foreground="#FFD700", font=("Arial", 11, "bold"))  # Gold for game end

    def _on_canvas_click(self, event):
        """Handle canvas click - delegate to input handler or close menu."""
        # If game is finished, ignore all clicks
        # But allow clicks when turns_left > 0 (current player still has their final turn)
        if self._game:
            state = self._game.state
            if state.turns_left is not None:
                # Deck is exhausted - only ignore if turns_left == 0
                if state.turns_left == 0 and self._game.is_finished:
                    return
            elif self._game.is_finished:
                # Game finished for other reasons (lives lost, perfect score, etc.)
                return

        # Delegate to input handler if available
        if self._input_handler and hasattr(self._input_handler, '_on_canvas_click'):
            self._input_handler._on_canvas_click(event)
        else:
            # Fallback: close action menu if clicking outside cards
            clicked_card = None
            if hasattr(self, '_card_positions') and self._card_positions:
                for (player_idx, card_idx), position in self._card_positions.items():
                    if len(position) != 4:
                        continue
                    x1, y1, x2, y2 = position
                    if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                        clicked_card = (player_idx, card_idx)
                        break

            if clicked_card is None and self._action_menu:
                self._close_action_menu()

    def set_input_handler(self, input_handler):
        """Set the input handler for card clicks."""
        self._input_handler = input_handler

    def _close_action_menu(self):
        """Close the action menu popup."""
        if self._action_menu:
            self._action_menu.destroy()
            self._action_menu = None
            self._action_menu_context = None

    def _add_event_to_history(self, message: str, event_type: str = "info", player_index: int = None, is_ai: bool = False, turn_number: int = None):
        """Add an event to the history panel (concise format)."""
        # Make message concise
        concise_message = message

        # Simplify common patterns
        import re
        # Format hint messages: "hints player 2: white at 2, 4, 5. hint tokens: X"
        # -> "P1 hints P2: white at 2, 4, 5"
        # Also remove hint token information from all messages
        hint_pattern = r'hints player (\d+): (\w+) at ([^.]+)\.'
        def format_hint(match):
            target_player = match.group(1)
            value = match.group(2).lower()  # color name or number
            indices_str = match.group(3)  # "2, 4, 5"
            # Clean up indices: remove extra spaces and split
            indices = [idx.strip() for idx in indices_str.split(',')]
            # Use provided player_index or try to get from engine
            if player_index is not None:
                player_num = player_index + 1
            elif self._game:
                # Fallback: use current player (may be wrong if turn advanced)
                player_num = self._current_player + 1
            else:
                return f"hints P{target_player}: {value} at {', '.join(indices)}"
            return f"P{player_num} hints P{target_player}: {value} at {', '.join(indices)}"

        concise_message = re.sub(hint_pattern, format_hint, concise_message)

        # Remove hint token information from all messages (e.g., "hint tokens: 5" or "hint tokens: 5/8")
        concise_message = re.sub(r'\.?\s*hint tokens?:\s*\d+(?:/\d+)?', '', concise_message, flags=re.IGNORECASE)

        # Add player prefix if message doesn't start with P\d+
        # Messages from engine are like "plays red 1" or "hints player 2: ..."
        # We need to add "P1 " prefix (or "P1 (AI) " for AI players)
        # BUT: Don't add prefix for "Game Over" or "The deck is empty" messages
        if not re.match(r'^P\d+', concise_message) and not concise_message.lower().startswith("game over") and not concise_message.lower().startswith("the deck is empty"):
            if player_index is not None:
                player_num = player_index + 1
                ai_suffix = " (AI)" if is_ai else ""
                concise_message = f"P{player_num}{ai_suffix} {concise_message}"
            elif self._game:
                player_num = self._current_player + 1
                ai_suffix = " (AI)" if is_ai else ""
                concise_message = f"P{player_num}{ai_suffix} {concise_message}"

        # Remove duplicate player references at start (e.g., "P1 P1 hints" -> "P1 hints")
        concise_message = re.sub(r'^(P\d+)\s+\1\s+', r'\1 ', concise_message)

        # Simplify "plays COLOR NUMBER" format (already lowercase from engine)
        # Handle "plays red 1" -> "plays red 1" (already correct)
        # Handle "discards red 1" -> "discards red 1" (already correct)
        # The engine now returns lowercase, so we just need to ensure proper formatting
        # Trim whitespace
        concise_message = concise_message.strip()

        # Get turn number - use provided turn_number, stored turn number for replay, or track for live play
        if turn_number is not None:
            # Use provided turn number (from callback)
            pass
        elif hasattr(self, '_replay_turn_numbers') and self._replay_turn_numbers:
            # Use stored turn number for this specific move in replay
            move_index = len(self._event_history)  # Current move index
            if move_index < len(self._replay_turn_numbers):
                turn_number = self._replay_turn_numbers[move_index]
            else:
                turn_number = 1
        elif self._live_turn_numbers:
            # Use tracked turn number for this specific move in live play
            move_index = len(self._event_history)  # Current move index
            if move_index < len(self._live_turn_numbers):
                turn_number = self._live_turn_numbers[move_index]
            else:
                # Fallback: use current game state (shouldn't happen)
                turn_number = self._game.state.turn_number if self._game else 1
        elif self._game:
            # Fallback: use turn number from game state (for live play)
            # This should only happen if turn_number wasn't provided and we haven't tracked it yet
            turn_number = self._game.state.turn_number
        else:
            turn_number = 1

        # Get timestamp - generate for live play, use replay timestamp if in replay mode
        timestamp = None
        # Check if we're in replay mode (has _replay_turn_numbers attribute)
        is_replay_mode = hasattr(self, '_replay_turn_numbers') and self._replay_turn_numbers
        if is_replay_mode:
            # Replay mode: use timestamp from replay history if available
            if hasattr(self, '_replay_timestamps') and self._replay_timestamps:
                move_index = len(self._event_history)  # Current move index
                if move_index < len(self._replay_timestamps):
                    timestamp = self._replay_timestamps[move_index]
        else:
            # Live play mode: generate timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")

        # Format message with timestamp if available, otherwise just turn number
        if timestamp:
            formatted_message = f"[{timestamp} T{turn_number:02d}] {concise_message}"
        else:
            # Pad turn number with 0 for alignment (e.g., T01, T02, ..., T10)
            formatted_message = f"[T{turn_number:02d}] {concise_message}"
        self._event_history.append((event_type, formatted_message))

        # Track turn number for this move (for live play, if not in replay mode)
        # This ensures we can look up the correct turn number even if the game state changes
        if not hasattr(self, '_replay_turn_numbers') or not self._replay_turn_numbers:
            # Only track if not in replay mode (replay mode uses _replay_turn_numbers)
            self._live_turn_numbers.append(turn_number)

        if self._history_text:
            # Enable text widget for editing
            self._history_text.config(state=tk.NORMAL)

            # Parse and colorize the message
            self._insert_colored_event(formatted_message, event_type)

            # Auto-scroll to bottom
            self._history_text.see(tk.END)

            # Limit history to last 100 events
            if len(self._event_history) > 100:
                self._event_history.pop(0)
                # Remove first line
                self._history_text.delete("1.0", "2.0")

            # Disable text widget (make read-only)
            self._history_text.config(state=tk.DISABLED)

    def _insert_colored_event(self, message: str, event_type: str):
        """Insert a colored event message into the history text widget - explicit coloring."""
        import re

        # Extract timestamp
        timestamp_match = re.match(r'\[([^\]]+)\]', message)
        if timestamp_match:
            timestamp = timestamp_match.group(1)
            message_after_timestamp = message[len(f"[{timestamp}]"):].strip()
            # Insert timestamp in grey
            self._history_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
        else:
            message_after_timestamp = message

        # Parse message explicitly - don't use regex for coloring
        # Known patterns (all lowercase, present tense):
        # - P1 hints P2: white at 2, 4, 5
        # - P1 plays red 1.
        # - P1 discards blue 3.

        # Split into words and colorize explicitly
        words = message_after_timestamp.split()
        color_tags = {
            "white": "color_white",
            "red": "color_red",
            "yellow": "color_yellow",
            "green": "color_green",
            "blue": "color_blue",
            "multi": "color_multi"
        }

        for i, word in enumerate(words):
            # Add space before word (except first)
            if i > 0:
                self._history_text.insert(tk.END, " ")

            # Check if word starts with P and is a player reference (don't color code it)
            if word.startswith("P") and len(word) > 1 and word[1:].isdigit():
                self._history_text.insert(tk.END, word)  # Insert without color tag
            # Check if word is a color name (exact match, case insensitive)
            elif word.lower() in color_tags:
                tag = color_tags[word.lower()]
                self._history_text.insert(tk.END, word, tag)
            # Check if word is a number (standalone or with trailing punctuation like "1.")
            elif word.rstrip('.,;:!?').isdigit():
                # Extract the number part and any trailing punctuation
                number_part = word.rstrip('.,;:!?')
                punctuation = word[len(number_part):]
                # Check if previous word was a color - if so, use that color tag (color both "yellow" and "1" in "yellow 1")
                if i > 0 and words[i - 1].lower() in color_tags:
                    prev_color = words[i - 1].lower()
                    tag = color_tags[prev_color]
                    # Color both the number and punctuation with the same color tag
                    self._history_text.insert(tk.END, number_part, tag)
                    if punctuation:
                        self._history_text.insert(tk.END, punctuation, tag)
                else:
                    self._history_text.insert(tk.END, number_part, "number")
                    if punctuation:
                        self._history_text.insert(tk.END, punctuation)
            # Check if word contains color+number (e.g., "red5", "blue3")
            elif len(word) > 1:
                # Try to split color and number
                for color_name in ["white", "red", "yellow", "green", "blue", "multi"]:
                    if word.lower().startswith(color_name) and word[len(color_name):].isdigit():
                        # Split and colorize separately - both parts get the same color tag
                        tag = color_tags[color_name]
                        self._history_text.insert(tk.END, word[:len(color_name)], tag)
                        self._history_text.insert(tk.END, word[len(color_name):], tag)  # Number also gets color tag
                        break
                else:
                    # Not a color+number combo, insert as-is
                    if event_type == "error" or word.startswith("Error"):
                        self._history_text.insert(tk.END, word, "error")
                    elif event_type == "game_end":
                        # Colorize game end message words
                        if word.lower() in ["game", "over", "final", "score"]:
                            self._history_text.insert(tk.END, word, "game_end")
                        elif "/" in word:
                            # Score like "25/25" - split and colorize
                            parts = word.split("/")
                            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                                self._history_text.insert(tk.END, parts[0], "number")
                                self._history_text.insert(tk.END, "/", "game_end")
                                self._history_text.insert(tk.END, parts[1], "number")
                            else:
                                self._history_text.insert(tk.END, word, "game_end")
                        elif word.isdigit():
                            self._history_text.insert(tk.END, word, "number")
                        else:
                            self._history_text.insert(tk.END, word, "game_end")
                    else:
                        self._history_text.insert(tk.END, word)
            else:
                # Single character or other
                if event_type == "error":
                    self._history_text.insert(tk.END, word, "error")
                elif event_type == "game_end":
                    self._history_text.insert(tk.END, word, "game_end")
                else:
                    self._history_text.insert(tk.END, word)

        # Add newline
        self._history_text.insert(tk.END, "\n")

    def set_game(self, game: Game):
        """Set the game instance."""
        self._game = game

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

        from .gui_player import GUIPlayer
        current_player = self._game.team.players[current_player_idx]
        return isinstance(current_player, GUIPlayer)

    def set_show_all_cards(self, show_all: bool):
        """Set whether to show all cards (for replay mode)."""
        self._show_all_cards = show_all

    def set_suppress_dialogs(self, suppress: bool):
        """Set whether to suppress message boxes (for testing)."""
        self._suppress_dialogs = suppress

    def display_game_state(self, game: Game, player_index: int) -> None:
        """Display the game state from a player's perspective."""
        # If we're currently animating (actively moving a card), skip display update
        # to prevent showing cards in their destination before animation completes
        # Check both the flag and active animations to be safe
        if self._is_animating or self._active_animations:
            # Don't update display while animation is actively in progress
            # Store the pending state to apply after animation completes
            self._pending_game_state = game
            self._pending_player_index = player_index
            # CRITICAL: Do NOT update self._game here - keep using frozen old state
            # The frozen state (_frozen_state) is used by all drawing methods
            # This ensures fireworks show the old state during animation
            return

        # Not animating - safe to update to new state
        # Clear frozen state first (in case it was set)
        self._frozen_game_state = None
        self._frozen_state = None
        # Now update to new state
        self._game = game
        self._current_player = player_index

        # Clear canvas, but preserve animated cards and explosions
        # Delete all items except animated cards and explosions
        all_items = self._canvas.find_all()
        for item in all_items:
            tags = self._canvas.gettags(item)
            if "animated_card" not in tags and "explosion" not in tags:
                self._canvas.delete(item)

        # After redrawing, ensure animated cards and explosions are still on top
        if self._active_animations:
            for animation in self._active_animations:
                if animation.get('widget_ids'):
                    for widget_id in animation['widget_ids']:
                        try:
                            self._canvas.lift(widget_id)
                        except:
                            pass

        # Ensure explosions are on top
        if self._active_explosions:
            for explosion in self._active_explosions:
                if explosion.get('widget_ids'):
                    for widget_id in explosion['widget_ids']:
                        try:
                            self._canvas.lift(widget_id)
                        except:
                            pass

        self._card_widgets.clear()
        self._card_positions.clear()
        self._firework_widgets.clear()
        self._token_widgets.clear()

        # Draw round table background
        self._draw_table()

        # Draw center area: tokens center, played cards above, discarded below
        self._draw_center_area()

        # Draw all player hands in a circle (current player at bottom)
        self._draw_player_hands()

        # Update status
        score = game.get_score()
        max_score = 25
        self._score_label.config(text=f"Score: {score}/{max_score}")

        # Show "last turn" warning if deck is empty
        self._update_last_turn_warning()

    def _draw_table(self):
        """Draw the round table background."""
        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800

        center_x = width // 2
        center_y = height // 2
        # Make table smaller (was // 3, now // 4)
        table_radius = min(width, height) // 4

        # Draw table circle
        self._canvas.create_oval(
            center_x - table_radius,
            center_y - table_radius,
            center_x + table_radius,
            center_y + table_radius,
            fill="#3D4A5C",
            outline="#5A6B7D",
            width=3
        )

    def _draw_center_area(self):
        """Draw center area: tokens on top, played cards centered, discarded cards and deck below with labels."""
        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800

        center_x = width // 2
        center_y = height // 2

        # Get table radius for positioning
        table_radius = min(width, height) // 4

        # Draw tokens on top of table
        tokens_y = center_y - table_radius + 40
        self._draw_tokens(center_x, tokens_y)

        # Draw played cards (fireworks) centered, moved a bit higher
        self._draw_fireworks_row(center_x, center_y - 30)

        # Draw discarded cards in a row below center with label
        discard_y = center_y + 70
        self._draw_discard_row(center_x, discard_y)

        # Draw deck cards with fixed grid layout: cards maintain positions as they're drawn
        # Show all remaining cards (with "?" during play, actual cards in replay)
        # Use frozen OLD state during animation, otherwise use current state
        if self._frozen_state is not None:
            state = self._frozen_state
        elif self._game:
            state = self._game.state
        else:
            return
        deck_count = state.common_view.cards_to_draw
        draw_deck_index = state.draw_deck_index

        # Draw deck label and cards (with more spacing from discard pile)
        deck_y = center_y + 180

        # Show cards in grid layout (both play and replay modes)
        # Always use current game for start_position (doesn't change)
        if self._game:
            # Get the total initial deck size to create fixed grid
            initial_deck = self._game.state.start_position.draw_deck.cards
            total_deck_size = len(initial_deck)

            if total_deck_size > 0 and draw_deck_index < total_deck_size:
                # Get remaining cards from deck (in order)
                deck_cards = initial_deck[draw_deck_index:]

                # Create a mapping: original_deck_index -> card (for remaining cards only)
                remaining_cards_map = {}
                for i, card in enumerate(deck_cards):
                    original_index = draw_deck_index + i
                    remaining_cards_map[original_index] = card

                # Get number of remaining cards
                remaining_count = len(deck_cards)

                # Fixed grid layout: at most 2 rows, cards maintain fixed positions
                # At beginning: distribute remaining cards evenly across rows
                # During play: cards keep their fixed positions, just disappear when drawn
                card_width = 35
                card_height = 50
                horizontal_overlap = 15  # Overlap cards horizontally

                # Calculate row distribution based on initial remaining cards (after dealing to players)
                # This determines the grid layout that will be maintained throughout the game
                # Calculate how many cards were in the deck at the start (after initial dealing)
                # Always use current game for settings (settings don't change)
                num_players = self._game.settings.num_players
                cards_per_player = self._game.settings.max_cards_in_hand
                initial_remaining = total_deck_size - (num_players * cards_per_player)

                if initial_remaining == 0:
                    num_rows = 1
                    bottom_row_cards = 0
                    top_row_cards = 0
                elif initial_remaining == 1:
                    num_rows = 1
                    bottom_row_cards = 1
                    top_row_cards = 0
                else:
                    # Two rows: distribute initial remaining cards evenly
                    # Top row should have same or one more card than bottom row
                    num_rows = 2
                    bottom_row_cards = initial_remaining // 2  # Floor division
                    top_row_cards = initial_remaining - bottom_row_cards  # Top row gets the extra card if odd

                row_height = card_height + 5  # Space between rows

                # Calculate width for each row
                bottom_row_width = (bottom_row_cards - 1) * horizontal_overlap + card_width if bottom_row_cards > 0 else 0
                top_row_width = (top_row_cards - 1) * horizontal_overlap + card_width
                max_row_width = max(bottom_row_width, top_row_width) if bottom_row_width > 0 else top_row_width

                # Get table radius to ensure cards stay within table
                max_width = table_radius * 1.6  # Allow some margin

                # Scale down if needed
                if max_row_width > max_width:
                    scale = max_width / max_row_width
                    horizontal_overlap = max(5, int(horizontal_overlap * scale))
                    card_width = max(25, int(card_width * scale))
                    # Recalculate row widths
                    bottom_row_width = (bottom_row_cards - 1) * horizontal_overlap + card_width if bottom_row_cards > 0 else 0
                    top_row_width = (top_row_cards - 1) * horizontal_overlap + card_width
                    max_row_width = max(bottom_row_width, top_row_width) if bottom_row_width > 0 else top_row_width

                # Position cards: use max_row_width for centering
                start_x = center_x + max_row_width // 2 - card_width
                start_y = deck_y + (num_rows - 1) * row_height  # Start from bottom row

                # Build list of remaining cards sorted by original deck index
                remaining_indices = sorted(remaining_cards_map.keys())

                # Build list of card positions: (original_index, card, row, col_from_right)
                # Cards maintain fixed positions based on their position in the initial remaining deck
                # Position is determined by balanced distribution of initial remaining cards
                # Calculate the starting index of the remaining deck (after initial dealing)
                initial_deck_start_index = num_players * cards_per_player

                card_positions = []
                for original_index in remaining_indices:
                    card = remaining_cards_map[original_index]

                    # Determine which row and position based on position in initial remaining deck
                    # Position in initial remaining deck = original_index - initial_deck_start_index
                    position_in_initial_deck = original_index - initial_deck_start_index

                    if position_in_initial_deck < bottom_row_cards:
                        # Bottom row: first bottom_row_cards of initial remaining deck
                        row = 0
                        col_from_right = position_in_initial_deck  # Position within bottom row (0 = rightmost)
                    else:
                        # Top row: remaining cards after bottom_row_cards
                        row = 1
                        col_from_right = position_in_initial_deck - bottom_row_cards  # Position within top row (0 = rightmost)

                    card_positions.append((original_index, card, row, col_from_right))

                # Sort by position (left to right, bottom to top) so we draw left cards first
                # This ensures right cards are drawn last and appear on top (z-order)
                # Sort by row (ascending), then by -col_from_right (descending) so right cards (lower col) are drawn last
                card_positions.sort(key=lambda x: (x[2], -x[3]))  # Sort by row, then -col (descending)

                # Track top row rightmost position for label placement
                top_row_rightmost_x = None

                for original_index, card, row, col_from_right in card_positions:
                    # Position from right to left (rightmost is col 0)
                    card_x = start_x - (col_from_right * horizontal_overlap)
                    # Bottom row is row 0, top row is higher
                    card_y = start_y - (row * row_height)

                    # Track top row rightmost card position (for label placement)
                    if row == 1 and col_from_right == 0:  # Top row, rightmost card
                        top_row_rightmost_x = card_x + card_width

                    # Draw card (drawing left cards first, right cards last so right cards are on top)
                    # In play mode, use gray background; in replay mode, use actual card color
                    if self._show_all_cards:
                        # Replay mode: show actual card color
                        color_code = self.COLOR_COLORS.get(card.color, "#FFFFFF")
                    else:
                        # Play mode: use gray background for unknown cards
                        color_code = "#808080"  # Gray

                    self._canvas.create_rectangle(
                        card_x, card_y - card_height // 2,
                        card_x + card_width, card_y + card_height // 2,
                        fill=color_code,
                        outline="#000000",
                        width=1
                    )
                    # Draw number or "?" on top left
                    if self._show_all_cards:
                        # Replay mode: show actual number
                        number_text = str(card.number.value)
                    else:
                        # Play mode: show "?"
                        number_text = "?"

                    self._canvas.create_text(
                        card_x + 8, card_y - card_height // 2 + 8,
                        text=number_text,
                        fill="#000000",
                        font=("Arial", 10, "bold"),
                        anchor="nw"
                    )

                # Draw count label to the right of top row (if there are cards)
                if top_row_rightmost_x is not None:
                    label_x = top_row_rightmost_x + 15  # Space after rightmost card
                    label_y = start_y - row_height  # Top row y position
                else:
                    # No cards in top row, but still show count at expected position
                    # Calculate where top row rightmost would be
                    if num_rows == 1:
                        # Only bottom row, use its rightmost position
                        if bottom_row_cards > 0:
                            bottom_rightmost_x = start_x
                            label_x = bottom_rightmost_x + 15
                        else:
                            label_x = start_x + 15
                        label_y = start_y
                    else:
                        # Two rows, but no cards in top row - use top row position
                        label_x = start_x + 15
                        label_y = start_y - row_height

                # Always show count label
                self._canvas.create_text(
                    label_x, label_y,
                    text=f"{deck_count}",
                    fill="white",
                    font=("Arial", 11, "bold"),
                    anchor="w"  # Left-aligned
                )
            else:
                # No cards left (draw_deck_index >= total_deck_size), show count at expected position
                # Calculate grid layout to determine where label should be (use balanced distribution)
                # For positioning, assume balanced two-row layout if total_deck_size > 1
                if total_deck_size <= 1:
                    num_rows = 1
                    bottom_row_cards = total_deck_size
                    top_row_cards = 0
                else:
                    num_rows = 2
                    # Balanced distribution
                    bottom_row_cards = total_deck_size // 2
                    top_row_cards = total_deck_size - bottom_row_cards

                row_height = 55  # card_height + 5
                card_width = 35
                horizontal_overlap = 15
                bottom_row_width = (bottom_row_cards - 1) * horizontal_overlap + card_width if bottom_row_cards > 0 else 0
                top_row_width = (top_row_cards - 1) * horizontal_overlap + card_width
                max_row_width = max(bottom_row_width, top_row_width) if bottom_row_width > 0 else top_row_width

                # Position label where top row rightmost would be
                start_x = center_x + max_row_width // 2 - card_width
                start_y = deck_y + (num_rows - 1) * row_height
                label_x = start_x + 15
                label_y = start_y - (row_height if num_rows > 1 else 0)

                self._canvas.create_text(
                    label_x, label_y,
                    text=f"{deck_count}",
                    fill="white",
                    font=("Arial", 11, "bold"),
                    anchor="w"  # Left-aligned
                )

    def _draw_tokens(self, center_x: int, y: int):
        """Draw hint and life tokens on top of table."""
        # Use frozen OLD state during animation, otherwise use current state
        if self._frozen_state is not None:
            state = self._frozen_state
        elif self._game:
            state = self._game.state
        else:
            return
        # Always use current game for settings (settings don't change)
        if not self._game:
            return
        settings = self._game.settings

        hint_tokens = state.common_view.hint_tokens
        life_tokens = state.common_view.live_tokens
        max_hints = settings.max_hint_tokens
        max_lives = settings.max_live_tokens

        token_size = 18
        token_spacing = 4

        # Draw hint tokens (blue clock tokens)
        self._canvas.create_text(
            center_x - 50, y - 20,
            text="Hints",
            fill="white",
            font=("Arial", 11, "bold"),
            anchor="center"
        )

        hint_widgets = []
        hint_start_x = center_x - 50 - (min(max_hints, 4) * (token_size + token_spacing)) // 2
        for i in range(max_hints):
            x = hint_start_x + (i % 4) * (token_size + token_spacing)
            token_y = y + (i // 4) * (token_size + token_spacing)

            color = "#4169E1" if i < hint_tokens else "#1A1A3E"
            widget = self._canvas.create_oval(
                x, token_y,
                x + token_size, token_y + token_size,
                fill=color,
                outline="#87CEEB",
                width=2
            )
            hint_widgets.append(widget)
        self._token_widgets["hint"] = hint_widgets

        # Draw life tokens (red/orange fuse tokens)
        self._canvas.create_text(
            center_x + 50, y - 20,
            text="Lives",
            fill="white",
            font=("Arial", 11, "bold"),
            anchor="center"
        )

        life_widgets = []
        life_start_x = center_x + 50 - (max_lives * (token_size + token_spacing)) // 2
        for i in range(max_lives):
            x = life_start_x + i * (token_size + token_spacing)
            token_y = y

            if i < life_tokens:
                # Use same color for all remaining lives
                color = "#FF4500"  # Red/orange for all remaining lives
            else:
                color = "#000000"  # Black for lost lives

            widget = self._canvas.create_oval(
                x, token_y,
                x + token_size, token_y + token_size,
                fill=color,
                outline="#654321",
                width=2
            )
            life_widgets.append(widget)
        self._token_widgets["life"] = life_widgets

    def _draw_fireworks_row(self, center_x: int, y: int):
        """Draw fireworks (played cards) in a horizontal row, centered."""
        # Use frozen OLD state during animation, otherwise use current state
        # This ensures fireworks don't update until animation completes
        if self._frozen_state is not None:
            # Use the frozen old state directly
            state = self._frozen_state
        elif self._game:
            state = self._game.state
        else:
            return
        cards_played = state.common_view.cards_played

        colors = [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]
        card_width = 50
        card_height = 70
        spacing = 15
        total_width = len(colors) * (card_width + spacing) - spacing
        # Center the row: start_x is the left edge, so we subtract half the total width
        start_x = center_x - total_width // 2

        self._firework_widgets.clear()

        for i, color in enumerate(colors):
            # Calculate x position for each card (card center)
            x = start_x + i * (card_width + spacing) + card_width // 2

            if color in cards_played:
                number = cards_played[color].value
                # Draw stack of cards (1 to number)
                cards = []
                for n in range(1, number + 1):
                    card_y = y - (number - n) * 3  # Stack effect
                    card_widget = self._create_card_widget(
                        x, card_y,
                        color, Number(n),
                        show_front=True
                    )
                    cards.append(card_widget)
                self._firework_widgets[color] = cards
            else:
                # Draw empty firework slot
                self._canvas.create_rectangle(
                    x - card_width // 2, y - card_height // 2,
                    x + card_width // 2, y + card_height // 2,
                    fill="#2C3E50",
                    outline=self.COLOR_COLORS.get(color, "#FFFFFF"),
                    width=2,
                    dash=(5, 5)
                )
                self._canvas.create_text(
                    x, y,
                    text=self.COLOR_NAMES.get(color, "?")[0],
                    fill=self.COLOR_COLORS.get(color, "#FFFFFF"),
                    font=("Arial", 10)
                )
                self._firework_widgets[color] = []

    def _draw_discard_row(self, center_x: int, y: int):
        """Draw discarded cards grouped by color, overlapped so numbers are visible, centered and within table."""
        # Get table radius to calculate left edge
        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800
        # Make table smaller (was // 3, now // 4)
        table_radius = min(width, height) // 4

        # Calculate left edge of table (with small padding to avoid overflow)
        table_left_edge = center_x - table_radius
        label_padding = 10  # Small padding from the edge
        label_x = table_left_edge + label_padding

        # Reconstruct discard pile from common view
        # Use frozen OLD state during animation, otherwise use current state
        if self._frozen_state is not None:
            state = self._frozen_state
        elif self._game:
            state = self._game.state
        else:
            return
        discard_pile = []
        for color, suit in state.common_view.cards_discarded.items():
            for number, count in suit.cards.items():
                for _ in range(count):
                    discard_pile.append(Card(color, number))

        if not discard_pile:
            # Draw label and empty message
            self._canvas.create_text(
                label_x, y,
                text="Discard:",
                fill="white",
                font=("Arial", 11, "bold"),
                anchor="w"  # Left-aligned so text starts at label_x
            )
            self._canvas.create_text(
                center_x, y + 10,
                text="(empty)",
                fill="#888888",
                font=("Arial", 10)
            )
            return

        # Group by color AND number (to overlap same color+number cards vertically)
        from collections import defaultdict
        # Group by (color, number) to count duplicates
        color_number_groups = defaultdict(list)
        for card in discard_pile:
            color_number_groups[(card.color, card.number.value)].append(card)

        # Also group by color for layout
        grouped_by_color = defaultdict(list)
        for (color, number), cards in color_number_groups.items():
            # Add each unique (color, number) combination once, but track count
            # Check if this (number, count) pair already exists for this color
            if not any(n == number for n, _ in grouped_by_color[color]):
                grouped_by_color[color].append((number, len(cards)))  # (number, count)

        # Sort numbers for each color
        for color in grouped_by_color:
            grouped_by_color[color].sort(key=lambda x: x[0])  # Sort by number

        colors = [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]
        card_width = 35
        card_height = 50
        horizontal_overlap = 15  # Overlap cards horizontally so numbers are visible
        vertical_offset = 8  # Vertical offset for stacking same color+number cards
        color_spacing = 30  # Space between color groups

        # Calculate total width needed for all colors
        total_width = 0
        color_groups = []
        for color in colors:
            if color in grouped_by_color:
                # Count unique (color, number) combinations
                num_unique = len(grouped_by_color[color])
                if num_unique > 0:
                    color_width = (num_unique - 1) * horizontal_overlap + card_width
                    color_groups.append((color, grouped_by_color[color], color_width))
                    total_width += color_width
        if color_groups:
            total_width += (len(color_groups) - 1) * color_spacing

        # Ensure cards don't go outside table (leave some margin)
        max_width = table_radius * 1.6  # Allow some margin
        if total_width > max_width:
            # Scale down if needed
            scale = max_width / total_width
            horizontal_overlap = max(5, int(horizontal_overlap * scale))  # Minimum overlap of 5
            card_width = max(25, int(card_width * scale))  # Minimum card width of 25
            color_spacing = max(10, int(color_spacing * scale))  # Minimum spacing of 10
            # Recalculate total width with scaled values
            total_width = 0
            color_groups = []
            for color in colors:
                if color in grouped_by_color:
                    num_unique = len(grouped_by_color[color])
                    if num_unique > 0:
                        color_width = (num_unique - 1) * horizontal_overlap + card_width
                        color_groups.append((color, grouped_by_color[color], color_width))
                        total_width += color_width
            if color_groups:
                total_width += (len(color_groups) - 1) * color_spacing

        # Calculate label width and spacing
        label_width = 70  # Approximate width for "Discard:"
        label_spacing = 10  # Space between label and cards

        # Draw "Discard:" label at fixed position (left edge of table)
        # label_x is already calculated above
        self._canvas.create_text(
            label_x, y,
            text="Discard:",
            fill="white",
            font=("Arial", 11, "bold"),
            anchor="w"  # Left-aligned so text starts at label_x
        )

        # Center the cards in the remaining space (after label)
        # Available space for cards: from after label to right edge of table
        table_right_edge = center_x + table_radius
        available_width = table_right_edge - (label_x + label_width + label_spacing)

        # If cards fit, center them in available space; otherwise use all available space
        if total_width <= available_width:
            # Center cards in available space
            cards_start_x = label_x + label_width + label_spacing
            start_x = cards_start_x + (available_width - total_width) // 2
        else:
            # Cards don't fit, start right after label
            start_x = label_x + label_width + label_spacing

        x = start_x
        for color, number_list, color_width in color_groups:
            # Draw each unique (color, number) combination
            # Draw from left to right so right cards are drawn last (on top) for z-order
            for i, (num, count) in enumerate(number_list):
                # Overlap cards horizontally
                card_x = x + i * horizontal_overlap
                # If multiple cards with same color+number, stack them vertically
                # Draw bottom cards first, top cards last (so top cards are visible)
                for stack_idx in range(count - 1, -1, -1):  # Reverse order: draw bottom first
                    card_y = y - stack_idx * vertical_offset

                    # Draw card with slight offset for depth
                    offset = 2
                    self._canvas.create_rectangle(
                        card_x - card_width // 2 + offset, card_y - card_height // 2 + offset,
                        card_x + card_width // 2 + offset, card_y + card_height // 2 + offset,
                        fill="#1A1A1A",  # Shadow
                        outline="",
                        width=0
                    )
                    self._canvas.create_rectangle(
                        card_x - card_width // 2, card_y - card_height // 2,
                        card_x + card_width // 2, card_y + card_height // 2,
                        fill=self.COLOR_COLORS.get(color, "#FFFFFF"),
                        outline="#000000",
                        width=2
                    )
                    # Position number in top left corner (like playing cards) - smaller font, always black
                    number_x = card_x - card_width // 2 + 4  # Left edge + small margin
                    number_y = card_y - card_height // 2 + 4  # Top edge + small margin
                    self._canvas.create_text(
                        number_x, number_y,
                        text=str(num),
                        fill="#000000",
                        font=("Arial", 10, "bold"),
                        anchor="nw"  # Top-left anchor
                    )
            # Move to next color position
            x += color_width + color_spacing

    def _draw_player_hands(self):
        """Draw all player hands in a circle with current player at bottom (270°)."""
        # Use frozen OLD state during animation, otherwise use current state
        if self._frozen_state is not None:
            state = self._frozen_state
        elif self._game:
            state = self._game.state
        else:
            return

        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800

        center_x = width // 2
        center_y = height // 2
        # Make table smaller (was // 3, now // 4)
        table_radius = min(width, height) // 4
        num_players = len(state.player_hands)

        # Calculate card dimensions
        card_width = 50
        card_height = 70
        spacing = 10

        # Find the maximum number of cards in any hand to ensure all hands are outside the table
        max_cards = max(len(hand.cards) for hand in state.player_hands) if state.player_hands else 5
        max_hand_width = max_cards * (card_width + spacing) - spacing
        max_half_width = max_hand_width // 2

        # Calculate hand_radius to ensure the nearest card edge is outside the table
        # hand_radius - max_half_width must be > table_radius + padding
        # So: hand_radius > table_radius + max_half_width + padding
        padding = 80  # Increased padding to move hands further from table (was 50)
        hand_radius = table_radius + max_half_width + padding

        # Add extra vertical margin for top/bottom hands to allow popup menus to show
        # Calculate maximum vertical distance from center for any hand
        # Top hands: y = center_y - hand_radius * sin(90°) = center_y - hand_radius
        # Bottom hands: y = center_y + hand_radius * sin(90°) = center_y + hand_radius
        # We need: center_y - hand_radius >= card_height/2 + vertical_margin (top)
        # And: center_y + hand_radius <= height - card_height/2 - vertical_margin (bottom)
        vertical_margin = 120  # Extra space for popup menus at top and bottom
        max_vertical_distance = min(
            center_y - vertical_margin - card_height // 2,  # Top constraint
            height - center_y - vertical_margin - card_height // 2  # Bottom constraint
        )
        # Limit hand_radius to ensure hands don't get too close to edges
        hand_radius = min(hand_radius, max_vertical_distance)

        # Calculate angles: current player at bottom (90° in standard math, but we use -90° for screen coords)
        # In screen coordinates: 0° = right, 90° = down (bottom), 180° = left, 270° = up (top)
        # So for bottom we want 90°, not 270°
        # For 3 players: current at 90° (bottom), next at 210° (left-up), next at 330° (right-up)
        base_angle = 90  # Bottom (current player) in screen coordinates
        angle_step = 360 / num_players

        for i in range(num_players):
            # Calculate relative position from current player (0 = current, 1 = next, etc.)
            relative_pos = (i - self._current_player) % num_players
            # Angle in degrees: current at 90° (bottom), go clockwise (increasing angle)
            # For relative_pos=0: 90°, for relative_pos=1: 90+120=210°, for relative_pos=2: 90+240=330°
            angle_deg = (base_angle + angle_step * relative_pos) % 360
            angle_rad = radians(angle_deg)

            x = center_x + hand_radius * cos(angle_rad)
            y = center_y + hand_radius * sin(angle_rad)

            # Draw player hand
            hand = state.player_hands[i]
            is_current_player = (i == self._current_player)

            # Draw player label - always on top of hand
            label_offset = 60
            # Always place label above the cards (toward center)
            label_y = y - label_offset

            # Get player name from replay history if available
            player_name = f"Player {i + 1}"
            # Check if game is over - don't show player type when game is over
            game_is_over = False
            if self._game:
                # Check if game is over by checking turns left or status label
                if self._game.state.turns_left == 0:
                    game_is_over = True
                elif hasattr(self, '_status_label'):
                    status_text = self._status_label.cget("text")
                    if "Game Over" in status_text:
                        game_is_over = True

            if hasattr(self, '_replay_player_names') and self._replay_player_names:
                if i < len(self._replay_player_names):
                    player_type = self._replay_player_names[i]
                    # Remove "Player" suffix if present (e.g., "GUIPlayer" -> "GUI")
                    if player_type.endswith("Player"):
                        player_type = player_type[:-6]  # Remove "Player"
                    if player_type and not game_is_over:
                        player_name = f"Player {i + 1} ({player_type})"
            else:
                # Live game mode: check if player is AI
                if self._game and not game_is_over:
                    player = self._game.team.players[i]
                    # Check if player is RandomPlayer from hanabi.ai
                    from hanabi.ai.random_player import RandomPlayer
                    if isinstance(player, RandomPlayer):
                        player_name = f"Player {i + 1} (AI: Random)"
                    elif is_current_player:
                        player_name += " (You)"
                elif is_current_player and not game_is_over:
                    player_name += " (You)"

            self._canvas.create_text(
                x, label_y,
                text=player_name,
                fill="white" if is_current_player else "#CCCCCC",
                font=("Arial", 12, "bold" if is_current_player else "normal")
            )

            # Draw cards in hand
            total_width = len(hand.cards) * (card_width + spacing) - spacing
            start_x = x - total_width // 2

            for card_idx, card in enumerate(hand.cards):
                card_x = start_x + card_idx * (card_width + spacing)
                card_y = y

                # Get hints for this card from GUI's independent hint tracking
                # Card and hints are always drawn together as a unit
                player_hints = self._hints.get(i, {})
                card_hints = player_hints.get(card_idx, {})

                # Show card front if: replay mode OR not current player
                # Current player's cards always show back (?) with hint boxes outside
                show_front = self._show_all_cards or not is_current_player

                # Always pass hints - they will be used when drawing the card
                # For front-facing cards (other players), hints are shown on the card
                # For back-facing cards (current player), hints are shown in boxes outside
                widget = self._create_card_widget(
                    card_x, card_y,
                    card.color, card.number,
                    show_front=show_front,
                    hints=card_hints,  # Always pass hints - card and hints are a unit
                    clickable=True,  # All cards clickable for action menu
                    player_idx=i,
                    card_idx=card_idx
                )
                self._card_widgets[(i, card_idx)] = widget
                # Store card position for click detection
                self._card_positions[(i, card_idx)] = (
                    card_x - card_width // 2,
                    card_y - card_height // 2,
                    card_x + card_width // 2,
                    card_y + card_height // 2
                )

    def _create_card_widget(
        self,
        x: int, y: int,
        color: Color, number: Number,
        show_front: bool = True,
        hints: Dict[str, any] = None,
        clickable: bool = False,
        player_idx: int = None,
        card_idx: int = None,
        selected: bool = False
    ) -> int:
        """Create a card widget on the canvas."""
        hints = hints or {}
        card_width = 50
        card_height = 70

        if show_front:
            bg_color = self.COLOR_COLORS.get(color, "#FFFFFF")
            text_color = "#000000"  # Use black for all numbers on cards

            widget = self._canvas.create_rectangle(
                x - card_width // 2, y - card_height // 2,
                x + card_width // 2, y + card_height // 2,
                fill=bg_color,
                outline="#000000",  # Normal black outline
                width=2,
                tags=("card", f"player_{player_idx}_card_{card_idx}") if clickable else ("card",)
            )

            self._canvas.create_text(
                x, y,
                text=str(number.value),
                fill=text_color,
                font=("Arial", 24, "bold"),
                tags=("card",)
            )

            # Add hint indicator boxes outside bottom of card if card has hints
            # Use hints passed as parameter - card and hints are always drawn together as a unit
            color_hint = hints.get("color")
            number_hint = hints.get("number")
            has_any_hints = color_hint is not None or number_hint is not None

            if has_any_hints:

                # Calculate position for boxes outside bottom of card
                box_height = 18
                box_width = 22
                box_spacing = 3
                # Position boxes below the card (outside)
                bottom_y = y + card_height // 2 + 2

                # Draw color hint box (left box)
                if color_hint is not None:
                    hint_color = self.COLOR_COLORS.get(color_hint, "#FFFFFF")
                    color_box_x = x - (box_width + box_spacing) // 2
                    self._canvas.create_rectangle(
                        color_box_x - box_width // 2, bottom_y,
                        color_box_x + box_width // 2, bottom_y + box_height,
                        fill=hint_color,
                        outline="#000000",
                        width=1,
                        tags=("card",)
                    )

                # Draw number hint (right side, no box - just white text on dark background)
                if number_hint is not None:
                    number_box_x = x + (box_width + box_spacing) // 2
                    # No box - just white text on the dark background
                    self._canvas.create_text(
                        number_box_x, bottom_y + box_height // 2,
                        text=str(number_hint.value),
                        fill="white",
                        font=("Arial", 12, "bold"),
                        tags=("card",)
                    )
        else:
            bg_color = "#2C3E50"
            outline_color = "#87CEEB" if clickable else "#666666"
            outline_width = 3 if clickable else 2

            widget = self._canvas.create_rectangle(
                x - card_width // 2, y - card_height // 2,
                x + card_width // 2, y + card_height // 2,
                fill=bg_color,
                outline=outline_color,
                width=outline_width,
                tags=("card", f"player_{player_idx}_card_{card_idx}") if clickable else ("card",)
            )

            color_hint = hints.get("color")
            number_hint = hints.get("number")

            # For current player's cards, always show "?" (hints shown in boxes outside)
            is_current_player_card = (player_idx == self._current_player)

            if is_current_player_card:
                # Always show "?" for current player's cards
                self._canvas.create_text(
                    x, y,
                    text="?",
                    fill="#888888",
                    font=("Arial", 24, "bold"),
                    tags=("card",)
                )
            else:
                # For other players' cards, show hints on the card itself
                if color_hint and number_hint:
                    hint_color = self.COLOR_COLORS.get(color_hint, "#FFFFFF")
                    text_color = "white"
                    self._canvas.create_text(
                        x, y - 10,
                        text=self.COLOR_NAMES.get(color_hint, "?")[0],
                        fill=hint_color,
                        font=("Arial", 20, "bold"),
                        tags=("card",)
                    )
                    self._canvas.create_text(
                        x, y + 10,
                        text=str(number_hint.value),
                        fill=text_color,
                        font=("Arial", 18, "bold"),
                        tags=("card",)
                    )
                elif color_hint:
                    # Only color hint: show "?" with background color set to hint color
                    hint_color = self.COLOR_COLORS.get(color_hint, "#FFFFFF")
                    # Update background color to hint color
                    self._canvas.itemconfig(widget, fill=hint_color)
                    self._canvas.create_text(
                        x, y,
                        text="?",
                        fill="#000000",  # Black text on colored background
                        font=("Arial", 24, "bold"),
                        tags=("card",)
                    )
                elif number_hint:
                    text_color = "white"
                    self._canvas.create_text(
                        x, y,
                        text=str(number_hint.value),
                        fill=text_color,
                        font=("Arial", 24, "bold"),
                        tags=("card",)
                    )
                else:
                    self._canvas.create_text(
                        x, y,
                        text="?",
                        fill="#888888",
                        font=("Arial", 24, "bold"),
                        tags=("card",)
                    )

            # Add hint indicator boxes outside bottom of card for current player's cards
            if player_idx is not None and card_idx is not None and player_idx == self._current_player:
                # Get actual hints from hint tracking
                player_hints = self._hints.get(player_idx, {})
                card_hints = player_hints.get(card_idx, {})
                color_hint = card_hints.get("color")
                number_hint = card_hints.get("number")

                # Calculate position for boxes outside bottom of card
                box_height = 18
                box_width = 22
                box_spacing = 3
                # Position boxes below the card (outside)
                bottom_y = y + card_height // 2 + 2

                # Draw color hint box (left box)
                if color_hint is not None:
                    hint_color = self.COLOR_COLORS.get(color_hint, "#FFFFFF")
                    color_box_x = x - (box_width + box_spacing) // 2
                    self._canvas.create_rectangle(
                        color_box_x - box_width // 2, bottom_y,
                        color_box_x + box_width // 2, bottom_y + box_height,
                        fill=hint_color,
                        outline="#000000",
                        width=1,
                        tags=("card",)
                    )

                # Draw number hint (right side, no box - just white text on dark background)
                if number_hint is not None:
                    number_box_x = x + (box_width + box_spacing) // 2
                    # No box - just white text on the dark background
                    self._canvas.create_text(
                        number_box_x, bottom_y + box_height // 2,
                        text=str(number_hint.value),
                        fill="white",
                        font=("Arial", 12, "bold"),
                        tags=("card",)
                    )

        return widget

    def show_action_menu(self, player_idx: int, card_idx: int, x: int, y: int):
        """
        Show action menu popup near cursor.

        Args:
            player_idx: Index of player whose card was clicked
            card_idx: Index of card that was clicked
            x, y: Screen coordinates for menu position
        """
        # Don't show menu if it's not the GUI player's turn
        if not self._is_gui_player_turn():
            return

        # Close any existing menu
        self._close_action_menu()

        # Get mouse position (screen coordinates)
        screen_x = self.root.winfo_pointerx()
        screen_y = self.root.winfo_pointery()

        # Create popup menu
        self._action_menu = tk.Toplevel(self.root)
        self._action_menu.overrideredirect(True)
        self._action_menu.geometry(f"+{screen_x + 10}+{screen_y + 10}")
        self._action_menu.configure(bg="#34495E")
        self._action_menu.attributes("-topmost", True)

        # Store context
        self._action_menu_context = {
            "player_idx": player_idx,
            "card_idx": card_idx
        }

        is_own_card = (player_idx == self._current_player)
        state = self._game.state
        common_view = state.common_view

        if is_own_card:
            # Own card: Play/Discard options - use grey buttons with black text for consistency
            play_btn = tk.Button(
                self._action_menu,
                text="Play",
                command=lambda: self._on_action_selected("play"),
                bg="#95A5A6",
                fg="black",
                font=("Arial", 10, "bold"),
                width=12,
                padx=5,
                pady=3,
                activebackground="#7F8C8D",
                activeforeground="black",
                highlightthickness=0,
                borderwidth=1,
                relief=tk.RAISED
            )
            # Force text color after creation
            play_btn.config(fg="black")
            play_btn.pack(pady=2)

            # Discard button (if hint tokens not at max)
            if common_view.hint_tokens < self._game.settings.max_hint_tokens:
                discard_btn = tk.Button(
                    self._action_menu,
                    text="Discard",
                    command=lambda: self._on_action_selected("discard"),
                    bg="#95A5A6",
                    fg="black",
                    font=("Arial", 10, "bold"),
                    width=12,
                    padx=5,
                    pady=3,
                    activebackground="#7F8C8D",
                    activeforeground="black",
                    highlightthickness=0,
                    borderwidth=1,
                    relief=tk.RAISED
                )
                # Force text color after creation
                discard_btn.config(fg="black")
                discard_btn.pack(pady=2)
            else:
                # Show explanation why discard is not available
                # Use a simple Label with explicit black foreground
                explanation = tk.Label(
                    self._action_menu,
                    text="Cannot discard:\nHint tokens full",
                    bg="#95A5A6",
                    fg="black",  # Use string name for tkinter
                    font=("Arial", 9),
                    justify=tk.LEFT,
                    anchor="w",
                    padx=5,
                    pady=3
                )
                # Force update to ensure color is applied
                explanation.config(fg="black")
                explanation.pack(pady=2, fill=tk.X)
        else:
            # Other player's card: Hint options (Number first, then Color - Number closer to cursor)
            if common_view.hint_tokens > 0:
                number_hint_btn = tk.Button(
                    self._action_menu,
                    text="Number Hint",
                    command=lambda: self._on_action_selected("number_hint"),
                    bg="#95A5A6",
                    fg="black",  # Black text on grey background
                    font=("Arial", 10, "bold"),
                    width=12,
                    padx=5,
                    pady=3,
                    activebackground="#7F8C8D",
                    activeforeground="black",
                    highlightthickness=0
                )
                number_hint_btn.pack(pady=2)

                color_hint_btn = tk.Button(
                    self._action_menu,
                    text="Color Hint",
                    command=lambda: self._on_action_selected("color_hint"),
                    bg="#95A5A6",
                    fg="black",  # Black text on grey background
                    font=("Arial", 10, "bold"),
                    width=12,
                    padx=5,
                    pady=3,
                    activebackground="#7F8C8D",
                    activeforeground="black",
                    highlightthickness=0
                )
                color_hint_btn.pack(pady=2)
            else:
                # Show explanation why hints are not available
                # Use a simple Label with explicit black foreground
                explanation = tk.Label(
                    self._action_menu,
                    text="Cannot hint:\nNo hint tokens",
                    bg="#95A5A6",
                    fg="black",  # Use string name for tkinter
                    font=("Arial", 9),
                    justify=tk.LEFT,
                    anchor="w",
                    padx=5,
                    pady=3
                )
                # Force update to ensure color is applied
                explanation.config(fg="black")
                explanation.pack(pady=2, fill=tk.X)

        # Close menu when clicking outside (handled by canvas click handler)

    def _on_action_selected(self, action: str):
        """Handle action selection from menu."""
        if not self._action_menu_context:
            return

        # Check if game is valid and not finished
        if not self._game:
            return

        # Check if game is finished, but allow moves when turns_left > 0 (current player still has their final turn)
        state = self._game.state
        # If deck is exhausted, check turns_left - game should only end when turns_left == 0
        # (meaning all players have taken their final turn)
        if state.turns_left is not None:
            # Deck is exhausted - game ends only when turns_left == 0
            if state.turns_left == 0:
                # All players have taken their final turn - game is finished
                if self._game.is_finished:
                    self._close_action_menu()
                    return
            # If turns_left > 0, allow the move (current player still has their final turn)
        elif self._game.is_finished:
            # Game finished for other reasons (lives lost, perfect score, etc.)
            self._close_action_menu()
            return

        # Get the teammate index (player whose card was clicked)
        teammate_idx = self._action_menu_context.get("player_idx")
        card_idx = self._action_menu_context.get("card_idx")

        # Validate context
        if teammate_idx is None or card_idx is None:
            return

        # Get the current player (who is making the move) - refresh from game state
        current_player = self._game.current_player

        # Safety check: ensure we're not trying to hint ourselves
        if teammate_idx == current_player and action in ("color_hint", "number_hint"):
            return

        if action == "play":
            if not self._move_callback:
                # No callback set - this shouldn't happen, but handle gracefully
                return
            if teammate_idx == current_player:
                from hanabi.core.moves import Play
                move = Play(card_idx)
                self._move_callback(move)
        elif action == "discard":
            if not self._move_callback:
                return
            if teammate_idx == current_player:
                from hanabi.core.moves import Discard
                move = Discard(card_idx)
                self._move_callback(move)
        elif action == "color_hint":
            # Hint can only be given to a teammate (not yourself)
            if not self._move_callback:
                return
            if teammate_idx != current_player:
                state = self._game.state
                # Validate teammate index - must be different from current player
                if (0 <= teammate_idx < len(state.player_hands) and
                    teammate_idx != current_player and
                    teammate_idx is not None):
                    hand = state.player_hands[teammate_idx]
                    if card_idx < len(hand.cards):
                        card = hand.cards[card_idx]
                        matching = [i for i, c in enumerate(hand.cards) if c.color == card.color]
                        if matching:
                            # Final validation: ensure teammate_idx is not the current player
                            # This should never happen due to earlier checks, but double-check
                            if teammate_idx != current_player:
                                move = ColorHint(teammate_idx, matching, card.color)
                                # Verify the move was created correctly before calling callback
                                if move.teammate == teammate_idx and move.teammate != current_player:
                                    self._move_callback(move)
        elif action == "number_hint":
            # Hint can only be given to a teammate (not yourself)
            if not self._move_callback:
                return
            if teammate_idx != current_player:
                state = self._game.state
                # Validate teammate index - must be different from current player
                if (0 <= teammate_idx < len(state.player_hands) and
                    teammate_idx != current_player and
                    teammate_idx is not None):
                    hand = state.player_hands[teammate_idx]
                    if card_idx < len(hand.cards):
                        card = hand.cards[card_idx]
                        matching = [i for i, c in enumerate(hand.cards) if c.number == card.number]
                        if matching:
                            # Final validation: ensure teammate_idx is not the current player
                            # This should never happen due to earlier checks, but double-check
                            if teammate_idx != current_player:
                                move = NumberHint(teammate_idx, matching, card.number)
                                # Verify the move was created correctly before calling callback
                                if move.teammate == teammate_idx and move.teammate != current_player:
                                    self._move_callback(move)

        # Close menu
        self._close_action_menu()

    def set_move_callback(self, callback):
        """Set callback for when a move is made."""
        self._move_callback = callback

    def display_move_result(self, success: bool, message: str, player_index: int, is_ai: bool = False, turn_number: int = None) -> None:
        """Display the result of a move in history panel."""
        if success:
            # Format message - pass player_index for hint formatting
            formatted_msg = message
            # If player_index is provided and message doesn't start with player info, add it
            if player_index is not None and not formatted_msg.startswith("Player ") and not formatted_msg.startswith("P"):
                formatted_msg = f"P{player_index + 1} {formatted_msg}"
            self._add_event_to_history(formatted_msg, "success", player_index, is_ai, turn_number=turn_number)
        else:
            self._add_event_to_history(f"Error: {message}", "error", player_index, is_ai, turn_number=turn_number)

    def _update_last_turn_warning(self):
        """Update the last turn warning banner visibility."""
        if not self._game:
            return

        state = self._game.state
        deck_empty = (state.common_view.cards_to_draw == 0)

        if deck_empty:
            # Show warning banner
            if not self._last_turn_label.winfo_ismapped():
                self._last_turn_label.pack(side=tk.LEFT, padx=10, pady=5)
        else:
            # Hide warning banner
            if self._last_turn_label.winfo_ismapped():
                self._last_turn_label.pack_forget()

    def display_game_end(self, game: Game) -> None:
        """Display game end information."""
        score = game.get_score()
        max_score = 25

        if score == max_score:
            rating = "Legendary! Everyone left speechless, stars in their eyes!"
        elif score >= 21:
            rating = "Amazing! They will be talking about it for weeks!"
        elif score >= 16:
            rating = "Excellent, crowd pleasing."
        elif score >= 11:
            rating = "Honorable attempt, but quickly forgotten..."
        elif score >= 6:
            rating = "Mediocre, just a hint of scattered applause..."
        else:
            rating = "Horrible, booed by the crowd..."

        message = f"Game Over! Final Score: {score}/{max_score} - {rating}"
        # Use game_end event type so it gets colored properly
        self._add_event_to_history(message, "game_end")
        self._status_label.config(text=f"Game Over! Score: {score}/{max_score}")

    def _on_canvas_resize(self, event):
        """Handle canvas resize - redraw game state."""
        if self._game and event.width > 1 and event.height > 1:
            # Only redraw if game is not finished (to preserve hints when game ends)
            # Also skip if animating (display_game_state will handle this, but be explicit)
            if not self._game.is_finished and not (self._is_animating or self._active_animations):
                self.display_game_state(self._game, self._current_player)

    def clear(self) -> None:
        """Clear the display."""
        # Cancel any active animations
        self._cancel_all_animations()

        if self._canvas:
            self._canvas.delete("all")
        self._card_widgets.clear()
        self._card_positions.clear()
        self._firework_widgets.clear()
        self._token_widgets.clear()
        if self._history_text:
            self._history_text.config(state=tk.NORMAL)
            self._history_text.delete("1.0", tk.END)
            self._history_text.config(state=tk.DISABLED)
        self._event_history.clear()
        self._live_turn_numbers.clear()
        self._hints.clear()  # Clear hint tracking

    def set_animations_enabled(self, enabled: bool) -> None:
        """Enable or disable card animations."""
        self._animations_enabled = enabled

    def _cancel_all_animations(self) -> None:
        """Cancel all active animations."""
        for anim in self._active_animations[:]:
            if anim.get('after_id'):
                self.root.after_cancel(anim['after_id'])
            # Remove animated widgets from canvas
            if anim.get('widget_ids') and self._canvas:
                for widget_id in anim['widget_ids']:
                    try:
                        self._canvas.delete(widget_id)
                    except:
                        pass
        self._active_animations.clear()
        self._animation_queue.clear()
        self._is_animating = False

        # Cancel all explosions
        for explosion in self._active_explosions[:]:
            if explosion.get('after_id'):
                self.root.after_cancel(explosion['after_id'])
            if explosion.get('widget_ids') and self._canvas:
                for widget_id in explosion['widget_ids']:
                    try:
                        self._canvas.delete(widget_id)
                    except:
                        pass
        self._active_explosions.clear()

    def has_pending_animations(self) -> bool:
        """Check if there are any pending animations (queued or active)."""
        return len(self._animation_queue) > 0 or len(self._active_animations) > 0 or len(self._active_explosions) > 0 or self._is_animating

    def _get_firework_position(self, color: Color) -> Optional[Tuple[int, int]]:
        """Get the center position of a firework stack for a given color."""
        if not self._game or not self._canvas:
            return None

        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800
        center_x = width // 2
        center_y = height // 2

        # Calculate fireworks row position (same as _draw_fireworks_row)
        colors = [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]
        card_width = 50
        spacing = 15
        total_width = len(colors) * (card_width + spacing) - spacing
        start_x = center_x - total_width // 2

        # Find the index of this color
        if color not in colors:
            return None

        color_index = colors.index(color)
        x = start_x + color_index * (card_width + spacing) + card_width // 2
        y = center_y - 30  # Same y as in _draw_fireworks_row

        return (x, y)

    def _get_discard_position(self) -> Optional[Tuple[int, int]]:
        """Get a position in the discard pile area (public method for explosion positioning)."""
        """Get a position in the discard pile area."""
        if not self._game or not self._canvas:
            return None

        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800
        center_x = width // 2
        center_y = height // 2

        # Discard pile is drawn at center_y + 70 (from _draw_discard_row)
        discard_y = center_y + 70

        # Position near the center of the discard area
        discard_x = center_x

        return (discard_x, discard_y)

    def _get_deck_position(self, state: GameState) -> Optional[Tuple[int, int]]:
        """Get the position of the next card to be drawn from the deck."""
        if not self._game or not self._canvas:
            return None

        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800
        center_x = width // 2
        center_y = height // 2

        draw_deck_index = state.draw_deck_index
        initial_deck = self._game.state.start_position.draw_deck.cards
        total_deck_size = len(initial_deck)

        if total_deck_size == 0 or draw_deck_index >= total_deck_size:
            return None

        deck_y = center_y + 180
        num_players = self._game.settings.num_players
        cards_per_player = self._game.settings.max_cards_in_hand
        initial_remaining = total_deck_size - (num_players * cards_per_player)

        if initial_remaining == 0:
            return None

        if initial_remaining == 1:
            num_rows = 1
            bottom_row_cards = 1
            top_row_cards = 0
        else:
            num_rows = 2
            bottom_row_cards = initial_remaining // 2
            top_row_cards = initial_remaining - bottom_row_cards

        card_width = 35
        card_height = 50
        horizontal_overlap = 15
        row_height = card_height + 5

        bottom_row_width = (bottom_row_cards - 1) * horizontal_overlap + card_width if bottom_row_cards > 0 else 0
        top_row_width = (top_row_cards - 1) * horizontal_overlap + card_width
        max_row_width = max(bottom_row_width, top_row_width) if bottom_row_width > 0 else top_row_width

        table_radius = min(width, height) // 4
        max_width = table_radius * 1.6

        if max_row_width > max_width:
            scale = max_width / max_row_width
            horizontal_overlap = max(5, int(horizontal_overlap * scale))
            card_width = max(25, int(card_width * scale))
            bottom_row_width = (bottom_row_cards - 1) * horizontal_overlap + card_width if bottom_row_cards > 0 else 0
            top_row_width = (top_row_cards - 1) * horizontal_overlap + card_width
            max_row_width = max(bottom_row_width, top_row_width) if bottom_row_width > 0 else top_row_width

        start_x = center_x + max_row_width // 2 - card_width
        start_y = deck_y + (num_rows - 1) * row_height

        initial_deck_start_index = num_players * cards_per_player
        position_in_initial_deck = draw_deck_index - initial_deck_start_index

        if position_in_initial_deck < 0:
            return None

        if position_in_initial_deck < bottom_row_cards:
            row = 0
            col_from_right = position_in_initial_deck
        else:
            row = 1
            col_from_right = position_in_initial_deck - bottom_row_cards

        card_x = start_x - (col_from_right * horizontal_overlap)
        card_y = start_y - (row * row_height)

        return (card_x + card_width // 2, card_y)

    def _get_card_position_in_hand(self, player_index: int, card_index: int, state: GameState) -> Optional[Tuple[int, int]]:
        """Calculate the position of a card in a player's hand based on the game state."""
        if not self._canvas or player_index >= len(state.player_hands):
            return None

        hand = state.player_hands[player_index]
        if card_index >= len(hand.cards):
            return None

        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800
        center_x = width // 2
        center_y = height // 2
        table_radius = min(width, height) // 4
        num_players = len(state.player_hands)

        card_width = 50
        card_height = 70
        spacing = 10

        max_cards = max(len(h.cards) for h in state.player_hands) if state.player_hands else 5
        max_hand_width = max_cards * (card_width + spacing) - spacing
        max_half_width = max_hand_width // 2
        padding = 80
        hand_radius = table_radius + max_half_width + padding
        vertical_margin = 120
        max_vertical_distance = min(
            center_y - vertical_margin - card_height // 2,
            height - center_y - vertical_margin - card_height // 2
        )
        hand_radius = min(hand_radius, max_vertical_distance)

        base_angle = 90
        angle_step = 360 / num_players
        relative_pos = (player_index - self._current_player) % num_players
        angle_deg = (base_angle + angle_step * relative_pos) % 360
        angle_rad = radians(angle_deg)

        x = center_x + hand_radius * cos(angle_rad)
        y = center_y + hand_radius * sin(angle_rad)

        total_width = len(hand.cards) * (card_width + spacing) - spacing
        start_x = x - total_width // 2
        card_x = start_x + card_index * (card_width + spacing)
        card_y = y

        return (card_x, card_y)

    def show_explosion(self, x: int, y: int) -> None:
        """
        Show an explosion effect at the given position (for invalid plays).

        Args:
            x, y: Center position for the explosion
        """
        if not self._canvas or not self._animations_enabled:
            return

        # Create explosion effect: expanding circles that fade out
        explosion_duration_ms = 600  # 0.6 seconds
        total_frames = int((explosion_duration_ms / 1000.0) * self._animation_fps)

        # Create multiple expanding circles for explosion effect
        num_circles = 3
        explosion_widgets = []

        for i in range(num_circles):
            # Different sizes and colors for layered effect
            base_radius = 20 + i * 15
            colors = ["#FF0000", "#FF4500", "#FFA500"]  # Red, Orange, Yellow
            circle = self._canvas.create_oval(
                x - base_radius, y - base_radius,
                x + base_radius, y + base_radius,
                fill=colors[i % len(colors)],
                outline=colors[i % len(colors)],
                width=2,
                tags=("explosion",)
            )
            explosion_widgets.append(circle)

        # Add some particle-like lines radiating outward
        num_particles = 8
        for i in range(num_particles):
            angle = (360 / num_particles) * i
            rad = math.radians(angle)
            start_radius = 15
            end_radius = 40
            x1 = x + start_radius * math.cos(rad)
            y1 = y + start_radius * math.sin(rad)
            x2 = x + end_radius * math.cos(rad)
            y2 = y + end_radius * math.sin(rad)
            particle = self._canvas.create_line(
                x1, y1, x2, y2,
                fill="#FF0000",
                width=3,
                tags=("explosion",)
            )
            explosion_widgets.append(particle)

        # Raise explosion above everything
        self._canvas.tag_raise("explosion")

        # Create explosion animation
        explosion = {
            'widget_ids': explosion_widgets,
            'current_frame': 0,
            'total_frames': total_frames,
            'center_x': x,
            'center_y': y,
            'base_radius': 20,
            'after_id': None
        }

        self._active_explosions.append(explosion)
        self._animate_explosion(explosion)

    def _animate_explosion(self, explosion: Dict) -> None:
        """Animate one frame of an explosion effect."""
        if explosion not in self._active_explosions:
            return  # Explosion was cancelled

        current_frame = explosion['current_frame']
        total_frames = explosion['total_frames']

        if current_frame >= total_frames:
            # Explosion complete - remove widgets
            if explosion.get('widget_ids') and self._canvas:
                for widget_id in explosion['widget_ids']:
                    try:
                        self._canvas.delete(widget_id)
                    except:
                        pass

            # Remove from active explosions
            if explosion in self._active_explosions:
                self._active_explosions.remove(explosion)
            return

        # Animate explosion: expand circles and fade out
        progress = current_frame / total_frames
        expansion_factor = 1.0 + progress * 2.0  # Expand to 3x size
        opacity = 1.0 - progress  # Fade out

        if explosion.get('widget_ids') and self._canvas:
            center_x = explosion['center_x']
            center_y = explosion['center_y']
            base_radius = explosion['base_radius']

            # Update circles (first 3 widgets)
            for i, widget_id in enumerate(explosion['widget_ids'][:3]):
                try:
                    radius = (base_radius + i * 15) * expansion_factor
                    # Update circle size
                    self._canvas.coords(
                        widget_id,
                        center_x - radius, center_y - radius,
                        center_x + radius, center_y + radius
                    )
                    # Fade out by changing opacity (tkinter doesn't support alpha directly,
                    # so we'll use stipple pattern or just delete when fully faded)
                    if opacity < 0.3:
                        # Too faded, make it more transparent by using stipple
                        pass
                except:
                    pass

            # Update particle lines (remaining widgets)
            num_particles = len(explosion['widget_ids']) - 3
            for i, widget_id in enumerate(explosion['widget_ids'][3:]):
                try:
                    angle = (360 / num_particles) * i
                    rad = math.radians(angle)
                    start_radius = 15 * expansion_factor
                    end_radius = 40 * expansion_factor
                    x1 = center_x + start_radius * math.cos(rad)
                    y1 = center_y + start_radius * math.sin(rad)
                    x2 = center_x + end_radius * math.cos(rad)
                    y2 = center_y + end_radius * math.sin(rad)
                    self._canvas.coords(widget_id, x1, y1, x2, y2)
                except:
                    pass

        # Schedule next frame
        explosion['current_frame'] += 1
        frame_delay_ms = int(1000 / self._animation_fps)
        explosion['after_id'] = self.root.after(
            frame_delay_ms,
            lambda: self._animate_explosion(explosion)
        )

    def animate_card_move(
        self,
        player_index: int,
        card_index: int,
        card: Card,
        destination: str,  # "firework" or "discard"
        color: Optional[Color] = None,  # Required if destination is "firework"
        edge_color: str = "#FF0000",  # Edge color for the animated card
        callback: Optional[Callable] = None,
        old_state: Optional[GameState] = None  # Old state to freeze during animation
    ) -> None:
        """
        Animate a card moving from its current position to a destination.
        Animations are queued and played sequentially.

        Args:
            player_index: Index of the player whose card is being moved
            card_index: Index of the card in the player's hand
            card: The card being moved
            destination: "firework" or "discard"
            color: Color of the firework (required if destination is "firework")
            callback: Optional callback to call when animation completes
        """
        if not self._animations_enabled or not self._canvas:
            # Animations disabled or canvas not ready - call callback immediately
            if callback:
                callback()
            return

        # Get source position from stored card positions
        source_key = (player_index, card_index)
        if source_key not in self._card_positions:
            # Card position not found - try to update display first to get positions
            # This can happen if display hasn't been updated yet
            # But only if not already animating (to prevent recursive updates)
            if self._game and not (self._is_animating or self._active_animations):
                # Use current player for display update
                self.display_game_state(self._game, self._current_player)
                # Force canvas update to ensure positions are calculated
                self._canvas.update_idletasks()

            # Try again after updating
            if source_key not in self._card_positions:
                # Still not found - skip animation
                if callback:
                    callback()
                return

        x1, y1, x2, y2 = self._card_positions[source_key]
        source_x = (x1 + x2) // 2
        source_y = (y1 + y2) // 2

        # Get destination position
        if destination == "firework":
            if color is None:
                if callback:
                    callback()
                return
            dest_pos = self._get_firework_position(color)
        elif destination == "discard":
            dest_pos = self._get_discard_position()
        else:
            if callback:
                callback()
            return

        if dest_pos is None:
            if callback:
                callback()
            return

        dest_x, dest_y = dest_pos

        # Create animation request object
        animation_request = {
            'player_index': player_index,
            'card_index': card_index,
            'card': card,
            'source_x': source_x,
            'source_y': source_y,
            'dest_x': dest_x,
            'dest_y': dest_y,
            'destination': destination,
            'color': color,
            'edge_color': edge_color,
            'callback': callback
        }

        # Add to queue
        self._animation_queue.append(animation_request)

        # Mark as animating immediately when we queue an animation
        # This prevents display updates from happening before animation completes
        # NOTE: This may already be set by the caller (gui_game.py) to prevent race conditions
        # But we set it here too to be safe
        self._is_animating = True

        # Freeze the OLD state to use during animation
        # This ensures fireworks show the old state (before card is played) during animation
        # We need to freeze old_state, not self._game (which is already the new state)
        # NOTE: This may already be set by the caller (gui_game.py) to prevent race conditions
        # But we set it here too to be safe
        if old_state is not None:
            # Store the old state directly - we'll use it in drawing methods
            self._frozen_state = old_state
            # Also keep game object reference for settings access
            if self._game:
                self._frozen_game_state = self._game
        elif self._game:
            # Fallback: freeze current state if old_state not provided
            self._frozen_game_state = self._game
            self._frozen_state = self._game.state

        # Start processing queue if not already processing
        if len(self._active_animations) == 0:
            self._process_animation_queue()

    def animate_card_draw(
        self,
        player_index: int,
        card: Card,
        edge_color: str = "#00FF00",  # Green for drawing
        callback: Optional[Callable] = None,
        old_state: Optional[GameState] = None,  # Old state to get deck position
        new_state: Optional[GameState] = None  # New state to get hand position
    ) -> None:
        """
        Animate a card being drawn from the deck to a player's hand.
        Uses the same animation queue system as animate_card_move.

        Args:
            player_index: Index of the player drawing the card
            card: The card being drawn
            edge_color: Edge color for the animated card (default: green)
            callback: Optional callback to call when animation completes
            old_state: Old state to get deck position (before card was drawn)
            new_state: New state to get hand position (after card was drawn)
        """
        if not self._animations_enabled or not self._canvas:
            if callback:
                callback()
            return

        # Get source position from deck using old_state
        if old_state is None:
            if callback:
                callback()
            return

        source_pos = self._get_deck_position(old_state)
        if source_pos is None:
            if callback:
                callback()
            return

        source_x, source_y = source_pos

        # Get destination position (position 0 in player's hand) using new_state
        if new_state is None or player_index >= len(new_state.player_hands):
            if callback:
                callback()
            return

        dest_pos = self._get_card_position_in_hand(player_index, 0, new_state)
        if dest_pos is None:
            if callback:
                callback()
            return

        dest_x, dest_y = dest_pos

        # Create animation request object
        animation_request = {
            'player_index': player_index,
            'card_index': 0,  # New card always goes to position 0
            'card': card,
            'source_x': source_x,
            'source_y': source_y,
            'dest_x': dest_x,
            'dest_y': dest_y,
            'destination': 'hand',
            'color': None,
            'edge_color': edge_color,
            'callback': callback
        }

        # Add to queue (will play after current animation completes)
        self._animation_queue.append(animation_request)

        # Keep frozen state for the draw animation
        if old_state is not None:
            self._frozen_state = old_state
            if self._game:
                self._frozen_game_state = self._game

        # Queue is already being processed, so this will play after current animation

    def _process_animation_queue(self):
        """Process the next animation in the queue."""
        if not self._animation_queue:
            # No more animations in queue - mark as not animating
            self._is_animating = False
            return

        # Already marked as animating when queued, but ensure it's set
        self._is_animating = True

        # Get next animation request
        request = self._animation_queue.pop(0)

        # Create animated card widget (temporary, will be deleted after animation)
        # Make it slightly larger and more visible
        card_width = 55
        card_height = 77
        bg_color = self.COLOR_COLORS.get(request['card'].color, "#FFFFFF")

        # Get edge color from request (default to red if not specified)
        edge_color = request.get('edge_color', "#FF0000")

        widget_ids = []

        # For gold (play of 5), make it shiny with a gradient-like effect
        if edge_color == "#FFD700":  # Gold
            # Create a slightly larger outer rectangle for glow effect
            glow_rect = self._canvas.create_rectangle(
                request['source_x'] - card_width // 2 - 2, request['source_y'] - card_height // 2 - 2,
                request['source_x'] + card_width // 2 + 2, request['source_y'] + card_height // 2 + 2,
                fill="",
                outline="#FFA500",  # Orange glow
                width=2,
                tags=("animated_card",)
            )
            widget_ids.append(glow_rect)

        # For draw animations (destination='hand'), show "?" instead of actual card
        is_draw_animation = request.get('destination') == 'hand'

        # Use gray background for draw animations (unknown card)
        if is_draw_animation:
            display_bg_color = "#808080"  # Gray
            display_text = "?"
        else:
            display_bg_color = bg_color
            display_text = str(request['card'].number.value)

        # Create card rectangle with colored outline based on move type
        card_rect = self._canvas.create_rectangle(
            request['source_x'] - card_width // 2, request['source_y'] - card_height // 2,
            request['source_x'] + card_width // 2, request['source_y'] + card_height // 2,
            fill=display_bg_color,
            outline=edge_color,
            width=4,  # Thicker outline for visibility
            tags=("animated_card",)
        )
        widget_ids.append(card_rect)

        # Create card number text (slightly larger)
        card_text = self._canvas.create_text(
            request['source_x'], request['source_y'],
            text=display_text,
            fill="#000000",
            font=("Arial", 26, "bold"),
            tags=("animated_card",)
        )
        widget_ids.append(card_text)

        # Raise animated card to top layer so it's visible above everything
        # Use lift to move to top of stacking order
        self._canvas.tag_raise("animated_card")
        # Also lift each widget individually to ensure they're on top
        for widget_id in widget_ids:
            self._canvas.lift(widget_id)

        # Calculate animation parameters
        total_frames = int((self._animation_duration_ms / 1000.0) * self._animation_fps)
        frame_delay_ms = int(1000 / self._animation_fps)

        dx = (request['dest_x'] - request['source_x']) / total_frames
        dy = (request['dest_y'] - request['source_y']) / total_frames

        # Create animation object with callback to process next in queue
        def animation_complete():
            # The animation is still in _active_animations at this point
            # Call original callback if provided (this updates event history, doesn't update game state)
            if request.get('callback'):
                request['callback']()

            # Mark as not animating AFTER callback
            self._is_animating = False

            # Force canvas update to ensure display is refreshed
            if self._canvas:
                self._canvas.update_idletasks()
            # Process next animation after a small delay to ensure display update is visible
            # This allows the display to update after each animation completes
            self.root.after(50, self._process_animation_queue)

        animation = {
            'widget_ids': widget_ids,
            'current_frame': 0,
            'total_frames': total_frames,
            'dx': dx,
            'dy': dy,
            'callback': animation_complete,
            'after_id': None
        }

        self._active_animations.append(animation)

        # Start animation
        self._animate_frame(animation)

    def _animate_frame(self, animation: Dict) -> None:
        """Animate one frame of a card movement."""
        if animation not in self._active_animations:
            return  # Animation was cancelled

        current_frame = animation['current_frame']
        total_frames = animation['total_frames']

        if current_frame >= total_frames:
            # Animation complete
            # Remove widgets
            if animation.get('widget_ids') and self._canvas:
                for widget_id in animation['widget_ids']:
                    try:
                        self._canvas.delete(widget_id)
                    except:
                        pass

            # Call callback BEFORE removing from active animations
            # This ensures the check in display_game_state still sees the animation as active
            if animation.get('callback'):
                animation['callback']()

            # Remove from active animations AFTER callback completes
            # This ensures display_game_state won't update until animation is fully done
            if animation in self._active_animations:
                self._active_animations.remove(animation)

            # Now that animation is removed, clear frozen state and apply pending game state
            # Order: 1. Clear frozen state, 2. Update to new state, 3. Update display
            self._frozen_game_state = None
            self._frozen_state = None

            if self._pending_game_state is not None:
                self._game = self._pending_game_state
                self._current_player = self._pending_player_index
                # Clear pending state before updating display
                pending_state = self._pending_game_state
                pending_player = self._pending_player_index
                self._pending_game_state = None
                self._pending_player_index = None
                # Now update the display with the new state (animation is gone, so it will proceed)
                # This will show the card in its final position (fireworks updated)
                self.display_game_state(pending_state, pending_player)
            elif self._game is not None:
                # Even if there's no pending state, we should refresh the display
                # to ensure everything is up to date after animation
                self.display_game_state(self._game, self._current_player)
            return

        # Move widgets
        if animation.get('widget_ids') and self._canvas:
            for widget_id in animation['widget_ids']:
                try:
                    self._canvas.move(widget_id, animation['dx'], animation['dy'])
                    # Keep animated card on top after each move
                    self._canvas.lift(widget_id)
                except:
                    pass

        # Schedule next frame
        animation['current_frame'] += 1
        frame_delay_ms = int(1000 / self._animation_fps)
        animation['after_id'] = self.root.after(
            frame_delay_ms,
            lambda: self._animate_frame(animation)
        )

    def update_hints_from_move(self, player_index: int, move: Move, old_state=None, new_state=None) -> None:
        """
        Update hint tracking based on a move.
        This is called independently of player implementations.

        Args:
            player_index: Index of the player who made the move
            move: The move that was made
            old_state: Previous game state (optional, used to detect if card was drawn)
            new_state: New game state (optional, used to detect if card was drawn)
        """
        from hanabi.core.moves import ColorHint, NumberHint, CardMove

        if isinstance(move, (ColorHint, NumberHint)):
            # A hint was given to a teammate
            teammate_idx = move.teammate

            # Initialize hints dict for this player if needed
            if teammate_idx not in self._hints:
                self._hints[teammate_idx] = {}

            # Update hints for each card in the hint
            for card_idx in move.cards:
                if card_idx not in self._hints[teammate_idx]:
                    self._hints[teammate_idx][card_idx] = {"color": None, "number": None}

                if isinstance(move, ColorHint):
                    self._hints[teammate_idx][card_idx]["color"] = move.color
                else:
                    assert isinstance(move, NumberHint)
                    self._hints[teammate_idx][card_idx]["number"] = move.number
            return

        if isinstance(move, CardMove):
            # A card was played or discarded - shift hint indices
            card_index = move.card

            # Determine if a new card was drawn
            # If old_state and new_state are provided, check hand size change
            # If hand size decreased, no card was drawn (deck exhausted)
            # If hand size stayed the same, a card was drawn
            card_was_drawn = True  # Default assumption
            if old_state is not None and new_state is not None:
                old_hand_size = len(old_state.player_hands[player_index].cards) if player_index < len(old_state.player_hands) else 0
                new_hand_size = len(new_state.player_hands[player_index].cards) if player_index < len(new_state.player_hands) else 0
                # If hand size decreased, no card was drawn
                card_was_drawn = (new_hand_size == old_hand_size)

            # Remove hints for the card being played/discarded
            if player_index in self._hints and card_index in self._hints[player_index]:
                del self._hints[player_index][card_index]

            # Shift remaining hints to new indices
            if player_index in self._hints:
                new_hints = {}
                for old_idx, hint_data in self._hints[player_index].items():
                    if card_was_drawn:
                        # A new card was drawn and inserted at position 0
                        # 1. The card at card_index is removed (cards after shift left by 1)
                        # 2. A new card is inserted at position 0 (all cards shift right by 1)
                        # Net effect:
                        # - Cards at indices < card_index: shift right by 1 (from insertion at 0)
                        # - Cards at indices > card_index: no net change (left by 1 from removal, right by 1 from insertion)
                        if old_idx < card_index:
                            # Card shifted right by 1 due to new card insertion at position 0
                            new_hints[old_idx + 1] = hint_data
                        elif old_idx > card_index:
                            # Card shifted left by 1 from removal, then right by 1 from insertion = no net change
                            new_hints[old_idx] = hint_data
                    else:
                        # No card was drawn (deck exhausted)
                        # The card at card_index is removed, all cards after shift left by 1
                        # - Cards at indices < card_index: no change
                        # - Cards at indices > card_index: shift left by 1
                        if old_idx < card_index:
                            # No change - card position unchanged
                            new_hints[old_idx] = hint_data
                        elif old_idx > card_index:
                            # Card shifted left by 1 due to removal
                            new_hints[old_idx - 1] = hint_data
                self._hints[player_index] = new_hints
            return

        assert False, f"unexpected move type in update_hints_from_move: {type(move)}"
