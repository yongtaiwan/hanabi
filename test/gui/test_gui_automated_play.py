"""
Automated playthrough test for GUI version.
Simulates playing a complete game to identify bugs.
"""

import unittest
import tkinter as tk
from unittest.mock import Mock, patch
import os
import tempfile

from hanabi.core.game import create_standard_game_settings
from hanabi.core.game import Game as GameEngine
from hanabi.gui.gui_display import GUIDisplay
from hanabi.gui.gui_input import GUIInput
from hanabi.gui.gui_game import GUIGame
from hanabi.core.player import HumanPlayer
from hanabi.core.moves import Play, Discard, ColorHint, NumberHint
from hanabi.core.game_history import GameHistory
from hanabi.core.enums import Color, Number


@unittest.skip("Obsolete Game(settings, players) API; rewrite against Game.create")
class TestGUIAutomatedPlay(unittest.TestCase):
    """Automated playthrough tests that simulate actual gameplay."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = tk.Tk()
        self.root.withdraw()  # Hide window during tests

    def tearDown(self):
        """Clean up after tests."""
        self.root.destroy()

    def test_complete_game_playthrough(self):
        """Simulate a complete game playthrough through GUI."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        input_handler = GUIInput(engine, display)
        move_callback_calls = []

        def record_move(move):
            move_callback_calls.append(move)
            # Actually process the move
            current_player = engine.current_player
            success, msg = engine.process_move(current_player, move)
            if success:
                engine.advanceTurn()
                display.display_game_state(engine, engine.current_player)
            return success, msg

        input_handler.set_move_callback(record_move)
        display.set_move_callback(record_move)
        input_handler.setup_canvas_clicks()

        history = GameHistory({
            "num_players": 2,
            "max_live_tokens": 3,
            "max_hint_tokens": 8,
            "max_cards_in_hand": 5
        })
        history.record_initial_state(engine)

        # Simulate playing the game
        moves_made = 0
        max_moves = 30  # Safety limit

        while not engine.is_finished() and moves_made < max_moves:
            current_player = engine.current_player
            state = engine.gameState
            hand = state.player_hands[current_player]

            if not hand.cards:
                break

            # Update display
            display.display_game_state(engine, current_player)

            # Strategy: Try to play valid cards, otherwise discard
            move_made = False

            # Try to play a valid card (number 1 or next in sequence)
            for i, card in enumerate(hand.cards):
                cards_played = state.common_view.cards_played
                if card.color not in cards_played:
                    # Need a 1
                    if card.number == Number.ONE:
                        move = Play(i)
                        success, msg = record_move(move)
                        if success:
                            history.record_move(current_player, move, msg, engine)
                            moves_made += 1
                            move_made = True
                            break
                else:
                    # Need next number
                    expected = cards_played[card.color].value + 1
                    if card.number.value == expected:
                        move = Play(i)
                        success, msg = record_move(move)
                        if success:
                            history.record_move(current_player, move, msg, engine)
                            moves_made += 1
                            move_made = True
                            break

            if move_made:
                continue

            # If can't play, try to give a hint
            if state.common_view.hint_tokens > 0:
                teammate = 1 if current_player == 0 else 0
                teammate_hand = state.player_hands[teammate]
                if teammate_hand.cards:
                    # Give color hint
                    color = teammate_hand.cards[0].color
                    matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                    if matching:
                        move = ColorHint(teammate, matching, color)
                        success, msg = record_move(move)
                        if success:
                            history.record_move(current_player, move, msg, engine)
                            moves_made += 1
                            continue

            # Otherwise discard
            if state.common_view.hint_tokens < engine.settings.max_hint_tokens:
                move = Discard(0)
                success, msg = record_move(move)
                if success:
                    history.record_move(current_player, move, msg, engine)
                    moves_made += 1
                else:
                    break
            else:
                # Must play something
                move = Play(0)
                success, msg = record_move(move)
                if success:
                    history.record_move(current_player, move, msg, engine)
                    moves_made += 1
                else:
                    break

        # Verify game ended in a valid state
        self.assertIsNotNone(engine.gameState)
        self.assertGreater(moves_made, 0)

        # Verify display is still functional
        display.display_game_state(engine, engine.current_player)
        self.assertGreater(len(display._card_widgets), 0)

        # Save and verify history
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            temp_filename = f.name

        try:
            history.save_to_file(temp_filename)
            self.assertTrue(os.path.exists(temp_filename))

            # Try to load it back
            loaded_history = GameHistory({})
            loaded_data = loaded_history.load_from_file(temp_filename)
            self.assertIn("s", loaded_data)
            self.assertIn("m", loaded_data)
        finally:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    def test_card_selection_and_play_flow(self):
        """Test the complete flow: select card, play it."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        input_handler = GUIInput(engine, display)
        move_callback_calls = []

        def record_move(move):
            move_callback_calls.append(move)

        input_handler.set_move_callback(record_move)
        display.set_move_callback(record_move)
        input_handler.setup_canvas_clicks()

        # Select a card
        state = engine.gameState
        hand = state.player_hands[0]
        if hand.cards:
            input_handler._on_card_selected(0)
            self.assertEqual(display._selected_card, 0)

            # Play the selected card
            display._on_play_clicked()

            # Verify move was created
            self.assertEqual(len(move_callback_calls), 1)
            self.assertIsInstance(move_callback_calls[0], Play)
            self.assertEqual(move_callback_calls[0].card, 0)

    def test_hint_flow_complete(self):
        """Test complete hint flow: activate mode, select target, give hint."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        input_handler = GUIInput(engine, display)
        move_callback_calls = []

        def record_move(move):
            move_callback_calls.append(move)

        input_handler.set_move_callback(record_move)
        display.set_move_callback(record_move)
        input_handler.setup_canvas_clicks()

        # Activate hint mode
        display._on_hint_mode_clicked("color")
        self.assertEqual(display._hint_mode, "color")

        # Select target card
        state = engine.gameState
        teammate_hand = state.player_hands[1]
        if teammate_hand.cards:
            card = teammate_hand.cards[0]
            matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == card.color]

            if matching:
                input_handler._on_hint_target_selected(1, 0)

                # Verify hint was created
                self.assertEqual(len(move_callback_calls), 1)
                self.assertIsInstance(move_callback_calls[0], ColorHint)
                self.assertEqual(move_callback_calls[0].teammate, 1)
                self.assertEqual(move_callback_calls[0].color, card.color)

                # Verify hint mode was reset
                self.assertIsNone(display._hint_mode)

    def test_multiple_turns_with_state_updates(self):
        """Test multiple turns with proper state updates."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        input_handler = GUIInput(engine, display)
        move_callback_calls = []

        def record_move(move):
            move_callback_calls.append(move)
            current_player = engine.current_player
            success, msg = engine.process_move(current_player, move)
            if success:
                engine.advanceTurn()
            return success, msg

        input_handler.set_move_callback(record_move)
        display.set_move_callback(record_move)
        input_handler.setup_canvas_clicks()

        # Make 5 moves
        for turn in range(5):
            if engine.is_finished():
                break

            current_player = engine.current_player
            display.display_game_state(engine, current_player)

            state = engine.gameState
            hand = state.player_hands[current_player]

            if not hand.cards:
                break

            # Select and discard a card
            input_handler._on_card_selected(0)
            if state.common_view.hint_tokens < engine.settings.max_hint_tokens:
                display._on_discard_clicked()
            else:
                display._on_play_clicked()

            # Process the move
            if move_callback_calls:
                move = move_callback_calls[-1]
                record_move(move)
                move_callback_calls.clear()

            # Verify display updated
            display.display_game_state(engine, engine.current_player)
            self.assertGreater(len(display._card_widgets), 0)

    def test_selected_card_validation(self):
        """Test that selected card is properly validated when hand size changes."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        # Select last card
        state = engine.gameState
        hand = state.player_hands[0]
        if len(hand.cards) > 1:
            last_idx = len(hand.cards) - 1
            display._selected_card = last_idx

            # Play a different card (reduces hand size)
            move = Play(0)
            engine.process_move(0, move)
            engine.advanceTurn()

            # Display new state - selected card should be validated
            display.display_game_state(engine, 1)

            # Selected card should be None (different player) or valid
            if display._selected_card is not None:
                new_hand = engine.gameState.player_hands[1]
                self.assertLess(display._selected_card, len(new_hand.cards))

    def test_button_state_updates(self):
        """Test that buttons update correctly based on game state."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        # Test with no card selected
        display._selected_card = None
        display.display_game_state(engine, 0)
        display._update_action_buttons()

        # Test with card selected
        display._selected_card = 0
        display._update_action_buttons()

        # Test when hint tokens at max (can't discard)
        state = engine.gameState
        # Use up hint tokens to max
        while state.common_view.hint_tokens < engine.settings.max_hint_tokens:
            move = Discard(0)
            engine.process_move(engine.current_player, move)
            engine.advanceTurn()
            state = engine.gameState

        display.display_game_state(engine, engine.current_player)
        display._update_action_buttons()

    def test_canvas_resize_handling(self):
        """Test that canvas resize doesn't cause errors."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        # Simulate resize event
        event = Mock()
        event.width = 800
        event.height = 600

        # Should not raise error
        display._on_canvas_resize(event)

        # Verify display still works
        display.display_game_state(engine, 0)
        self.assertGreater(len(display._card_widgets), 0)

    def test_replay_mode_toggle(self):
        """Test replay mode toggle."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        # Toggle show all cards
        display.set_show_all_cards(True)
        self.assertTrue(display._show_all_cards)

        display.set_show_all_cards(False)
        self.assertFalse(display._show_all_cards)

        # Display should work in both modes
        display.display_game_state(engine, 0)
        self.assertGreater(len(display._card_widgets), 0)

    def test_error_handling_invalid_moves(self):
        """Test that invalid moves are handled gracefully."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        input_handler = GUIInput(engine, display)

        # Try to select invalid card index
        state = engine.gameState
        hand = state.player_hands[0]
        invalid_idx = len(hand.cards) + 10

        # Should not crash
        input_handler._on_card_selected(invalid_idx)

        # Selected card should be set but will be validated on next display
        display.display_game_state(engine, 0)
        if display._selected_card is not None:
            self.assertLess(display._selected_card, len(hand.cards))

    def test_hint_with_no_matching_cards(self):
        """Test hint when clicking on a card with no matching cards."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        input_handler = GUIInput(engine, display)
        move_callback_calls = []

        def record_move(move):
            move_callback_calls.append(move)

        input_handler.set_move_callback(record_move)
        display.set_move_callback(record_move)

        # Activate hint mode
        display._on_hint_mode_clicked("color")

        # Try to give hint - should handle gracefully even if no matching
        state = engine.gameState
        teammate_hand = state.player_hands[1]
        if teammate_hand.cards:
            # This should work even if there's only one card of that color
            input_handler._on_hint_target_selected(1, 0)

            # Should either create a hint or handle gracefully
            # (The method should check for matching cards)


if __name__ == '__main__':
    unittest.main()

