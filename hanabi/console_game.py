"""
Main entry point for console-based Hanabi game.
"""

from typing import List
from .game import create_standard_game_settings
from .game_engine import GameEngine
from .console_display import ConsoleDisplay
from .console_input import ConsoleInput
from .game_history import GameHistory
from .player import HumanPlayer


def play_console_game(num_players: int = None) -> None:
    """
    Play a console-based Hanabi game.
    
    Args:
        num_players: Number of players (2-5). If None, prompts for input.
    """
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
    
    # Create players
    players: List[HumanPlayer] = []
    for i in range(num_players):
        players.append(HumanPlayer(i))
    
    # Initialize game engine
    engine = GameEngine(settings, players)
    engine.initialize()
    
    # Initialize display and input
    display = ConsoleDisplay(use_colors=True)
    input_parser = ConsoleInput(engine)
    
    # Initialize game history
    history = GameHistory({
        "num_players": num_players,
        "max_live_tokens": settings.maxLiveTokens,
        "max_hint_tokens": settings.maxHintTokens,
        "max_cards_in_hand": settings.maxCardsInHand
    })
    history.record_initial_state(engine)
    
    # Game loop
    from .console_display import Colors
    print(f"\n{Colors.BRIGHT_CYAN}Welcome to Hanabi!{Colors.RESET}")
    print("=" * 70)
    
    # Clear screen before showing player 1's first turn
    display.clear_screen()
    
    while not engine.isFinished():
        current_player = engine.currentPlayer
        
        # Display game state
        display.display_game_state(engine, current_player)
        
        # Display available moves
        display.display_available_moves(engine, current_player)
        
        # Get player input
        move = None
        error_msg = None
        
        while move is None:
            display.display_prompt(current_player)
            user_input = input().strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                from .console_display import Colors
                print(f"\n{Colors.BRIGHT_YELLOW}Game quit by player.{Colors.RESET}")
                return
            
            move, error_msg = input_parser.parse_move(current_player, user_input)
            
            if move is None:
                from .console_display import Colors
                print(f"{Colors.BRIGHT_RED}Error: {error_msg}{Colors.RESET}")
                print(f"{Colors.BRIGHT_BLACK}Please try again.{Colors.RESET}\n")
        
        # Process the move
        success, result_msg = engine.processMove(current_player, move)
        
        # Display result
        display.display_move_result(success, result_msg)
        
        # If move failed, ask user to retry (loop back to input)
        if not success:
            from .console_display import Colors
            print(f"{Colors.BRIGHT_BLACK}Please try again.{Colors.RESET}\n")
            continue  # Go back to the start of the loop to ask for input again
        
        # Record move in history (only successful moves)
        history.record_move(current_player, move, result_msg, engine)
        
        # Advance to next turn (only if successful)
        engine.advanceTurn()
        
        # Pause before next turn (only if game is not finished)
        if not engine.isFinished():
            from .console_display import Colors
            input(f"{Colors.BRIGHT_BLACK}Press Enter to continue to next turn...{Colors.RESET}")
            display.clear_screen()
    
    # Game finished
    display.display_game_end(engine)
    
    # Save game history (now in YAML format)
    from .console_display import Colors
    history_file = history.save_to_file()
    print(f"{Colors.BRIGHT_CYAN}Game history saved to: {Colors.BRIGHT_WHITE}{history_file}{Colors.RESET}")
    print(f"{Colors.BRIGHT_BLACK}You can use this file to replay the game later.{Colors.RESET}")


if __name__ == "__main__":
    play_console_game()

