"""
Main entry point for console-based Hanabi game.
"""

import sys
import logging
from typing import List
from hanabi.core.game import create_standard_game_settings, Game
from hanabi.core.player import PlayerTeam
from .console_display import ConsoleDisplay
from .console_input import ConsoleInput
from .console_player import ConsolePlayer
from hanabi.core.game_history import GameHistory


def play_console_game(num_players: int = None, one_player_mode: bool = None) -> None:
    """
    Play a console-based Hanabi game.

    Args:
        num_players: Number of players (2-5). If None, prompts for input.
        one_player_mode: If True, enables 1-player mode (1 human + AI players).
                         If None, prompts for input.
    """
    # Enable debug logging if --debug flag is present
    if "--debug" in sys.argv or "-d" in sys.argv:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        logging.getLogger('hanabi.game').setLevel(logging.DEBUG)
        print("Debug logging enabled. Check console for detailed game state information.")

    # Check if 1-player mode
    if one_player_mode is None:
        while True:
            response = input("Play in 1-player mode? (y/n): ").strip().lower()
            if response in ['y', 'yes']:
                one_player_mode = True
                break
            elif response in ['n', 'no']:
                one_player_mode = False
                break
            else:
                print("Please enter 'y' or 'n'.")

    # Get number of players
    if num_players is None:
        if one_player_mode:
            while True:
                try:
                    num_players = int(input("Enter total number of players (2-5): "))
                    if 2 <= num_players <= 5:
                        break
                    else:
                        print("Number of players must be between 2 and 5.")
                except ValueError:
                    print("Please enter a valid number.")
        else:
            while True:
                try:
                    num_players = int(input("Enter number of players (2-5): "))
                    if 2 <= num_players <= 5:
                        break
                    else:
                        print("Number of players must be between 2 and 5.")
                except ValueError:
                    print("Please enter a valid number.")

    # Create game settings
    settings = create_standard_game_settings(num_players)

    # Initialize display
    display = ConsoleDisplay(use_colors=True)
    display.clear_screen()
    display.clear_previous_round_moves()  # Initialize move tracking

    # Initialize game history (before creating game so callback can use it)
    history = GameHistory({
        "num_players": num_players,
        "max_live_tokens": settings.maxLiveTokens,
        "max_hint_tokens": settings.maxHintTokens,
        "max_cards_in_hand": settings.maxCardsInHand
    })

    # Create game (will create players inside)
    # First create placeholder players, then replace with ConsolePlayers
    from hanabi.core.player import HumanPlayer
    placeholder_players = [HumanPlayer(i) for i in range(num_players)]
    team = PlayerTeam(placeholder_players)

    # Set up move callback for display updates
    def on_move_callback(player_index: int, move, old_state, new_state):
        """Callback to update display when a move is made."""
        from .console_display import Colors

        # Record the move for previous round display
        # Use old_state.turnNumber + 1 because the move was made at that turn
        # (old_state has turn N, move is made, new_state has turn N+1)
        move_turn_number = old_state.turnNumber + 1
        display.record_move(player_index, move, move_turn_number)

        # Record move in history (using closure to access history and game)
        if history and game:
            # Format a simple result message for history (not used in new format, but kept for compatibility)
            result_msg = f"Player {player_index} made move: {move}"
            history.record_move(player_index, move, result_msg, game)

        # Check if this is an AI player (in 1-player mode, player 0 is human, rest are AI)
        is_ai_player = one_player_mode and player_index > 0

        if is_ai_player:
            # Show AI move
            print(f"\n{Colors.BRIGHT_MAGENTA}Player {player_index} (AI) made move: {move}{Colors.RESET}")

        # Only update display if it's not the current player's turn (to avoid double display)
        # The display will be shown in play() when it's the player's turn
        if player_index != new_state.currentPlayer:
            # Update display to show the new game state
            display.display_game_state(game, game.currentPlayer)

            # Pause before next turn (only if game not finished)
            if not game.isFinished:
                input(f"{Colors.BRIGHT_BLACK}Press Enter to continue to next turn...{Colors.RESET}")
                display.clear_screen()

    game = Game.create(team, settings, on_move=on_move_callback)

    # Create players: 1 ConsolePlayer (human) + rest as RandomPlayers (AI)
    players = []
    if one_player_mode:
        # 1-player mode: first player is human, rest are AI
        from hanabi.ai import RandomPlayer

        # Create human player (player 0)
        input_parser = ConsoleInput(game, 0)
        console_player = ConsolePlayer(0, game, display, input_parser)
        players.append(console_player)

        # Create AI players (players 1 to num_players-1)
        for i in range(1, num_players):
            ai_player = RandomPlayer(i, game)
            players.append(ai_player)
    else:
        # Multi-player mode: all players are human
        for i in range(num_players):
            input_parser = ConsoleInput(game, i)
            console_player = ConsolePlayer(i, game, display, input_parser)
            players.append(console_player)

    # Update team with players
    game._team = PlayerTeam(players)

    # Update common view for all players
    common_view = game.state.commonView
    for player in players:
        player.set_common_view(common_view)

    # Record initial state in history (after game is fully set up)
    history.record_initial_state(game)

    # Welcome message
    from .console_display import Colors
    print(f"\n{Colors.BRIGHT_CYAN}Welcome to Hanabi!{Colors.RESET}")
    if one_player_mode:
        print(f"{Colors.BRIGHT_GREEN}Playing in 1-player mode with {num_players - 1} AI player(s){Colors.RESET}")
    print("=" * 70)

    # Play the game (game loop is handled by Game.play())
    try:
        game.play()
    except KeyboardInterrupt:
        from .console_display import Colors
        print(f"\n{Colors.BRIGHT_YELLOW}Game quit by player.{Colors.RESET}")
        return
    except RuntimeError as e:
        # Game ended due to invalid move or player error
        from .console_display import Colors
        print(f"\n{Colors.BRIGHT_RED}Game ended: {e}{Colors.RESET}")
        return

    # Game finished - display game end
    display.display_game_end(game)

    # Save game history with final score
    from .console_display import Colors
    final_score = game.getScore()
    history.record_final_score(game)
    history_file = history.save_to_file(final_score=final_score)
    print(f"{Colors.BRIGHT_CYAN}Game history saved to: {Colors.BRIGHT_WHITE}{history_file}{Colors.RESET}")
    print(f"{Colors.BRIGHT_BLACK}You can use this file to replay the game later.{Colors.RESET}")


if __name__ == "__main__":
    play_console_game()

