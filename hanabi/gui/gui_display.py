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
from datetime import datetime
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card
from hanabi.core.game import Game
from hanabi.core.moves import ColorHint, NumberHint


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
        self._history_listbox: Optional[tk.Listbox] = None
        self._history_scrollbar: Optional[ttk.Scrollbar] = None

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
        self._history_frame = tk.Frame(content_frame, bg="#34495E", width=400)
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
            font=("Arial", 9),
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
        self._history_text.tag_config("number", foreground="#FFFFFF", font=("Arial", 9, "bold"))
        self._history_text.tag_config("error", foreground="#FF6B6B")  # Light red
        self._history_text.tag_config("timestamp", foreground="#888888")  # Grey
        self._history_text.tag_config("game_end", foreground="#FFD700", font=("Arial", 9, "bold"))  # Gold for game end

    def _on_canvas_click(self, event):
        """Handle canvas click - delegate to input handler or close menu."""
        # If game is finished, ignore all clicks
        if self._game and self._game.isFinished:
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

    def _add_event_to_history(self, message: str, event_type: str = "info", player_index: int = None):
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
        # We need to add "P1 " prefix
        # BUT: Don't add prefix for "Game Over" messages
        if not re.match(r'^P\d+', concise_message) and not concise_message.lower().startswith("game over"):
            if player_index is not None:
                player_num = player_index + 1
                concise_message = f"P{player_num} {concise_message}"
            elif self._game:
                player_num = self._current_player + 1
                concise_message = f"P{player_num} {concise_message}"

        # Remove duplicate player references at start (e.g., "P1 P1 hints" -> "P1 hints")
        concise_message = re.sub(r'^(P\d+)\s+\1\s+', r'\1 ', concise_message)

        # Simplify "plays COLOR NUMBER" format (already lowercase from engine)
        # Handle "plays red 1" -> "plays red 1" (already correct)
        # Handle "discards red 1" -> "discards red 1" (already correct)
        # The engine now returns lowercase, so we just need to ensure proper formatting
        # Trim whitespace
        concise_message = concise_message.strip()

        timestamp = datetime.now().strftime("%H:%M:%S")
        # Get turn number from game state
        # processMove() increments turn_number before updating, so:
        # - After first move: turnNumber = 1 (display as T01)
        # - After second move: turnNumber = 2 (display as T02)
        # We use turnNumber directly since it's already 1-based after the first move
        turn_number = 1
        if self._game:
            # Use turn number from game state (already 1-based after processMove)
            turn_number = self._game.state.turnNumber
        # Pad turn number with 0 for alignment (e.g., T01, T02, ..., T10)
        formatted_message = f"[{timestamp} T{turn_number:02d}] {concise_message}"
        self._event_history.append((event_type, formatted_message))

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

    def set_show_all_cards(self, show_all: bool):
        """Set whether to show all cards (for replay mode)."""
        self._show_all_cards = show_all

    def set_suppress_dialogs(self, suppress: bool):
        """Set whether to suppress message boxes (for testing)."""
        self._suppress_dialogs = suppress

    def display_game_state(self, game: Game, player_index: int) -> None:
        """Display the game state from a player's perspective."""
        self._game = game
        self._current_player = player_index

        # Clear canvas
        self._canvas.delete("all")
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
        score = game.getScore()
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
        """Draw center area: tokens in center, played cards row above, discarded cards row below."""
        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800

        center_x = width // 2
        center_y = height // 2

        # Draw tokens in center
        self._draw_tokens(center_x, center_y)

        # Draw played cards (fireworks) in a row above center
        self._draw_fireworks_row(center_x, center_y - 100)

        # Draw discarded cards in a row below center
        self._draw_discard_row(center_x, center_y + 100)

        # Draw deck count
        state = self._game.state
        deck_count = state.commonView.cardsToDraw
        self._canvas.create_text(
            center_x, center_y + 180,
            text=f"Deck: {deck_count} cards",
            fill="white",
            font=("Arial", 11, "bold")
        )

    def _draw_tokens(self, center_x: int, center_y: int):
        """Draw hint and life tokens centered."""
        state = self._game.state
        settings = self._game.settings

        hint_tokens = state.commonView.hintTokens
        life_tokens = state.commonView.liveTokens
        max_hints = settings.maxHintTokens
        max_lives = settings.maxLiveTokens

        # Draw hint tokens (blue clock tokens) - centered
        self._canvas.create_text(
            center_x - 50, center_y - 30,
            text="Hints",
            fill="white",
            font=("Arial", 11, "bold"),
            anchor="center"
        )

        hint_widgets = []
        token_size = 18
        hint_start_x = center_x - 50 - (min(max_hints, 4) * (token_size + 4)) // 2
        for i in range(max_hints):
            x = hint_start_x + (i % 4) * (token_size + 4)
            y = center_y - 10 + (i // 4) * (token_size + 4)

            color = "#4169E1" if i < hint_tokens else "#1A1A3E"
            widget = self._canvas.create_oval(
                x, y,
                x + token_size, y + token_size,
                fill=color,
                outline="#87CEEB",
                width=2
            )
            hint_widgets.append(widget)
        self._token_widgets["hint"] = hint_widgets

        # Draw life tokens (black fuse tokens) - centered
        self._canvas.create_text(
            center_x + 50, center_y - 30,
            text="Lives",
            fill="white",
            font=("Arial", 11, "bold"),
            anchor="center"
        )

        life_widgets = []
        life_start_x = center_x + 50 - (max_lives * (token_size + 4)) // 2
        for i in range(max_lives):
            x = life_start_x + i * (token_size + 4)
            y = center_y - 10

            if i < life_tokens:
                # Use same color for all remaining lives
                color = "#FF4500"  # Red/orange for all remaining lives
            else:
                color = "#000000"  # Black for lost lives

            widget = self._canvas.create_oval(
                x, y,
                x + token_size, y + token_size,
                fill=color,
                outline="#654321",
                width=2
            )
            life_widgets.append(widget)
        self._token_widgets["life"] = life_widgets

    def _draw_fireworks_row(self, center_x: int, y: int):
        """Draw fireworks (played cards) in a horizontal row."""
        state = self._game.state
        cards_played = state.commonView.cardsPlayed

        colors = [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]
        card_width = 50
        card_height = 70
        spacing = 15
        total_width = len(colors) * (card_width + spacing) - spacing
        start_x = center_x - total_width // 2

        self._firework_widgets.clear()

        for i, color in enumerate(colors):
            x = start_x + i * (card_width + spacing)

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
        # Reconstruct discard pile from common view
        state = self._game.state
        discard_pile = []
        for color, suit in state.commonView.cardsDiscarded.items():
            for number, count in suit.cards.items():
                for _ in range(count):
                    discard_pile.append(Card(color, number))

        if not discard_pile:
            self._canvas.create_text(
                center_x, y,
                text="Discard Pile (empty)",
                fill="#888888",
                font=("Arial", 10)
            )
            return

        # Get table radius to ensure cards stay within table
        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800
        # Make table smaller (was // 3, now // 4)
        table_radius = min(width, height) // 4

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

        # Start from left edge of centered area
        start_x = center_x - total_width // 2

        x = start_x
        for color, number_list, color_width in color_groups:
            # Draw each unique (color, number) combination
            for i, (num, count) in enumerate(number_list):
                # Overlap cards horizontally
                card_x = x + i * horizontal_overlap
                # If multiple cards with same color+number, stack them vertically
                for stack_idx in range(count):
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
                    text_color = "#000000" if color in [Color.WHITE, Color.YELLOW] else "#FFFFFF"
                    # Position number in top left corner (like playing cards) - smaller font
                    number_x = card_x - card_width // 2 + 4  # Left edge + small margin
                    number_y = card_y - card_height // 2 + 4  # Top edge + small margin
                    self._canvas.create_text(
                        number_x, number_y,
                        text=str(num),
                        fill=text_color,
                        font=("Arial", 10, "bold"),
                        anchor="nw"  # Top-left anchor
                    )
            # Move to next color position
            x += color_width + color_spacing

    def _draw_player_hands(self):
        """Draw all player hands in a circle with current player at bottom (270°)."""
        if not self._game:
            return

        width = self._canvas.winfo_width() or 1200
        height = self._canvas.winfo_height() or 800

        center_x = width // 2
        center_y = height // 2
        # Make table smaller (was // 3, now // 4)
        table_radius = min(width, height) // 4
        state = self._game.state
        num_players = len(state.playerHands)

        # Calculate card dimensions
        card_width = 50
        card_height = 70
        spacing = 10

        # Find the maximum number of cards in any hand to ensure all hands are outside the table
        max_cards = max(len(hand.cards) for hand in state.playerHands) if state.playerHands else 5
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
            hand = state.playerHands[i]
            is_current_player = (i == self._current_player)

            # Draw player label - always on top of hand
            label_offset = 60
            # Always place label above the cards (toward center)
            label_y = y - label_offset

            self._canvas.create_text(
                x, label_y,
                text=f"Player {i + 1}" + (" (You)" if is_current_player else ""),
                fill="white" if is_current_player else "#CCCCCC",
                font=("Arial", 12, "bold" if is_current_player else "normal")
            )

            # Draw cards in hand
            total_width = len(hand.cards) * (card_width + spacing) - spacing
            start_x = x - total_width // 2

            for card_idx, card in enumerate(hand.cards):
                card_x = start_x + card_idx * (card_width + spacing)
                card_y = y

                # Get hints for this card (for all players, including current player)
                from hanabi.core.player import HintTrackingPlayer
                player = self._game.team.players[i]
                hints = player.getHints() if (not self._show_all_cards and isinstance(player, HintTrackingPlayer)) else {}
                card_hints = hints.get(card_idx, {})

                # Check if card actually has hints (color or number is not None)
                has_hints = bool(card_hints and (card_hints.get("color") is not None or card_hints.get("number") is not None))

                # Check if card has both color and number hints (fully known)
                has_both_hints = bool(card_hints and
                                     card_hints.get("color") is not None and
                                     card_hints.get("number") is not None)

                # Show card front if: replay mode OR not current player OR current player has both hints
                show_front = self._show_all_cards or not is_current_player or (is_current_player and has_both_hints)

                widget = self._create_card_widget(
                    card_x, card_y,
                    card.color, card.number,
                    show_front=show_front,
                    hints=card_hints if not show_front else {},
                    clickable=True,  # All cards clickable for action menu
                    player_idx=i,
                    card_idx=card_idx,
                    has_hints=has_hints if not is_current_player else False  # Don't show hint indicator dot for current player
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
        selected: bool = False,
        has_hints: bool = False
    ) -> int:
        """Create a card widget on the canvas."""
        hints = hints or {}
        card_width = 50
        card_height = 70

        if show_front:
            bg_color = self.COLOR_COLORS.get(color, "#FFFFFF")
            text_color = "#000000" if color in [Color.WHITE, Color.YELLOW] else "#FFFFFF"

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

            # Add hint indicator dot if card has hints
            if has_hints:
                self._canvas.create_oval(
                    x + card_width // 2 - 8, y - card_height // 2 + 3,
                    x + card_width // 2 - 3, y - card_height // 2 + 8,
                    fill="#FFD700",
                    outline="#000000",
                    width=1,
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

            if color_hint and number_hint:
                hint_color = self.COLOR_COLORS.get(color_hint, "#FFFFFF")
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
                    fill="white",
                    font=("Arial", 18, "bold"),
                    tags=("card",)
                )
            elif color_hint:
                hint_color = self.COLOR_COLORS.get(color_hint, "#FFFFFF")
                self._canvas.create_text(
                    x, y,
                    text=self.COLOR_NAMES.get(color_hint, "?")[0],
                    fill=hint_color,
                    font=("Arial", 24, "bold"),
                    tags=("card",)
                )
            elif number_hint:
                self._canvas.create_text(
                    x, y,
                    text=str(number_hint.value),
                    fill="white",
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

        return widget

    def show_action_menu(self, player_idx: int, card_idx: int, x: int, y: int):
        """
        Show action menu popup near cursor.

        Args:
            player_idx: Index of player whose card was clicked
            card_idx: Index of card that was clicked
            x, y: Screen coordinates for menu position
        """
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
        common_view = state.commonView

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
            if common_view.hintTokens < self._game.settings.maxHintTokens:
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
            if common_view.hintTokens > 0:
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

        if self._game.isFinished:
            # Game is finished - close menu and return
            self._close_action_menu()
            return

        # Get the teammate index (player whose card was clicked)
        teammate_idx = self._action_menu_context.get("player_idx")
        card_idx = self._action_menu_context.get("card_idx")

        # Validate context
        if teammate_idx is None or card_idx is None:
            return

        # Get the current player (who is making the move) - refresh from game state
        current_player = self._game.currentPlayer

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
                if (0 <= teammate_idx < len(state.playerHands) and
                    teammate_idx != current_player and
                    teammate_idx is not None):
                    hand = state.playerHands[teammate_idx]
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
                if (0 <= teammate_idx < len(state.playerHands) and
                    teammate_idx != current_player and
                    teammate_idx is not None):
                    hand = state.playerHands[teammate_idx]
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

    def display_move_result(self, success: bool, message: str, player_index: int = None) -> None:
        """Display the result of a move in history panel."""
        if success:
            # Format message - pass player_index for hint formatting
            formatted_msg = message
            # If player_index is provided and message doesn't start with player info, add it
            if player_index is not None and not formatted_msg.startswith("Player ") and not formatted_msg.startswith("P"):
                formatted_msg = f"P{player_index + 1} {formatted_msg}"
            self._add_event_to_history(formatted_msg, "success", player_index)
        else:
            self._add_event_to_history(f"Error: {message}", "error")

    def _update_last_turn_warning(self):
        """Update the last turn warning banner visibility."""
        if not self._game:
            return

        state = self._game.state
        deck_empty = (state.commonView.cardsToDraw == 0)

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
        score = game.getScore()
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
            self.display_game_state(self._game, self._current_player)

    def clear(self) -> None:
        """Clear the display."""
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
