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
            level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        )
        logging.getLogger("hanabi.game").setLevel(logging.DEBUG)
        print("Debug logging enabled. Check console for detailed game state information.")

    # Check if 1-player mode
    if one_player_mode is None:
        while True:
            response = input("Play in 1-player mode? (y/n): ").strip().lower()
            if response in ["y", "yes"]:
                one_player_mode = True
                break
            elif response in ["n", "no"]:
                one_player_mode = False
                break
            else:
                print("Please enter 'y' or 'n'.")

    # Get number of players (before AI selection so we can filter by game settings)
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

    # Get AI player type if in 1-player mode (options depend on player count)
    ai_player_type = None
    if one_player_mode:
        from hanabi.ai import RandomPlayer, CommonSensePlayer, RecommendationPlayer
        from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig

        # Full-state benchmark bots (e.g. CommonSenseCheater) are registered only in run_ai_experiments.py.

        # For interactive play, use fast config for MonteCarlo
        def create_monte_carlo_player(player_index: int) -> MonteCarloPlayer:
            config = MonteCarloConfig(
                min_think_time_s=0.3,  # 300ms
                max_think_time_s=0.5,  # 500ms
                min_simulations=2,
                max_simulations=50,
            )
            return MonteCarloPlayer(player_index, config=config)

        option_list = [
            ("Random", RandomPlayer, RandomPlayer),
            ("CommonSense", CommonSensePlayer, CommonSensePlayer),
            ("Recommendation", RecommendationPlayer, RecommendationPlayer),
            ("MonteCarlo", create_monte_carlo_player, MonteCarloPlayer),
        ]
        ai_types = [
            (name, factory)
            for name, factory, support_cls in option_list
            if support_cls.supports_game_settings(settings)
        ]

        print("\nSelect AI player type:")
        for i, (name, _) in enumerate(ai_types, 1):
            print(f"  {i}. {name}")

        n_choices = len(ai_types)
        while True:
            choice = input(f"Enter choice (1-{n_choices}): ").strip()
            try:
                idx = int(choice)
                if 1 <= idx <= n_choices:
                    ai_player_type = ai_types[idx - 1][1]
                    print(f"Selected: {ai_types[idx - 1][0]}")
                    break
            except ValueError:
                pass
            print(f"Please enter a number from 1 to {n_choices}.")

    # Initialize display
    display = ConsoleDisplay(use_colors=True)
    display.clear_screen()
    display.clear_previous_round_moves()  # Initialize move tracking

    # Initialize game history (before creating game so callback can use it)
    history = GameHistory(
        {
            "num_players": num_players,
            "max_live_tokens": settings.max_live_tokens,
            "max_hint_tokens": settings.max_hint_tokens,
            "max_cards_in_hand": settings.max_cards_in_hand,
        }
    )

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
        # Use old_state.turn_number + 1 because the move was made at that turn
        # (old_state has turn N, move is made, new_state has turn N+1)
        move_turn_number = old_state.turn_number + 1
        display.record_move(player_index, move, move_turn_number)

        # Record move in history (using closure to access history and game)
        if history and game:
            # Format a simple result message for history (not used in new format, but kept for compatibility)
            result_msg = f"Player {player_index} made move: {move}"
            history.record_move(player_index, move, result_msg, game)

        # Format and print move message (same format as Game Events, with color coding)
        # Format: "[HH:MM:SS T##] P1 plays red 1." or "[HH:MM:SS T##] P1 hints P2: white at 2, 4, 5"
        from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
        from datetime import datetime

        # Get timestamp and turn number
        timestamp = datetime.now().strftime("%H:%M:%S")
        turn_number = move_turn_number  # Already calculated above

        # Get the move message in the same format as Game Events
        if isinstance(move, Play):
            state = old_state if old_state else game.state
            if state and player_index < len(state.player_hands):
                card = state.player_hands[player_index].cards[move.card]
                move_msg = f"P{player_index + 1} plays {card.color.name.lower()} {card.number.value}."
            else:
                move_msg = f"P{player_index + 1} plays card {move.card + 1}."
        elif isinstance(move, Discard):
            state = old_state if old_state else game.state
            if state and player_index < len(state.player_hands):
                card = state.player_hands[player_index].cards[move.card]
                move_msg = f"P{player_index + 1} discards {card.color.name.lower()} {card.number.value}."
            else:
                move_msg = f"P{player_index + 1} discards card {move.card + 1}."
        elif isinstance(move, NumberHint):
            indices_str = ", ".join(str(c + 1) for c in move.cards)
            move_msg = f"P{player_index + 1} hints P{move.teammate + 1}: {move.number.value} at {indices_str}"
        elif isinstance(move, ColorHint):
            indices_str = ", ".join(str(c + 1) for c in move.cards)
            move_msg = f"P{player_index + 1} hints P{move.teammate + 1}: {move.color.name.lower()} at {indices_str}"
        else:
            assert False, f"unexpected move type in move message: {type(move)}"

        # Format with timestamp and turn number: "[HH:MM:SS T##] message"
        formatted_msg = f"[{timestamp} T{turn_number:02d}] {move_msg}"

        # Colorize the message using console display's colorize method
        colored_msg = display._colorize_message(formatted_msg)
        print(colored_msg)

        # Print decision summary
        player = game.team.players[player_index]
        if hasattr(player, "get_decision_summary"):
            summary = player.get_decision_summary()
            if summary:
                # Get player class name for display
                player_class_name = player.__class__.__name__
                print(f"{player_class_name}: {summary}")

        # Only update display if it's not the current player's turn (to avoid double display)
        # The display will be shown in play() when it's the player's turn
        if player_index != new_state.current_player:
            # Update display to show the new game state
            display.display_game_state(game, game.current_player)

            # Pause before next turn (only if game not finished)
            if not game.is_finished:
                input(f"{Colors.BRIGHT_BLACK}Press Enter to continue to next turn...{Colors.RESET}")
                display.clear_screen()

    game = Game.create(team, settings, on_move=on_move_callback)

    # Create players: 1 ConsolePlayer (human) + rest as AI players
    players = []
    if one_player_mode:
        # 1-player mode: first player is human, rest are AI
        # ai_player_type should be set above
        if ai_player_type is None:
            from hanabi.ai import RandomPlayer

            ai_player_type = RandomPlayer  # Default fallback

        # Create human player (player 0)
        input_parser = ConsoleInput(game, 0)
        console_player = ConsolePlayer(0, game, display, input_parser)
        players.append(console_player)

        # Create AI players (players 1 to num_players-1)
        for i in range(1, num_players):
            ai_player = ai_player_type(i)
            players.append(ai_player)
    else:
        # Multi-player mode: all players are human
        for i in range(num_players):
            input_parser = ConsoleInput(game, i)
            console_player = ConsolePlayer(i, game, display, input_parser)
            players.append(console_player)

    # Update team with players
    game._team = PlayerTeam(players)

    # Set game settings and common view for all players
    common_view = game.state.common_view
    for player in players:
        player.set_game_settings(settings)
        player.set_common_view(common_view)

    # Record initial state in history (after game is fully set up)
    history.record_initial_state(game)

    # Welcome message
    from .console_display import Colors

    print(f"\n{Colors.BRIGHT_CYAN}Welcome to Hanabi!{Colors.RESET}")
    if one_player_mode:
        ai_type_name = ai_player_type.__name__ if ai_player_type else "Random"
        print(
            f"{Colors.BRIGHT_GREEN}Playing in 1-player mode with {num_players - 1} "
            f"{ai_type_name} AI player(s){Colors.RESET}"
        )
    print("=" * 70)

    # Play the game (game loop is handled by Game.play())
    # Let AssertionError propagate (fail fast on bugs)
    # Only catch KeyboardInterrupt for user cancellation
    try:
        game.play()
    except KeyboardInterrupt:
        from .console_display import Colors

        print(f"\n{Colors.BRIGHT_YELLOW}Game quit by player.{Colors.RESET}")
        return

    # Game finished - display game end
    display.display_game_end(game)

    # Save game history with final score
    from .console_display import Colors

    final_score = game.get_score()
    history.record_final_score(game)
    history_file = history.save_to_file(final_score=final_score)
    print(f"{Colors.BRIGHT_CYAN}Game history saved to: {Colors.BRIGHT_WHITE}{history_file}{Colors.RESET}")
    print(f"{Colors.BRIGHT_BLACK}You can use this file to replay the game later.{Colors.RESET}")


if __name__ == "__main__":
    play_console_game()
