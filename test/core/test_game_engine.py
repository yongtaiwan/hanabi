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
        self.assertEqual(self.game.current_player, 0)
        self.assertEqual(len(self.game.state.player_hands), 3)

        # Each player should have 5 cards (for 3 players)
        for hand in self.game.state.player_hands:
            self.assertEqual(len(hand.cards), 5)

        # Check initial tokens
        common_view = self.game.state.common_view
        self.assertEqual(common_view.hint_tokens, 8)
        self.assertEqual(common_view.live_tokens, 3)

    def test_play_valid_card(self):
        """Test playing a valid card."""
        hand = self.game.state.player_hands[0]

        # Find a card that can be played (a 1 of any color)
        playable_card_index = None
        for i, card in enumerate(hand.cards):
            if card.number == Number.ONE:
                playable_card_index = i
                break

        if playable_card_index is not None:
            move = Play(playable_card_index)
            try:
                self.game.process_move(0, move)
            except AssertionError:
                self.fail("Valid play should not raise AssertionError")

            # Check that card was removed and new card drawn
            new_hand = self.game.state.player_hands[0]
            self.assertEqual(len(new_hand.cards), 5)  # Should still have 5 cards

            # Check that card was added to played cards
            cards_played = self.game.state.common_view.cards_played
            self.assertGreater(len(cards_played), 0)

    def test_play_invalid_card(self):
        """Test playing an invalid card."""
        hand = self.game.state.player_hands[0]

        # Find a card that cannot be played (not a 1, or wrong sequence)
        invalid_card_index = None
        for i, card in enumerate(hand.cards):
            if card.number != Number.ONE:
                invalid_card_index = i
                break

        if invalid_card_index is not None:
            initial_lives = self.game.state.common_view.live_tokens
            move = Play(invalid_card_index)
            # Invalid play is still processed (card is discarded, life lost)
            try:
                self.game.process_move(0, move)
            except AssertionError:
                self.fail("Invalid play should be processed, not raise AssertionError")

            # Check that life token was lost
            new_lives = self.game.state.common_view.live_tokens
            self.assertEqual(new_lives, initial_lives - 1)

    def test_discard_card(self):
        """Test discarding a card."""
        # Discarding is illegal when hint tokens are already at maximum
        if self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens:
            teammate_hand = self.game.state.player_hands[1]
            color = teammate_hand.cards[0].color
            matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
            self.game.process_move(0, ColorHint(1, matching, color))
            self.game._advance_turn()

        initial_hint_tokens = self.game.state.common_view.hint_tokens
        discarder = self.game.current_player
        move = Discard(0)
        try:
            self.game.process_move(discarder, move)
        except AssertionError:
            self.fail("Valid discard should not raise AssertionError")

        # Check that hint token was gained (if not at max before discard)
        new_hint_tokens = self.game.state.common_view.hint_tokens
        if initial_hint_tokens < self.settings.max_hint_tokens:
            self.assertEqual(new_hint_tokens, initial_hint_tokens + 1)

        # Check that card was removed and new card drawn
        new_hand = self.game.state.player_hands[discarder]
        self.assertEqual(len(new_hand.cards), 5)

    def test_color_hint(self):
        """Test giving a color hint."""
        initial_hint_tokens = self.game.state.common_view.hint_tokens

        # Get teammate's hand
        teammate_hand = self.game.state.player_hands[1]

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
                self.game.process_move(0, move)
            except AssertionError:
                self.fail("Valid hint should not raise AssertionError")

            # Check that hint token was used
            new_hint_tokens = self.game.state.common_view.hint_tokens
            self.assertEqual(new_hint_tokens, initial_hint_tokens - 1)

    def test_number_hint(self):
        """Test giving a number hint."""
        initial_hint_tokens = self.game.state.common_view.hint_tokens

        # Get teammate's hand
        teammate_hand = self.game.state.player_hands[1]

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
                self.game.process_move(0, move)
            except AssertionError:
                self.fail("Valid hint should not raise AssertionError")

            # Check that hint token was used
            new_hint_tokens = self.game.state.common_view.hint_tokens
            self.assertEqual(new_hint_tokens, initial_hint_tokens - 1)

    def test_invalid_move_wrong_player(self):
        """Test that wrong player cannot make a move."""
        move = Play(0)
        with self.assertRaises(AssertionError) as context:
            self.game.process_move(1, move)
        self.assertIn("Invalid move", str(context.exception))

    def test_invalid_move_no_hint_tokens(self):
        """Test that hint cannot be given without hint tokens."""
        # Use up all hint tokens
        teammate_hand = self.game.state.player_hands[1]

        # Find a color to hint
        color_to_hint = teammate_hand.cards[0].color if teammate_hand.cards else None
        matching_indices = (
            [i for i, card in enumerate(teammate_hand.cards) if card.color == color_to_hint] if color_to_hint else []
        )

        if color_to_hint and matching_indices:
            # Use up all hint tokens (always move on behalf of the current player)
            while self.game.state.common_view.hint_tokens > 0:
                cp = self.game.current_player
                moved = False
                for tgt in range(3):
                    if tgt == cp:
                        continue
                    th = self.game.state.player_hands[tgt]
                    if not th.cards:
                        continue
                    col = th.cards[0].color
                    matching = [i for i, c in enumerate(th.cards) if c.color == col]
                    move = ColorHint(tgt, matching, col)
                    if self.game.state._validate(cp, move):
                        self.game.process_move(cp, move)
                        self.game._advance_turn()
                        moved = True
                        break
                if not moved:
                    break

            new_state = self.game.state
            if 0 == new_state.common_view.hint_tokens:
                cp = self.game.current_player
                tgt = 1 if 1 != cp else 2
                th = new_state.player_hands[tgt]
                col = th.cards[0].color
                matching = [i for i, c in enumerate(th.cards) if c.color == col]
                move = ColorHint(tgt, matching, col)
                with self.assertRaises(AssertionError) as context:
                    self.game.process_move(cp, move)
                self.assertIn("Invalid move", str(context.exception))

    def test_advance_turn(self):
        """Test turn advancement."""
        initial_player = self.game.current_player
        self.game._advance_turn()
        self.assertEqual(self.game.current_player, (initial_player + 1) % 3)

    def test_deck_exhaustion(self):
        """Test that game handles deck exhaustion correctly."""
        # Play/discard cards until deck is exhausted
        initial_deck_size = self.game.state.common_view.cards_to_draw

        # Make many moves to exhaust deck
        moves_made = 0
        max_moves = 100  # Safety limit

        while not self.game.is_finished and moves_made < max_moves:
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]

            if hand.cards:
                # Try to discard
                move = Discard(0)
                try:
                    self.game.process_move(current_player, move)
                    self.game._advance_turn()
                    moves_made += 1
                except AssertionError:
                    break
            else:
                break

        # Check that deck exhaustion is tracked
        final_state = self.game.state
        if 0 == final_state.common_view.cards_to_draw:
            # Game tracks turns_left when deck is exhausted
            self.assertIsNotNone(final_state.turns_left)

    def test_game_finished_no_lives(self):
        """Test that game finishes when no lives remain."""
        hand = self.game.state.player_hands[0]

        # Play invalid cards to lose all lives
        lives_lost = 0
        for i in range(len(hand.cards)):
            if hand.cards[i].number != Number.ONE:
                move = Play(i)
                try:
                    self.game.process_move(0, move)
                    lives_lost += 1
                    if self.game.state.common_view.live_tokens <= 0:
                        break
                except AssertionError:
                    break

        # Game should be finished if no lives
        if self.game.state.common_view.live_tokens <= 0:
            self.assertTrue(self.game.is_finished)

    def test_score_calculation(self):
        """Test score calculation."""
        # Initial score should be 0
        self.assertEqual(self.game.get_score(), 0)

        # Play some cards and check score increases
        hand = self.game.state.player_hands[0]

        # Find and play a 1
        for i, card in enumerate(hand.cards):
            if card.number == Number.ONE:
                move = Play(i)
                try:
                    self.game.process_move(0, move)
                    score = self.game.get_score()
                    self.assertGreater(score, 0)
                    break
                except AssertionError:
                    continue

    def test_hint_shifting_after_play(self):
        """Test that hints shift correctly when a card is played."""

        # Manually set up hints on the player:
        # Index 3: number=1 hint
        # Index 4: color=YELLOW hint
        from hanabi.core.player import HintTrackingPlayer

        player = self.game.team.players[0]
        if isinstance(player, HintTrackingPlayer):
            player._hints = {3: {"color": None, "number": Number.ONE}, 4: {"color": Color.YELLOW, "number": None}}

        from hanabi.core.player import HintTrackingPlayer

        player = self.game.team.players[0]
        hints_before = player.get_hints() if isinstance(player, HintTrackingPlayer) else {}
        self.assertIn(3, hints_before)
        self.assertIn(4, hints_before)

        # Play card at index 4
        move = Play(4)
        try:
            self.game.process_move(0, move)
        except AssertionError as e:
            self.fail(f"Play failed: {e}")

        hints_after = player.get_hints() if isinstance(player, HintTrackingPlayer) else {}

        # Left-to-right draw: playing index 4 removes the rightmost card; indices 0–3 unchanged.
        self.assertIn(3, hints_after, "number=1 hint should still be on index 3")
        hint_3 = hints_after[3]
        self.assertEqual(hint_3.get("number"), Number.ONE)
        self.assertIsNone(hint_3.get("color"))
        # New card appended at index 4 should have no hints
        if 4 in hints_after:
            hint_new = hints_after[4]
            self.assertIsNone(hint_new.get("color"))
            self.assertIsNone(hint_new.get("number"))

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
                4: {"color": Color.YELLOW, "number": None},
            }

        # Play card at index 4
        move = Play(4)
        try:
            self.game.process_move(0, move)
        except AssertionError as e:
            self.fail(f"Play failed: {e}")

        from hanabi.core.player import HintTrackingPlayer

        player = self.game.team.players[0]
        hints_after = player.get_hints() if isinstance(player, HintTrackingPlayer) else {}

        # Indices 2 and 3 unchanged after playing rightmost (index 4).
        self.assertIn(2, hints_after)
        self.assertEqual(hints_after[2].get("color"), Color.YELLOW)
        self.assertIn(3, hints_after)
        self.assertEqual(hints_after[3].get("number"), Number.ONE)
        self.assertIsNone(hints_after[3].get("color"))


class TestAutoEndWhenNoPointsPossible(unittest.TestCase):
    def test_standard_settings_leave_auto_end_off(self) -> None:
        """Human / default settings keep official play-out when suits are blocked."""
        self.assertFalse(create_standard_game_settings(3).auto_end_when_no_points_possible)

    def test_ai_simulation_settings_enable_auto_end(self) -> None:
        from hanabi.core.game import create_ai_simulation_game_settings

        self.assertTrue(create_ai_simulation_game_settings(3).auto_end_when_no_points_possible)

    def test_game_finishes_when_all_remaining_suits_are_blocked(self) -> None:
        """With auto-end on, blocked unfinished colors end the game without deck play-out."""
        from hanabi.core.card import Suit
        from hanabi.core.game import create_ai_simulation_game_settings

        settings = create_ai_simulation_game_settings(3)
        players = [HumanPlayer(i) for i in range(3)]
        game = Game.create(PlayerTeam(players), settings)
        state = game.state
        # W/G/B complete; R and Y stuck needing a 5 that is fully discarded.
        state.common_view._cards_played = {
            Color.WHITE: Number.FIVE,
            Color.GREEN: Number.FIVE,
            Color.BLUE: Number.FIVE,
            Color.RED: Number.FOUR,
            Color.YELLOW: Number.FOUR,
        }
        state.common_view._cards_discarded = {
            Color.RED: Suit({Number.FIVE: 1}),
            Color.YELLOW: Suit({Number.FIVE: 1}),
        }
        self.assertTrue(state._is_no_more_points_possible())
        self.assertTrue(game.is_finished)


if __name__ == "__main__":
    unittest.main()
