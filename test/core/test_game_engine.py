"""
Tests for Game class.
"""

import unittest
from hanabi.core.game import create_standard_game_settings, Game
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
from hanabi.core.player import HumanPlayer, PlayerTeam
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card


class TestGame(unittest.TestCase):
    """Test cases for Game."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.players = [HumanPlayer(i) for i in range(3)]
        team = PlayerTeam(self.players)
        self.game = Game.create(team, self.settings)

    def test_initialization(self):
        """Test game initialization."""
        self.assertIsNotNone(self.game.state)
        self.assertEqual(self.game.currentPlayer, 0)
        self.assertEqual(len(self.game.state.playerHands), 3)

        # Each player should have 5 cards (for 3 players)
        for hand in self.game.state.playerHands:
            self.assertEqual(len(hand.cards), 5)

        # Check initial tokens
        common_view = self.game.state.commonView
        self.assertEqual(common_view.hintTokens, 8)
        self.assertEqual(common_view.liveTokens, 3)

    def test_play_valid_card(self):
        """Test playing a valid card."""
        state = self.game.state
        hand = state.playerHands[0]

        # Find a card that can be played (a 1 of any color)
        playable_card_index = None
        for i, card in enumerate(hand.cards):
            if card.number == Number.ONE:
                playable_card_index = i
                break

        if playable_card_index is not None:
            move = Play(playable_card_index)
            try:
                self.game.processMove(0, move)
            except AssertionError:
                self.fail("Valid play should not raise AssertionError")

            # Check that card was removed and new card drawn
            new_hand = self.game.state.playerHands[0]
            self.assertEqual(len(new_hand.cards), 5)  # Should still have 5 cards

            # Check that card was added to played cards
            cards_played = self.game.state.commonView.cardsPlayed
            self.assertGreater(len(cards_played), 0)

    def test_play_invalid_card(self):
        """Test playing an invalid card."""
        state = self.game.state
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
            # Invalid play is still processed (card is discarded, life lost)
            try:
                self.game.processMove(0, move)
            except AssertionError:
                self.fail("Invalid play should be processed, not raise AssertionError")

            # Check that life token was lost
            new_lives = self.game.state.commonView.liveTokens
            self.assertEqual(new_lives, initial_lives - 1)

    def test_discard_card(self):
        """Test discarding a card."""
        state = self.game.state
        # Discarding is illegal when hint tokens are already at maximum
        if state.commonView.hintTokens >= self.settings.maxHintTokens:
            teammate_hand = state.playerHands[1]
            color = teammate_hand.cards[0].color
            matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
            self.game.processMove(0, ColorHint(1, matching, color))
            self.game._advanceTurn()
            state = self.game.state

        initial_hint_tokens = state.commonView.hintTokens
        discarder = self.game.currentPlayer
        move = Discard(0)
        try:
            self.game.processMove(discarder, move)
        except AssertionError:
            self.fail("Valid discard should not raise AssertionError")

        # Check that hint token was gained (if not at max before discard)
        new_hint_tokens = self.game.state.commonView.hintTokens
        if initial_hint_tokens < self.settings.maxHintTokens:
            self.assertEqual(new_hint_tokens, initial_hint_tokens + 1)

        # Check that card was removed and new card drawn
        new_hand = self.game.state.playerHands[discarder]
        self.assertEqual(len(new_hand.cards), 5)

    def test_color_hint(self):
        """Test giving a color hint."""
        state = self.game.state
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
            try:
                self.game.processMove(0, move)
            except AssertionError:
                self.fail("Valid hint should not raise AssertionError")

            # Check that hint token was used
            new_hint_tokens = self.game.state.commonView.hintTokens
            self.assertEqual(new_hint_tokens, initial_hint_tokens - 1)

    def test_number_hint(self):
        """Test giving a number hint."""
        state = self.game.state
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
            try:
                self.game.processMove(0, move)
            except AssertionError:
                self.fail("Valid hint should not raise AssertionError")

            # Check that hint token was used
            new_hint_tokens = self.game.state.commonView.hintTokens
            self.assertEqual(new_hint_tokens, initial_hint_tokens - 1)

    def test_invalid_move_wrong_player(self):
        """Test that wrong player cannot make a move."""
        move = Play(0)
        with self.assertRaises(AssertionError) as context:
            self.game.processMove(1, move)
        self.assertIn("Invalid move", str(context.exception))

    def test_invalid_move_no_hint_tokens(self):
        """Test that hint cannot be given without hint tokens."""
        # Use up all hint tokens
        state = self.game.state
        teammate_hand = state.playerHands[1]

        # Find a color to hint
        color_to_hint = teammate_hand.cards[0].color if teammate_hand.cards else None
        matching_indices = [i for i, card in enumerate(teammate_hand.cards)
                           if card.color == color_to_hint] if color_to_hint else []

        if color_to_hint and matching_indices:
            # Use up all hint tokens (always move on behalf of the current player)
            while state.commonView.hintTokens > 0:
                cp = self.game.currentPlayer
                moved = False
                for tgt in range(3):
                    if tgt == cp:
                        continue
                    th = state.playerHands[tgt]
                    if not th.cards:
                        continue
                    col = th.cards[0].color
                    matching = [i for i, c in enumerate(th.cards) if c.color == col]
                    move = ColorHint(tgt, matching, col)
                    if state._validate(cp, move):
                        self.game.processMove(cp, move)
                        self.game._advanceTurn()
                        state = self.game.state
                        moved = True
                        break
                if not moved:
                    break

            new_state = self.game.state
            if new_state.commonView.hintTokens == 0:
                cp = self.game.currentPlayer
                tgt = 1 if cp != 1 else 2
                th = new_state.playerHands[tgt]
                col = th.cards[0].color
                matching = [i for i, c in enumerate(th.cards) if c.color == col]
                move = ColorHint(tgt, matching, col)
                with self.assertRaises(AssertionError) as context:
                    self.game.processMove(cp, move)
                self.assertIn("Invalid move", str(context.exception))

    def test_advance_turn(self):
        """Test turn advancement."""
        initial_player = self.game.currentPlayer
        self.game._advanceTurn()
        self.assertEqual(self.game.currentPlayer, (initial_player + 1) % 3)

    def test_deck_exhaustion(self):
        """Test that game handles deck exhaustion correctly."""
        # Play/discard cards until deck is exhausted
        state = self.game.state
        initial_deck_size = state.commonView.cardsToDraw

        # Make many moves to exhaust deck
        moves_made = 0
        max_moves = 100  # Safety limit

        while not self.game.isFinished and moves_made < max_moves:
            current_player = self.game.currentPlayer
            hand = self.game.state.playerHands[current_player]

            if hand.cards:
                # Try to discard
                move = Discard(0)
                try:
                    self.game.processMove(current_player, move)
                    self.game._advanceTurn()
                    moves_made += 1
                except AssertionError:
                    break
            else:
                break

        # Check that deck exhaustion is tracked
        final_state = self.game.state
        if final_state.commonView.cardsToDraw == 0:
            # Game tracks turns_left when deck is exhausted
            self.assertIsNotNone(final_state.turnsLeft)

    def test_game_finished_no_lives(self):
        """Test that game finishes when no lives remain."""
        state = self.game.state
        hand = state.playerHands[0]

        # Play invalid cards to lose all lives
        lives_lost = 0
        for i in range(len(hand.cards)):
            if hand.cards[i].number != Number.ONE:
                move = Play(i)
                try:
                    self.game.processMove(0, move)
                    lives_lost += 1
                    if self.game.state.commonView.liveTokens <= 0:
                        break
                except AssertionError:
                    break

        # Game should be finished if no lives
        if self.game.state.commonView.liveTokens <= 0:
            self.assertTrue(self.game.isFinished)

    def test_score_calculation(self):
        """Test score calculation."""
        # Initial score should be 0
        self.assertEqual(self.game.getScore(), 0)

        # Play some cards and check score increases
        state = self.game.state
        hand = state.playerHands[0]

        # Find and play a 1
        for i, card in enumerate(hand.cards):
            if card.number == Number.ONE:
                move = Play(i)
                try:
                    self.game.processMove(0, move)
                    score = self.game.getScore()
                    self.assertGreater(score, 0)
                    break
                except AssertionError:
                    continue

    def test_hint_shifting_after_play(self):
        """Test that hints shift correctly when a card is played."""
        state = self.game.state

        # Manually set up hints on the player:
        # Index 3: number=1 hint
        # Index 4: color=YELLOW hint
        from hanabi.core.player import HintTrackingPlayer
        player = self.game.team.players[0]
        if isinstance(player, HintTrackingPlayer):
            player._hints = {
                3: {"color": None, "number": Number.ONE},
                4: {"color": Color.YELLOW, "number": None}
            }

        from hanabi.core.player import HintTrackingPlayer
        player = self.game.team.players[0]
        hints_before = player.getHints() if isinstance(player, HintTrackingPlayer) else {}
        self.assertIn(3, hints_before)
        self.assertIn(4, hints_before)

        # Play card at index 4
        move = Play(4)
        try:
            self.game.processMove(0, move)
        except AssertionError as e:
            self.fail(f"Play failed: {e}")

        hints_after = player.getHints() if isinstance(player, HintTrackingPlayer) else {}

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
        # Set up: multiple cards with yellow hint
        # Index 2: yellow hint
        # Index 3: number=1 hint
        # Index 4: yellow hint (to be played)
        from hanabi.core.player import HintTrackingPlayer
        player = self.game.team.players[0]
        if isinstance(player, HintTrackingPlayer):
            player._hints = {
                2: {"color": Color.YELLOW, "number": None},
                3: {"color": None, "number": Number.ONE},
                4: {"color": Color.YELLOW, "number": None}
            }

        # Play card at index 4
        move = Play(4)
        try:
            self.game.processMove(0, move)
        except AssertionError as e:
            self.fail(f"Play failed: {e}")

        from hanabi.core.player import HintTrackingPlayer
        player = self.game.team.players[0]
        hints_after = player.getHints() if isinstance(player, HintTrackingPlayer) else {}

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

