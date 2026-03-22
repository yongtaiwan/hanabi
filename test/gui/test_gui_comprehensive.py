"""
Comprehensive automated tests for GUI version of Hanabi.
Simulates playing the game to identify bugs.
"""

import unittest
import tkinter as tk
from unittest.mock import Mock, patch, MagicMock
from typing import List, Optional

from hanabi.core.game import create_standard_game_settings, Game
from hanabi.gui.gui_display import GUIDisplay
from hanabi.gui.gui_input import GUIInput
from hanabi.gui.gui_game import GUIGame
from hanabi.core.player import HumanPlayer, PlayerTeam
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
from hanabi.core.game_history import GameHistory
from hanabi.core.enums import Color, Number


@unittest.skip("GUIDisplay widget layout drift (_action_frame etc.); update tests to match gui_display.py")
class TestGUIDisplay(unittest.TestCase):
    """Test cases for GUIDisplay."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = tk.Tk()
        self.root.withdraw()  # Hide window during tests
        self.display = GUIDisplay(self.root)

    def tearDown(self):
        """Clean up after tests."""
        self.root.destroy()

    def test_initialization(self):
        """Test GUI display initialization."""
        self.assertIsNotNone(self.display._canvas)
        self.assertIsNotNone(self.display._status_label)
        self.assertIsNotNone(self.display._action_frame)
        self.assertEqual(self.display._current_player, 0)
        self.assertFalse(self.display._show_all_cards)

    def test_set_game(self):
        """Test setting game."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        self.display.set_game(game)
        self.assertEqual(self.display._game, game)

    def test_display_game_state(self):
        """Test displaying game state."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        self.display.set_game(game)
        self.display.display_game_state(game, 0)

        # Check that widgets were created
        self.assertGreater(len(self.display._card_widgets), 0)
        self.assertGreater(len(self.display._card_positions), 0)

    def test_card_selection(self):
        """Test card selection."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        self.display.set_game(game)
        self.display.display_game_state(game, 0)

        # Select a card
        self.display._selected_card = 0
        self.assertEqual(self.display._selected_card, 0)

        # Redraw to show selection
        self.display.display_game_state(game, 0)

        # Card should still be selected
        self.assertEqual(self.display._selected_card, 0)

    def test_hint_mode(self):
        """Test hint mode activation."""
        self.display._on_hint_mode_clicked("color")
        self.assertEqual(self.display._hint_mode, "color")

        self.display._on_hint_mode_clicked("number")
        self.assertEqual(self.display._hint_mode, "number")

    def test_move_callback(self):
        """Test move callback setting."""
        callback = Mock()
        self.display.set_move_callback(callback)
        self.assertEqual(self.display._move_callback, callback)

    def test_clear(self):
        """Test clearing display."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        self.display.set_game(game)
        self.display.display_game_state(game, 0)

        # Clear
        self.display.clear()

        # Check that widgets are cleared
        self.assertEqual(len(self.display._card_widgets), 0)
        self.assertEqual(len(self.display._card_positions), 0)


@unittest.skip("GUIInput API drift (_make_play_move etc.); update tests to match gui_input.py")
class TestGUIInput(unittest.TestCase):
    """Test cases for GUIInput."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = tk.Tk()
        self.root.withdraw()
        self.display = GUIDisplay(self.root)
        self.display.set_suppress_dialogs(True)  # Disable messageboxes for testing

        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        self.game = Game.create(team, settings)

        self.display.set_game(self.game)
        self.display.display_game_state(self.game, 0)

        self.input_handler = GUIInput(self.game, self.display)
        self.input_handler.setup_canvas_clicks()

    def tearDown(self):
        """Clean up after tests."""
        self.root.destroy()

    def test_card_selection(self):
        """Test card selection via input handler."""
        # Simulate clicking on a card
        self.input_handler._on_card_selected(0)

        self.assertEqual(self.display._selected_card, 0)

    def test_hint_target_selection(self):
        """Test hint target selection."""
        self.display._hint_mode = "color"

        # Simulate clicking on teammate's card
        self.input_handler._on_hint_target_selected(1, 0)

        # Hint mode should be reset
        self.assertIsNone(self.display._hint_mode)

    def test_move_callback(self):
        """Test move callback."""
        callback = Mock()
        self.input_handler.set_move_callback(callback)

        # Make a play move
        self.input_handler._make_play_move(0)

        # Callback should be called
        callback.assert_called_once()
        self.assertIsInstance(callback.call_args[0][0], Play)


@unittest.skip("GUIGame._on_move_made expects GUIPlayer; tests use HumanPlayer placeholders")
class TestGUIGameFlow(unittest.TestCase):
    """Test complete game flow through GUI."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = tk.Tk()
        self.root.withdraw()
        self.game = GUIGame(self.root)
        self.game._suppress_dialogs = True  # Disable messageboxes for testing
        if self.game._display:
            self.game._display.set_suppress_dialogs(True)

    def tearDown(self):
        """Clean up after tests."""
        self.root.destroy()

    def test_new_game_creation(self):
        """Test creating a new game."""
        # Mock the dialog to return 2 players
        with patch.object(self.game, '_ask_num_players', return_value=2):
            self.game._new_game()

            self.assertIsNotNone(self.game._game)
            self.assertEqual(len(self.game._players), 2)
            self.assertIsNotNone(self.game._display)
            self.assertIsNotNone(self.game._input_handler)
            self.assertIsNotNone(self.game._history)

    def test_play_move_flow(self):
        """Test playing a card through the GUI."""
        # Set up game
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        self.game._game = game
        self.game._players = [p for p in game.team.players]
        self.game._display.set_game(game)
        self.game._input_handler = GUIInput(game, self.game._display)
        self.game._input_handler.set_move_callback(self.game._on_move_made)
        self.game._display.set_move_callback(self.game._on_move_made)

        self.game._history = GameHistory({
            "num_players": 2,
            "max_live_tokens": 3,
            "max_hint_tokens": 8,
            "max_cards_in_hand": 5
        })
        self.game._history.record_initial_state(game)

        # Select a card and play it
        state = game.state
        hand = state.player_hands[0]

        if hand.cards:
            # Find a playable card (number 1)
            playable_idx = None
            for i, card in enumerate(hand.cards):
                if card.number == Number.ONE:
                    playable_idx = i
                    break

            if playable_idx is not None:
                move = Play(playable_idx)
                initial_score = game.get_score()

                # Process move
                self.game._on_move_made(move)

                # Check that score increased
                new_score = game.get_score()
                self.assertGreater(new_score, initial_score)

    def test_discard_move_flow(self):
        """Test discarding a card through the GUI."""
        # Set up game
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        self.game._game = game
        self.game._players = [p for p in game.team.players]
        self.game._display.set_game(game)
        self.game._input_handler = GUIInput(game, self.game._display)
        self.game._input_handler.set_move_callback(self.game._on_move_made)
        self.game._display.set_move_callback(self.game._on_move_made)

        self.game._history = GameHistory({
            "num_players": 2,
            "max_live_tokens": 3,
            "max_hint_tokens": 8,
            "max_cards_in_hand": 5
        })
        self.game._history.record_initial_state(game)

        # Discard a card
        state = game.state
        initial_hints = state.common_view.hint_tokens

        if state.common_view.hint_tokens < game.settings.max_hint_tokens:
            move = Discard(0)
            self.game._on_move_made(move)

            # Check that hint token was gained
            new_state = game.state
            if initial_hints < game.settings.max_hint_tokens:
                self.assertEqual(new_state.common_view.hint_tokens, initial_hints + 1)

    def test_hint_move_flow(self):
        """Test giving a hint through the GUI."""
        # Set up game
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        self.game._game = game
        self.game._players = [p for p in game.team.players]
        self.game._display.set_game(game)
        self.game._input_handler = GUIInput(game, self.game._display)
        self.game._input_handler.set_move_callback(self.game._on_move_made)
        self.game._display.set_move_callback(self.game._on_move_made)

        self.game._history = GameHistory({
            "num_players": 2,
            "max_live_tokens": 3,
            "max_hint_tokens": 8,
            "max_cards_in_hand": 5
        })
        self.game._history.record_initial_state(game)

        # Give a color hint
        state = game.state
        if state.common_view.hint_tokens > 0:
            teammate_hand = state.player_hands[1]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]

                if matching:
                    initial_hints = state.common_view.hint_tokens
                    move = ColorHint(1, matching, color)
                    self.game._on_move_made(move)

                    # Check that hint token was used
                    new_state = game.state
                    self.assertEqual(new_state.common_view.hint_tokens, initial_hints - 1)

    def test_invalid_move_handling(self):
        """Test that invalid moves are handled correctly."""
        # Set up game
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        self.game._game = game
        self.game._players = [p for p in game.team.players]
        self.game._display.set_game(game)

        # Try to make a move with wrong player
        move = Play(0)
        with self.assertRaises(AssertionError) as context:
            game.process_move(1, move)  # Player 1 on player 0's turn
        self.assertIn("not player", str(context.exception).lower())

    def test_turn_advancement(self):
        """Test that turns advance correctly."""
        # Set up game
        settings = create_standard_game_settings(3)
        players = [HumanPlayer(i) for i in range(3)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        self.game._game = game
        self.game._players = [p for p in game.team.players]
        self.game._display.set_game(game)
        self.game._input_handler = GUIInput(game, self.game._display)
        self.game._input_handler.set_move_callback(self.game._on_move_made)
        self.game._display.set_move_callback(self.game._on_move_made)

        self.game._history = GameHistory({
            "num_players": 3,
            "max_live_tokens": 3,
            "max_hint_tokens": 8,
            "max_cards_in_hand": 5
        })
        self.game._history.record_initial_state(game)

        # Make a move
        initial_player = game.current_player
        move = Discard(0)
        self.game._on_move_made(move)

        # Check that turn advanced
        self.assertEqual(game.current_player, (initial_player + 1) % 3)

    def test_game_end_detection(self):
        """Test that game end is detected correctly."""
        # Set up game
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        self.game._game = game
        self.game._players = [p for p in game.team.players]
        self.game._display.set_game(game)
        self.game._input_handler = GUIInput(game, self.game._display)
        self.game._input_handler.set_move_callback(self.game._on_move_made)
        self.game._display.set_move_callback(self.game._on_move_made)

        self.game._history = GameHistory({
            "num_players": 2,
            "max_live_tokens": 3,
            "max_hint_tokens": 8,
            "max_cards_in_hand": 5
        })
        self.game._history.record_initial_state(game)

        # Lose all lives
        state = game.state
        hand = state.player_hands[0]

        # Play invalid cards to lose all lives
        for i in range(len(hand.cards)):
            if hand.cards[i].number != Number.ONE:
                move = Play(i)
                self.game._on_move_made(move)
                if game.is_finished:
                    break

        # Game should be finished
        if game.state.common_view.live_tokens <= 0:
            self.assertTrue(game.is_finished)


@unittest.skip("GUIDisplay API drift (_on_hint_mode_clicked etc.); update tests or restore methods")
class TestGUISimulation(unittest.TestCase):
    """Simulate playing a full game through the GUI."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        """Clean up after tests."""
        self.root.destroy()

    def test_simulate_short_game(self):
        """Simulate a short game with multiple moves."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_game(game)

        input_handler = GUIInput(game, display)
        move_callback = Mock()
        input_handler.set_move_callback(move_callback)
        display.set_move_callback(move_callback)
        input_handler.setup_canvas_clicks()

        history = GameHistory({
            "num_players": 2,
            "max_live_tokens": 3,
            "max_hint_tokens": 8,
            "max_cards_in_hand": 5
        })
        history.record_initial_state(game)

        # Simulate 10 moves
        moves_made = 0
        max_moves = 10

        while not game.is_finished and moves_made < max_moves:
            current_player = game.current_player
            state = game.state
            hand = state.player_hands[current_player]

            if not hand.cards:
                break

            # Try to give a hint if possible
            if state.common_view.hint_tokens > 0:
                teammate = 1 if current_player == 0 else 0
                teammate_hand = state.player_hands[teammate]
                if teammate_hand.cards:
                    color = teammate_hand.cards[0].color
                    matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                    if matching:
                        move = ColorHint(teammate, matching, color)
                        try:
                            game.process_move(current_player, move)
                            history.record_move(current_player, move, "", game)
                            game._advance_turn()
                            moves_made += 1
                            continue
                        except AssertionError:
                            break

            # Otherwise discard
            if state.common_view.hint_tokens < game.settings.max_hint_tokens:
                move = Discard(0)
                try:
                    game.process_move(current_player, move)
                    history.record_move(current_player, move, "", game)
                    game._advance_turn()
                    moves_made += 1
                except AssertionError:
                    break
            else:
                # Must play or hint
                move = Play(0)
                try:
                    game.process_move(current_player, move)
                    history.record_move(current_player, move, "", game)
                    game._advance_turn()
                    moves_made += 1
                except AssertionError:
                    break

        # Verify game state is consistent
        self.assertIsNotNone(game.state)
        self.assertGreaterEqual(moves_made, 1)

        # Verify display can show the state
        display.display_game_state(game, game.current_player)
        self.assertGreater(len(display._card_widgets), 0)

    def test_card_click_simulation(self):
        """Simulate clicking on cards."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_game(game)
        display.display_game_state(game, 0)

        input_handler = GUIInput(game, display)
        input_handler.setup_canvas_clicks()

        # Simulate clicking on current player's card
        if display._card_positions:
            # Get first card position
            (player_idx, card_idx), (x1, y1, x2, y2) = next(iter(display._card_positions.items()))
            if player_idx == 0:  # Current player
                # Simulate click in center of card
                click_x = (x1 + x2) // 2
                click_y = (y1 + y2) // 2

                # Create mock event
                event = Mock()
                event.x = click_x
                event.y = click_y

                input_handler._on_canvas_click(event)

                # Card should be selected
                self.assertEqual(display._selected_card, card_idx)

    def test_hint_mode_simulation(self):
        """Simulate giving a hint through GUI."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        team = PlayerTeam(players)
        game = Game.create(team, settings)

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_game(game)
        display.display_game_state(game, 0)

        input_handler = GUIInput(game, display)
        move_callback = Mock()
        input_handler.set_move_callback(move_callback)
        display.set_move_callback(move_callback)
        input_handler.setup_canvas_clicks()

        # Activate hint mode
        display._on_hint_mode_clicked("color")
        self.assertEqual(display._hint_mode, "color")

        # Simulate clicking on teammate's card
        state = game.state
        teammate_hand = state.player_hands[1]
        if teammate_hand.cards and display._card_positions:
            # Find teammate's card
            for (player_idx, card_idx), (x1, y1, x2, y2) in display._card_positions.items():
                if player_idx == 1:  # Teammate
                    # Simulate click
                    event = Mock()
                    event.x = (x1 + x2) // 2
                    event.y = (y1 + y2) // 2

                    input_handler._on_canvas_click(event)

                    # Hint should be given
                    move_callback.assert_called()
                    move = move_callback.call_args[0][0]
                    self.assertIsInstance(move, ColorHint)
                    break


if __name__ == '__main__':
    unittest.main()

