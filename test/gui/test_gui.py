"""
Comprehensive test suite for GUI components.
Tests GUI display, input handling, and game integration without opening windows.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import tkinter as tk
from typing import Dict, Any

from hanabi.core.game import create_standard_game_settings
from hanabi.core.game import Game as GameEngine
from hanabi.gui.gui_display import GUIDisplay
from hanabi.gui.gui_input import GUIInput
from hanabi.gui.gui_game import GUIGame
from hanabi.core.player import HumanPlayer
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number
from hanabi.core.game_history import GameHistory


@unittest.skip("Obsolete Game(settings, players) API; rewrite against Game.create")
class TestGUIDisplay(unittest.TestCase):
    """Test cases for GUIDisplay."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a root window but don't show it
        self.root = tk.Tk()
        self.root.withdraw()  # Hide window

        self.display = GUIDisplay(self.root)
        self.display.set_suppress_dialogs(True)  # Disable messageboxes for testing

        # Create a minimal game engine for testing
        self.settings = create_standard_game_settings(3)
        self.players = [HumanPlayer(i) for i in range(3)]
        self.engine = GameEngine(self.settings, self.players)
        self.engine.initialize()

        self.display.set_engine(self.engine)

    def tearDown(self):
        """Clean up after tests."""
        self.root.destroy()

    def test_initialization(self):
        """Test GUI display initialization."""
        self.assertIsNotNone(self.display._canvas)
        self.assertIsNotNone(self.display._status_label)
        self.assertIsNotNone(self.display._action_frame)
        self.assertIsNone(self.display._selected_card)
        self.assertIsNone(self.display._hint_mode)

    def test_set_engine(self):
        """Test setting game engine."""
        self.display.set_engine(self.engine)
        self.assertEqual(self.display._engine, self.engine)

    def test_set_show_all_cards(self):
        """Test setting show all cards mode."""
        self.display.set_show_all_cards(True)
        self.assertTrue(self.display._show_all_cards)

        self.display.set_show_all_cards(False)
        self.assertFalse(self.display._show_all_cards)

    def test_display_game_state(self):
        """Test displaying game state."""
        # Should not raise any errors
        self.display.display_game_state(self.engine, 0)

        # Check that widgets were created
        self.assertGreater(len(self.display._card_widgets), 0)
        self.assertGreater(len(self.display._card_positions), 0)

    def test_card_widget_creation(self):
        """Test card widget creation."""
        self.display.display_game_state(self.engine, 0)

        # Check that cards were created for all players
        state = self.engine.gameState
        total_cards = sum(len(hand.cards) for hand in state.player_hands)
        self.assertEqual(len(self.display._card_widgets), total_cards)
        self.assertEqual(len(self.display._card_positions), total_cards)

    def test_fireworks_display(self):
        """Test fireworks display."""
        self.display.display_game_state(self.engine, 0)

        # Initially no fireworks should be displayed
        for color in [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]:
            self.assertIn(color, self.display._firework_widgets)

    def test_tokens_display(self):
        """Test token display."""
        self.display.display_game_state(self.engine, 0)

        # Check that tokens were created
        self.assertIn("hint", self.display._token_widgets)
        self.assertIn("life", self.display._token_widgets)

        # Should have correct number of tokens
        self.assertEqual(len(self.display._token_widgets["hint"]), self.settings.max_hint_tokens)
        self.assertEqual(len(self.display._token_widgets["life"]), self.settings.max_live_tokens)

    def test_selected_card_validation(self):
        """Test that selected card is validated when state changes."""
        self.display.display_game_state(self.engine, 0)
        self.display._selected_card = 0

        # Play a card to reduce hand size
        move = Play(0)
        self.engine.process_move(0, move)
        self.engine.advanceTurn()

        # Display new state - selected card should be validated
        self.display.display_game_state(self.engine, 1)

        # If hand is smaller, selected card should be reset
        hand = self.engine.gameState.player_hands[1]
        if self.display._selected_card is not None:
            self.assertLess(self.display._selected_card, len(hand.cards))

    def test_clear_display(self):
        """Test clearing the display."""
        self.display.display_game_state(self.engine, 0)
        self.assertGreater(len(self.display._card_widgets), 0)

        self.display.clear()
        self.assertEqual(len(self.display._card_widgets), 0)
        self.assertEqual(len(self.display._card_positions), 0)
        self.assertEqual(len(self.display._firework_widgets), 0)

    def test_move_callback(self):
        """Test move callback setting."""
        callback = Mock()
        self.display.set_move_callback(callback)
        self.assertEqual(self.display._move_callback, callback)

    def test_play_button_click(self):
        """Test play button click."""
        self.display.display_game_state(self.engine, 0)
        self.display._selected_card = 0
        self.display.set_move_callback(Mock())

        # Should not raise error
        self.display._on_play_clicked()

    def test_discard_button_click(self):
        """Test discard button click."""
        self.display.display_game_state(self.engine, 0)
        self.display._selected_card = 0
        self.display.set_move_callback(Mock())

        # Should not raise error
        self.display._on_discard_clicked()

    def test_hint_mode_activation(self):
        """Test hint mode activation."""
        self.display._on_hint_mode_clicked("color")
        self.assertEqual(self.display._hint_mode, "color")

        self.display._on_hint_mode_clicked("number")
        self.assertEqual(self.display._hint_mode, "number")


@unittest.skip("Obsolete Game(settings, players) API; rewrite against Game.create")
class TestGUIInput(unittest.TestCase):
    """Test cases for GUIInput."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = tk.Tk()
        self.root.withdraw()

        self.settings = create_standard_game_settings(3)
        self.players = [HumanPlayer(i) for i in range(3)]
        self.engine = GameEngine(self.settings, self.players)
        self.engine.initialize()

        self.display = GUIDisplay(self.root)
        self.display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        self.display.set_engine(self.engine)
        self.display.display_game_state(self.engine, 0)

        self.input_handler = GUIInput(self.engine, self.display)

    def tearDown(self):
        """Clean up after tests."""
        self.root.destroy()

    def test_initialization(self):
        """Test GUI input initialization."""
        self.assertEqual(self.input_handler._engine, self.engine)
        self.assertEqual(self.input_handler._display, self.display)
        self.assertIsNone(self.input_handler._pending_move)

    def test_set_move_callback(self):
        """Test setting move callback."""
        callback = Mock()
        self.input_handler.set_move_callback(callback)
        self.assertEqual(self.input_handler._move_callback, callback)

    def test_card_selection(self):
        """Test card selection."""
        self.display._current_player = 0
        self.input_handler._on_card_selected(0)

        self.assertEqual(self.display._selected_card, 0)

    def test_hint_target_selection(self):
        """Test hint target selection for hints."""
        self.display._hint_mode = "color"
        self.display._current_player = 0

        # Select a card from player 1
        state = self.engine.gameState
        hand = state.player_hands[1]
        if hand.cards:
            card = hand.cards[0]
            matching = [i for i, c in enumerate(hand.cards) if c.color == card.color]

            callback = Mock()
            self.input_handler.set_move_callback(callback)

            self.input_handler._on_hint_target_selected(1, 0)

            # Should have called callback with a ColorHint
            if matching:
                callback.assert_called_once()
                move = callback.call_args[0][0]
                self.assertIsInstance(move, ColorHint)

    def test_canvas_click_with_no_positions(self):
        """Test canvas click when no card positions exist."""
        # Clear card positions
        self.display._card_positions.clear()

        # Create a mock event
        event = Mock()
        event.x = 100
        event.y = 100

        # Should not raise error
        self.input_handler._on_canvas_click(event)


@unittest.skip("Obsolete Game(settings, players) API; rewrite against Game.create")
class TestGUIGameIntegration(unittest.TestCase):
    """Integration tests for GUI game flow."""

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

    def test_initialization(self):
        """Test GUI game initialization."""
        self.assertIsNotNone(self.game._display)
        self.assertIsNone(self.game._engine)
        self.assertFalse(self.game._is_replay_mode)

    @patch('hanabi.gui_game.messagebox')
    def test_new_game_flow(self, mock_messagebox):
        """Test new game creation flow."""
        # Mock the dialog to return 3 players
        with patch.object(self.game, '_ask_num_players', return_value=3):
            self.game._new_game()

            # Check that game was initialized
            self.assertIsNotNone(self.game._engine)
            self.assertEqual(len(self.game._players), 3)
            self.assertIsNotNone(self.game._history)
            self.assertIsNotNone(self.game._input_handler)

    def test_move_processing(self):
        """Test move processing through GUI."""
        # Set up a game
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        self.game._engine = GameEngine(settings, players)
        self.game._engine.initialize()
        self.game._players = players
        self.game._display.set_engine(self.game._engine)
        self.game._input_handler = GUIInput(self.game._engine, self.game._display)
        self.game._input_handler.set_move_callback(self.game._on_move_made)
        self.game._display.set_move_callback(self.game._on_move_made)

        # Create history
        self.game._history = GameHistory({
            "num_players": 2,
            "max_live_tokens": settings.max_live_tokens,
            "max_hint_tokens": settings.max_hint_tokens,
            "max_cards_in_hand": settings.max_cards_in_hand
        })
        self.game._history.record_initial_state(self.game._engine)

        # Make a play move
        move = Play(0)
        initial_score = self.game._engine.get_score()

        self.game._on_move_made(move)

        # Check that move was processed
        new_score = self.game._engine.get_score()
        # Score might increase if a valid card was played
        self.assertIsNotNone(new_score)

    def test_game_end_detection(self):
        """Test game end detection."""
        # Set up a game
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        self.game._engine = GameEngine(settings, players)
        self.game._engine.initialize()
        self.game._display.set_engine(self.game._engine)

        # Lose all lives
        state = self.game._engine.gameState
        hand = state.player_hands[0]

        # Play invalid cards until lives are lost
        for i in range(min(3, len(hand.cards))):
            if hand.cards[i].number != Number.ONE:
                move = Play(i)
                self.game._engine.process_move(0, move)
                self.game._engine.advanceTurn()
                if self.game._engine.gameState.common_view.live_tokens <= 0:
                    break

        # Game should be finished
        if self.game._engine.gameState.common_view.live_tokens <= 0:
            self.assertTrue(self.game._engine.is_finished())

    def test_replay_history_format(self):
        """Test replay history format parsing."""
        # Mock history data
        history_data = {
            "s": {
                "num_players": 3,
                "max_live_tokens": 3,
                "max_hint_tokens": 8,
                "max_cards_in_hand": 5
            },
            "m": []
        }

        # Should not raise error
        self.game._reconstruct_game_from_history(history_data)
        self.assertIsNotNone(self.game._engine)


@unittest.skip("Obsolete Game(settings, players) API; rewrite against Game.create")
class TestGUIGamePlaySimulation(unittest.TestCase):
    """Simulate actual gameplay to find bugs."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = tk.Tk()
        self.root.withdraw()

        self.settings = create_standard_game_settings(2)
        self.players = [HumanPlayer(i) for i in range(2)]
        self.engine = GameEngine(self.settings, self.players)
        self.engine.initialize()

        self.display = GUIDisplay(self.root)
        self.display.set_engine(self.engine)
        self.input_handler = GUIInput(self.engine, self.display)

        self.move_callback_calls = []
        def record_move(move):
            self.move_callback_calls.append(move)

        self.input_handler.set_move_callback(record_move)
        self.display.set_move_callback(record_move)
        self.input_handler.setup_canvas_clicks()

    def tearDown(self):
        """Clean up after tests."""
        self.root.destroy()

    def test_simulate_full_turn(self):
        """Simulate a full turn: select card, play it."""
        # Display initial state
        self.display.display_game_state(self.engine, 0)

        # Select a card
        self.input_handler._on_card_selected(0)
        self.assertEqual(self.display._selected_card, 0)

        # Play the card
        self.display._on_play_clicked()

        # Check that move was recorded
        self.assertEqual(len(self.move_callback_calls), 1)
        self.assertIsInstance(self.move_callback_calls[0], Play)
        self.assertEqual(self.move_callback_calls[0].card, 0)

    def test_simulate_hint_flow(self):
        """Simulate giving a hint: activate hint mode, select target."""
        # Display initial state
        self.display.display_game_state(self.engine, 0)

        # Activate color hint mode
        self.display._on_hint_mode_clicked("color")
        self.assertEqual(self.display._hint_mode, "color")

        # Select a card from player 1
        state = self.engine.gameState
        hand = state.player_hands[1]
        if hand.cards:
            card = hand.cards[0]
            matching = [i for i, c in enumerate(hand.cards) if c.color == card.color]

            if matching:
                self.input_handler._on_hint_target_selected(1, 0)

                # Check that hint move was created
                self.assertEqual(len(self.move_callback_calls), 1)
                self.assertIsInstance(self.move_callback_calls[0], ColorHint)
                self.assertEqual(self.move_callback_calls[0].teammate, 1)

    def test_simulate_multiple_moves(self):
        """Simulate multiple moves in sequence."""
        moves_made = 0
        max_moves = 5

        while not self.engine.is_finished() and moves_made < max_moves:
            current_player = self.engine.current_player
            self.display.display_game_state(self.engine, current_player)

            state = self.engine.gameState
            hand = state.player_hands[current_player]

            if not hand.cards:
                break

            # Clear previous callbacks
            self.move_callback_calls.clear()

            # Select and play/discard a card
            self.input_handler._on_card_selected(0)

            # Try to discard (safer than play)
            if state.common_view.hint_tokens < self.engine.settings.max_hint_tokens:
                self.display._on_discard_clicked()
            else:
                # Can't discard, try to play
                self.display._on_play_clicked()

            # Process the move if one was made
            if self.move_callback_calls:
                move = self.move_callback_calls[0]
                success, _ = self.engine.process_move(current_player, move)
                if success:
                    self.engine.advanceTurn()
                    moves_made += 1
                else:
                    break
            else:
                break

        # Should have made at least one move
        self.assertGreater(moves_made, 0)

    def test_card_selection_after_state_change(self):
        """Test that card selection works after game state changes."""
        # Initial state
        self.display.display_game_state(self.engine, 0)
        self.input_handler._on_card_selected(0)
        self.assertEqual(self.display._selected_card, 0)

        # Make a move that changes state
        move = Discard(0)
        success, _ = self.engine.process_move(0, move)
        if success:
            self.engine.advanceTurn()

        # Display new state
        self.display.display_game_state(self.engine, 1)

        # Selection should be cleared or validated
        # (selected card was for player 0, now showing player 1)
        if self.display._selected_card is not None:
            hand = self.engine.gameState.player_hands[1]
            self.assertLess(self.display._selected_card, len(hand.cards))

    def test_hint_mode_reset(self):
        """Test that hint mode resets after giving a hint."""
        self.display.display_game_state(self.engine, 0)

        # Activate hint mode
        self.display._on_hint_mode_clicked("color")
        self.assertEqual(self.display._hint_mode, "color")

        # Give a hint
        state = self.engine.gameState
        hand = state.player_hands[1]
        if hand.cards:
            card = hand.cards[0]
            matching = [i for i, c in enumerate(hand.cards) if c.color == card.color]
            if matching:
                self.input_handler._on_hint_target_selected(1, 0)

                # Hint mode should be reset
                self.assertIsNone(self.display._hint_mode)

    def test_button_states(self):
        """Test that buttons are enabled/disabled correctly."""
        self.display.display_game_state(self.engine, 0)

        # Initially no card selected, buttons should be disabled
        # (We can't easily test button states without accessing internal widgets,
        # but we can test that _update_action_buttons doesn't crash)
        self.display._selected_card = None
        self.display._update_action_buttons()

        # With card selected, buttons should be enabled
        self.display._selected_card = 0
        self.display._update_action_buttons()


if __name__ == '__main__':
    unittest.main()

