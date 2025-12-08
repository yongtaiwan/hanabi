"""
Test to catch the hint message bug where player numbers are displayed incorrectly.
"""

import unittest
from hanabi.core.game import create_standard_game_settings
from hanabi.core.game import Game as GameEngine
from hanabi.console.console_input import ConsoleInput
from hanabi.core.player import HumanPlayer
from hanabi.core.moves import NumberHint, ColorHint


class TestHintBug(unittest.TestCase):
    """Test to catch hint message bugs."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.players = [HumanPlayer(i) for i in range(3)]
        self.engine = GameEngine(self.settings, self.players)
        self.engine.initialize()
        self.input_parser = ConsoleInput(self.engine)
    
    def test_hint_message_player_number(self):
        """Test that hint messages show correct player numbers (1-indexed for display)."""
        state = self.engine.gameState
        teammate_hand = state.playerHands[1]  # Player 2 (0-indexed: 1)
        
        if teammate_hand.cards and state.commonView.hintTokens > 0:
            number = teammate_hand.cards[0].number
            matching_indices = [i for i, card in enumerate(teammate_hand.cards) 
                               if card.number == number]
            if matching_indices:
                # Give hint to player 2 (index 1)
                move = NumberHint(1, matching_indices, number)
                success, msg = self.engine.processMove(0, move)
                
                if success:
                    # Message should say "player 2" (1-indexed), not "player 1"
                    # The bug was showing "player 1" when it should show "player 2"
                    self.assertIn("player 2", msg.lower(), 
                                f"Message should mention 'player 2' but got: {msg}")
    
    def test_console_input_hint_parsing(self):
        """Test that console input correctly parses player numbers."""
        state = self.engine.gameState
        teammate_hand = state.playerHands[1]  # Player 2
        
        if teammate_hand.cards:
            number = teammate_hand.cards[0].number
            
            # User enters "hint 2 number X" (1-indexed)
            move, error = self.input_parser.parse_move(0, f"hint 2 number {number.value}")
            
            self.assertIsNotNone(move, f"Move should be parsed, error: {error}")
            self.assertIsNone(error)
            self.assertIsInstance(move, NumberHint)
            # Should be player index 1 (0-indexed), which is player 2 (1-indexed)
            self.assertEqual(move.teammate, 1, 
                           "Teammate should be index 1 (player 2 in 1-indexed)")
    
    def test_hint_message_consistency(self):
        """Test that hint messages are consistent with input."""
        state = self.engine.gameState
        
        # Test with player 2 (index 1)
        if state.commonView.hintTokens > 0:
            teammate_hand = state.playerHands[1]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                
                if matching:
                    # Parse input "hint 2 color RED" (1-indexed)
                    move, error = self.input_parser.parse_move(0, f"hint 2 color {color.name}")
                    
                    if move and not error:
                        # Process the move
                        success, msg = self.engine.processMove(0, move)
                        
                        if success:
                            # Message should say "player 2" since input was "hint 2"
                            # Check that message mentions the correct player
                            self.assertIn("player 2", msg.lower() or "player 1", 
                                        f"Expected message about player 2, got: {msg}")


if __name__ == '__main__':
    unittest.main()

