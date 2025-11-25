"""
Tests for GameHistory class.
"""

import unittest
import json
import os
import tempfile
from hanabi.game import create_standard_game_settings
from hanabi.game_engine import GameEngine
from hanabi.game_history import GameHistory
from hanabi.player import HumanPlayer
from hanabi.moves import Play, Discard, ColorHint, NumberHint
from hanabi.enums import Color, Number


class TestGameHistory(unittest.TestCase):
    """Test cases for GameHistory."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.players = [HumanPlayer(i) for i in range(3)]
        self.engine = GameEngine(self.settings, self.players)
        self.engine.initialize()
        
        self.history = GameHistory({
            "num_players": 3,
            "max_live_tokens": 3,
            "max_hint_tokens": 8
        })
        self.history.record_initial_state(self.engine)
    
    def test_record_initial_state(self):
        """Test recording initial state."""
        self.assertIsNotNone(self.history._initial_state)
        self.assertEqual(self.history._initial_state["current_player"], 0)
        self.assertEqual(len(self.history._initial_state["player_hands"]), 3)
    
    def test_record_play_move(self):
        """Test recording a play move."""
        state = self.engine.gameState
        hand = state.playerHands[0]
        
        if hand.cards:
            move = Play(0)
            success, msg = self.engine.processMove(0, move)
            if success:
                self.history.record_move(0, move, msg, self.engine)
                self.assertEqual(len(self.history._moves), 1)
                self.assertEqual(self.history._moves[0]["player"], 0)
                self.assertEqual(self.history._moves[0]["move"]["type"], "play")
    
    def test_record_discard_move(self):
        """Test recording a discard move."""
        move = Discard(0)
        success, msg = self.engine.processMove(0, move)
        if success:
            self.history.record_move(0, move, msg, self.engine)
            self.assertEqual(len(self.history._moves), 1)
            self.assertEqual(self.history._moves[0]["move"]["type"], "discard")
    
    def test_record_color_hint(self):
        """Test recording a color hint."""
        state = self.engine.gameState
        teammate_hand = state.playerHands[1]
        
        if teammate_hand.cards and state.commonView.hintTokens > 0:
            color = teammate_hand.cards[0].color
            matching_indices = [i for i, card in enumerate(teammate_hand.cards) 
                               if card.color == color]
            if matching_indices:
                move = ColorHint(1, matching_indices, color)
                success, msg = self.engine.processMove(0, move)
                if success:
                    self.history.record_move(0, move, msg, self.engine)
                    self.assertEqual(len(self.history._moves), 1)
                    self.assertEqual(self.history._moves[0]["move"]["type"], "color_hint")
                    self.assertEqual(self.history._moves[0]["move"]["color"], color.name)
    
    def test_record_number_hint(self):
        """Test recording a number hint."""
        state = self.engine.gameState
        teammate_hand = state.playerHands[1]
        
        if teammate_hand.cards and state.commonView.hintTokens > 0:
            number = teammate_hand.cards[0].number
            matching_indices = [i for i, card in enumerate(teammate_hand.cards) 
                               if card.number == number]
            if matching_indices:
                move = NumberHint(1, matching_indices, number)
                success, msg = self.engine.processMove(0, move)
                if success:
                    self.history.record_move(0, move, msg, self.engine)
                    self.assertEqual(len(self.history._moves), 1)
                    self.assertEqual(self.history._moves[0]["move"]["type"], "number_hint")
                    self.assertEqual(self.history._moves[0]["move"]["number"], number.value)
    
    def test_save_to_file(self):
        """Test saving history to file."""
        # Record a move
        move = Discard(0)
        success, msg = self.engine.processMove(0, move)
        if success:
            self.history.record_move(0, move, msg, self.engine)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_filename = f.name
        
        try:
            filename = self.history.save_to_file(temp_filename)
            self.assertEqual(filename, temp_filename)
            self.assertTrue(os.path.exists(filename))
            
            # Verify file contents
            with open(filename, 'r') as f:
                data = json.load(f)
                self.assertIn("settings", data)
                self.assertIn("moves", data)
                self.assertIn("initial_state", data)
                self.assertEqual(len(data["moves"]), 1)
        finally:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
    
    def test_save_to_file_auto_filename(self):
        """Test saving with auto-generated filename."""
        filename = self.history.save_to_file()
        self.assertIsNotNone(filename)
        self.assertTrue(filename.startswith("hanabi_game_"))
        self.assertTrue(filename.endswith(".json"))
        self.assertTrue(os.path.exists(filename))
        
        # Clean up
        if os.path.exists(filename):
            os.remove(filename)
    
    def test_load_from_file(self):
        """Test loading history from file."""
        # Record and save
        move = Discard(0)
        success, msg = self.engine.processMove(0, move)
        if success:
            self.history.record_move(0, move, msg, self.engine)
        
        filename = self.history.save_to_file()
        
        try:
            # Load it back
            loaded_history = GameHistory({})
            data = loaded_history.load_from_file(filename)
            
            self.assertIn("settings", data)
            self.assertIn("moves", data)
            self.assertIn("initial_state", data)
            self.assertEqual(len(data["moves"]), 1)
        finally:
            if os.path.exists(filename):
                os.remove(filename)


if __name__ == '__main__':
    unittest.main()

