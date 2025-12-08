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


def play_console_game(num_players: int = None) -> None:
    """
    Play a console-based Hanabi game.

    Args:
        num_players: Number of players (2-5). If None, prompts for input.
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
    # Get number of players
    if num_players is None:
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

    # Create game (will create players inside)
    # First create placeholder players, then replace with ConsolePlayers
    from hanabi.core.player import HumanPlayer
    placeholder_players = [HumanPlayer(i) for i in range(num_players)]
    team = PlayerTeam(placeholder_players)

    # Set up move callback for display updates
    def on_move_callback(player_index: int, move, old_state, new_state):
        """Callback to update display when a move is made."""
        # Only update display if it's not the current player's turn (to avoid double display)
        # The display will be shown in play() when it's the player's turn
        if player_index != new_state.currentPlayer:
            # Update display to show the new game state
            display.display_game_state(game, game.currentPlayer)

            # Pause before next turn (only if game not finished)
            if not game.isFinished:
                from .console_display import Colors
                input(f"{Colors.BRIGHT_BLACK}Press Enter to continue to next turn...{Colors.RESET}")
                display.clear_screen()

    game = Game.create(team, settings, on_move=on_move_callback)

    # Replace players with ConsolePlayers that have display and input
    console_players = []
    for i in range(num_players):
        input_parser = ConsoleInput(game, i)
        console_player = ConsolePlayer(i, game, display, input_parser)
        console_players.append(console_player)

    # Update team with console players
    game._team = PlayerTeam(console_players)

    # Update common view for new players
    common_view = game.state.commonView
    for player in console_players:
        player.set_common_view(common_view)

    # Initialize game history
    history = GameHistory({
        "num_players": num_players,
        "max_live_tokens": settings.maxLiveTokens,
        "max_hint_tokens": settings.maxHintTokens,
        "max_cards_in_hand": settings.maxCardsInHand
    })
    # Note: history recording will need to be updated to work with Game instead of GameEngine
    # For now, we'll skip it or update it later

    # Welcome message
    from .console_display import Colors
    print(f"\n{Colors.BRIGHT_CYAN}Welcome to Hanabi!{Colors.RESET}")
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

    # Save game history
    from .console_display import Colors
    # history_file = history.save_to_file()
    # print(f"{Colors.BRIGHT_CYAN}Game history saved to: {Colors.BRIGHT_WHITE}{history_file}{Colors.RESET}")
    # print(f"{Colors.BRIGHT_BLACK}You can use this file to replay the game later.{Colors.RESET}")


if __name__ == "__main__":
    play_console_game()

