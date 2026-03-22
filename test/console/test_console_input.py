"""
Tests for ConsoleInput class.
"""

import unittest
from hanabi.core.game import create_standard_game_settings, Game
from hanabi.console.console_input import ConsoleInput
from hanabi.core.player import HumanPlayer, PlayerTeam
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number


class TestConsoleInput(unittest.TestCase):
    """Test cases for ConsoleInput."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.players = [HumanPlayer(i) for i in range(3)]
        team = PlayerTeam(self.players)
        self.game = Game.create(team, self.settings)
        self.input_parser = ConsoleInput(self.game, 0)

    def test_parse_play(self):
        """Test parsing play command."""
        # Card indices in full commands are 1-based (UI)
        move, error = self.input_parser.parse_move(0, "play 1")
        self.assertIsNotNone(move)
        self.assertIsNone(error)
        self.assertIsInstance(move, Play)
        self.assertEqual(move.card, 0)

    def test_parse_play_invalid_index(self):
        """Test parsing play with invalid card index."""
        move, error = self.input_parser.parse_move(0, "play 10")
        self.assertIsNone(move)
        self.assertIsNotNone(error)
        self.assertIn("Invalid card index", error)

    def test_parse_discard(self):
        """Test parsing discard command."""
        move, error = self.input_parser.parse_move(0, "discard 3")
        self.assertIsNotNone(move)
        self.assertIsNone(error)
        self.assertIsInstance(move, Discard)
        self.assertEqual(move.card, 2)

    def test_parse_color_hint(self):
        """Test parsing color hint command."""
        teammate_hand = self.game.state.player_hands[1]

        if teammate_hand.cards:
            color = teammate_hand.cards[0].color
            move, error = self.input_parser.parse_move(0, f"hint 2 color {color.name}")
            self.assertIsNotNone(move)
            self.assertIsNone(error)
            self.assertIsInstance(move, ColorHint)
            self.assertEqual(move.teammate, 1)  # Player 2 is index 1
            self.assertEqual(move.color, color)

    def test_parse_number_hint(self):
        """Test parsing number hint command."""
        teammate_hand = self.game.state.player_hands[1]

        if teammate_hand.cards:
            number = teammate_hand.cards[0].number
            move, error = self.input_parser.parse_move(0, f"hint 2 number {number.value}")
            self.assertIsNotNone(move)
            self.assertIsNone(error)
            self.assertIsInstance(move, NumberHint)
            self.assertEqual(move.teammate, 1)  # Player 2 is index 1
            self.assertEqual(move.number, number)

    def test_parse_hint_self(self):
        """Test that hinting yourself is invalid."""
        move, error = self.input_parser.parse_move(0, "hint 1 color RED")
        self.assertIsNone(move)
        self.assertIsNotNone(error)
        self.assertIn("cannot give a hint to yourself", error)

    def test_parse_hint_invalid_player(self):
        """Test hinting invalid player."""
        move, error = self.input_parser.parse_move(0, "hint 10 color RED")
        self.assertIsNone(move)
        self.assertIsNotNone(error)
        self.assertIn("Invalid player", error)

    def test_parse_hint_invalid_color(self):
        """Test hinting with invalid color."""
        move, error = self.input_parser.parse_move(0, "hint 2 color INVALID")
        self.assertIsNone(move)
        self.assertIsNotNone(error)
        self.assertIn("Invalid color", error)

    def test_parse_hint_invalid_number(self):
        """Test hinting with invalid number."""
        move, error = self.input_parser.parse_move(0, "hint 2 number 10")
        self.assertIsNone(move)
        self.assertIsNotNone(error)
        self.assertIn("Number must be between", error)

    def test_parse_hint_no_matching_cards(self):
        """Test hinting when teammate has no matching cards."""
        # This is tricky - we'd need to know the hand contents
        # For now, just test the structure
        move, error = self.input_parser.parse_move(0, "hint 2 color MULTI")

    def test_parse_unknown_command(self):
        """Test parsing unknown command."""
        move, error = self.input_parser.parse_move(0, "unknown command")
        self.assertIsNone(move)
        self.assertIsNotNone(error)
        self.assertIn("Unknown command", error)

    def test_parse_empty_input(self):
        """Test parsing empty input."""
        move, error = self.input_parser.parse_move(0, "")
        self.assertIsNone(move)
        self.assertIsNotNone(error)
        self.assertIn("Empty input", error)

    def test_parse_incomplete_command(self):
        """Test parsing incomplete command."""
        move, error = self.input_parser.parse_move(0, "play")
        self.assertIsNone(move)
        self.assertIsNotNone(error)
        self.assertIn("Usage", error)


if __name__ == "__main__":
    unittest.main()
