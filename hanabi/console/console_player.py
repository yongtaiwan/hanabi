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

    def __init__(
        self,
        player_index: int,
        game: Game,
        display: ConsoleDisplay,
        input_parser: ConsoleInput
    ):
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
        self._display.display_game_state(self._game, self.playerIndex)

        # Display available moves
        self._display.display_available_moves(self._game, self.playerIndex)

        # Get input from user (with retry loop for invalid input)
        while True:
            self._display.display_prompt(self.playerIndex)
            user_input = input().strip()

            if user_input.lower() in ['quit', 'exit', 'q']:
                from .console_display import Colors
                print(f"\n{Colors.BRIGHT_YELLOW}Game quit by player.{Colors.RESET}")
                raise KeyboardInterrupt("Game quit by player")

            # Parse the move
            move, error_msg = self._input_parser.parse_move(self.playerIndex, user_input)

            if move is None:
                # Invalid input - show error and retry
                from .console_display import Colors
                print(f"{Colors.BRIGHT_RED}Error: {error_msg}{Colors.RESET}")
                print(f"{Colors.BRIGHT_BLACK}Please try again.{Colors.RESET}\n")
                continue

            return move

    def observe(self, player_index: int, move: Move) -> None:
        """
        Observe a move (for player's internal state tracking only).

        Display updates are handled by the global callback in Game, not here.

        Args:
            player_index: Index of the player who made the move
            move: The move that was made
        """
        super().observe(player_index, move)

