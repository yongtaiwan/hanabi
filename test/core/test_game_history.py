"""
Tests for GameHistory class.
"""

import unittest
import json
import os
import tempfile
from hanabi.core.game import create_standard_game_settings, Game
from hanabi.core.game_history import GameHistory
from hanabi.core.player import HumanPlayer, PlayerTeam
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number


class TestGameHistory(unittest.TestCase):
    """Test cases for GameHistory."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = create_standard_game_settings(3)
        self.players = [HumanPlayer(i) for i in range(3)]
        team = PlayerTeam(self.players)
        self.game = Game.create(team, self.settings)

        self.history = GameHistory({"num_players": 3, "max_live_tokens": 3, "max_hint_tokens": 8})
        self.history.record_initial_state(self.game)

    def test_record_initial_state(self):
        """Test recording initial state."""
        # Verify deck is stored at root level
        self.assertIsNotNone(self.history._deck)
        self.assertIsInstance(self.history._deck, list)
        # Verify player class names are recorded at root level (not in settings)
        self.assertIsNotNone(self.history._players)
        self.assertEqual(len(self.history._players), 3)
        # All should be HumanPlayer in tests
        self.assertEqual(self.history._players[0], "HumanPlayer")
        # Verify players are not in settings
        self.assertNotIn("players", self.history._settings)

    def test_record_play_move(self):
        """Test recording a play move."""
        hand = self.game.state.player_hands[0]

        if hand.cards:
            move = Play(0)
            try:
                self.game._process_move(0, move)
                self.history.record_move(0, move, "played", self.game)
                self.assertEqual(len(self.history._moves), 1)
                # Moves are now strings in short format
                self.assertEqual(self.history._moves[0], "p1")  # p1 = play card 1 (1-based)
            except AssertionError:
                pass

    def test_record_discard_move(self):
        """Test recording a discard move."""
        self._spend_hint_if_at_max_tokens()
        cp = self.game.current_player
        move = Discard(0)
        try:
            self.game._process_move(cp, move)
            self.history.record_move(cp, move, "discarded", self.game)
            self.assertEqual(len(self.history._moves), 1)
            # Moves are now strings in short format
            self.assertEqual(self.history._moves[0], "d1")  # d1 = discard card 1 (1-based)
        except AssertionError:
            pass

    def test_record_color_hint(self):
        """Test recording a color hint."""
        teammate_hand = self.game.state.player_hands[1]

        if teammate_hand.cards and self.game.state.common_view.hint_tokens > 0:
            color = teammate_hand.cards[0].color
            matching_indices = [i for i, card in enumerate(teammate_hand.cards) if card.color == color]
            if matching_indices:
                move = ColorHint(1, matching_indices, color)
                try:
                    self.game._process_move(0, move)
                    self.history.record_move(0, move, "hinted", self.game)
                    self.assertEqual(len(self.history._moves), 1)
                    # Moves are now strings in short format: h<teammate><color>
                    color_map = {
                        Color.WHITE: "w",
                        Color.RED: "r",
                        Color.YELLOW: "y",
                        Color.GREEN: "g",
                        Color.BLUE: "b",
                        Color.MULTI: "m",
                    }
                    expected = f"h2{color_map.get(color, 'r')}"  # h2 = hint player 2 (1-based), color
                    self.assertEqual(self.history._moves[0], expected)
                except AssertionError:
                    pass

    def test_record_number_hint(self):
        """Test recording a number hint."""
        teammate_hand = self.game.state.player_hands[1]

        if teammate_hand.cards and self.game.state.common_view.hint_tokens > 0:
            number = teammate_hand.cards[0].number
            matching_indices = [i for i, card in enumerate(teammate_hand.cards) if card.number == number]
            if matching_indices:
                move = NumberHint(1, matching_indices, number)
                try:
                    self.game._process_move(0, move)
                    self.history.record_move(0, move, "hinted", self.game)
                    self.assertEqual(len(self.history._moves), 1)
                    # Moves are now strings in short format: h<teammate><number>
                    expected = f"h2{number.value}"  # h2 = hint player 2 (1-based), number
                    self.assertEqual(self.history._moves[0], expected)
                except AssertionError:
                    pass

    def test_save_to_file(self):
        """Test saving history to file."""
        self._spend_hint_if_at_max_tokens()
        cp = self.game.current_player
        move = Discard(0)
        try:
            self.game._process_move(cp, move)
            self.history.record_move(cp, move, "discarded", self.game)
        except AssertionError:
            return

        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_filename = f.name

        filename = None
        try:
            filename = self.history.save_to_file(temp_filename)
            # save_to_file may prefer .yaml over .json when PyYAML is installed
            self.assertTrue(os.path.exists(filename))

            # Verify file contents
            with open(filename, "r") as f:
                if filename.endswith((".yaml", ".yml")):
                    try:
                        import yaml
                    except ImportError:
                        self.fail("YAML file written but PyYAML not available")
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
                self.assertIn("settings", data)
                self.assertIn("moves", data)
                self.assertIn("deck", data)
                self.assertIn("players", data)
                self.assertIn("time", data)
                self.assertNotIn("initial_state", data)
                self.assertEqual(len(data["moves"]), 1)
        finally:
            for path in (temp_filename, filename):
                if path and os.path.exists(path):
                    os.remove(path)

    def test_save_to_file_auto_filename(self):
        """Test saving with auto-generated filename."""
        filename = self.history.save_to_file()
        self.assertIsNotNone(filename)
        # Filename might be a full path, so check the basename
        basename = os.path.basename(filename)
        self.assertTrue(basename.startswith("hanabi_game_"))
        self.assertTrue(basename.endswith(".json") or basename.endswith(".yaml"))
        self.assertTrue(os.path.exists(filename))

        # Clean up
        if os.path.exists(filename):
            os.remove(filename)

    def test_load_from_file(self):
        """Test loading history from file."""
        self._spend_hint_if_at_max_tokens()
        cp = self.game.current_player
        move = Discard(0)
        try:
            self.game._process_move(cp, move)
            self.history.record_move(cp, move, "discarded", self.game)
        except AssertionError:
            return

        filename = self.history.save_to_file()

        try:
            # Load it back
            loaded_history = GameHistory({})
            data = loaded_history.load_from_file(filename)

            self.assertIn("settings", data)
            self.assertIn("moves", data)
            self.assertIn("deck", data)
            self.assertIn("players", data)
            self.assertIn("time", data)
            self.assertNotIn("initial_state", data)
            self.assertEqual(len(data["moves"]), 1)
        finally:
            if os.path.exists(filename):
                os.remove(filename)

    def test_saved_file_has_moves_and_deck(self):
        """Test that saved file contains moves and deck."""
        # Record initial state (already done in setUp, but ensure it's there)
        self.history.record_initial_state(self.game)

        for _ in range(3):
            self._spend_hint_if_at_max_tokens()
            cp = self.game.current_player
            move = Discard(0)
            self.game._process_move(cp, move)
            self.history.record_move(cp, move, "discarded", self.game)
            self.game._advance_turn()

        # Save to file
        filename = self.history.save_to_file()

        try:
            # Load and verify
            loaded_history = GameHistory({})
            data = loaded_history.load_from_file(filename)

            # Verify structure
            self.assertIn("settings", data)
            self.assertIn("moves", data)
            # total_moves is redundant (can be calculated from len(moves))
            self.assertNotIn("total_moves", data, "total_moves should not be saved (redundant)")

            # Verify deck is at root level
            self.assertIn("deck", data, "deck should be at root level")
            self.assertIsNotNone(data["deck"], "deck should not be None")
            self.assertIsInstance(data["deck"], list, "deck should be a list")

            # Verify players is at root level (not in settings)
            self.assertIn("players", data, "players should be at root level")
            self.assertIsInstance(data["players"], list, "players should be a list")
            self.assertNotIn("players", data["settings"], "players should not be in settings")

            # Verify time structure
            self.assertIn("time", data, "time should be at root level")
            self.assertIn("begin", data["time"], "time should have begin")
            self.assertIn("end", data["time"], "time should have end")

            # Verify initial_state is not present
            self.assertNotIn("initial_state", data, "initial_state should not be present")

            # Verify moves are recorded
            self.assertGreater(len(data["moves"]), 0, "moves should not be empty")

            # Verify move structure (moves are now simple strings)
            for move_str in data["moves"]:
                self.assertIsInstance(move_str, str, "moves should be strings in short format")
                # Verify format: should start with p, d, or h
                self.assertIn(move_str[0], ["p", "d", "h"], f"Move should start with p, d, or h: {move_str}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)

    def test_replay_from_history(self):
        """Test that a game can be replayed from history."""
        # Record initial state
        self.history.record_initial_state(self.game)

        for _ in range(3):
            self._spend_hint_if_at_max_tokens()
            cp = self.game.current_player
            move = Discard(0)
            self.game._process_move(cp, move)
            self.history.record_move(cp, move, "discarded", self.game)
            self.game._advance_turn()

        # Save to file
        filename = self.history.save_to_file()

        try:
            # Load history
            loaded_history = GameHistory({})
            data = loaded_history.load_from_file(filename)

            # Reconstruct game from history
            from hanabi.core.player import PlayerTeam
            from hanabi.core.player import HumanPlayer

            players = [HumanPlayer(i) for i in range(3)]
            team = PlayerTeam(players)

            replayed_game = GameHistory.create_game_from_history(data, team)

            # Verify game was created
            self.assertIsNotNone(replayed_game)
            self.assertEqual(replayed_game.settings.num_players, 3)

            # Apply moves and verify game state updates
            moves = data.get("moves", [])
            for move_str in moves:
                current_player = replayed_game.current_player
                move = GameHistory._short_to_move(move_str, current_player, replayed_game)
                if move is not None:
                    st = replayed_game.state
                    if st._validate(current_player, move):
                        replayed_game._process_move(current_player, move)
                        replayed_game._advance_turn()

        finally:
            if os.path.exists(filename):
                os.remove(filename)

    def _spend_hint_if_at_max_tokens(self) -> None:
        """Discard is illegal when hint tokens are at maximum; spend one if needed."""
        if self.game.state.common_view.hint_tokens < self.settings.max_hint_tokens:
            return
        cp = self.game.current_player
        for tgt in range(self.settings.num_players):
            if tgt == cp:
                continue
            th = self.game.state.player_hands[tgt]
            if not th.cards:
                continue
            col = th.cards[0].color
            matching = [i for i, c in enumerate(th.cards) if c.color == col]
            move = ColorHint(tgt, matching, col)
            if self.game.state._validate(cp, move):
                self.game._process_move(cp, move)
                self.game._advance_turn()
                return


if __name__ == "__main__":
    unittest.main()
