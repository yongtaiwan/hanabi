"""
Tests for RandomPlayer to ensure it only returns valid moves.
"""

import unittest
from hanabi.core.game import create_standard_game_settings, Game
from hanabi.core.player import PlayerTeam
from hanabi.ai.random_player import RandomPlayer
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint


class TestRandomPlayer(unittest.TestCase):
    """Test cases for RandomPlayer to ensure move validity."""

    def test_random_player_only_returns_valid_moves(self):
        """
        Test that RandomPlayer only returns valid moves.

        This test plays multiple games and verifies that RandomPlayer
        never returns an invalid move that trips engine assertions.
        """
        settings = create_standard_game_settings(3)

        # Run multiple games to catch edge cases
        for game_num in range(10):
            with self.subTest(game_num=game_num):
                players = [RandomPlayer(i) for i in range(3)]
                team = PlayerTeam(players)
                game = Game.create(team, settings)

                try:
                    game.play()
                    self.assertTrue(game.isFinished)
                except AssertionError as e:
                    self.fail(f"RandomPlayer returned an invalid move in game {game_num}: {e}")
                except Exception as e:
                    self.fail(f"Unexpected exception in game {game_num}: {e}")

    def test_random_player_handles_hint_token_exhaustion(self):
        """
        Test that RandomPlayer correctly handles hint token exhaustion.

        This test ensures that when hint tokens are exhausted, RandomPlayer
        doesn't try to give hints.
        """
        settings = create_standard_game_settings(3)
        players = [RandomPlayer(i) for i in range(3)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        # Exhaust hint tokens by giving hints
        state = game.state
        initial_tokens = state.commonView.hintTokens

        # Give hints until tokens are exhausted
        for _ in range(initial_tokens):
            if state.commonView.hintTokens <= 0:
                break
            # Find a valid hint to give
            current_player = state.currentPlayer
            teammate_idx = (current_player + 1) % 3
            teammate_hand = state.playerHands[teammate_idx]

            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                if matching:
                    move = ColorHint(teammate_idx, matching, color)
                    try:
                        game._processMove(current_player, move)
                        state = game.state
                    except Exception:
                        break

        # Now try to get a move from RandomPlayer
        # It should not return a hint move when tokens are 0
        if state.commonView.hintTokens <= 0:
            player = players[state.currentPlayer]
            from hanabi.core.game import PlayerView
            teammates = {i: state.playerHands[i] for i in range(3) if i != state.currentPlayer}
            player_view = PlayerView(teammates, len(state.playerHands[state.currentPlayer].cards))

            # Get multiple moves to ensure consistency
            for _ in range(10):
                move = player.play(player_view)
                # Should not be a hint move when tokens are 0
                if isinstance(move, (ColorHint, NumberHint)):
                    self.fail(f"RandomPlayer returned a hint move when tokens are 0: {move}")

    def test_random_player_handles_discard_when_tokens_at_max(self):
        """
        Test that RandomPlayer doesn't discard when hint tokens are at maximum.
        """
        settings = create_standard_game_settings(3)
        players = [RandomPlayer(i) for i in range(3)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        state = game.state
        max_tokens = settings.maxHintTokens

        # Set hint tokens to maximum (by discarding cards)
        # Actually, we can't easily set tokens to max, but we can test the validation
        # by checking that RandomPlayer's validation method works correctly

        # Get a player and check validation
        player = players[0]
        from hanabi.core.game import PlayerView
        teammates = {i: state.playerHands[i] for i in range(3) if i != 0}
        player_view = PlayerView(teammates, len(state.playerHands[0].cards))

        # Create a discard move
        if player_view.ownHandSize > 0:
            discard_move = Discard(0)

            # If tokens are at max, the move should be invalid
            if state.commonView.hintTokens >= max_tokens:
                is_valid = player.is_move_legal(player_view, discard_move)
                self.assertFalse(is_valid, "Discard should be invalid when hint tokens are at max")


if __name__ == "__main__":
    unittest.main()
