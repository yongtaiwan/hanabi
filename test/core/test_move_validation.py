"""
Comprehensive unit tests for move validation logic in GameState.

Tests all validation rules for Play, Discard, ColorHint, and NumberHint moves.
"""

import unittest
from hanabi.core.game import Game, GameState, create_standard_game_settings, Deck, StartPosition, CommonView, Hand
from hanabi.core.player import PlayerTeam, HumanPlayer
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
from hanabi.core.card import Card
from hanabi.core.enums import Color, Number


class TestMoveValidation(unittest.TestCase):
    """Test move validation logic."""

    def setUp(self):
        """Set up a test game state."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(0), HumanPlayer(1)]
        team = PlayerTeam(players)
        self.game = Game.create(team, settings)
        self.state = self.game.state

    def test_play_valid_card(self):
        """Test that playing a valid card passes validation."""
        # Get player 0's hand
        hand = self.state.player_hands[0]
        if len(hand.cards) > 0:
            # Try to play the first card (may or may not be valid, but should pass basic validation)
            move = Play(0)
            # Basic validation should pass (card index valid, not discarding when hints full)
            result = self.state._validate_card_move(0, move)
            # Should pass basic card move validation (actual play validity checked in _update_play)
            self.assertTrue(result)

    def test_play_invalid_card_index(self):
        """Test that playing with invalid card index fails."""
        hand = self.state.player_hands[0]
        invalid_index = len(hand.cards)  # Out of bounds
        move = Play(invalid_index)
        result = self.state._validate_card_move(0, move)
        self.assertFalse(result)

    def test_play_negative_card_index(self):
        """Test that playing with negative card index fails."""
        move = Play(-1)
        result = self.state._validate_card_move(0, move)
        self.assertFalse(result)

    def test_discard_when_hints_full(self):
        """Test that discarding when hint tokens are at maximum fails."""
        # Set hint tokens to maximum
        settings = self.state.settings
        max_hints = settings.max_hint_tokens

        # Create a state with max hint tokens
        new_common_view = CommonView(
            live_tokens=self.state.common_view.live_tokens,
            hint_tokens=max_hints,
            cards_to_draw=self.state.common_view.cards_to_draw,
            cards_discarded=self.state.common_view.cards_discarded,
            cards_played=self.state.common_view.cards_played,
        )

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=new_common_view,
            player_hands=self.state.player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        hand = new_state.player_hands[0]
        if len(hand.cards) > 0:
            move = Discard(0)
            result = new_state._validate_card_move(0, move)
            self.assertFalse(result, "Should not be able to discard when hint tokens are at maximum")

    def test_discard_when_hints_not_full(self):
        """Test that discarding when hint tokens are not at maximum passes."""
        # Ensure hint tokens are not at maximum
        if self.state.common_view.hint_tokens < self.state.settings.max_hint_tokens:
            hand = self.state.player_hands[0]
            if len(hand.cards) > 0:
                move = Discard(0)
                result = self.state._validate_card_move(0, move)
                self.assertTrue(result)

    def test_hint_no_tokens(self):
        """Test that hinting with no hint tokens fails."""
        # Create a state with no hint tokens
        new_common_view = CommonView(
            live_tokens=self.state.common_view.live_tokens,
            hint_tokens=0,
            cards_to_draw=self.state.common_view.cards_to_draw,
            cards_discarded=self.state.common_view.cards_discarded,
            cards_played=self.state.common_view.cards_played,
        )

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=new_common_view,
            player_hands=self.state.player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Try to hint player 1 from player 0
        teammate_hand = new_state.player_hands[1]
        if len(teammate_hand.cards) > 0:
            # Get the color of the first card
            card_color = teammate_hand.cards[0].color
            move = ColorHint(1, [0], card_color)
            result = new_state._validate_hint(0, move)
            self.assertFalse(result, "Should not be able to hint with no hint tokens")

    def test_hint_yourself(self):
        """Test that hinting yourself fails."""
        teammate_hand = self.state.player_hands[0]
        if len(teammate_hand.cards) > 0:
            card_color = teammate_hand.cards[0].color
            move = ColorHint(0, [0], card_color)  # Player 0 hinting themselves
            result = self.state._validate_hint(0, move)
            self.assertFalse(result, "Should not be able to hint yourself")

    def test_hint_invalid_teammate(self):
        """Test that hinting with invalid teammate index fails."""
        move = ColorHint(-1, [0], Color.RED)  # Negative index
        result = self.state._validate_hint(0, move)
        self.assertFalse(result)

        move = ColorHint(10, [0], Color.RED)  # Out of bounds
        result = self.state._validate_hint(0, move)
        self.assertFalse(result)

    def test_hint_empty_cards(self):
        """Test that hinting with empty cards list fails."""
        move = ColorHint(1, [], Color.RED)
        result = self.state._validate_hint(0, move)
        self.assertFalse(result, "Should not be able to hint with empty cards list")

    def test_color_hint_must_include_all_matching_cards(self):
        """Test that a color hint must include ALL cards of that color."""
        # Create a hand with multiple cards of the same color
        red_cards = [Card(Color.RED, Number.ONE), Card(Color.RED, Number.TWO), Card(Color.BLUE, Number.ONE)]
        hand = Hand(red_cards)

        # Create a game state with this hand for player 1
        player_hands = [self.state.player_hands[0], hand]

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=self.state.common_view,
            player_hands=player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Try to hint only one red card (should fail - must hint both)
        move = ColorHint(1, [0], Color.RED)  # Only hinting first red card
        result = new_state._validate_hint(0, move)
        self.assertFalse(result, "Color hint must include ALL matching cards")

        # Hinting both red cards should pass
        move = ColorHint(1, [0, 1], Color.RED)  # Hinting both red cards
        result = new_state._validate_hint(0, move)
        self.assertTrue(result, "Color hint with all matching cards should pass")

    def test_number_hint_must_include_all_matching_cards(self):
        """Test that a number hint must include ALL cards of that number."""
        # Create a hand with multiple cards of the same number
        one_cards = [Card(Color.RED, Number.ONE), Card(Color.BLUE, Number.ONE), Card(Color.YELLOW, Number.TWO)]
        hand = Hand(one_cards)

        # Create a game state with this hand for player 1
        player_hands = [self.state.player_hands[0], hand]

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=self.state.common_view,
            player_hands=player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Try to hint only one "1" card (should fail - must hint both)
        move = NumberHint(1, [0], Number.ONE)  # Only hinting first "1" card
        result = new_state._validate_hint(0, move)
        self.assertFalse(result, "Number hint must include ALL matching cards")

        # Hinting both "1" cards should pass
        move = NumberHint(1, [0, 1], Number.ONE)  # Hinting both "1" cards
        result = new_state._validate_hint(0, move)
        self.assertTrue(result, "Number hint with all matching cards should pass")

    def test_color_hint_wrong_color(self):
        """Test that a color hint with wrong color fails."""
        # Create a hand with blue cards
        blue_cards = [Card(Color.BLUE, Number.ONE), Card(Color.BLUE, Number.TWO)]
        hand = Hand(blue_cards)

        player_hands = [self.state.player_hands[0], hand]

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=self.state.common_view,
            player_hands=player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Try to hint red when hand has blue
        move = ColorHint(1, [0, 1], Color.RED)  # Hinting red on blue cards
        result = new_state._validate_hint(0, move)
        self.assertFalse(result, "Color hint must match actual card colors")

    def test_number_hint_wrong_number(self):
        """Test that a number hint with wrong number fails."""
        # Create a hand with "2" cards
        two_cards = [Card(Color.RED, Number.TWO), Card(Color.BLUE, Number.TWO)]
        hand = Hand(two_cards)

        player_hands = [self.state.player_hands[0], hand]

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=self.state.common_view,
            player_hands=player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Try to hint "1" when hand has "2"
        move = NumberHint(1, [0, 1], Number.ONE)  # Hinting "1" on "2" cards
        result = new_state._validate_hint(0, move)
        self.assertFalse(result, "Number hint must match actual card numbers")

    def test_color_hint_invalid_card_index(self):
        """Test that a color hint with invalid card index fails."""
        teammate_hand = self.state.player_hands[1]
        invalid_index = len(teammate_hand.cards)  # Out of bounds

        move = ColorHint(1, [invalid_index], Color.RED)
        result = self.state._validate_hint(0, move)
        self.assertFalse(result, "Color hint with invalid card index should fail")

    def test_number_hint_invalid_card_index(self):
        """Test that a number hint with invalid card index fails."""
        teammate_hand = self.state.player_hands[1]
        invalid_index = len(teammate_hand.cards)  # Out of bounds

        move = NumberHint(1, [invalid_index], Number.ONE)
        result = self.state._validate_hint(0, move)
        self.assertFalse(result, "Number hint with invalid card index should fail")

    def test_color_hint_single_matching_card(self):
        """Test that a color hint with a single matching card passes."""
        # Create a hand with one red card
        red_card = [Card(Color.RED, Number.ONE)]
        hand = Hand(red_card)

        player_hands = [self.state.player_hands[0], hand]

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=self.state.common_view,
            player_hands=player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Hint the single red card
        move = ColorHint(1, [0], Color.RED)
        result = new_state._validate_hint(0, move)
        self.assertTrue(result, "Color hint with single matching card should pass")

    def test_number_hint_single_matching_card(self):
        """Test that a number hint with a single matching card passes."""
        # Create a hand with one "1" card
        one_card = [Card(Color.RED, Number.ONE)]
        hand = Hand(one_card)

        player_hands = [self.state.player_hands[0], hand]

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=self.state.common_view,
            player_hands=player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Hint the single "1" card
        move = NumberHint(1, [0], Number.ONE)
        result = new_state._validate_hint(0, move)
        self.assertTrue(result, "Number hint with single matching card should pass")

    def test_color_hint_no_matching_cards(self):
        """Test that a color hint when there are no matching cards fails."""
        # Create a hand with no red cards
        blue_cards = [Card(Color.BLUE, Number.ONE), Card(Color.BLUE, Number.TWO)]
        hand = Hand(blue_cards)

        player_hands = [self.state.player_hands[0], hand]

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=self.state.common_view,
            player_hands=player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Try to hint red when there are no red cards
        move = ColorHint(1, [0], Color.RED)  # Can't hint red on blue cards
        result = new_state._validate_hint(0, move)
        self.assertFalse(result, "Color hint must have matching cards")

    def test_number_hint_no_matching_cards(self):
        """Test that a number hint when there are no matching cards fails."""
        # Create a hand with no "1" cards
        two_cards = [Card(Color.RED, Number.TWO), Card(Color.BLUE, Number.TWO)]
        hand = Hand(two_cards)

        player_hands = [self.state.player_hands[0], hand]

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=self.state.common_view,
            player_hands=player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Try to hint "1" when there are no "1" cards
        move = NumberHint(1, [0], Number.ONE)  # Can't hint "1" on "2" cards
        result = new_state._validate_hint(0, move)
        self.assertFalse(result, "Number hint must have matching cards")

    def test_color_hint_extra_cards(self):
        """Test that a color hint with extra non-matching cards fails."""
        # Create a hand with one red and one blue card
        mixed_cards = [Card(Color.RED, Number.ONE), Card(Color.BLUE, Number.ONE)]
        hand = Hand(mixed_cards)

        player_hands = [self.state.player_hands[0], hand]

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=self.state.common_view,
            player_hands=player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Try to hint red but include the blue card too
        move = ColorHint(1, [0, 1], Color.RED)  # Hinting red but including blue card
        result = new_state._validate_hint(0, move)
        self.assertFalse(result, "Color hint must only include matching cards")

    def test_number_hint_extra_cards(self):
        """Test that a number hint with extra non-matching cards fails."""
        # Create a hand with one "1" and one "2" card
        mixed_cards = [Card(Color.RED, Number.ONE), Card(Color.BLUE, Number.TWO)]
        hand = Hand(mixed_cards)

        player_hands = [self.state.player_hands[0], hand]

        new_state = GameState(
            start_position=self.state.start_position,
            common_view=self.state.common_view,
            player_hands=player_hands,
            draw_deck_index=self.state.draw_deck_index,
            turn_number=self.state.turn_number,
            current_player=self.state.current_player,
            turns_left=self.state.turns_left,
        )

        # Try to hint "1" but include the "2" card too
        move = NumberHint(1, [0, 1], Number.ONE)  # Hinting "1" but including "2" card
        result = new_state._validate_hint(0, move)
        self.assertFalse(result, "Number hint must only include matching cards")


if __name__ == "__main__":
    unittest.main()
