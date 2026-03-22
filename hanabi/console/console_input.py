"""
Console input parsing for Hanabi game.
"""

from typing import Optional, Tuple
from hanabi.core.enums import Color, Number
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint
from hanabi.core.game import Game, PlayerView


class ConsoleInput:
    """Handles parsing of console input for Hanabi moves."""

    def __init__(self, game: Game, player_index: int):
        """
        Initialize console input parser.

        Args:
            game: The game instance
            player_index: Index of the player using this input parser
        """
        self._game = game
        self._player_index = player_index

    def parse_move(self, player_index: int, input_str: str) -> Tuple[Optional[Move], Optional[str]]:
        """
        Parse a move from user input. Supports both full and simplified commands.

        Simplified commands:
        - p<index> or play <index> - play a card
        - d<index> or discard <index> - discard a card
        - h<value> or h<color><value> or h<number><value> - give a hint
          Examples: h3 (hint number 3), hr (hint red), hy5 (hint yellow 5)

        Args:
            player_index: Index of the player making the move
            input_str: The input string from the user

        Returns:
            Tuple of (Move object or None, error message or None)
        """
        input_str = input_str.strip().lower()
        if not input_str:
            return None, "Empty input"

        parts = input_str.split()
        if not parts:
            return None, "Invalid input format"

        command = parts[0]

        # Full words first — avoids treating "play 1" as simplified "p" + "lay 1"
        if command == "play":
            return self._parse_play(parts)
        if command == "discard":
            return self._parse_discard(parts)
        if command == "hint":
            return self._parse_hint(player_index, parts)

        # Single-letter simplified: p1, d2, h3, hr, ...
        if len(input_str) >= 2 and input_str[0] in ['p', 'd', 'h']:
            return self._parse_simplified(player_index, input_str)

        if command in ["p"]:
            return self._parse_play(parts)
        elif command in ["d"]:
            return self._parse_discard(parts)
        elif command in ["h"]:
            return self._parse_hint(player_index, parts)
        else:
            return None, f"Unknown command: {command}. Use 'play'/'p', 'discard'/'d', or 'hint'/'h'"

    def _parse_simplified(self, player_index: int, input_str: str) -> Tuple[Optional[Move], Optional[str]]:
        """Parse simplified command format."""
        cmd = input_str[0]
        rest = input_str[1:]

        if cmd == 'p':  # play
            try:
                card_index_ui = int(rest) if rest else None
                if card_index_ui is None:
                    return None, "Usage: p<index> (e.g., p1)"
                # Convert 1-based UI index to 0-based internal index
                card_index = card_index_ui - 1
                state = self._game.state
                hand = state.player_hands[self._player_index]
                if card_index < 0 or card_index >= len(hand.cards):
                    return None, f"Invalid card index. Your hand has {len(hand.cards)} cards (indices 1-{len(hand.cards)})"
                return Play(card_index), None
            except ValueError:
                return None, f"Invalid card index: {rest}"

        elif cmd == 'd':  # discard
            try:
                card_index_ui = int(rest) if rest else None
                if card_index_ui is None:
                    return None, "Usage: d<index> (e.g., d2)"
                # Convert 1-based UI index to 0-based internal index
                card_index = card_index_ui - 1
                state = self._game.state
                hand = state.player_hands[self._player_index]
                if card_index < 0 or card_index >= len(hand.cards):
                    return None, f"Invalid card index. Your hand has {len(hand.cards)} cards (indices 1-{len(hand.cards)})"
                return Discard(card_index), None
            except ValueError:
                return None, f"Invalid card index: {rest}"

        elif cmd == 'h':  # hint
            return self._parse_simplified_hint(player_index, rest)

        return None, f"Unknown command: {cmd}"

    def _parse_simplified_hint(self, player_index: int, rest: str) -> Tuple[Optional[Move], Optional[str]]:
        """Parse simplified hint format: h<value> or h<color><value> or h<number><value>."""
        state = self._game.state
        num_players = len(state.player_hands)

        # In 2-player game, automatically hint the other player
        if num_players == 2:
            teammate_idx = 1 if self._player_index == 0 else 0
        else:
            # For 3+ players, need to specify player
            # Try to parse player number first
            if rest and rest[0].isdigit():
                try:
                    teammate_idx = int(rest[0]) - 1
                    rest = rest[1:]
                    if teammate_idx < 0 or teammate_idx >= num_players or teammate_idx == self._player_index:
                        return None, f"Invalid player. Valid players: {', '.join(str(i+1) for i in range(num_players) if i != self._player_index)}"
                except ValueError:
                    return None, "Invalid player number"
            else:
                return None, f"In {num_players}-player game, specify player: h<player><value>"

        if not rest:
            return None, "Usage: h<value> (e.g., h3 for number 3, hr for red)"

        teammate_hand = state.player_hands[teammate_idx]

        # Try to parse as number first
        if rest.isdigit():
            try:
                number_value = int(rest)
                if number_value < 1 or number_value > 5:
                    return None, "Number must be 1-5"
                number = {1: Number.ONE, 2: Number.TWO, 3: Number.THREE, 4: Number.FOUR, 5: Number.FIVE}[number_value]
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.number == number]
                if not matching:
                    return None, f"Player {teammate_idx + 1} has no {number_value} cards"
                return NumberHint(teammate_idx, matching, number), None
            except (ValueError, KeyError):
                return None, f"Invalid number: {rest}"

        # Try to parse as color (single letter)
        color_map = {
            'r': Color.RED, 'red': Color.RED,
            'b': Color.BLUE, 'blue': Color.BLUE,
            'g': Color.GREEN, 'green': Color.GREEN,
            'y': Color.YELLOW, 'yellow': Color.YELLOW,
            'w': Color.WHITE, 'white': Color.WHITE,
            'm': Color.MULTI, 'multi': Color.MULTI
        }

        if rest.lower() in color_map:
            color = color_map[rest.lower()]
            matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
            if not matching:
                return None, f"Player {teammate_idx + 1} has no {color.name} cards"
            return ColorHint(teammate_idx, matching, color), None

        # Try color + number format (e.g., "r3" for red 3)
        if len(rest) >= 2:
            color_char = rest[0].lower()
            number_str = rest[1:]
            if color_char in color_map and number_str.isdigit():
                color = color_map[color_char]
                try:
                    number_value = int(number_str)
                    if number_value < 1 or number_value > 5:
                        return None, "Number must be 1-5"
                    # This format (e.g., "r3") is ambiguous - could mean:
                    # - Color hint for red (all red cards)
                    # - Number hint for 3 (all 3s)
                    # We'll default to color hint (more common)
                    matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                    if matching:
                        return ColorHint(teammate_idx, matching, color), None
                    else:
                        return None, f"Player {teammate_idx + 1} has no {color.name} cards"
                except ValueError:
                    pass

        return None, f"Invalid hint format: h{rest}. Use h<number> (e.g., h3) or h<color> (e.g., hr)"

    def _parse_play(self, parts: list) -> Tuple[Optional[Move], Optional[str]]:
        """Parse a play move (accepts 1-based indices)."""
        if len(parts) < 2:
            return None, "Usage: play <card_index> (indices 1-5)"

        try:
            card_index_ui = int(parts[1])
            # Convert 1-based UI index to 0-based internal index
            card_index = card_index_ui - 1
            state = self._game.state
            hand = state.player_hands[self._player_index]

            if card_index < 0 or card_index >= len(hand.cards):
                return None, f"Invalid card index. Your hand has {len(hand.cards)} cards (indices 1-{len(hand.cards)})"

            return Play(card_index), None
        except ValueError:
            return None, f"Invalid card index: {parts[1]}"

    def _parse_discard(self, parts: list) -> Tuple[Optional[Move], Optional[str]]:
        """Parse a discard move (accepts 1-based indices)."""
        if len(parts) < 2:
            return None, "Usage: discard <card_index> (indices 1-5)"

        try:
            card_index_ui = int(parts[1])
            # Convert 1-based UI index to 0-based internal index
            card_index = card_index_ui - 1
            state = self._game.state
            hand = state.player_hands[self._player_index]

            if card_index < 0 or card_index >= len(hand.cards):
                return None, f"Invalid card index. Your hand has {len(hand.cards)} cards (indices 1-{len(hand.cards)})"

            return Discard(card_index), None
        except ValueError:
            return None, f"Invalid card index: {parts[1]}"

    def _parse_hint(self, player_index: int, parts: list) -> Tuple[Optional[Move], Optional[str]]:
        """Parse a hint move."""
        if len(parts) < 4:
            return None, "Usage: hint <player> <color|number> <value>"

        try:
            teammate_idx = int(parts[1]) - 1  # Convert from 1-based to 0-based
            state = self._game.state

            if teammate_idx < 0 or teammate_idx >= len(state.player_hands):
                return None, f"Invalid player index. Valid players: 1-{len(state.player_hands)}"

            if teammate_idx == self._player_index:
                return None, "You cannot give a hint to yourself"

            hint_type = parts[2].lower()
            teammate_hand = state.player_hands[teammate_idx]

            if hint_type == "color":
                # Parse color
                color_str = parts[3].upper()
                try:
                    color = Color[color_str]
                except KeyError:
                    return None, f"Invalid color: {color_str}. Valid colors: {', '.join(c.name for c in Color)}"

                # Find matching cards
                matching_indices = []
                for i, card in enumerate(teammate_hand.cards):
                    if card.color == color:
                        matching_indices.append(i)

                if not matching_indices:
                    return None, f"Player {teammate_idx + 1} has no {color_str} cards"

                return ColorHint(teammate_idx, matching_indices, color), None

            elif hint_type == "number":
                # Parse number
                try:
                    number_value = int(parts[3])
                    if number_value < 1 or number_value > 5:
                        return None, "Number must be between 1 and 5"
                    # Map number value to Number enum
                    number_map = {1: Number.ONE, 2: Number.TWO, 3: Number.THREE, 4: Number.FOUR, 5: Number.FIVE}
                    number = number_map[number_value]
                except (ValueError, KeyError):
                    return None, f"Invalid number: {parts[3]}. Must be 1-5"

                # Find matching cards
                matching_indices = []
                for i, card in enumerate(teammate_hand.cards):
                    if card.number == number:
                        matching_indices.append(i)

                if not matching_indices:
                    return None, f"Player {teammate_idx + 1} has no {number_value} cards"

                return NumberHint(teammate_idx, matching_indices, number), None
            else:
                return None, f"Invalid hint type: {hint_type}. Use 'color' or 'number'"

        except (ValueError, IndexError) as e:
            return None, f"Invalid hint format: {str(e)}"

