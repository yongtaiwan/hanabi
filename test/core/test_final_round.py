"""
Tests for final round logic - simplified version.
When draw deck becomes empty, each player gets exactly one more turn.
The player who exhausts the deck gets to finish that turn (their final turn).
All other players then get one final turn each.
When it comes back to the player who exhausted the deck, the game ends.
"""

import unittest
from hanabi.core.game import create_standard_game_settings
from hanabi.core.game import Game as GameEngine
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
from hanabi.core.player import HumanPlayer
from hanabi.core.enums import Color, Number


@unittest.skip("Obsolete Game(settings, players) API; rewrite against Game.create / current engine")
class TestFinalRound(unittest.TestCase):
    """Test final round logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.players = [HumanPlayer(i) for i in range(3)]
        self.engine = GameEngine(self.settings, self.players)
        self.engine.initialize()

    def _exhaust_deck(self):
        """Helper to exhaust the deck by discarding/playing until empty."""
        # Keep making moves until deck is exhausted
        # _player_exhausting_deck is set when a move tries to draw from an empty deck
        while self.engine._player_exhausting_deck is None:
            if len(self.engine._draw_deck) == 0:
                # Deck is empty, but we need to make one more move to trigger exhaustion
                # Make a move that will try to draw
                current = self.engine.currentPlayer
                hand = self.engine.gameState.playerHands[current]
                if hand.cards:
                    if self.engine.gameState.commonView.hintTokens < self.settings.maxHintTokens:
                        move = Discard(0)
                    else:
                        move = Play(0)
                    success, _ = self.engine.processMove(current, move)
                    if success:
                        # Now _player_exhausting_deck should be set
                        break
                break

            current = self.engine.currentPlayer
            hand = self.engine.gameState.playerHands[current]
            if hand.cards and self.engine.gameState.commonView.hintTokens < self.settings.maxHintTokens:
                move = Discard(0)
                success, _ = self.engine.processMove(current, move)
                if success:
                    # Check if deck was exhausted (before advancing turn)
                    if self.engine._player_exhausting_deck is not None:
                        return  # Deck exhausted during this move
                    self.engine.advanceTurn()
                else:
                    break
            elif hand.cards:
                # Can't discard, try playing
                move = Play(0)
                success, _ = self.engine.processMove(current, move)
                if success:
                    # Check if deck was exhausted (before advancing turn)
                    if self.engine._player_exhausting_deck is not None:
                        return  # Deck exhausted during this move
                    self.engine.advanceTurn()
                else:
                    break
            else:
                break

    def test_deck_exhaustion_sets_player_exhausting_deck(self):
        """Test that when deck becomes empty, _player_exhausting_deck is set."""
        # Exhaust the deck
        self._exhaust_deck()

        # _player_exhausting_deck should be set to the player who exhausted it
        self.assertIsNotNone(self.engine._player_exhausting_deck,
                           "Player exhausting deck should be set")
        self.assertIsInstance(self.engine._player_exhausting_deck, int)
        self.assertGreaterEqual(self.engine._player_exhausting_deck, 0)
        self.assertLess(self.engine._player_exhausting_deck, 3)

    def test_player_exhausting_deck_cannot_move_again(self):
        """Test that the player who exhausted the deck cannot make another move."""
        # Exhaust deck
        self._exhaust_deck()

        player_exhausting = self.engine._player_exhausting_deck
        self.assertIsNotNone(player_exhausting)

        # That player finishes their turn (already done when exhausting)
        # Advance to next players
        for _ in range(3):
            self.engine.advanceTurn()
            if self.engine.currentPlayer == player_exhausting:
                break

        # Now it's back to the player who exhausted the deck
        self.assertEqual(self.engine.currentPlayer, player_exhausting)

        # They should not be able to make a move
        hand = self.engine.gameState.playerHands[player_exhausting]
        if hand.cards:
            move = Discard(0)
            success, msg = self.engine.processMove(player_exhausting, move)
            self.assertFalse(success)
            self.assertIn("Game is over", msg)

    def test_all_players_get_final_turn(self):
        """Test that all players get exactly one final turn after deck is exhausted."""
        # Exhaust deck
        self._exhaust_deck()

        player_exhausting = self.engine._player_exhausting_deck
        self.assertIsNotNone(player_exhausting)

        # The player who exhausted the deck already took their final turn
        # Now all other players should get one final turn each

        # Track which players have taken their final turn
        players_taken_final_turn = {player_exhausting}  # Already took it

        # Go through remaining players
        for _ in range(3):
            current = self.engine.currentPlayer

            # Skip if this is the player who exhausted (they already took their turn)
            if current == player_exhausting:
                # Game should end when it comes back to this player
                self.assertTrue(self.engine.isFinished())
                break

            # This player should be able to take their final turn
            self.assertNotIn(current, players_taken_final_turn,
                           f"Player {current} should not have taken final turn yet")

            # Make a move (discard if possible)
            hand = self.engine.gameState.playerHands[current]
            if hand.cards:
                if self.engine.gameState.commonView.hintTokens < self.settings.maxHintTokens:
                    move = Discard(0)
                else:
                    # Can't discard, try to play
                    move = Play(0)
                success, _ = self.engine.processMove(current, move)
                self.assertTrue(success, f"Player {current} should be able to take final turn")
                players_taken_final_turn.add(current)
                self.engine.advanceTurn()
            else:
                break

    def test_game_ends_when_back_to_player_exhausting_deck(self):
        """Test that game ends when it comes back to the player who exhausted the deck."""
        # Exhaust deck
        self._exhaust_deck()

        player_exhausting = self.engine._player_exhausting_deck
        self.assertIsNotNone(player_exhausting)

        # Advance through all other players
        for _ in range(3):
            current = self.engine.currentPlayer
            if current == player_exhausting:
                # Should be finished when back to this player
                self.assertTrue(self.engine.isFinished())
                break

            # Make a move
            hand = self.engine.gameState.playerHands[current]
            if hand.cards:
                if self.engine.gameState.commonView.hintTokens < self.settings.maxHintTokens:
                    move = Discard(0)
                else:
                    move = Play(0)
                success, _ = self.engine.processMove(current, move)
                if success:
                    self.engine.advanceTurn()
                else:
                    break
            else:
                break

    def test_invalid_play_in_final_round_loses_life(self):
        """Test that invalid play in final round loses life but still ends turn."""
        # Exhaust deck
        self._exhaust_deck()

        player_exhausting = self.engine._player_exhausting_deck
        # Advance to a different player (not the one who exhausted)
        while self.engine.currentPlayer == player_exhausting:
            self.engine.advanceTurn()

        current = self.engine.currentPlayer
        self.assertNotEqual(current, player_exhausting, "Should be a different player")
        initial_lives = self.engine.gameState.commonView.liveTokens

        # Play an invalid card
        hand = self.engine.gameState.playerHands[current]
        invalid_index = None
        for i, card in enumerate(hand.cards):
            if card.number != Number.ONE:
                invalid_index = i
                break

        if invalid_index is not None:
            move = Play(invalid_index)
            success, _ = self.engine.processMove(current, move)
            self.assertTrue(success)  # Move processes (loses life)

            # Life should be lost
            self.assertEqual(self.engine.gameState.commonView.liveTokens, initial_lives - 1)

            # Game should continue (not finished yet unless lives = 0)
            if initial_lives > 1:
                self.assertFalse(self.engine.isFinished())

    def test_invalid_play_ends_game_if_last_life(self):
        """Test that invalid play ends game if it's the last life."""
        # First exhaust deck (with normal lives)
        self._exhaust_deck()

        # Now set lives to 1
        from hanabi.core.game import CommonView, GameState
        state = self.engine.gameState
        new_common_view = CommonView(
            live_tokens=1,
            hint_tokens=state.commonView.hintTokens,
            cards_to_draw=state.commonView.cardsToDraw,
            cards_discarded=state.commonView.cardsDiscarded,
            cards_played=state.commonView.cardsPlayed
        )
        new_state = GameState(
            common_view=new_common_view,
            player_hands=state.playerHands,
            draw_deck_index=state.drawDeckIndex
        )
        self.engine._game_state = new_state

        # Advance to a different player (not the one who exhausted)
        player_exhausting = self.engine._player_exhausting_deck
        while self.engine.currentPlayer == player_exhausting:
            self.engine.advanceTurn()

        # Now in final round with 1 life
        current = self.engine.currentPlayer
        self.assertNotEqual(current, player_exhausting, "Should be a different player")
        self.assertEqual(self.engine.gameState.commonView.liveTokens, 1)

        # Play an invalid card
        hand = self.engine.gameState.playerHands[current]
        invalid_index = None
        for i, card in enumerate(hand.cards):
            if card.number != Number.ONE:
                invalid_index = i
                break

        if invalid_index is not None:
            move = Play(invalid_index)
            success, _ = self.engine.processMove(current, move)
            self.assertTrue(success)

            # Game should be finished (lives = 0)
            self.assertTrue(self.engine.isFinished())
            self.assertEqual(self.engine.gameState.commonView.liveTokens, 0)


if __name__ == '__main__':
    unittest.main()
