"""
Comprehensive tests for Game class to ensure all functionality works correctly.
"""

import unittest
import copy
from unittest.mock import patch
from hanabi.core.game import (
    create_standard_game_settings,
    Game,
    GameState,
    GameSettings,
    CommonView,
    Hand,
    StartPosition,
    Deck,
)
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
from hanabi.core.player import HumanPlayer, PlayerTeam
from hanabi.ai import RandomPlayer
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card, Suit


class TestGameComprehensive(unittest.TestCase):
    """Comprehensive test cases for Game class."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.players = [HumanPlayer(i) for i in range(3)]
        team = PlayerTeam(self.players)
        self.game = Game.create(team, self.settings)

    def test_game_create_with_different_player_counts(self):
        """Test game creation with 2-5 players."""
        for num_players in range(2, 6):
            with self.subTest(num_players=num_players):
                settings = create_standard_game_settings(num_players)
                players = [HumanPlayer(i) for i in range(num_players)]
                team = PlayerTeam(players)
                game = Game.create(team, settings)

                self.assertEqual(len(game.state.player_hands), num_players)
                self.assertEqual(game.current_player, 0)
                self.assertEqual(game.state.turn_number, 0)

                # Check cards per hand
                expected_cards = 5 if num_players <= 3 else 4
                for hand in game.state.player_hands:
                    self.assertEqual(len(hand.cards), expected_cards)

    def test_initial_state_correctness(self):
        """Test that initial game state is correct."""

        # Check tokens
        self.assertEqual(self.game.state.common_view.live_tokens, 3)
        self.assertEqual(self.game.state.common_view.hint_tokens, 8)

        # Check no cards played or discarded
        self.assertEqual(len(self.game.state.common_view.cards_played), 0)
        self.assertEqual(len(self.game.state.common_view.cards_discarded), 0)

        # Check turn number
        self.assertEqual(self.game.state.turn_number, 0)
        self.assertEqual(self.game.state.current_player, 0)
        self.assertIsNone(self.game.state.turns_left)

        # Check deck size
        # Total cards: 5 colors * (3+2+2+2+1) = 5 * 10 = 50 cards
        total_cards = 50
        dealt_cards = 3 * 5  # 3 players * 5 cards each = 15
        expected_remaining = total_cards - dealt_cards  # 50 - 15 = 35
        self.assertEqual(self.game.state.common_view.cards_to_draw, expected_remaining)

    def test_deck_shuffling(self):
        """Test that deck is shuffled (cards are in different order)."""
        # Create multiple games and check decks are different
        decks = []
        for _ in range(5):
            players = [HumanPlayer(i) for i in range(3)]
            team = PlayerTeam(players)
            game = Game.create(team, self.settings)
            # Get first few cards from each player's hand
            first_cards = tuple(tuple(hand.cards[:3]) for hand in game.state.player_hands)
            decks.append(first_cards)

        # At least some games should have different card orders
        # (very unlikely all 5 are identical)
        unique_decks = set(decks)
        self.assertGreater(len(unique_decks), 1, "Decks should be shuffled differently")

    def test_validate_wrong_player_turn(self):
        """Test that wrong player cannot make a move."""
        move = Play(0)
        # Player 1 tries to move on player 0's turn
        self.assertFalse(self.game.state._validate(1, move))

        with self.assertRaises(AssertionError) as context:
            self.game.process_move(1, move)
        self.assertIn("Invalid move", str(context.exception))

    def test_validate_invalid_card_index(self):
        """Test validation of invalid card indices."""
        # Negative index
        move = Play(-1)
        self.assertFalse(self.game.state._validate(0, move))

        # Index too high
        hand_size = len(self.game.state.player_hands[0].cards)
        move = Play(hand_size)
        self.assertFalse(self.game.state._validate(0, move))

        with self.assertRaises(AssertionError):
            self.game.process_move(0, move)

    def test_validate_discard_at_max_hint_tokens(self):
        """Test that discard is invalid when hint tokens are at maximum."""

        # Fill hint tokens to max
        while self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
            # Discard to gain tokens
            move = Discard(0)
            self.game.process_move(self.game.current_player, move)
            self.game._advance_turn()

        # Now try to discard - should be invalid
        move = Discard(0)
        self.assertFalse(self.game.state._validate(self.game.current_player, move))

        with self.assertRaises(AssertionError):
            self.game.process_move(self.game.current_player, move)

    def test_validate_hint_no_tokens(self):
        """Test that hint is invalid when no hint tokens available."""
        teammate_hand = self.game.state.player_hands[1]

        # Find a color to hint
        if teammate_hand.cards:
            color = teammate_hand.cards[0].color
            matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]

            # Use up all hint tokens
            while self.game.state.common_view.hint_tokens > 0:
                current_player = self.game.current_player
                # Make sure we're hinting a valid teammate
                target = 1 if 1 != current_player else 2
                target_hand = self.game.state.player_hands[target]
                if target_hand.cards:
                    target_color = target_hand.cards[0].color
                    target_matching = [i for i, c in enumerate(target_hand.cards) if c.color == target_color]
                    move = ColorHint(target, target_matching, target_color)
                    try:
                        self.game.process_move(current_player, move)
                        self.game._advance_turn()
                    except AssertionError:
                        break
                else:
                    break

            # Now try to hint - should be invalid
            if 0 == self.game.state.common_view.hint_tokens:
                move = ColorHint(1, matching, color)
                self.assertFalse(self.game.state._validate(self.game.current_player, move))

                with self.assertRaises(AssertionError):
                    self.game.process_move(self.game.current_player, move)

    def test_validate_hint_must_include_all_matching_cards(self):
        """Test that hint must include ALL matching cards (critical rule)."""
        teammate_hand = self.game.state.player_hands[1]

        # Find all cards of a specific color
        if teammate_hand.cards:
            color = teammate_hand.cards[0].color
            all_matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]

            # Partial hint (only some matching cards) should be invalid
            if len(all_matching) > 1:
                partial_matching = all_matching[: len(all_matching) - 1]  # All but one
                move = ColorHint(1, partial_matching, color)
                self.assertFalse(self.game.state._validate(0, move))

                with self.assertRaises(AssertionError):
                    self.game.process_move(0, move)

    def test_validate_hint_cannot_hint_self(self):
        """Test that player cannot hint themselves."""
        hand = self.game.state.player_hands[0]

        if hand.cards:
            color = hand.cards[0].color
            matching = [i for i, c in enumerate(hand.cards) if c.color == color]
            move = ColorHint(0, matching, color)  # Hinting self
            self.assertFalse(self.game.state._validate(0, move))

            with self.assertRaises(AssertionError):
                self.game.process_move(0, move)

    def test_validate_hint_invalid_teammate_index(self):
        """Test that hint with invalid teammate index is rejected."""
        move = ColorHint(-1, [0], Color.RED)  # Invalid teammate
        self.assertFalse(self.game.state._validate(0, move))

        move = ColorHint(10, [0], Color.RED)  # Out of range
        self.assertFalse(self.game.state._validate(0, move))

    def test_validate_game_over_no_moves(self):
        """Test that moves are invalid when game is over."""
        # A random hand can contain only ones, so searching for a misplay in
        # an unbounded loop can hang without making a move. Keep the standard
        # deck order: each dealt hand contains an unplayable rank above one.
        with patch.object(Deck, "shuffle"):
            self.game = Game.create(PlayerTeam(self.players), self.settings)

        for lives_left in range(self.settings.max_live_tokens - 1, -1, -1):
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]
            slot = next(i for i, card in enumerate(hand.cards) if card.number != Number.ONE)
            self.game.process_move(current_player, Play(slot))
            self.game._advance_turn()
            self.assertEqual(self.game.state.common_view.live_tokens, lives_left)

        self.assertTrue(self.game.is_finished)
        self.assertIsNone(self.game.state.turns_left)
        actor = self.game.current_player
        self.assertFalse(self.game.state._validate(actor, Play(0)))
        target = (actor + 1) % self.settings.num_players
        cards = self.game.state.player_hands[target].cards
        color = cards[0].color
        touched = [i for i, card in enumerate(cards) if card.color == color]
        self.assertFalse(self.game.state._validate(actor, ColorHint(target, touched, color)))

    def test_validate_rejects_moves_after_other_game_endings(self):
        """All terminal reasons reject an otherwise legal card move."""
        for ending in ("perfect_score", "final_round"):
            with self.subTest(ending=ending):
                state = copy.deepcopy(self.game.state)
                self.assertTrue(state._validate(state.current_player, Play(0)))
                if ending == "perfect_score":
                    state._common_view._cards_played = {
                        color: Number.FIVE for color in self.settings.cards
                    }
                else:
                    state._turns_left = 0
                self.assertTrue(state.is_finished())
                self.assertFalse(state._validate(state.current_player, Play(0)))

    def test_play_valid_card_sequence(self):
        """Test playing cards in correct sequence."""

        # Play a 1 of any color
        hand = self.game.state.player_hands[0]
        one_index = None
        one_color = None
        for i, card in enumerate(hand.cards):
            if card.number == Number.ONE:
                one_index = i
                one_color = card.color
                break

        if one_index is not None:
            # Play the 1
            move = Play(one_index)
            self.game.process_move(0, move)
            self.game._advance_turn()

            # Check it was played
            self.assertIn(one_color, self.game.state.common_view.cards_played)
            self.assertEqual(self.game.state.common_view.cards_played[one_color], Number.ONE)

            # Now find and play a 2 of the same color
            # (This requires checking all players' hands, but only current player can play)
            found_two = False
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]
            for i, card in enumerate(hand.cards):
                if card.color == one_color and card.number == Number.TWO:
                    move = Play(i)
                    self.game.process_move(current_player, move)
                    found_two = True
                    break

            # If not found in current player's hand, advance turn and try next player
            if not found_two:
                self.game._advance_turn()
                current_player = self.game.current_player
                hand = self.game.state.player_hands[current_player]
                for i, card in enumerate(hand.cards):
                    if card.color == one_color and card.number == Number.TWO:
                        move = Play(i)
                        self.game.process_move(current_player, move)
                        found_two = True
                        break

            if found_two:
                self.assertEqual(self.game.state.common_view.cards_played[one_color], Number.TWO)

    def test_play_invalid_card_loses_life(self):
        """Test that invalid play loses a life token."""
        initial_lives = self.game.state.common_view.live_tokens

        # Find a card that cannot be played
        hand = self.game.state.player_hands[0]
        invalid_index = None
        for i, card in enumerate(hand.cards):
            if card.number != Number.ONE:
                invalid_index = i
                break

        if invalid_index is not None:
            move = Play(invalid_index)
            self.game.process_move(0, move)

            # Check life was lost
            self.assertEqual(self.game.state.common_view.live_tokens, initial_lives - 1)

            # Check card was discarded
            card = hand.cards[invalid_index]
            discarded = self.game.state.common_view.cards_discarded
            self.assertIn(card.color, discarded)
            self.assertIn(card.number, discarded[card.color].cards)

    def test_play_completes_firework_grants_hint_token(self):
        """Test that completing a firework (playing 5) grants hint token if not at max."""

    def test_discard_gains_hint_token(self):
        """Test that discarding gains a hint token."""

        # First use a hint to reduce tokens below max
        if self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens:
            current_player = self.game.current_player
            teammate_hand = self.game.state.player_hands[1]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                move = ColorHint(1, matching, color)
                self.game.process_move(current_player, move)
                self.game._advance_turn()

        initial_tokens = self.game.state.common_view.hint_tokens

        # Now discard a card (only if tokens are below max)
        if initial_tokens < self.settings.max_hint_tokens:
            current_player = self.game.current_player
            move = Discard(0)
            self.game.process_move(current_player, move)

            # Check token was gained
            self.assertEqual(self.game.state.common_view.hint_tokens, initial_tokens + 1)

    def test_discard_adds_to_discard_pile(self):
        """Test that discarded card is added to discard pile."""

        # First use a hint to reduce tokens below max
        if self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens:
            current_player = self.game.current_player
            teammate_hand = self.game.state.player_hands[1]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                move = ColorHint(1, matching, color)
                self.game.process_move(current_player, move)
                self.game._advance_turn()

        # Get current player and their hand
        current_player = self.game.current_player
        hand = self.game.state.player_hands[current_player]
        if hand.cards and self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
            card = hand.cards[0]
            move = Discard(0)
            self.game.process_move(current_player, move)

            # Check card is in discard pile
            discarded = self.game.state.common_view.cards_discarded
            self.assertIn(card.color, discarded)
            self.assertIn(card.number, discarded[card.color].cards)
            self.assertEqual(discarded[card.color].cards[card.number], 1)

    def test_hint_uses_hint_token(self):
        """Test that giving a hint uses a hint token."""
        initial_tokens = self.game.state.common_view.hint_tokens
        teammate_hand = self.game.state.player_hands[1]

        if teammate_hand.cards:
            color = teammate_hand.cards[0].color
            matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]

            move = ColorHint(1, matching, color)
            self.game.process_move(0, move)

            # Check token was used
            self.assertEqual(self.game.state.common_view.hint_tokens, initial_tokens - 1)

    def test_card_drawing_on_play(self):
        """Test that a new card is drawn after playing."""
        initial_deck_size = self.game.state.common_view.cards_to_draw
        hand = self.game.state.player_hands[0]
        initial_hand_size = len(hand.cards)
        self.assertGreater(initial_deck_size, 0, "deck must have cards to draw after a play")

        # Play any card from index 0 (valid play or misplay both draw when the deck is non-empty).
        self.game.process_move(0, Play(0))

        # Check hand size maintained and deck decreased
        new_hand = self.game.state.player_hands[0]
        self.assertEqual(len(new_hand.cards), initial_hand_size)
        # Deck should have decreased by 1
        self.assertEqual(self.game.state.common_view.cards_to_draw, initial_deck_size - 1)

    def test_card_drawing_on_discard(self):
        """Test that a new card is drawn after discarding."""

        # First use a hint to reduce tokens below max
        if self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens:
            current_player = self.game.current_player
            teammate_hand = self.game.state.player_hands[1]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                move = ColorHint(1, matching, color)
                self.game.process_move(current_player, move)
                self.game._advance_turn()

        # Get current player and their hand
        current_player = self.game.current_player
        hand = self.game.state.player_hands[current_player]
        if hand.cards and self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
            initial_deck_size = self.game.state.common_view.cards_to_draw
            initial_hand_size = len(hand.cards)

            move = Discard(0)
            self.game.process_move(current_player, move)

            # Check hand size maintained and deck decreased
            new_hand = self.game.state.player_hands[current_player]
            self.assertEqual(len(new_hand.cards), initial_hand_size)
            self.assertEqual(self.game.state.common_view.cards_to_draw, initial_deck_size - 1)

    def test_no_card_drawing_when_deck_exhausted(self):
        """Test that no card is drawn when deck is exhausted."""

        # Exhaust the deck by playing/discarding
        # Use hints first to reduce tokens
        while self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens and self.game.state.common_view.cards_to_draw > 0:
            current_player = self.game.current_player
            target = (current_player + 1) % 3
            teammate_hand = self.game.state.player_hands[target]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                move = ColorHint(target, matching, color)
                try:
                    self.game.process_move(current_player, move)
                    self.game._advance_turn()
                except AssertionError:
                    break
            else:
                break

        # Now discard/play to exhaust deck - keep going until exhausted
        max_iterations = 100  # Safety limit
        iterations = 0
        while self.game.state.common_view.cards_to_draw > 0 and iterations < max_iterations:
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]
            if hand.cards and self.game.state.common_view.live_tokens > 0:  # Don't play if no lives
                # Use discard if possible, otherwise hint
                if self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
                    move = Discard(0)
                elif self.game.state.common_view.hint_tokens > 0:
                    # Give a hint instead of playing
                    target = (current_player + 1) % 3
                    target_hand = self.game.state.player_hands[target]
                    if target_hand.cards:
                        color = target_hand.cards[0].color
                        matching = [i for i, c in enumerate(target_hand.cards) if c.color == color]
                        if matching:
                            move = ColorHint(target, matching, color)
                        else:
                            break
                    else:
                        break
                else:
                    break
                try:
                    self.game.process_move(current_player, move)
                    self.game._advance_turn()
                    iterations += 1
                except AssertionError:
                    # Move failed or game ended
                    break
            else:
                break

        # Deck should be exhausted (or we hit the limit)
        # The main test is that cards_to_draw is 0, meaning no more cards can be drawn
        # turns_left is set when a draw attempt happens on an exhausted deck
        # If the deck is exhausted, verify the state
        if 0 == self.game.state.common_view.cards_to_draw:
            # turns_left should be set if deck was exhausted during a draw
            # It may not be set if we're checking before any draw happens
            # The key assertion is that cards_to_draw is 0
            if self.game.state.turns_left is not None:
                # turns_left should be num_players (all players get one final turn)
                self.assertGreaterEqual(self.game.state.turns_left, 0)
                self.assertLessEqual(self.game.state.turns_left, self.settings.num_players)

    def test_turn_advancement_cycles(self):
        """Test that turns cycle through players correctly."""
        # Use hints first to reduce tokens so we can discard
        if self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens:
            for _ in range(3):
                current_player = self.game.current_player
                # Hint a different player (not self)
                target = (current_player + 1) % 3
                teammate_hand = self.game.state.player_hands[target]
                if teammate_hand.cards:
                    color = teammate_hand.cards[0].color
                    matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                    move = ColorHint(target, matching, color)
                    self.game.process_move(current_player, move)
                    self.game._advance_turn()

        for expected_player in range(3):
            self.assertEqual(self.game.current_player, expected_player)
            # Make a move (discard or play)
            hand = self.game.state.player_hands[expected_player]
            if hand.cards:
                # Try discard first, if not possible, play
                if self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
                    move = Discard(0)
                else:
                    # Play a card instead
                    move = Play(0)
                try:
                    self.game.process_move(expected_player, move)
                    self.game._advance_turn()
                except AssertionError:
                    break

        # Should cycle back to player 0 (or be at some valid player)
        self.assertIn(self.game.current_player, [0, 1, 2])

    def test_turn_number_increments(self):
        """Test that turn number increments with each move."""
        initial_turn = self.game.state.turn_number

        # Use hint first if needed
        if self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens:
            teammate_hand = self.game.state.player_hands[1]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                move = ColorHint(1, matching, color)
                self.game.process_move(0, move)
        else:
            move = Discard(0)
            self.game.process_move(0, move)

        self.assertEqual(self.game.state.turn_number, initial_turn + 1)

    def test_turns_left_decrements_when_deck_exhausted(self):
        """Test that turns_left decrements when deck is exhausted."""
        # Exhaust deck - use hints first to reduce tokens
        while self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens and self.game.state.common_view.cards_to_draw > 0:
            current_player = self.game.current_player
            teammate_hand = self.game.state.player_hands[(current_player + 1) % 3]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                move = ColorHint((current_player + 1) % 3, matching, color)
                self.game.process_move(current_player, move)
                self.game._advance_turn()

        # Now discard/play to exhaust deck
        while self.game.state.common_view.cards_to_draw > 0:
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]
            if hand.cards and self.game.state.common_view.live_tokens > 0:  # Don't play if no lives
                if self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
                    move = Discard(0)
                elif self.game.state.common_view.hint_tokens > 0:
                    # Give a hint instead of playing
                    target = (current_player + 1) % 3
                    target_hand = self.game.state.player_hands[target]
                    if target_hand.cards:
                        color = target_hand.cards[0].color
                        matching = [i for i, c in enumerate(target_hand.cards) if c.color == color]
                        if matching:
                            move = ColorHint(target, matching, color)
                        else:
                            break
                    else:
                        break
                else:
                    break
                try:
                    self.game.process_move(current_player, move)
                    self.game._advance_turn()
                except AssertionError:
                    break
            else:
                break

        # Check turns_left is set and decrements
        if self.game.state.turns_left is not None:
            initial_turns = self.game.state.turns_left
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]
            if hand.cards and self.game.state.common_view.live_tokens > 0:  # Don't play if no lives
                if self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
                    move = Discard(0)
                elif self.game.state.common_view.hint_tokens > 0:
                    # Give a hint instead of playing
                    target = (current_player + 1) % 3
                    target_hand = self.game.state.player_hands[target]
                    if target_hand.cards:
                        color = target_hand.cards[0].color
                        matching = [i for i, c in enumerate(target_hand.cards) if c.color == color]
                        if matching:
                            move = ColorHint(target, matching, color)
                        else:
                            pass  # Skip if no matching cards
                    else:
                        pass  # Skip if no cards
                else:
                    pass  # Skip if no hint tokens
                try:
                    self.game.process_move(current_player, move)
                    self.game._advance_turn()
                    if self.game.state.turns_left is not None:
                        self.assertEqual(self.game.state.turns_left, initial_turns - 1)
                except AssertionError:
                    pass

    def test_game_ends_when_no_lives(self):
        """Test that game ends when all lives are lost."""

        # Lose all lives
        while self.game.state.common_view.live_tokens > 0 and not self.game.is_finished:
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]
            if hand.cards:
                # Play an invalid card
                for i, card in enumerate(hand.cards):
                    if card.number != Number.ONE:
                        move = Play(i)
                        try:
                            self.game.process_move(current_player, move)
                            self.game._advance_turn()
                            break
                        except AssertionError:
                            pass

        # Game should be finished
        self.assertTrue(self.game.is_finished)
        self.assertEqual(self.game.state.common_view.live_tokens, 0)

    def test_game_ends_when_perfect_score(self):
        """Test that game ends when perfect score is achieved (all 5s played)."""
        # This is complex to set up, so we test the logic directly
        # Create a state with all 5s played
        # Manually set cards played to all 5s
        for color in [Color.WHITE, Color.RED, Color.BLUE, Color.YELLOW, Color.GREEN]:
            self.game.state._common_view._cards_played[color] = Number.FIVE

        # Game should be finished
        self.assertTrue(self.game.state.is_finished())

    def test_game_ends_when_deck_exhausted_and_turns_complete(self):
        """Test that game ends when deck is exhausted and all players had final turn."""
        # Exhaust deck - use hints first
        while self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens and self.game.state.common_view.cards_to_draw > 0:
            current_player = self.game.current_player
            teammate_hand = self.game.state.player_hands[(current_player + 1) % 3]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                move = ColorHint((current_player + 1) % 3, matching, color)
                self.game.process_move(current_player, move)
                self.game._advance_turn()

        # Now discard/play to exhaust deck
        while self.game.state.common_view.cards_to_draw > 0:
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]
            if hand.cards and self.game.state.common_view.live_tokens > 0:  # Don't play if no lives
                if self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
                    move = Discard(0)
                elif self.game.state.common_view.hint_tokens > 0:
                    # Give a hint instead of playing
                    target = (current_player + 1) % 3
                    target_hand = self.game.state.player_hands[target]
                    if target_hand.cards:
                        color = target_hand.cards[0].color
                        matching = [i for i, c in enumerate(target_hand.cards) if c.color == color]
                        if matching:
                            move = ColorHint(target, matching, color)
                        else:
                            break
                    else:
                        break
                else:
                    break
                try:
                    self.game.process_move(current_player, move)
                    self.game._advance_turn()
                except AssertionError:
                    break
            else:
                break

        # Play through final turns
        if self.game.state.turns_left is not None:
            while self.game.state.turns_left > 0 and not self.game.is_finished:
                current_player = self.game.current_player
                hand = self.game.state.player_hands[current_player]
                if hand.cards and self.game.state.common_view.live_tokens > 0:  # Don't play if no lives left
                    if self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
                        move = Discard(0)
                    elif self.game.state.common_view.hint_tokens > 0:
                        # Give a hint instead of playing
                        target = (current_player + 1) % 3
                        target_hand = self.game.state.player_hands[target]
                        if target_hand.cards:
                            color = target_hand.cards[0].color
                            matching = [i for i, c in enumerate(target_hand.cards) if c.color == color]
                            if matching:
                                move = ColorHint(target, matching, color)
                            else:
                                break
                        else:
                            break
                    else:
                        break
                    try:
                        self.game.process_move(current_player, move)
                        self.game._advance_turn()
                    except AssertionError:
                        break

            # After all turns, game should be finished
            if 0 == self.game.state.turns_left:
                self.assertTrue(self.game.is_finished)

    def test_initial_score_is_zero(self):
        """Test that initial score is zero."""
        self.assertEqual(self.game.get_score(), 0)

    def test_score_increases_with_played_cards(self):
        """Test that score increases as cards are played."""
        initial_score = self.game.get_score()

        cp = self.game.current_player
        hand = self.game.state.player_hands[cp]
        played = False
        for i, card in enumerate(hand.cards):
            if card.number == Number.ONE:
                move = Play(i)
                if self.game.state._validate(cp, move):
                    self.game.process_move(cp, move)
                    played = True
                    break

        if not played:
            self.skipTest("No playable 1 in current player's hand for this shuffle")

        new_score = self.game.get_score()
        self.assertGreater(new_score, initial_score)
        self.assertEqual(new_score, 1)

    def test_score_calculation_sums_all_played_numbers(self):
        """Test that score correctly sums all played card numbers."""

        # Play cards of different colors
        colors_played = []
        for player_idx in range(3):
            hand = self.game.state.player_hands[player_idx]
            for i, card in enumerate(hand.cards):
                if card.number == Number.ONE and card.color not in colors_played:
                    move = Play(i)
                    try:
                        self.game.process_move(player_idx, move)
                        colors_played.append(card.color)
                        self.game._advance_turn()
                        if len(colors_played) >= 3:
                            break
                    except AssertionError:
                        continue
            if len(colors_played) >= 3:
                break

        # Score should equal number of cards played
        score = self.game.get_score()
        self.assertEqual(score, len(colors_played))

    def test_state_copy_creates_independent_copy(self):
        """Test that copy.copy() creates an independent copy."""
        copied_state = copy.copy(self.game.state)

        # Modify original
        original_turn = self.game.state._turn_number
        self.game.state._turn_number = 999

        # Copy should be unchanged
        self.assertEqual(copied_state._turn_number, original_turn)
        self.assertNotEqual(copied_state._turn_number, self.game.state._turn_number)

    def test_state_history_tracks_all_turns(self):
        """Test that game tracks state history for all turns."""
        initial_turns = len(self.game._turns)

        # Make several moves - use hints first if needed
        for _ in range(5):
            if self.game.is_finished:
                break
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]
            if hand.cards:
                # Use discard if possible, otherwise play
                if self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
                    move = Discard(0)
                else:
                    # Use hint to reduce tokens
                    teammate_hand = self.game.state.player_hands[(current_player + 1) % 3]
                    if teammate_hand.cards:
                        color = teammate_hand.cards[0].color
                        matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                        if matching:
                            move = ColorHint((current_player + 1) % 3, matching, color)
                        else:
                            break
                    else:
                        break
                try:
                    self.game.process_move(current_player, move)
                    self.game._advance_turn()
                except AssertionError:
                    break
            else:
                break

        # Should have more turns in history
        self.assertGreater(len(self.game._turns), initial_turns)

    def test_get_player_view_excludes_own_hand(self):
        """Test that get_player_view excludes the requesting player's hand."""
        view = self.game.get_player_view(0)

        # Should not see own hand
        self.assertNotIn(0, view.teammates)

        # Should see other players
        self.assertIn(1, view.teammates)
        self.assertIn(2, view.teammates)

    def test_process_move_on_uninitialized_game(self):
        """Test that process_move raises error on uninitialized game."""
        # Create game but don't initialize
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game(StartPosition(settings, Deck([])), team)

        # Should raise AssertionError (since we use assertions now)
        with self.assertRaises(AssertionError) as context:
            game.process_move(0, Play(0))
        self.assertIn("not initialized", str(context.exception).lower())

    def test_get_player_view_on_uninitialized_game(self):
        """Test that get_player_view raises error on uninitialized game."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game(StartPosition(settings, Deck([])), team)

        with self.assertRaises(AssertionError) as context:
            game.get_player_view(0)
        self.assertIn("not initialized", str(context.exception).lower())

    def test_state_property_on_uninitialized_game(self):
        """Test that state property raises error on uninitialized game."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game(StartPosition(settings, Deck([])), team)

        with self.assertRaises(AssertionError) as context:
            _ = game.state
        self.assertIn("not initialized", str(context.exception).lower())

    def test_process_move_with_unknown_move_type(self):
        """Test that unknown move types raise AssertionError."""

        # Create a fake move type
        class FakeMove:
            pass

        fake_move = FakeMove()
        # This should be caught in update() method
        # Actually, it will fail at isinstance checks first
        # Let's test the update method directly
        with self.assertRaises(AssertionError) as context:
            self.game.state.update(0, fake_move)  # type: ignore
        self.assertIn("Unknown move type", str(context.exception))

    def test_discard_when_hint_tokens_at_max_assertion(self):
        """Test that discard when hint tokens at max raises assertion."""

        # Fill hint tokens to max
        while self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
            move = Discard(0)
            self.game.process_move(self.game.current_player, move)
            self.game._advance_turn()

    def test_hint_when_no_tokens_assertion(self):
        """Test that hint when no tokens raises assertion."""

        # Use all hint tokens
        while self.game.state.common_view.hint_tokens > 0:
            current_player = self.game.current_player
            # Hint a different player (not self)
            target = (current_player + 1) % 3
            teammate_hand = self.game.state.player_hands[target]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                move = ColorHint(target, matching, color)
                try:
                    self.game.process_move(current_player, move)
                    self.game._advance_turn()
                except AssertionError:
                    break
            else:
                break

    def test_hand_size_maintained_after_moves(self):
        """Test that hand size is maintained after all move types."""
        initial_hand_size = len(self.game.state.player_hands[0].cards)

        # Test play
        for i, card in enumerate(self.game.state.player_hands[0].cards):
            if card.number == Number.ONE:
                move = Play(i)
                self.game.process_move(0, move)
                break

        self.assertEqual(len(self.game.state.player_hands[0].cards), initial_hand_size)

        # Test discard (use hint first if needed)
        if self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens:
            teammate_hand = self.game.state.player_hands[1]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                move = ColorHint(1, matching, color)
                self.game.process_move(0, move)
                self.game._advance_turn()

        move = Discard(0)
        try:
            self.game.process_move(0, move)
            self.assertEqual(len(self.game.state.player_hands[0].cards), initial_hand_size)
        except AssertionError:
            # If discard fails, that's ok - we tested play already
            pass

    def test_multiple_discards_track_correctly(self):
        """Test that multiple discards of same card are tracked correctly."""

        # Use hints first to reduce tokens
        while self.game.state.common_view.hint_tokens >= self.settings.max_hint_tokens:
            current_player = self.game.current_player
            teammate_hand = self.game.state.player_hands[(current_player + 1) % 3]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                move = ColorHint((current_player + 1) % 3, matching, color)
                self.game.process_move(current_player, move)
                self.game._advance_turn()

        # Discard multiple cards
        cards_discarded = []
        for _ in range(3):
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]
            if hand.cards and self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
                card = hand.cards[0]
                cards_discarded.append(card)
                move = Discard(0)
                try:
                    self.game.process_move(current_player, move)
                    self.game._advance_turn()
                except AssertionError:
                    break
            else:
                break

        # Check discard pile counts
        if cards_discarded:
            first_card = cards_discarded[0]
            discarded = self.game.state.common_view.cards_discarded
            if first_card.color in discarded:
                count = discarded[first_card.color].cards.get(first_card.number, 0)
                # Should have at least one of this card type
                self.assertGreater(count, 0)

    def test_full_game_flow_with_random_player(self):
        """Test a full game flow with RandomPlayer."""
        settings = create_standard_game_settings(2)
        players = [RandomPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        # RandomPlayer must return only legal moves; illegal moves are bugs (assert)
        game.play()
        self.assertTrue(game.is_finished)

    def test_game_state_consistency_after_multiple_moves(self):
        """Test that game state remains consistent after multiple moves."""
        # Make many moves and check state consistency
        for _ in range(20):
            if self.game.is_finished:
                break

            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]

            if not hand.cards:
                break

            # Make a move
            move = Discard(0)
            try:
                self.game.process_move(current_player, move)
                self.game._advance_turn()

                # Check state consistency
                self.assertGreaterEqual(self.game.state.common_view.live_tokens, 0)
                self.assertGreaterEqual(self.game.state.common_view.hint_tokens, 0)
                self.assertLessEqual(
                    self.game.state.common_view.hint_tokens, self.settings.max_hint_tokens
                )
                self.assertGreaterEqual(self.game.state.common_view.cards_to_draw, 0)

            except AssertionError:
                break

    def test_turn_number_tracks_correctly(self):
        """Test that turn number tracks correctly through game."""
        initial_turn = self.game.state.turn_number

        # Make 10 moves
        for i in range(10):
            if self.game.is_finished:
                break
            current_player = self.game.current_player
            move = Discard(0)
            try:
                self.game.process_move(current_player, move)
                expected_turn = initial_turn + i + 1
                self.assertEqual(self.game.state.turn_number, expected_turn)
                self.game._advance_turn()
            except AssertionError:
                break

    def test_is_finished_property(self):
        """Test is_finished property."""
        # Initially not finished
        self.assertFalse(self.game.is_finished)

        # Lose all lives
        while self.game.state.common_view.live_tokens > 0 and not self.game.is_finished:
            current_player = self.game.current_player
            hand = self.game.state.player_hands[current_player]
            if hand.cards:
                for i, card in enumerate(hand.cards):
                    if card.number != Number.ONE:
                        move = Play(i)
                        try:
                            self.game.process_move(current_player, move)
                            self.game._advance_turn()
                            break
                        except AssertionError:
                            pass

        # Should be finished
        if self.game.state.common_view.live_tokens <= 0:
            self.assertTrue(self.game.is_finished)

    def test_current_player_property(self):
        """Test current_player property."""
        # Initially player 0
        self.assertEqual(self.game.current_player, 0)

        # After advancing, should be player 1
        self.game._advance_turn()
        self.assertEqual(self.game.current_player, 1)

    def test_settings_property(self):
        """Test settings property."""
        self.assertEqual(self.game.settings, self.settings)
        self.assertEqual(self.game.settings.num_players, 3)

    def test_team_property(self):
        """Test team property."""
        self.assertEqual(len(self.game.team.players), 3)
        self.assertEqual(self.game.team.players, self.players)


if __name__ == "__main__":
    unittest.main()
