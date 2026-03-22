"""
Console Player implementation for Hanabi game.
"""

from typing import Optional
from hanabi.core.player import HumanPlayer
from hanabi.core.game import PlayerView, Game
from hanabi.core.moves import Move
from .console_input import ConsoleInput
from .console_display import ConsoleDisplay


class ConsolePlayer(HumanPlayer):
    """Human player for console that gets moves from console input and updates display."""

    def __init__(self, player_index: int, game: Game, display: ConsoleDisplay, input_parser: ConsoleInput):
        """
        Initialize a console player.

        Args:
            player_index: The index of this player
            game: The game instance
            display: Console display for showing game state
            input_parser: ConsoleInput parser for parsing moves
        """
        super().__init__(player_index)
        self._game = game
        self._display = display
        self._input_parser = input_parser

    def play(self, player_view: PlayerView) -> Move:
        """
        Get a move from console input (displays game state first).

        Args:
            player_view: The current view of the game

        Returns:
            The move to make
        """
        # Display game state
        self._display.display_game_state(self._game, self.player_index)

        # Display available moves
        self._display.display_available_moves(self._game, self.player_index)

        # Get input from user (with retry loop for invalid input)
        while True:
            self._display.display_prompt(self.player_index)
            user_input = input().strip()

            if user_input.lower() in ["quit", "exit", "q"]:
                from .console_display import Colors

                print(f"\n{Colors.BRIGHT_YELLOW}Game quit by player.{Colors.RESET}")
                raise KeyboardInterrupt("Game quit by player")

            # Parse the move
            move, error_msg = self._input_parser.parse_move(self.player_index, user_input)

            if move is None:
                # Invalid input format - show error and retry
                from .console_display import Colors

                print(f"{Colors.BRIGHT_RED}Error: {error_msg}{Colors.RESET}")
                print(f"{Colors.BRIGHT_BLACK}Please try again.{Colors.RESET}\n")
                continue

            # Validate the move against game state
            if not self._game.state._validate(self.player_index, move):
                # Invalid move according to game rules - show error and retry
                from .console_display import Colors

                error_msg = self._game.state._get_validation_error_message(
                    self.player_index, move
                )
                print(f"{Colors.BRIGHT_RED}Invalid move: {error_msg}{Colors.RESET}")
                print(f"{Colors.BRIGHT_BLACK}Please try again.{Colors.RESET}\n")
                continue

            return move
