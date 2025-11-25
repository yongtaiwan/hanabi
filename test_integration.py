"""
Integration tests for the full game flow.
"""

import unittest
from hanabi.game import create_standard_game_settings
from hanabi.game_engine import GameEngine
from hanabi.console_input import ConsoleInput
from hanabi.game_history import GameHistory
from hanabi.player import HumanPlayer
from hanabi.moves import Play, Discard


class TestIntegration(unittest.TestCase):
    """Integration tests for complete game flow."""
    
    def test_full_game_flow(self):
        """Test a complete game flow with multiple moves."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()
        
        history = GameHistory({
            "num_players": 2,
            "max_live_tokens": 3,
            "max_hint_tokens": 8
        })
        history.record_initial_state(engine)
        
        input_parser = ConsoleInput(engine)
        
        # Make several moves
        moves_made = 0
        max_moves = 10
        
        while not engine.isFinished() and moves_made < max_moves:
            current_player = engine.currentPlayer
            state = engine.gameState
            hand = state.playerHands[current_player]
            
            if not hand.cards:
                break
            
            # Try to make a move
            if state.commonView.hintTokens > 0:
                # Try a hint
                teammate = 1 if current_player == 0 else 0
                teammate_hand = state.playerHands[teammate]
                if teammate_hand.cards:
                    color = teammate_hand.cards[0].color
                    matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                    if matching:
                        from hanabi.moves import ColorHint
                        move = ColorHint(teammate, matching, color)
                        success, msg = engine.processMove(current_player, move)
                        if success:
                            history.record_move(current_player, move, msg, engine)
                            engine.advanceTurn()
                            moves_made += 1
                            continue
            
            # Otherwise discard
            move = Discard(0)
            success, msg = engine.processMove(current_player, move)
            if success:
                history.record_move(current_player, move, msg, engine)
                engine.advanceTurn()
                moves_made += 1
            else:
                break
        
        # Verify game state is consistent
        self.assertIsNotNone(engine.gameState)
        self.assertGreaterEqual(moves_made, 1)
        
        # Save history
        filename = history.save_to_file()
        self.assertTrue(filename.endswith('.json'))
        
        # Clean up
        import os
        if os.path.exists(filename):
            os.remove(filename)
    
    def test_player_view_consistency(self):
        """Test that player views are consistent."""
        settings = create_standard_game_settings(3)
        players = [HumanPlayer(i) for i in range(3)]
        engine = GameEngine(settings, players)
        engine.initialize()
        
        # Get views for all players
        views = []
        for i in range(3):
            view = engine.getPlayerView(i)
            views.append(view)
        
        # Each player should see other players' hands
        for player_idx, view in enumerate(views):
            self.assertEqual(len(view.teammates), 2)  # Should see 2 other players
            for teammate_idx in view.teammates:
                self.assertNotEqual(teammate_idx, player_idx)
    
    def test_turn_rotation(self):
        """Test that turns rotate correctly."""
        settings = create_standard_game_settings(3)
        players = [HumanPlayer(i) for i in range(3)]
        engine = GameEngine(settings, players)
        engine.initialize()
        
        # Make a move and advance
        move = Discard(0)
        engine.processMove(0, move)
        engine.advanceTurn()
        self.assertEqual(engine.currentPlayer, 1)
        
        engine.processMove(1, Discard(0))
        engine.advanceTurn()
        self.assertEqual(engine.currentPlayer, 2)
        
        engine.processMove(2, Discard(0))
        engine.advanceTurn()
        self.assertEqual(engine.currentPlayer, 0)  # Should wrap around


if __name__ == '__main__':
    unittest.main()

