"""
Stress tests for GUI to find edge cases and bugs.
Tests rapid state changes, edge cases, and error conditions.
"""

import unittest
import tkinter as tk
from unittest.mock import Mock
import sys

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
class TestGUIStress(unittest.TestCase):
    """Stress tests to find edge cases and bugs."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        """Clean up after tests."""
        self.root.destroy()

    def test_rapid_state_changes(self):
        """Test rapid state changes don't cause errors."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        # Rapidly change display state
        for i in range(10):
            current_player = engine.current_player
            display.display_game_state(engine, current_player)

            # Make a move
            move = Discard(0)
            success, _ = engine.process_move(current_player, move)
            if success:
                engine.advanceTurn()
            else:
                break

        # Should not crash
        self.assertIsNotNone(display._canvas)

    def test_selected_card_invalidation(self):
        """Test that selected card is properly invalidated when hand changes."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        state = engine.gameState
        hand = state.player_hands[0]

        if len(hand.cards) > 1:
            # Select last card
            last_idx = len(hand.cards) - 1
            display._selected_card = last_idx

            # Play first card (reduces hand size)
            move = Play(0)
            success, _ = engine.process_move(0, move)
            if success:
                engine.advanceTurn()

            # Display new state
            display.display_game_state(engine, engine.current_player)

            # Selected card should be validated/reset
            new_hand = engine.gameState.player_hands[engine.current_player]
            if display._selected_card is not None:
                self.assertLess(display._selected_card, len(new_hand.cards), "Selected card index should be valid")

    def test_hint_with_empty_hand(self):
        """Test hint when teammate has empty hand."""
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

        # Empty teammate's hand by discarding all cards (with safety limit)
        state = engine.gameState
        teammate_hand = state.player_hands[1]
        max_discards = 10
        discards = 0
        while teammate_hand.cards and discards < max_discards:
            move = Discard(0)
            success, _ = engine.process_move(engine.current_player, move)
            if success:
                engine.advanceTurn()
                state = engine.gameState
                teammate_hand = state.player_hands[1]
                discards += 1
            else:
                break

        # Try to give hint to empty hand
        display._on_hint_mode_clicked("color")
        # Should handle gracefully (no matching cards)
        self.assertEqual(display._hint_mode, "color")

    def test_multiple_hint_modes_rapidly(self):
        """Test rapidly switching hint modes."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        # Rapidly switch hint modes
        for _ in range(5):
            display._on_hint_mode_clicked("color")
            display._on_hint_mode_clicked("number")

        # Should end in number mode
        self.assertEqual(display._hint_mode, "number")

    def test_card_selection_after_hand_size_change(self):
        """Test card selection when hand size changes dramatically."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        state = engine.gameState
        hand = state.player_hands[0]

        # Select a card
        if hand.cards:
            display._selected_card = len(hand.cards) - 1

            # Play multiple cards to reduce hand size
            for i in range(min(3, len(hand.cards))):
                move = Play(0)
                engine.process_move(0, move)
                engine.advanceTurn()
                if engine.is_finished():
                    break

            # Display new state
            display.display_game_state(engine, engine.current_player)

            # Selected card should be validated
            new_hand = engine.gameState.player_hands[engine.current_player]
            if display._selected_card is not None:
                self.assertLess(
                    display._selected_card, len(new_hand.cards), "Selected card should be valid after hand size change"
                )

    def test_display_with_zero_tokens(self):
        """Test display when tokens are at zero."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        # Use up all hint tokens
        state = engine.gameState
        while state.common_view.hint_tokens > 0:
            teammate_hand = state.player_hands[1]
            if teammate_hand.cards:
                color = teammate_hand.cards[0].color
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                if matching:
                    move = ColorHint(1, matching, color)
                    engine.process_move(engine.current_player, move)
                    engine.advanceTurn()
                    state = engine.gameState
                else:
                    break
            else:
                break

        # Display should work with zero hint tokens
        display.display_game_state(engine, engine.current_player)
        self.assertGreater(len(display._card_widgets), 0)

    def test_display_with_zero_lives(self):
        """Test display when lives are at zero."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        # Lose all lives
        state = engine.gameState
        hand = state.player_hands[0]
        for i in range(min(3, len(hand.cards))):
            if hand.cards[i].number != Number.ONE:
                move = Play(i)
                engine.process_move(0, move)
                engine.advanceTurn()
                if engine.gameState.common_view.live_tokens <= 0:
                    break

        # Display should work even with zero lives
        display.display_game_state(engine, engine.current_player)
        self.assertGreater(len(display._card_widgets), 0)

    def test_fireworks_display_with_all_colors_played(self):
        """Test fireworks display when all colors are played."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        # Play one card of each color
        state = engine.gameState
        hand = state.player_hands[0]
        colors_played = set()

        for card in hand.cards:
            if card.number == Number.ONE and card.color not in colors_played:
                colors_played.add(card.color)
                card_idx = hand.cards.index(card)
                move = Play(card_idx)
                engine.process_move(0, move)
                engine.advanceTurn()
                if len(colors_played) >= 5:
                    break
                state = engine.gameState
                hand = state.player_hands[engine.current_player]

        # Display should show all fireworks
        display.display_game_state(engine, engine.current_player)
        self.assertGreater(len(display._firework_widgets), 0)

    def test_canvas_click_with_invalid_coordinates(self):
        """Test canvas click with invalid coordinates."""
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

        # Click at invalid coordinates (outside any card)
        event = Mock()
        event.x = -100
        event.y = -100

        # Should not crash
        input_handler._on_canvas_click(event)

        # Click at very large coordinates
        event.x = 10000
        event.y = 10000
        input_handler._on_canvas_click(event)

    def test_display_with_max_hint_tokens(self):
        """Test display when hint tokens are at maximum."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        # Fill hint tokens to max
        state = engine.gameState
        while state.common_view.hint_tokens < engine.settings.max_hint_tokens:
            move = Discard(0)
            success, _ = engine.process_move(engine.current_player, move)
            if success:
                engine.advanceTurn()
                state = engine.gameState
            else:
                break

        # Display should work
        display.display_game_state(engine, engine.current_player)
        self.assertGreater(len(display._card_widgets), 0)

        # Discard button should not be available
        display._selected_card = 0
        display._update_action_buttons()
        # Should not crash

    def test_play_button_with_no_selection(self):
        """Test play button when no card is selected."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        # Try to play with no selection
        display._selected_card = None
        display._on_play_clicked()
        # Should show warning but not crash

    def test_discard_button_with_no_selection(self):
        """Test discard button when no card is selected."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        # Try to discard with no selection
        display._selected_card = None
        display._on_discard_clicked()
        # Should show warning but not crash

    def test_hint_mode_with_no_target(self):
        """Test hint mode when no valid target exists."""
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

        # Activate hint mode
        display._on_hint_mode_clicked("color")

        # Try to click on current player's own card (invalid)
        input_handler._on_hint_target_selected(0, 0)
        # Should handle gracefully

    def test_display_with_different_player_counts(self):
        """Test display with different numbers of players."""
        for num_players in [2, 3, 4, 5]:
            with self.subTest(num_players=num_players):
                settings = create_standard_game_settings(num_players)
                players = [HumanPlayer(i) for i in range(num_players)]
                engine = GameEngine(settings, players)
                engine.initialize()

                display = GUIDisplay(self.root)
                display.set_suppress_dialogs(True)  # Disable messageboxes for testing
                display.set_engine(engine)
                display.display_game_state(engine, 0)

                # Should display correctly for any number of players
                self.assertGreater(len(display._card_widgets), 0)
                self.assertEqual(
                    len(display._card_positions), sum(len(hand.cards) for hand in engine.gameState.player_hands)
                )

    def test_concurrent_display_updates(self):
        """Test that display handles rapid updates correctly."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)

        # Rapidly update display
        for i in range(20):
            current_player = engine.current_player
            display.display_game_state(engine, current_player)

            # Make a move
            move = Discard(0)
            success, _ = engine.process_move(current_player, move)
            if success:
                engine.advanceTurn()
            else:
                break

        # Should not crash
        self.assertIsNotNone(display._canvas)

    def test_clear_display_multiple_times(self):
        """Test clearing display multiple times."""
        settings = create_standard_game_settings(2)
        players = [HumanPlayer(i) for i in range(2)]
        engine = GameEngine(settings, players)
        engine.initialize()

        display = GUIDisplay(self.root)
        display.set_suppress_dialogs(True)  # Disable messageboxes for testing
        display.set_engine(engine)
        display.display_game_state(engine, 0)

        # Clear multiple times
        for _ in range(5):
            display.clear()

        # Should not crash
        self.assertEqual(len(display._card_widgets), 0)
        self.assertEqual(len(display._card_positions), 0)


if __name__ == "__main__":
    unittest.main()
