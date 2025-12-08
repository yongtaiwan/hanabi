"""
Automated playthrough test that simulates playing a complete game through the GUI.
This test actually plays the game to identify bugs and verify functionality.
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


class TestGUIPlaythrough(unittest.TestCase):
    """Automated playthrough that simulates actual gameplay to find bugs."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = tk.Tk()
        self.root.withdraw()  # Hide window during tests

    def tearDown(self):
        """Clean up after tests."""
        self.root.destroy()

    def test_complete_game_playthrough(self):
        """Simulate a complete game playthrough to find bugs."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        input_handler = GUIInput(engine, display)
        moves_processed = []

        def process_move(move):
            """Process a move and record it."""
            current_player = engine.currentPlayer
            success, msg = engine.processMove(current_player, move)
            if success:
                engine.advanceTurn()
                moves_processed.append((current_player, move, success, msg))
                # Update display
                display.display_game_state(engine, engine.currentPlayer)
            return success, msg

        input_handler.set_move_callback(process_move)
        display.set_move_callback(process_move)
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
        max_moves = 50  # Safety limit

        while not engine.isFinished() and moves_made < max_moves:
            current_player = engine.currentPlayer
            state = engine.gameState
            hand = state.playerHands[current_player]

            if not hand.cards:
                break

            # Update display
            display.display_game_state(engine, current_player)

            # Verify display state
            self.assertGreater(len(display._card_widgets), 0, "Card widgets should exist")
            self.assertGreater(len(display._card_positions), 0, "Card positions should exist")

            move_made = False

            # Strategy: Try to play valid cards first
            for i, card in enumerate(hand.cards):
                cards_played = state.commonView.cardsPlayed
                if card.color not in cards_played:
                    # Need a 1
                    if card.number == Number.ONE:
                        # Select card and play it
                        input_handler._on_card_selected(i)
                        self.assertEqual(display._selected_card, i, "Card should be selected")

                        # Play via button
                        display._on_play_clicked()

                        # Verify move was processed
                        if moves_processed:
                            last_move = moves_processed[-1][1]
                            self.assertIsInstance(last_move, Play, "Should be a Play move")
                            self.assertEqual(last_move.card, i, "Should play selected card")
                            history.record_move(current_player, last_move, moves_processed[-1][3], engine)
                            moves_made += 1
                            move_made = True
                            break
                else:
                    # Need next number
                    expected = cards_played[card.color].value + 1
                    if card.number.value == expected:
                        # Select and play
                        input_handler._on_card_selected(i)
                        display._on_play_clicked()

                        if moves_processed:
                            last_move = moves_processed[-1][1]
                            self.assertIsInstance(last_move, Play, "Should be a Play move")
                            history.record_move(current_player, last_move, moves_processed[-1][3], engine)
                            moves_made += 1
                            move_made = True
                            break

            if move_made:
                continue

            # If can't play, try to give a hint
            if state.commonView.hintTokens > 0:
                teammate = 1 if current_player == 0 else 0
                teammate_hand = state.playerHands[teammate]
                if teammate_hand.cards:
                    # Activate hint mode
                    display._on_hint_mode_clicked("color")
                    self.assertEqual(display._hint_mode, "color", "Hint mode should be activated")

                    # Give color hint
                    card = teammate_hand.cards[0]
                    matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == card.color]
                    if matching:
                        input_handler._on_hint_target_selected(teammate, 0)

                        # Verify hint was given
                        if moves_processed:
                            last_move = moves_processed[-1][1]
                            self.assertIsInstance(last_move, ColorHint, "Should be a ColorHint")
                            history.record_move(current_player, last_move, moves_processed[-1][3], engine)
                            moves_made += 1
                            move_made = True
                            continue

            # Otherwise discard
            if state.commonView.hintTokens < engine.settings.maxHintTokens:
                # Select and discard
                input_handler._on_card_selected(0)
                display._on_discard_clicked()

                if moves_processed:
                    last_move = moves_processed[-1][1]
                    self.assertIsInstance(last_move, Discard, "Should be a Discard move")
                    history.record_move(current_player, last_move, moves_processed[-1][3], engine)
                    moves_made += 1
                    move_made = True
                else:
                    break
            else:
                # Must play something
                input_handler._on_card_selected(0)
                display._on_play_clicked()

                if moves_processed:
                    last_move = moves_processed[-1][1]
                    history.record_move(current_player, last_move, moves_processed[-1][3], engine)
                    moves_made += 1
                    move_made = True
                else:
                    break

        # Verify game ended in a valid state
        self.assertIsNotNone(engine.gameState, "Game state should exist")
        self.assertGreater(moves_made, 0, "Should have made at least one move")

        # Verify display is still functional
        display.display_game_state(engine, engine.currentPlayer)
        self.assertGreater(len(display._card_widgets), 0, "Display should show cards")

        # Verify history was saved correctly
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            temp_filename = f.name

        try:
            history.save_to_file(temp_filename)
            self.assertTrue(os.path.exists(temp_filename), "History file should be created")

            # Try to load it back
            loaded_history = GameHistory({})
            loaded_data = loaded_history.load_from_file(temp_filename)
            self.assertIn("s", loaded_data, "History should have settings")
            self.assertIn("m", loaded_data, "History should have moves")
            self.assertGreater(len(loaded_data["m"]), 0, "Should have recorded moves")
        finally:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    def test_card_selection_edge_cases(self):
        """Test edge cases in card selection."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        input_handler = GUIInput(engine, display)
        input_handler.setup_canvas_clicks()

        # Test selecting card, then playing it
        state = engine.gameState
        hand = state.playerHands[0]
        if hand.cards:
            # Select first card
            input_handler._on_card_selected(0)
            self.assertEqual(display._selected_card, 0)

            # Play it
            move = Play(0)
            success, _ = engine.processMove(0, move)
            if success:
                engine.advanceTurn()

            # Display new state - selected card should be validated
            display.display_game_state(engine, engine.currentPlayer)

            # Selected card should be None (different player now) or valid
            if display._selected_card is not None:
                new_hand = engine.gameState.playerHands[engine.currentPlayer]
                self.assertLess(display._selected_card, len(new_hand.cards),
                              "Selected card should be valid")

    def test_hint_mode_reset(self):
        """Test that hint mode resets correctly."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        input_handler = GUIInput(engine, display)
        move_callback = Mock()
        input_handler.set_move_callback(move_callback)
        display.set_move_callback(move_callback)
        input_handler.setup_canvas_clicks()

        # Activate hint mode
        display._on_hint_mode_clicked("color")
        self.assertEqual(display._hint_mode, "color")

        # Give hint
        state = engine.gameState
        teammate_hand = state.playerHands[1]
        if teammate_hand.cards:
            card = teammate_hand.cards[0]
            matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == card.color]
            if matching:
                input_handler._on_hint_target_selected(1, 0)

                # Hint mode should be reset
                self.assertIsNone(display._hint_mode, "Hint mode should be reset after giving hint")

    def test_button_state_consistency(self):
        """Test that buttons are enabled/disabled correctly."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        # No card selected
        display._selected_card = None
        display._update_action_buttons()
        # Should not crash

        # Card selected
        display._selected_card = 0
        display._update_action_buttons()
        # Should not crash

    def test_display_after_multiple_moves(self):
        """Test that display works correctly after multiple moves."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        # Make several moves
        for i in range(5):
            if engine.isFinished():
                break

            current_player = engine.currentPlayer
            state = engine.gameState
            hand = state.playerHands[current_player]

            if not hand.cards:
                break

            # Display state
            display.display_game_state(engine, current_player)

            # Verify display
            self.assertGreater(len(display._card_widgets), 0, f"Should have cards after move {i}")
            self.assertGreater(len(display._card_positions), 0, f"Should have positions after move {i}")

            # Make a move
            if state.commonView.hintTokens < engine.settings.maxHintTokens:
                move = Discard(0)
            else:
                move = Play(0)

            success, _ = engine.processMove(current_player, move)
            if success:
                engine.advanceTurn()

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

        # Simulate resize events
        event = Mock()
        event.width = 800
        event.height = 600
        display._on_canvas_resize(event)

        event.width = 1200
        event.height = 800
        display._on_canvas_resize(event)

        # Should not crash and display should still work
        display.display_game_state(engine, 0)
        self.assertGreater(len(display._card_widgets), 0)

    def test_replay_mode_display(self):
        """Test replay mode (show all cards)."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        # Normal mode
        display.set_show_all_cards(False)
        display.display_game_state(engine, 0)
        self.assertFalse(display._show_all_cards)

        # Replay mode
        display.set_show_all_cards(True)
        display.display_game_state(engine, 0)
        self.assertTrue(display._show_all_cards)
        self.assertGreater(len(display._card_widgets), 0)


if __name__ == '__main__':
    unittest.main()

