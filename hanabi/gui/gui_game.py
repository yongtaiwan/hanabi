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

            # Create 3-column layout
            columns_frame = tk.Frame(self._control_frame, bg="#2C3E50")
            columns_frame.pack()

            # Column 1: Hot Seat (Multiplayer)
            hot_seat_column = tk.Frame(columns_frame, bg="#2C3E50")
            hot_seat_column.pack(side=tk.LEFT, padx=30, fill=tk.BOTH, expand=True)

            tk.Label(
                hot_seat_column,
                text="Hot Seat",
                bg="#2C3E50",
                fg="white",
                font=("Arial", 14, "bold")
            ).pack(pady=(0, 10))

            self._player_buttons = []
            for num_players in range(2, 6):
                btn = tk.Button(
                    hot_seat_column,
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

            # Column 2: Single Player
            single_player_column = tk.Frame(columns_frame, bg="#2C3E50")
            single_player_column.pack(side=tk.LEFT, padx=30, fill=tk.BOTH, expand=True)

            tk.Label(
                single_player_column,
                text="Single Player",
                bg="#2C3E50",
                fg="white",
                font=("Arial", 14, "bold")
            ).pack(pady=(0, 10))

            for num_ai in range(1, 5):  # 1-4 AIs
                btn = tk.Button(
                    single_player_column,
                    text=f"{num_ai} AI{'s' if num_ai > 1 else ''}",
                    command=lambda n=num_ai + 1: self._select_ai_type_and_start(n),
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

            # Column 3: Replay
            replay_column = tk.Frame(columns_frame, bg="#2C3E50")
            replay_column.pack(side=tk.LEFT, padx=30, fill=tk.BOTH, expand=True)

            tk.Label(
                replay_column,
                text="Replay",
                bg="#2C3E50",
                fg="white",
                font=("Arial", 14, "bold")
            ).pack(pady=(0, 10))

            self._replay_btn = tk.Button(
                replay_column,
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

    def _select_ai_type_and_start(self, num_players: int):
        """Show dialog to select AI player type, then start game."""
        if self._suppress_dialogs:
            # In test mode, use default
            self._new_game_with_players(num_players, one_player_mode=True, ai_player_type=None)
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Select AI Player Type")
        dialog.geometry("350x250")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#34495E")

        result = [None]

        tk.Label(
            dialog,
            text="Select AI player type:",
            font=("Arial", 12, "bold"),
            bg="#34495E",
            fg="white"
        ).pack(pady=20)

        button_frame = tk.Frame(dialog, bg="#34495E")
        button_frame.pack(pady=10)

        from hanabi.ai import RandomPlayer, CommonSensePlayer
        from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig

        # For interactive play, use reasonable config for MonteCarlo
        # (slower than fast config but faster than default for better decisions)
        # Need enough simulations to reliably distinguish playable cards from other moves
        def create_monte_carlo_player(player_index: int) -> MonteCarloPlayer:
            config = MonteCarloConfig(
                min_think_time_s=1.0,   # 1 second minimum
                max_think_time_s=2.0,   # 2 seconds maximum
                min_simulations=20,     # Minimum 20 simulations per move (reduced variance)
                max_simulations=200,    # Cap at 200 simulations
            )
            return MonteCarloPlayer(player_index, config=config)

        ai_types = [
            ("Random", RandomPlayer),
            ("CommonSense", CommonSensePlayer),
            ("MonteCarlo", create_monte_carlo_player),
        ]

        for name, ai_class in ai_types:
            btn = tk.Button(
                button_frame,
                text=name,
                command=lambda ac=ai_class: self._select_ai_type(dialog, result, ac),
                bg="#3498DB",
                fg="black",
                font=("Arial", 11, "bold"),
                width=15,
                padx=10,
                pady=8
            )
            btn.pack(pady=5, fill=tk.X)

        dialog.wait_window()

        if result[0]:
            self._new_game_with_players(num_players, one_player_mode=True, ai_player_type=result[0])

    def _select_ai_type(self, dialog, result, ai_class):
        """Handle AI type selection."""
        result[0] = ai_class
        dialog.destroy()

    def _new_game(self):
        """Start a new game (legacy method - now uses _start_new_game)."""
        # This method is kept for compatibility but shouldn't be called directly
        pass

    def _new_game_with_players(self, num_players: int, one_player_mode: bool = False, ai_player_type=None):
        """Start a new game with specified number of players.

        Args:
            num_players: Total number of players
            one_player_mode: If True, first player is human, rest are AI
            ai_player_type: AI player class to use (if None, defaults to RandomPlayer)
        """
        self._is_replay_mode = False
        self._replay_history = None
        self._replay_move_index = 0
        self._game_ended = False  # Reset game ended flag
        self._one_player_mode = one_player_mode  # Store for reference

        # Create game settings
        settings = create_standard_game_settings(num_players)

        # Create players: 1 GUIPlayer (human) + rest as AI players if 1-player mode
        self._players = []
        if one_player_mode:
            # 1-player mode: first player is human, rest are AI
            # Use provided AI type or default to RandomPlayer
            if ai_player_type is None:
                from hanabi.ai import RandomPlayer
                ai_player_type = RandomPlayer

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
            # Update hint tracking in display (independent of player implementations)
            self._display.update_hints_from_move(player_index, move)

            # Format move message
            logger.debug(f"[on_move_callback] player={player_index}, move={move}, old_state={old_state is not None}, new_state={new_state is not None}")
            move_message = self._format_move_message(player_index, move, old_state, new_state)
            logger.debug(f"[on_move_callback] formatted message: {move_message}")

            # Record move in history
            if self._history and self._game:
                # Format a simple result message for history (not used in new format, but kept for compatibility)
                result_msg = move_message
                self._history.record_move(player_index, move, result_msg, self._game)

            # Schedule display updates on GUI thread (Tkinter is not thread-safe)
            # Get turn number when move was made (new_state has the turn number after increment)
            move_turn_number = new_state.turnNumber

            def update_display():
                # Only update game state display if game is not finished
                # (when game ends, display is already correct and we want to preserve hints)
                if not self._game.isFinished:
                    # In single player mode, always show human player's view (player 0)
                    # In multi-player mode, show current player's view
                    display_player = 0 if getattr(self, '_one_player_mode', False) else self._game.currentPlayer
                    self._display.display_game_state(self._game, display_player)

                # Display move result in event history with correct turn number
                # Check if this is an AI player for display purposes
                is_ai_player = getattr(self, '_one_player_mode', False) and player_index > 0
                self._display.display_move_result(True, move_message, player_index, is_ai_player, turn_number=move_turn_number)

                # Force immediate GUI update to ensure display refreshes right away
                # This ensures the display updates immediately after each move, even for fast AI players
                try:
                    # Process all pending GUI events to ensure the display updates immediately
                    # This is critical for ensuring updates are visible when AI players move quickly
                    self._display.root.update_idletasks()
                except:
                    # Ignore errors (e.g., if window was closed)
                    pass

            # Schedule update immediately (0 = highest priority, runs as soon as possible)
            # The callback will call update_idletasks() to force immediate processing
            # This ensures the display refreshes after each move, not just after all AI players move
            self._display.root.after(0, update_display)

        self._game = Game.create(team, settings, on_move=on_move_callback)

        # For 1-player mode, replace placeholder players with actual AI players
        if one_player_mode:
            # Use the provided AI player type or default to RandomPlayer
            if ai_player_type is None:
                from hanabi.ai import RandomPlayer
                ai_player_type = RandomPlayer

            actual_players = [self._players[0]]  # Keep the human player
            for i in range(1, num_players):
                ai_player = ai_player_type(i)
                # Set game settings on the new player instance
                # This is required for hint generation to work
                ai_player.set_game_settings(settings)
                actual_players.append(ai_player)
            self._players = actual_players
            # Update team with actual players
            self._game._team = PlayerTeam(actual_players)
            # CRITICAL: Set game settings on all players in the new team
            # This ensures all players have access to gameSettings
            for player in actual_players:
                player.set_game_settings(settings)
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

        # Enable home button (acts as abandon game during play)
        if hasattr(self._display, '_home_btn'):
            self._display._home_btn.config(state=tk.NORMAL, command=self._abandon_game)

        # Set up input handler
        self._input_handler = GUIInput(self._game, self._display)
        self._display.set_input_handler(self._input_handler)
        self._input_handler.setup_canvas_clicks()

        # Start game in a separate thread (non-blocking)
        import threading
        self._game_thread = threading.Thread(target=self._run_game, daemon=True)
        self._game_thread.start()

        # Start a periodic GUI update processor to ensure updates are processed immediately
        # This helps when AI players make moves quickly in sequence
        self._process_gui_updates()

        # Initialize game history
        self._history = GameHistory({
            "num_players": num_players,
            "max_live_tokens": settings.maxLiveTokens,
            "max_hint_tokens": settings.maxHintTokens,
            "max_cards_in_hand": settings.maxCardsInHand
        })
        # Record initial state
        if self._game:
            self._history.record_initial_state(self._game)

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

        # Home button will serve as abandon game button during play

        # Initial display update to show the starting game state
        # In single player mode, always show human player's view (player 0)
        display_player = 0 if one_player_mode else self._game.currentPlayer
        self._display.display_game_state(self._game, display_player)

    # Removed _add_abandon_button - home button now serves this purpose

    def _abandon_game(self):
        """Abandon current game/replay and return to start screen."""
        # Clear game state
        self._game = None
        self._players = []
        self._input_handler = None
        self._history = None
        self._is_replay_mode = False
        self._replay_history = None
        self._replay_move_index = 0

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
            # Clear replay-specific display state
            self._display.set_game(None)
            self._display.set_show_all_cards(False)
            if hasattr(self._display, '_replay_player_names'):
                self._display._replay_player_names = None

        # Remove replay controls if any
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
            for widget in status_frame.winfo_children():
                if isinstance(widget, tk.Frame) and hasattr(widget, '_replay_controls'):
                    widget.destroy()

        # Clear replay button references to prevent stale references
        if hasattr(self, '_replay_first_btn'):
            self._replay_first_btn = None
        if hasattr(self, '_replay_prev_btn'):
            self._replay_prev_btn = None
        if hasattr(self, '_replay_next_btn'):
            self._replay_next_btn = None
        if hasattr(self, '_replay_last_btn'):
            self._replay_last_btn = None

        # Hide game control buttons
        if self._back_to_start_btn:
            self._back_to_start_btn.pack_forget()
            self._back_to_start_btn = None

        # Disable home button
        if hasattr(self._display, '_home_btn'):
            self._display._home_btn.config(state=tk.DISABLED, command=None)

        # Show start screen
        self._show_start_screen()

        # Force a full repaint of the display
        if self._display:
            # Update the canvas frame to ensure it's visible
            if hasattr(self._display, '_canvas_frame'):
                self._display._canvas_frame.update_idletasks()
            # Force root window update to ensure everything is repainted
            self._display.root.update_idletasks()
            self._display.root.update()

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
                fg="black",
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
        assert self._game is not None, "No game is active."

        if self._game.isFinished:
            # Game is finished - show end screen if not already shown
            if not hasattr(self, '_game_ended') or not self._game_ended:
                self._on_game_end()
            return

        current_player = self._game.currentPlayer

        # Set the move on the current player (this will unblock player.play())
        # Display updates are now handled by the global callback in Game
        self._players[current_player].set_move(move)

    def _process_gui_updates(self):
        """Periodically process GUI updates to ensure display refreshes immediately."""
        # Only continue if game is active and not finished
        if self._game and not self._game.isFinished:
            # Process any pending GUI events
            # This ensures display updates are processed even when AI players move quickly
            try:
                self._display.root.update_idletasks()
            except:
                # Ignore errors (e.g., if window was closed)
                pass
            # Schedule next check (every 50ms to ensure responsive updates)
            # This helps ensure the display refreshes immediately after each move
            self._display.root.after(50, self._process_gui_updates)
        # If game is finished or doesn't exist, stop the periodic updates

    def _run_game(self):
        """Run the game in a separate thread (non-blocking for GUI)."""
        # Let all exceptions propagate (fail fast on bugs)
        # No defensive programming - assertions should crash with stack trace
        self._game.play()
        # Game finished normally
        if self._game and self._game.isFinished:
            self._on_game_end()

    def _update_display(self):
        """Update the display."""
        if not self._game:
            return

        # In single player mode, always show human player's view (player 0)
        # In multi-player mode, show current player's view
        display_player = 0 if getattr(self, '_one_player_mode', False) else self._game.currentPlayer
        self._display.display_game_state(self._game, display_player)

    def _on_game_end(self):
        """Handle game end."""
        # Mark that game has ended to prevent multiple calls
        self._game_ended = True

        if self._game and self._history:
            # Record and save game history with final score
            final_score = self._game.getScore()
            self._history.record_final_score(self._game)
            self._history.save_to_file(final_score=final_score)

        # Close any open action menu
        if self._display and hasattr(self._display, '_close_action_menu'):
            self._display._close_action_menu()

        # If playing with AI (one-player mode), show human player's view (player 0) at bottom
        if getattr(self, '_one_player_mode', False) and self._game:
            # Update display to show player 0's view (human player)
            self._display.display_game_state(self._game, 0)

        # Display game end message (game state is already displayed from last move)
        self._display.display_game_end(self._game)

        # Home button already serves as back to start button
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

        history = GameHistory({})
        history_data = history.load_from_file(filename)

        # Validate history data
        if not isinstance(history_data, dict):
            raise ValueError("Invalid replay file format: expected a dictionary")

        # Check for required keys
        if "settings" not in history_data:
            raise ValueError("Invalid replay file: missing settings")
        if "deck" not in history_data:
            raise ValueError("Invalid replay file: missing deck")

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

        # Reconstruct game from history (initial state, no moves applied yet)
        self._reconstruct_game_from_history(history_data)

        # Enable home button (acts as abandon/back to start during replay)
        if hasattr(self._display, '_home_btn'):
            self._display._home_btn.config(state=tk.NORMAL, command=self._abandon_game)

        # Set up replay controls
        self._setup_replay_controls()

    def _back_to_home(self):
        """Return to home screen from replay mode."""
        # Clear replay state
        self._replay_history = None
        self._replay_move_index = 0
        self._is_replay_mode = False

        # Clear game
        self._game = None
        self._display.set_game(None)
        self._display.set_show_all_cards(False)

        # Disable home button
        if hasattr(self._display, '_home_btn'):
            self._display._home_btn.config(state=tk.DISABLED, command=None)

        # Clear canvas completely
        if hasattr(self._display, 'canvas'):
            self._display.canvas.delete("all")

        # Remove replay controls
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
            for widget in status_frame.winfo_children():
                if isinstance(widget, tk.Frame) and hasattr(widget, '_replay_controls'):
                    widget.destroy()

        # Show home screen - this will create/repaint the control frame
        self._show_start_screen()

        # Force a full repaint of the display
        if self._display:
            # Update the canvas frame to ensure it's visible
            if hasattr(self._display, '_canvas_frame'):
                self._display._canvas_frame.update_idletasks()
            # Force root window update to ensure everything is repainted
            self._display.root.update_idletasks()
            self._display.root.update()

    def _reconstruct_game_from_history(self, history_data: dict):
        """Reconstruct game engine from history data."""
        # This method is called on initial load
        # The history data and move index are already set in _load_replay
        # Just update the display to show the current state
        self._update_replay_display()

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

        # Note: Home button is now always visible in status bar, no need to add it here
        # Add separator before replay controls
        separator = tk.Frame(replay_frame, width=2, bg="#5A6B7D")
        separator.pack(side=tk.LEFT, padx=5, fill=tk.Y)

        # Store button references for enabling/disabling
        self._replay_first_btn = tk.Button(
            replay_frame,
            text="⏮ First",
            command=self._replay_first,
            bg="#95A5A6",
            fg="black",
            font=("Arial", 9),
            highlightthickness=0
        )
        self._replay_first_btn.pack(side=tk.LEFT, padx=2)

        self._replay_prev_btn = tk.Button(
            replay_frame,
            text="⏪ Prev",
            command=self._replay_previous,
            bg="#95A5A6",
            fg="black",
            font=("Arial", 9),
            highlightthickness=0
        )
        self._replay_prev_btn.pack(side=tk.LEFT, padx=2)

        self._replay_next_btn = tk.Button(
            replay_frame,
            text="⏩ Next",
            command=self._replay_next,
            bg="#95A5A6",
            fg="black",
            font=("Arial", 9),
            highlightthickness=0
        )
        self._replay_next_btn.pack(side=tk.LEFT, padx=2)

        self._replay_last_btn = tk.Button(
            replay_frame,
            text="⏭ Last",
            command=self._replay_last,
            bg="#95A5A6",
            fg="black",
            font=("Arial", 9),
            highlightthickness=0
        )
        self._replay_last_btn.pack(side=tk.LEFT, padx=2)

        # Update button states
        self._update_replay_button_states()

    def _update_replay_button_states(self):
        """Update replay button states based on current position."""
        if not hasattr(self, '_replay_history') or not self._replay_history:
            return

        moves = self._replay_history.get("moves", [])
        total_moves = len(moves)
        current_index = getattr(self, '_replay_move_index', 0)

        # Disable First and Prev if at start
        # Check if buttons exist and are valid widgets before configuring
        if hasattr(self, '_replay_first_btn') and self._replay_first_btn is not None:
            try:
                self._replay_first_btn.config(state=tk.DISABLED if current_index == 0 else tk.NORMAL)
            except (tk.TclError, AttributeError):
                # Widget was destroyed, clear reference
                self._replay_first_btn = None
        if hasattr(self, '_replay_prev_btn') and self._replay_prev_btn is not None:
            try:
                self._replay_prev_btn.config(state=tk.DISABLED if current_index == 0 else tk.NORMAL)
            except (tk.TclError, AttributeError):
                self._replay_prev_btn = None

        # Disable Next and Last if at end
        if hasattr(self, '_replay_next_btn') and self._replay_next_btn is not None:
            try:
                self._replay_next_btn.config(state=tk.DISABLED if current_index >= total_moves else tk.NORMAL)
            except (tk.TclError, AttributeError):
                self._replay_next_btn = None
        if hasattr(self, '_replay_last_btn') and self._replay_last_btn is not None:
            try:
                self._replay_last_btn.config(state=tk.DISABLED if current_index >= total_moves else tk.NORMAL)
            except (tk.TclError, AttributeError):
                self._replay_last_btn = None

    def _replay_first(self):
        """Go to first move in replay."""
        self._replay_move_index = 0
        self._update_replay_display()
        self._update_replay_button_states()

    def _replay_previous(self):
        """Go to previous move in replay."""
        if self._replay_move_index > 0:
            self._replay_move_index -= 1
            self._update_replay_display()
            self._update_replay_button_states()

    def _replay_next(self):
        """Go to next move in replay."""
        if self._replay_history:
            moves = self._replay_history.get("moves", [])
            if self._replay_move_index < len(moves):
                self._replay_move_index += 1
                self._update_replay_display()
                self._update_replay_button_states()

    def _replay_last(self):
        """Go to last move in replay."""
        if self._replay_history:
            moves = self._replay_history.get("moves", [])
            self._replay_move_index = len(moves)
            self._update_replay_display()
            self._update_replay_button_states()

    def _update_replay_display(self):
        """Update display for replay mode."""
        if not self._replay_history:
            return

        # Clear event history before reconstructing
        if hasattr(self._display, '_event_history'):
            self._display._event_history.clear()
        if hasattr(self._display, '_history_text'):
            self._display._history_text.config(state=tk.NORMAL)
            self._display._history_text.delete("1.0", tk.END)
            self._display._history_text.config(state=tk.DISABLED)

        # Store timestamps for each move if available in history
        # (Currently not stored per-move, so this will be empty)
        # If per-move timestamps are added to history format in the future, they can be used here
        self._display._replay_timestamps = []

        # Store turn numbers for each move (needed to show correct turn in event history)
        moves = self._replay_history.get("moves", [])
        replay_turn_numbers = []
        for i in range(len(moves)):
            # Turn numbers are 1-based, starting from 1 after the first move
            replay_turn_numbers.append(i + 1)
        self._display._replay_turn_numbers = replay_turn_numbers

        # Store player names from history for display
        players_list = self._replay_history.get("players", [])
        self._display._replay_player_names = players_list

        # Reconstruct game from history up to current move index
        from hanabi.core.player import HumanPlayer
        from hanabi.core.game_history import GameHistory

        settings_dict = self._replay_history.get("settings", {})
        num_players = settings_dict.get("num_players", 3)

        # Use HintTrackingPlayer (HumanPlayer extends it) so hints are tracked
        placeholder_players = [HumanPlayer(i) for i in range(num_players)]
        team = PlayerTeam(placeholder_players)

        # Set up move callback to track moves for event history
        moves_applied = []  # Track moves for event history

        def on_move_callback(player_index: int, move: Move, old_state, new_state):
            """Callback to track moves for event history."""
            # Update hint tracking in display (independent of player implementations)
            self._display.update_hints_from_move(player_index, move)
            # Store move info for later display in event history
            moves_applied.append((player_index, move, old_state, new_state))

        # Reconstruct game from history using the saved deck
        self._game = GameHistory.create_game_from_history(self._replay_history, team, on_move=on_move_callback)

        # Apply moves from history up to current index
        moves = self._replay_history.get("moves", [])
        for move_str in moves[:self._replay_move_index]:
            # Get current player (moves are deterministic)
            current_player = self._game.currentPlayer

            # Parse move from short format
            move = GameHistory._short_to_move(move_str, current_player, self._game)
            if move is None:
                logger.warning(f"Replay: Failed to parse move '{move_str}'")
                continue  # Skip invalid moves

            # Get state before move
            old_state = self._game.state

            # Apply the move
            try:
                self._game._processMove(current_player, move)
                # Note: _processMove now calls _notify_players internally
                # Advance to next player's turn (moves are deterministic)
                self._game._advanceTurn()
            except ValueError as e:
                # Move might be invalid at this point in replay
                logger.error(f"Replay: Failed to apply move '{move_str}': {e}")
                # Continue anyway - might be able to recover
                continue

            # Get state after move
            new_state = self._game.state

            # Update hint tracking (callback may have done this, but ensure it's done)
            self._display.update_hints_from_move(current_player, move)

            # Add move to event history
            move_message = self._format_move_message(current_player, move, old_state, new_state)
            # Check if this is an AI player (based on player class names from history)
            players_list = self._replay_history.get("players", [])
            is_ai_player = (current_player < len(players_list) and
                          players_list[current_player] != "GUIPlayer" and
                          players_list[current_player] != "HumanPlayer" and
                          players_list[current_player] != "ConsolePlayer")
            self._display.display_move_result(True, move_message, current_player, is_ai_player)

        # Update display with the reconstructed game state
        self._display.set_game(self._game)
        self._display.set_show_all_cards(True)  # Show all cards in replay

        # Force display update
        # In single player mode, always show human player's view (player 0)
        # In replay mode, we can show any player, but for consistency use player 0 in single player mode
        display_player = 0 if getattr(self, '_one_player_mode', False) else self._game.currentPlayer
        self._display.display_game_state(self._game, display_player)

        # Update status label
        if hasattr(self._display, '_status_label'):
            self._display._status_label.config(
                text=f"Replay: Move {self._replay_move_index}/{len(moves)}"
            )

        # Force GUI update
        self._display.root.update_idletasks()

        # Update replay button states
        self._update_replay_button_states()

    def _toggle_replay_mode(self):
        """Toggle replay mode (if replay is loaded)."""
        if self._is_replay_mode:
            self._display.set_show_all_cards(True)
        else:
            self._display.set_show_all_cards(False)


def play_gui_game():
    """Main entry point for GUI game."""
    import sys
    import os

    # Suppress macOS IMK warning (harmless but annoying)
    # This warning comes from macOS Input Method Kit and doesn't affect functionality
    if sys.platform == "darwin":  # macOS
        # Set environment variable to reduce IMK logging
        os.environ.setdefault("PYTHONUNBUFFERED", "1")
        # Note: The IMKCFRunLoopWakeUpReliable warning is a known macOS/tkinter issue
        # It's harmless and comes from system-level logging, so it can't be easily suppressed
        # without affecting other error messages. It doesn't impact functionality.

        # Enable debug logging if --debug flag is present
        import logging
        if "--debug" in sys.argv or "-d" in sys.argv:
            # Configure logging to output to console (stderr)
            # Use force=True to override any existing configuration
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S',
                force=True,  # Force reconfiguration if already configured
                stream=sys.stderr  # Explicitly use stderr to ensure visibility
            )
            # Set specific loggers to DEBUG level
            logging.getLogger('hanabi.game').setLevel(logging.DEBUG)
            logging.getLogger('hanabi.ai.monte_carlo_player').setLevel(logging.DEBUG)
            # Ensure root logger is at DEBUG
            logging.root.setLevel(logging.DEBUG)
            print("Debug logging enabled. Check console for detailed game state information.", file=sys.stderr)
            print("Monte Carlo player debug logs will show simulation counts and scores per move.", file=sys.stderr)
            # Test that logging works
            test_logger = logging.getLogger('hanabi.ai.monte_carlo_player')
            test_logger.debug("Monte Carlo debug logging is active")

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

