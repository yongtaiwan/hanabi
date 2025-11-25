"""
Tests for GameEngine class.
"""

import unittest
from hanabi.game import create_standard_game_settings
from hanabi.game_engine import GameEngine
from hanabi.moves import Play, Discard, ColorHint, NumberHint
from hanabi.player import HumanPlayer
from hanabi.enums import Color, Number
from hanabi.card import Card


class TestGameEngine(unittest.TestCase):
    """Test cases for GameEngine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.players = [HumanPlayer(i) for i in range(3)]
        self.engine = GameEngine(self.settings, self.players)
        self.engine.initialize()
    
    def test_initialization(self):
        """Test game initialization."""
        self.assertIsNotNone(self.engine.gameState)
        self.assertEqual(self.engine.currentPlayer, 0)
        self.assertEqual(len(self.engine.gameState.playerHands), 3)
        
        # Each player should have 5 cards (for 3 players)
        for hand in self.engine.gameState.playerHands:
            self.assertEqual(len(hand.cards), 5)
        
        # Check initial tokens
        common_view = self.engine.gameState.commonView
        self.assertEqual(common_view.hintTokens, 8)
        self.assertEqual(common_view.liveTokens, 3)
    
    def test_play_valid_card(self):
        """Test playing a valid card."""
        state = self.engine.gameState
        hand = state.playerHands[0]
        
        # Find a card that can be played (a 1 of any color)
        playable_card_index = None
        for i, card in enumerate(hand.cards):
            if card.number == Number.ONE:
                playable_card_index = i
                break
        
        if playable_card_index is not None:
            move = Play(playable_card_index)
            success, msg = self.engine.processMove(0, move)
            self.assertTrue(success)
            self.assertIn("Successfully played", msg)
            
            # Check that card was removed and new card drawn
            new_hand = self.engine.gameState.playerHands[0]
            self.assertEqual(len(new_hand.cards), 5)  # Should still have 5 cards
            
            # Check that card was added to played cards
            cards_played = self.engine.gameState.commonView.cardsPlayed
            self.assertGreater(len(cards_played), 0)
    
    def test_play_invalid_card(self):
        """Test playing an invalid card."""
        state = self.engine.gameState
        hand = state.playerHands[0]
        
        # Find a card that cannot be played (not a 1, or wrong sequence)
        invalid_card_index = None
        for i, card in enumerate(hand.cards):
            if card.number != Number.ONE:
                invalid_card_index = i
                break
        
        if invalid_card_index is not None:
            initial_lives = state.commonView.liveTokens
            move = Play(invalid_card_index)
            success, msg = self.engine.processMove(0, move)
            self.assertTrue(success)  # Move is processed, but card is invalid
            self.assertIn("Invalid play", msg)
            
            # Check that life token was lost
            new_lives = self.engine.gameState.commonView.liveTokens
            self.assertEqual(new_lives, initial_lives - 1)
    
    def test_discard_card(self):
        """Test discarding a card."""
        state = self.engine.gameState
        initial_hint_tokens = state.commonView.hintTokens
        
        # Discard first card
        move = Discard(0)
        success, msg = self.engine.processMove(0, move)
        self.assertTrue(success)
        self.assertIn("Discarded", msg)
        
        # Check that hint token was gained (if not at max)
        new_hint_tokens = self.engine.gameState.commonView.hintTokens
        if initial_hint_tokens < self.settings.maxHintTokens:
            self.assertEqual(new_hint_tokens, initial_hint_tokens + 1)
        
        # Check that card was removed and new card drawn
        new_hand = self.engine.gameState.playerHands[0]
        self.assertEqual(len(new_hand.cards), 5)
    
    def test_color_hint(self):
        """Test giving a color hint."""
        state = self.engine.gameState
        initial_hint_tokens = state.commonView.hintTokens
        
        # Get teammate's hand
        teammate_hand = state.playerHands[1]
        
        # Find a color that exists in teammate's hand
        color_to_hint = None
        matching_indices = []
        for i, card in enumerate(teammate_hand.cards):
            if color_to_hint is None:
                color_to_hint = card.color
            if card.color == color_to_hint:
                matching_indices.append(i)
        
        if color_to_hint and matching_indices:
            move = ColorHint(1, matching_indices, color_to_hint)
            success, msg = self.engine.processMove(0, move)
            self.assertTrue(success)
            self.assertIn("Gave color hint", msg)
            
            # Check that hint token was used
            new_hint_tokens = self.engine.gameState.commonView.hintTokens
            self.assertEqual(new_hint_tokens, initial_hint_tokens - 1)
    
    def test_number_hint(self):
        """Test giving a number hint."""
        state = self.engine.gameState
        initial_hint_tokens = state.commonView.hintTokens
        
        # Get teammate's hand
        teammate_hand = state.playerHands[1]
        
        # Find a number that exists in teammate's hand
        number_to_hint = None
        matching_indices = []
        for i, card in enumerate(teammate_hand.cards):
            if number_to_hint is None:
                number_to_hint = card.number
            if card.number == number_to_hint:
                matching_indices.append(i)
        
        if number_to_hint and matching_indices:
            move = NumberHint(1, matching_indices, number_to_hint)
            success, msg = self.engine.processMove(0, move)
            self.assertTrue(success)
            self.assertIn("Gave number hint", msg)
            
            # Check that hint token was used
            new_hint_tokens = self.engine.gameState.commonView.hintTokens
            self.assertEqual(new_hint_tokens, initial_hint_tokens - 1)
    
    def test_invalid_move_wrong_player(self):
        """Test that wrong player cannot make a move."""
        move = Play(0)
        success, msg = self.engine.processMove(1, move)  # Player 1 tries to move on player 0's turn
        self.assertFalse(success)
        self.assertIn("Not player", msg)
    
    def test_invalid_move_no_hint_tokens(self):
        """Test that hint cannot be given without hint tokens."""
        # Use up all hint tokens
        state = self.engine.gameState
        teammate_hand = state.playerHands[1]
        
        # Find a color to hint
        color_to_hint = teammate_hand.cards[0].color if teammate_hand.cards else None
        matching_indices = [i for i, card in enumerate(teammate_hand.cards) 
                           if card.color == color_to_hint] if color_to_hint else []
        
        if color_to_hint and matching_indices:
            # Use up all hint tokens
            for _ in range(state.commonView.hintTokens):
                move = ColorHint(1, matching_indices, color_to_hint)
                self.engine.processMove(0, move)
                self.engine.advanceTurn()
            
            # Now try to give another hint
            new_state = self.engine.gameState
            if new_state.commonView.hintTokens == 0:
                move = ColorHint(1, matching_indices, color_to_hint)
                success, msg = self.engine.processMove(self.engine.currentPlayer, move)
                self.assertFalse(success)
    
    def test_advance_turn(self):
        """Test turn advancement."""
        initial_player = self.engine.currentPlayer
        self.engine.advanceTurn()
        self.assertEqual(self.engine.currentPlayer, (initial_player + 1) % 3)
    
    def test_deck_exhaustion(self):
        """Test that game handles deck exhaustion correctly."""
        # Play/discard cards until deck is exhausted
        state = self.engine.gameState
        initial_deck_size = state.commonView.cardsToDraw
        
        # Make many moves to exhaust deck
        moves_made = 0
        max_moves = 100  # Safety limit
        
        while not self.engine.isFinished() and moves_made < max_moves:
            current_player = self.engine.currentPlayer
            hand = self.engine.gameState.playerHands[current_player]
            
            if hand.cards:
                # Try to discard
                move = Discard(0)
                success, _ = self.engine.processMove(current_player, move)
                if success:
                    self.engine.advanceTurn()
                    moves_made += 1
                else:
                    break
            else:
                break
        
        # Check that deck exhaustion is tracked
        final_state = self.engine.gameState
        if final_state.commonView.cardsToDraw == 0:
            self.assertTrue(self.engine._deck_exhausted)
    
    def test_game_finished_no_lives(self):
        """Test that game finishes when no lives remain."""
        state = self.engine.gameState
        hand = state.playerHands[0]
        
        # Play invalid cards to lose all lives
        lives_lost = 0
        for i in range(len(hand.cards)):
            if hand.cards[i].number != Number.ONE:
                move = Play(i)
                success, _ = self.engine.processMove(0, move)
                if success:
                    lives_lost += 1
                    if self.engine.gameState.commonView.liveTokens <= 0:
                        break
        
        # Game should be finished if no lives
        if self.engine.gameState.commonView.liveTokens <= 0:
            self.assertTrue(self.engine.isFinished())
    
    def test_score_calculation(self):
        """Test score calculation."""
        # Initial score should be 0
        self.assertEqual(self.engine.getScore(), 0)
        
        # Play some cards and check score increases
        state = self.engine.gameState
        hand = state.playerHands[0]
        
        # Find and play a 1
        for i, card in enumerate(hand.cards):
            if card.number == Number.ONE:
                move = Play(i)
                success, _ = self.engine.processMove(0, move)
                if success:
                    score = self.engine.getScore()
                    self.assertGreater(score, 0)
                    break
    
    def test_hint_shifting_after_play(self):
        """Test that hints shift correctly when a card is played."""
        self.engine.initialize()
        state = self.engine.gameState
        
        # Manually set up hints:
        # Index 3: number=1 hint
        # Index 4: color=YELLOW hint
        self.engine._player_hints[0] = {
            3: {"color": None, "number": Number.ONE},
            4: {"color": Color.YELLOW, "number": None}
        }
        
        hints_before = self.engine.getPlayerHints(0)
        self.assertIn(3, hints_before)
        self.assertIn(4, hints_before)
        
        # Play card at index 4
        move = Play(4)
        success, msg = self.engine.processMove(0, move)
        self.assertTrue(success, f"Play failed: {msg}")
        
        hints_after = self.engine.getPlayerHints(0)
        
        # New card at index 0 should have no hints
        if 0 in hints_after:
            hint_0 = hints_after[0]
            self.assertIsNone(hint_0.get("color"), 
                            "New card at index 0 should have no color hint")
            self.assertIsNone(hint_0.get("number"),
                            "New card at index 0 should have no number hint")
        
        # Card at new index 4 should have number=1 hint (from old index 3), NOT yellow
        self.assertIn(4, hints_after, "Card from old index 3 should now be at index 4")
        hint_4 = hints_after[4]
        self.assertEqual(hint_4.get("number"), Number.ONE,
                        "Card at new index 4 should have number=1 hint")
        self.assertIsNone(hint_4.get("color"),
                         "Card at new index 4 should NOT have color hint (yellow hint was on played card)")
    
    def test_hint_shifting_with_multiple_hints(self):
        """Test hint shifting when multiple cards have the same hint."""
        self.engine.initialize()
        
        # Set up: multiple cards with yellow hint
        # Index 2: yellow hint
        # Index 3: number=1 hint
        # Index 4: yellow hint (to be played)
        self.engine._player_hints[0] = {
            2: {"color": Color.YELLOW, "number": None},
            3: {"color": None, "number": Number.ONE},
            4: {"color": Color.YELLOW, "number": None}
        }
        
        # Play card at index 4
        move = Play(4)
        success, msg = self.engine.processMove(0, move)
        self.assertTrue(success, f"Play failed: {msg}")
        
        hints_after = self.engine.getPlayerHints(0)
        
        # Index 3 should have yellow hint (from old index 2)
        self.assertIn(3, hints_after)
        self.assertEqual(hints_after[3].get("color"), Color.YELLOW,
                        "Index 3 should have yellow hint from old index 2")
        
        # Index 4 should have number=1 hint (from old index 3), NOT yellow
        self.assertIn(4, hints_after)
        hint_4 = hints_after[4]
        self.assertEqual(hint_4.get("number"), Number.ONE,
                        "Index 4 should have number=1 hint from old index 3")
        self.assertIsNone(hint_4.get("color"),
                         "Index 4 should NOT have yellow hint (that was on the played card)")


if __name__ == '__main__':
    unittest.main()

