"""
Main GUI game controller for Hanabi.
Integrates GUI display and input with the game engine.
"""

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except ImportError:
    raise ImportError(
        "tkinter is not available. On macOS, install it with: brew install python-tk\n"
        "Or use the CLI version: python -m hanabi"
    )
from typing import List, Optional
import logging
from hanabi.core.game import create_standard_game_settings, Game
from hanabi.core.player import PlayerTeam
from .gui_display import GUIDisplay
from .gui_input import GUIInput
from .gui_player import GUIPlayer
from hanabi.core.game_history import GameHistory
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Number

logger = logging.getLogger(__name__)


class GUIGame:
    """Main GUI game controller."""

    def __init__(self, root: tk.Tk):
        """
        Initialize GUI game.

        Args:
            root: Tkinter root window
        """
        self.root = root
        self._game: Optional[Game] = None
        self._players: List[GUIPlayer] = []
        self._display: Optional[GUIDisplay] = None
        self._input_handler: Optional[GUIInput] = None
        self._history: Optional[GameHistory] = None
        self._is_replay_mode: bool = False
        self._replay_history: Optional[dict] = None
        self._replay_move_index: int = 0
        self._suppress_dialogs: bool = False  # Set to True to disable messageboxes (for testing)
        self._game_ended: bool = False  # Track if game has ended to prevent duplicate end screens

        self._setup_menu()
        self._setup_menu()
        self._setup_ui()

    def _setup_menu(self):
        """Set up menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Game", command=self._new_game)
        file_menu.add_command(label="Load Replay", command=self._load_replay)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

        # Game menu
        game_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Game", menu=game_menu)
        game_menu.add_command(label="Replay Mode", command=self._toggle_replay_mode)

    def _setup_ui(self):
        """Set up the UI."""
        self._display = GUIDisplay(self.root)

        # Store reference to control frame for showing/hiding
        self._control_frame = None
        self._player_buttons = []
        self._replay_btn = None
        self._abandon_btn = None
        self._back_to_start_btn = None

        # Show start screen buttons
        self._show_start_screen()

    def _show_start_screen(self):
        """Show the start screen with player selection buttons."""
        # Ensure display is set up
        if not self._display:
            return

        # Show all display frames
        for widget in self._display.root.winfo_children():
            if isinstance(widget, tk.Frame):
                widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Get the canvas frame from display
        canvas_frame = self._display._canvas_frame if hasattr(self._display, '_canvas_frame') else None

        if canvas_frame:
            # Clear any existing control frame
            if self._control_frame:
                self._control_frame.destroy()

            # Create control frame centered on canvas frame
            self._control_frame = tk.Frame(canvas_frame, bg="#2C3E50")

            # Center the frame
            def center_buttons():
                # Check if control frame still exists (it may have been destroyed)
                if self._control_frame and canvas_frame.winfo_width() > 1 and canvas_frame.winfo_height() > 1:
                    try:
                        self._control_frame.place(relx=0.5, rely=0.5, anchor="center")
                    except (tk.TclError, AttributeError):
                        # Frame was destroyed, unbind the event
                        canvas_frame.unbind("<Configure>")

            canvas_frame.bind("<Configure>", lambda e: center_buttons())
            # Call immediately to position buttons
            self.root.after_idle(center_buttons)

            # Player selection buttons (2-5 players) - vertical layout
            self._player_buttons = []
            for num_players in range(2, 6):
                btn = tk.Button(
                    self._control_frame,
                    text=f"{num_players} Players",
                    command=lambda n=num_players: self._start_new_game(n, one_player_mode=False),
                    bg="#95A5A6",
                    fg="black",
                    font=("Arial", 14, "bold"),
                    padx=25,
                    pady=12,
                    width=18,
                    highlightthickness=0
                )
                btn.pack(pady=8)
                self._player_buttons.append(btn)

            # Add separator
            separator = tk.Frame(self._control_frame, height=2, bg="#34495E")
            separator.pack(fill=tk.X, pady=10)

            # Add 1-player mode buttons (1 human + AI players)
            tk.Label(
                self._control_frame,
                text="1-Player Mode (with AI):",
                bg="#2C3E50",
                fg="white",
                font=("Arial", 12, "bold")
            ).pack(pady=(5, 8))

            for num_players in range(2, 6):
                btn = tk.Button(
                    self._control_frame,
                    text=f"1 Player + {num_players - 1} AI",
                    command=lambda n=num_players: self._start_new_game(n, one_player_mode=True),
                    bg="#95A5A6",
                    fg="black",
                    font=("Arial", 14, "bold"),
                    padx=25,
                    pady=12,
                    width=18,
                    highlightthickness=0
                )
                btn.pack(pady=8)
                self._player_buttons.append(btn)

            self._replay_btn = tk.Button(
                self._control_frame,
                text="Load Replay",
                command=self._load_replay,
                bg="#95A5A6",
                fg="black",
                font=("Arial", 14, "bold"),
                padx=25,
                pady=12,
                width=18,
                highlightthickness=0
            )
            self._replay_btn.pack(pady=8)

    def _start_new_game(self, num_players: int, one_player_mode: bool = False):
        """Start a new game with specified number of players."""
        self._new_game_with_players(num_players, one_player_mode)

    def _new_game(self):
        """Start a new game (legacy method - now uses _start_new_game)."""
        # This method is kept for compatibility but shouldn't be called directly
        pass

    def _new_game_with_players(self, num_players: int, one_player_mode: bool = False):
        """Start a new game with specified number of players."""
        self._is_replay_mode = False
        self._replay_history = None
        self._replay_move_index = 0
        self._game_ended = False  # Reset game ended flag
        self._one_player_mode = one_player_mode  # Store for reference

        # Create game settings
        settings = create_standard_game_settings(num_players)

        # Create players: 1 GUIPlayer (human) + rest as RandomPlayers (AI) if 1-player mode
        self._players = []
        if one_player_mode:
            # 1-player mode: first player is human, rest are AI
            from hanabi.ai import RandomPlayer

            # Create human player (player 0)
            gui_player = GUIPlayer(0, None, self._display)  # game will be set after creation
            self._players.append(gui_player)

            # Create AI players (players 1 to num_players-1)
            # Note: We'll set the game reference after creating the game
            for i in range(1, num_players):
                # Create placeholder - will be replaced after game is created
                self._players.append(None)
        else:
            # Multi-player mode: all players are human
            for i in range(num_players):
                gui_player = GUIPlayer(i, None, self._display)  # game will be set after creation
                self._players.append(gui_player)

        # For 1-player mode, we need to create the game first to get a reference for AI players
        # Create placeholder team for now
        if one_player_mode:
            # Create temporary placeholder players for team creation
            from hanabi.core.player import HumanPlayer
            placeholder_players = [HumanPlayer(i) for i in range(num_players)]
            team = PlayerTeam(placeholder_players)
        else:
            # Create game with GUI players
            team = PlayerTeam(self._players)

        # Set up move callback for display updates
        def on_move_callback(player_index: int, move: Move, old_state, new_state):
            """Callback to update display when a move is made."""
            # Format move message
            logger.debug(f"[on_move_callback] player={player_index}, move={move}, old_state={old_state is not None}, new_state={new_state is not None}")
            move_message = self._format_move_message(player_index, move, old_state, new_state)
            logger.debug(f"[on_move_callback] formatted message: {move_message}")

            # Schedule display updates on GUI thread (Tkinter is not thread-safe)
            def update_display():
                # Update game state display
                self._display.display_game_state(self._game, self._game.currentPlayer)

                # Display move result in event history
                # Check if this is an AI player for display purposes
                is_ai_player = getattr(self, '_one_player_mode', False) and player_index > 0
                self._display.display_move_result(True, move_message, player_index, is_ai_player)

            self._display.root.after(0, update_display)

        self._game = Game.create(team, settings, on_move=on_move_callback)

        # For 1-player mode, replace placeholder players with actual AI players
        if one_player_mode:
            from hanabi.ai import RandomPlayer
            actual_players = [self._players[0]]  # Keep the human player
            for i in range(1, num_players):
                ai_player = RandomPlayer(i, self._game)
                actual_players.append(ai_player)
            self._players = actual_players
            # Update team with actual players
            self._game._team = PlayerTeam(actual_players)
            # Update common view for AI players
            common_view = self._game.state.commonView
            for player in actual_players:
                player.set_common_view(common_view)

        # Set game reference in players (needed for display updates)
        for player in self._players:
            if hasattr(player, '_game'):
                player._game = self._game

        # Set up display
        self._display.set_game(self._game)
        self._display.set_show_all_cards(False)
        self._display.set_suppress_dialogs(self._suppress_dialogs)
        # Connect display's move callback to set move on current player
        self._display.set_move_callback(self._on_move_made)

        # Set up input handler
        self._input_handler = GUIInput(self._game, self._display)
        self._display.set_input_handler(self._input_handler)
        self._input_handler.setup_canvas_clicks()

        # Start game in a separate thread (non-blocking)
        import threading
        self._game_thread = threading.Thread(target=self._run_game, daemon=True)
        self._game_thread.start()

        # Initialize game history
        self._history = GameHistory({
            "num_players": num_players,
            "max_live_tokens": settings.maxLiveTokens,
            "max_hint_tokens": settings.maxHintTokens,
            "max_cards_in_hand": settings.maxCardsInHand
        })
        # Note: history recording will need to be updated to work with Game
        # For now, we'll skip it or update it later

        # Hide start screen buttons
        if self._control_frame:
            # Unbind the Configure event to prevent errors after frame is destroyed
            canvas_frame = self._display._canvas_frame if hasattr(self._display, '_canvas_frame') else None
            if canvas_frame:
                try:
                    # Unbind all Configure handlers (we can't unbind specific ones, so we'll handle it in the callback)
                    pass  # The callback will check if _control_frame exists
                except:
                    pass
            self._control_frame.place_forget()
            self._control_frame.destroy()
            self._control_frame = None

        # Ensure game display is visible
        if self._display:
            for widget in self._display.root.winfo_children():
                if isinstance(widget, tk.Frame):
                    widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Add abandon game button to status bar
        self._add_abandon_button()

        # Initial display update to show the starting game state
        self._display.display_game_state(self._game, self._game.currentPlayer)

    def _add_abandon_button(self):
        """Add abandon game button to status bar."""
        if self._abandon_btn:
            return

        status_frame = None
        for widget in self._display.root.winfo_children():
            if isinstance(widget, tk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, tk.Frame) and child.cget("bg") == "#34495E":
                        status_frame = child
                        break
                if status_frame:
                    break

        if status_frame:
            self._abandon_btn = tk.Button(
                status_frame,
                text="Abandon Game",
                command=self._abandon_game,
                bg="#95A5A6",
                fg="black",
                font=("Arial", 10, "bold"),
                padx=10,
                pady=3,
                highlightthickness=0,
                borderwidth=1,
                relief=tk.RAISED
            )
            # Force text color after creation
            self._abandon_btn.config(fg="black")
            self._abandon_btn.pack(side=tk.RIGHT, padx=5)

    def _abandon_game(self):
        """Abandon current game and return to start screen."""
        # Clear game state
        self._game = None
        self._players = []
        self._input_handler = None
        self._history = None
        self._is_replay_mode = False

        # Clear the canvas and top panel (status bar)
        if self._display:
            self._display.clear()
            # Clear status label
            if hasattr(self._display, '_status_label'):
                self._display._status_label.config(text="")
            # Clear score label
            if hasattr(self._display, '_score_label'):
                self._display._score_label.config(text="Score: 0/25")
            # Hide last turn warning
            if hasattr(self._display, '_last_turn_label'):
                self._display._last_turn_label.pack_forget()
            # Clear event history
            if hasattr(self._display, '_history_text'):
                self._display._history_text.config(state=tk.NORMAL)
                self._display._history_text.delete("1.0", tk.END)
                self._display._history_text.config(state=tk.DISABLED)
            if hasattr(self._display, '_event_history'):
                self._display._event_history.clear()

        # Hide game control buttons
        if self._abandon_btn:
            self._abandon_btn.pack_forget()
            self._abandon_btn = None
        if self._back_to_start_btn:
            self._back_to_start_btn.pack_forget()
            self._back_to_start_btn = None

        # Show start screen
        self._show_start_screen()

    def _ask_num_players(self) -> Optional[int]:
        """Ask user for number of players with clickable buttons."""
        if self._suppress_dialogs:
            # In test mode, return default
            return 3

        dialog = tk.Toplevel(self.root)
        dialog.title("New Game")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#34495E")

        result = [None]

        tk.Label(
            dialog,
            text="Select number of players:",
            font=("Arial", 12, "bold"),
            bg="#34495E",
            fg="white"
        ).pack(pady=20)

        button_frame = tk.Frame(dialog, bg="#34495E")
        button_frame.pack(pady=10)

        # Create 4 buttons for 2-5 players
        for num_players in range(2, 6):
            btn = tk.Button(
                button_frame,
                text=f"{num_players} Players",
                command=lambda n=num_players: self._select_players(dialog, result, n),
                bg="#3498DB",
                fg="white",
                font=("Arial", 11, "bold"),
                width=12,
                padx=10,
                pady=8
            )
            btn.pack(pady=5, fill=tk.X)

        dialog.wait_window()
        return result[0]

    def _select_players(self, dialog, result, num_players):
        """Handle player count selection."""
        result[0] = num_players
        dialog.destroy()

    def _format_move_message(self, player_index: int, move: Move, old_state=None, new_state=None) -> str:
        """
        Format a move into a human-readable message for the event history.
        Matches the previous format that _add_event_to_history expects.

        Args:
            player_index: Index of the player making the move
            move: The move being made
            old_state: Game state before the move (optional, for detecting invalid plays)
            new_state: Game state after the move (optional, for detecting invalid plays)

        Returns:
            Formatted message string (will be further processed by _add_event_to_history)
        """
        # For Play and Discard moves, use old_state to get the card that was played/discarded
        # (new_state has the card already removed and a new card drawn)
        if isinstance(move, (Play, Discard)):
            state = old_state if old_state else (self._game.state if self._game else None)
        else:
            # For hints, use new_state (or current state)
            state = new_state if new_state else (self._game.state if self._game else None)

        if state is None or player_index >= len(state.playerHands):
            return f"makes move: {move}."

        player_hand = state.playerHands[player_index]

        # Format the base message
        if isinstance(move, Play):
            if move.card < len(player_hand.cards):
                card = player_hand.cards[move.card]
                # Format: "plays red 1." (with period, lowercase)
                message = f"plays {card.color.name.lower()} {card.number.value}."
            else:
                # Use 1-based indexing for card position
                message = f"plays card {move.card + 1}."

            # Check for special events (invalid play, firework completion, perfect score)
            if old_state and new_state:
                old_lives = old_state.commonView.liveTokens
                new_lives = new_state.commonView.liveTokens
                lost_life = new_lives < old_lives
                old_score = old_state.score()
                new_score = new_state.score()
                perfect_score = new_score == 25

                logger.debug(f"[_format_move_message] Play move: old_lives={old_lives}, new_lives={new_lives}, lost_life={lost_life}")

                # Check if firework was completed by comparing cards played
                firework_completed = False
                if not lost_life and move.card < len(player_hand.cards):
                    card = player_hand.cards[move.card]
                    # Firework is completed when a 5 is played and previous value was 4
                    old_cards_played = old_state.commonView.cardsPlayed
                    new_cards_played = new_state.commonView.cardsPlayed
                    old_value = old_cards_played.get(card.color)
                    new_value = new_cards_played.get(card.color)

                    # Debug logging
                    logger.debug(f"[_format_move_message] Play move: card={card}, card.number={card.number}, card.number==FIVE={card.number == Number.FIVE}")
                    logger.debug(f"[_format_move_message] old_cards_played={old_cards_played}, new_cards_played={new_cards_played}")
                    logger.debug(f"[_format_move_message] old_value={old_value} (type: {type(old_value)}), new_value={new_value} (type: {type(new_value)})")

                    # Firework is completed when:
                    # 1. Card played is a 5
                    # 2. Previous value for that color was 4
                    # 3. New value is 5
                    if card.number == Number.FIVE:
                        # Check if we're completing a firework (going from 4 to 5)
                        if old_value is not None and old_value == Number.FOUR and new_value == Number.FIVE:
                            firework_completed = True
                            logger.debug(f"[_format_move_message] ✓ Firework completed detected! card={card}, old_value={old_value}, new_value={new_value}")
                        else:
                            logger.debug(f"[_format_move_message] ✗ Not a firework completion: card.number={card.number}, old_value={old_value}, new_value={new_value}")

                # Build additional message parts
                additional_parts = []

                if lost_life:
                    # Invalid play - indicate life lost
                    # Replace only the trailing period
                    if message.endswith("."):
                        message = message[:-1] + " (invalid, loses a life)."
                    else:
                        message += " (invalid, loses a life)."
                    logger.debug(f"[_format_move_message] Invalid play detected, message: {message}")
                else:
                    # Valid play - check for firework completion
                    if firework_completed:
                        additional_parts.append("firework completed.")
                        # Show bonus hint token returned with current count
                        max_hints = new_state.startPosition.settings.maxHintTokens
                        hint_count = new_state.commonView.hintTokens
                        additional_parts.append(f"bonus hint token returned. ({hint_count}/{max_hints})")
                        logger.debug(f"[_format_move_message] Added firework completion to additional_parts: {additional_parts}")

                # Check for perfect score
                if perfect_score:
                    additional_parts.append("Perfect score! 5 bonus points!")
                    logger.debug(f"[_format_move_message] Added perfect score to additional_parts")

                # Append additional parts to message (only if not invalid play)
                logger.debug(f"[_format_move_message] additional_parts={additional_parts}, lost_life={lost_life}")
                if additional_parts and not lost_life:
                    # Remove the trailing period from the base message if we're adding more info
                    if message.endswith("."):
                        message = message[:-1]
                    message += " " + " ".join(additional_parts) + "."
                    logger.debug(f"[_format_move_message] Final message after appending parts: {message}")

            return message
        elif isinstance(move, Discard):
            if move.card < len(player_hand.cards):
                card = player_hand.cards[move.card]
                # Format: "discards blue 3." (with period, lowercase)
                return f"discards {card.color.name.lower()} {card.number.value}."
            # Use 1-based indexing for card position
            return f"discards card {move.card + 1}."
        elif isinstance(move, ColorHint):
            # Format: "hints player 2: white at 2, 4, 5." (with "at", period, lowercase)
            # Use 1-based indexing for card positions
            card_indices = ", ".join(str(card_idx + 1) for card_idx in move.cards)
            return f"hints player {move.teammate + 1}: {move.color.name.lower()} at {card_indices}."
        elif isinstance(move, NumberHint):
            # Format: "hints player 2: 3 at 1, 3." (with "at", period, lowercase)
            # Use 1-based indexing for card positions
            card_indices = ", ".join(str(card_idx + 1) for card_idx in move.cards)
            return f"hints player {move.teammate + 1}: {move.number.value} at {card_indices}."
        else:
            return f"makes move: {move}."

    def _on_move_made(self, move: Move):
        """
        Handle move made by player (callback from GUI input).

        This is called when the user clicks/interacts to make a move.
        Sets the move on the current player so game.play() can retrieve it.
        """
        # Check if game is valid and not finished
        if not self._game:
            if not self._suppress_dialogs:
                messagebox.showerror("Game Error", "No game is active.")
            return

        if self._game.isFinished:
            # Game is finished - show end screen if not already shown
            if not hasattr(self, '_game_ended') or not self._game_ended:
                self._on_game_end()
            return

        current_player = self._game.currentPlayer

        # Set the move on the current player (this will unblock player.play())
        # Display updates are now handled by the global callback in Game
        self._players[current_player].set_move(move)

    def _run_game(self):
        """Run the game in a separate thread (non-blocking for GUI)."""
        try:
            self._game.play()
        except RuntimeError as e:
            # Game ended due to invalid move or player error
            if not self._suppress_dialogs:
                messagebox.showerror("Game Error", str(e))
            self._on_game_end()
        except Exception as e:
            # Unexpected error
            import traceback
            error_msg = f"Unexpected error: {e}\n\n{traceback.format_exc()}"
            if not self._suppress_dialogs:
                messagebox.showerror("Game Error", error_msg)
            self._on_game_end()
        finally:
            # Game finished normally
            if self._game and self._game.isFinished:
                self._on_game_end()

    def _update_display(self):
        """Update the display."""
        if not self._game:
            return

        current_player = self._game.currentPlayer
        self._display.display_game_state(self._game, current_player)

    def _on_game_end(self):
        """Handle game end."""
        # Mark that game has ended to prevent multiple calls
        self._game_ended = True

        if self._game and self._history:
            # Save game history
            self._history.save_to_file()

        # Close any open action menu
        if self._display and hasattr(self._display, '_close_action_menu'):
            self._display._close_action_menu()

        # Update display with final game state before showing game over
        if self._game:
            current_player = self._game.currentPlayer
            self._display.display_game_state(self._game, current_player)

        self._display.display_game_end(self._game)

        # Hide abandon button, show back to start button
        if self._abandon_btn:
            self._abandon_btn.pack_forget()

        self._add_back_to_start_button()

    def _add_back_to_start_button(self):
        """Add back to start button after game ends."""
        if self._back_to_start_btn:
            return

        status_frame = None
        for widget in self._display.root.winfo_children():
            if isinstance(widget, tk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, tk.Frame) and child.cget("bg") == "#34495E":
                        status_frame = child
                        break
                if status_frame:
                    break

        if status_frame:
            self._back_to_start_btn = tk.Button(
                status_frame,
                text="Back to Start",
                command=self._abandon_game,  # Same as abandon - returns to start
                bg="#95A5A6",
                fg="black",
                font=("Arial", 10, "bold"),
                padx=10,
                pady=3,
                highlightthickness=0,
                borderwidth=1,
                relief=tk.RAISED
            )
            # Force text color after creation
            self._back_to_start_btn.config(fg="black")
            self._back_to_start_btn.pack(side=tk.RIGHT, padx=5)

    def _load_replay(self):
        """Load and play a replay file."""
        if self._suppress_dialogs:
            # In test mode, skip file dialog
            return

        # Set initial directory to game_records if it exists
        import os
        from hanabi.core.game_history import GameHistory
        initial_dir = GameHistory._get_records_dir() if os.path.exists(GameHistory._get_records_dir()) else "."

        filename = filedialog.askopenfilename(
            title="Load Replay",
            initialdir=initial_dir,
            filetypes=[("YAML files", "*.yaml"), ("JSON files", "*.json"), ("All files", "*.*")]
        )

        if not filename:
            return

        try:
            history = GameHistory({})
            history_data = history.load_from_file(filename)

            # Validate history data
            if not isinstance(history_data, dict):
                raise ValueError("Invalid replay file format: expected a dictionary")

            # Check for required keys
            if "s" not in history_data:
                raise ValueError("Invalid replay file: missing settings (key 's')")

            self._replay_history = history_data
            self._replay_move_index = 0
            self._is_replay_mode = True

            # Hide start screen if visible
            if self._control_frame:
                self._control_frame.destroy()
                self._control_frame = None
                self._player_buttons = []
                self._replay_btn = None

            # Show game display elements (same as _start_new_game)
            if self._display:
                self._display._status_label.pack(side=tk.LEFT, padx=10, pady=5)
                self._display._score_label.pack(side=tk.RIGHT, padx=10, pady=5)
                if hasattr(self._display, '_history_frame'):
                    self._display._history_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

            # Reconstruct game from history
            self._reconstruct_game_from_history(history_data)

            # Set up replay controls
            self._setup_replay_controls()

            if not self._suppress_dialogs:
                messagebox.showinfo("Replay Loaded", "Replay loaded successfully. Use controls to step through the game.")
        except Exception as e:
            import traceback
            error_msg = f"Failed to load replay: {str(e)}"
            if not self._suppress_dialogs:
                messagebox.showerror("Error", error_msg)
            else:
                # In test mode, raise the exception so tests can catch it
                raise

    def _reconstruct_game_from_history(self, history_data: dict):
        """Reconstruct game engine from history data."""
        # History format uses "s" for settings
        settings_dict = history_data.get("s", {})
        num_players = settings_dict.get("num_players", 3)

        settings = create_standard_game_settings(num_players)
        from hanabi.core.player import HumanPlayer
        placeholder_players = [HumanPlayer(i) for i in range(num_players)]
        team = PlayerTeam(placeholder_players)
        # Set up move callback for display updates (same as new game)
        def on_move_callback(player_index: int, move: Move, old_state, new_state):
            """Callback to update display when a move is made."""
            # Format move message
            move_message = self._format_move_message(player_index, move, old_state, new_state)

            # Schedule display updates on GUI thread (Tkinter is not thread-safe)
            def update_display():
                # Update game state display
                self._display.display_game_state(self._game, self._game.currentPlayer)

                # Display move result in event history
                # Check if this is an AI player for display purposes
                is_ai_player = getattr(self, '_one_player_mode', False) and player_index > 0
                self._display.display_move_result(True, move_message, player_index, is_ai_player)

            self._display.root.after(0, update_display)

        self._game = Game.create(team, settings, on_move=on_move_callback)

        # Apply moves from history up to current index
        moves = history_data.get("m", [])
        for move_data in moves[:self._replay_move_index]:
            # TODO: Full deserialization would reconstruct exact game state
            # For now, we just show the initial state
            pass

        self._display.set_game(self._game)
        self._display.set_show_all_cards(True)  # Show all cards in replay
        self._update_display()

    def _setup_replay_controls(self):
        """Set up replay control buttons."""
        # Find status frame to add replay controls
        status_frame = None
        for widget in self._display.root.winfo_children():
            if isinstance(widget, tk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, tk.Frame) and child.cget("bg") == "#34495E":
                        status_frame = child
                        break
                if status_frame:
                    break

        if not status_frame:
            return

        # Remove existing replay controls if any
        for widget in status_frame.winfo_children():
            if isinstance(widget, tk.Frame) and hasattr(widget, '_replay_controls'):
                widget.destroy()

        # Add replay controls to status frame
        replay_frame = tk.Frame(status_frame, bg="#34495E")
        replay_frame._replay_controls = True  # Mark as replay controls
        replay_frame.pack(side=tk.LEFT, padx=10)

        tk.Button(
            replay_frame,
            text="⏮ First",
            command=self._replay_first,
            bg="#95A5A6",
            fg="black",
            font=("Arial", 9),
            highlightthickness=0
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            replay_frame,
            text="⏪ Prev",
            command=self._replay_previous,
            bg="#95A5A6",
            fg="black",
            font=("Arial", 9),
            highlightthickness=0
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            replay_frame,
            text="⏩ Next",
            command=self._replay_next,
            bg="#95A5A6",
            fg="black",
            font=("Arial", 9),
            highlightthickness=0
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            replay_frame,
            text="⏭ Last",
            command=self._replay_last,
            bg="#95A5A6",
            fg="black",
            font=("Arial", 9),
            highlightthickness=0
        ).pack(side=tk.LEFT, padx=2)

    def _replay_first(self):
        """Go to first move in replay."""
        self._replay_move_index = 0
        self._update_replay_display()

    def _replay_previous(self):
        """Go to previous move in replay."""
        if self._replay_move_index > 0:
            self._replay_move_index -= 1
            self._update_replay_display()

    def _replay_next(self):
        """Go to next move in replay."""
        if self._replay_history:
            moves = self._replay_history.get("m", [])
            if self._replay_move_index < len(moves):
                self._replay_move_index += 1
                self._update_replay_display()

    def _replay_last(self):
        """Go to last move in replay."""
        if self._replay_history:
            moves = self._replay_history.get("m", [])
            self._replay_move_index = len(moves)
            self._update_replay_display()

    def _update_replay_display(self):
        """Update display for replay mode."""
        if not self._replay_history or not self._game:
            return

        # Reconstruct game state up to current move index
        # (This would need full deserialization implementation)
        self._update_display()

        # Update status
        moves = self._replay_history.get("m", [])
        self._display._status_label.config(
            text=f"Replay: Move {self._replay_move_index}/{len(moves)}"
        )

    def _toggle_replay_mode(self):
        """Toggle replay mode (if replay is loaded)."""
        if self._is_replay_mode:
            self._display.set_show_all_cards(True)
        else:
            self._display.set_show_all_cards(False)


def play_gui_game():
    """Main entry point for GUI game."""
    # Enable debug logging if --debug flag is present
    import sys
    import logging
    if "--debug" in sys.argv or "-d" in sys.argv:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        logging.getLogger('hanabi.game').setLevel(logging.DEBUG)
        print("Debug logging enabled. Check console for detailed game state information.")

    root = tk.Tk()
    # Start maximized
    try:
        # Try macOS/Linux way
        root.attributes('-zoomed', True)
    except:
        try:
            # Try Windows way
            root.state('zoomed')
        except:
            # Fallback: set geometry to screen size
            root.update_idletasks()
            width = root.winfo_screenwidth()
            height = root.winfo_screenheight()
            root.geometry(f"{width}x{height}+0+0")
    game = GUIGame(root)
    root.mainloop()


if __name__ == "__main__":
    play_gui_game()

