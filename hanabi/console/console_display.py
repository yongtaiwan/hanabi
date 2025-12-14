"""
Console display utilities for Hanabi game with color support.
"""

import os
from typing import List, Dict, Optional
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card
from hanabi.core.game import GameSettings, CommonView, Hand, PlayerView
from hanabi.core.game import Game
from hanabi.core.moves import Move, ColorHint, NumberHint


class Colors:
    """ANSI color codes for terminal output."""
    # Reset
    RESET = '\033[0m'

    # Text colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Bright colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'

    # Background colors
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'


class ConsoleDisplay:
    """Handles console display for Hanabi game."""

    def __init__(self, use_colors: bool = True):
        """
        Initialize console display.

        Args:
            use_colors: Whether to use color output
        """
        self.use_colors = use_colors and self._supports_colors()
        self._color_map = self._init_color_map()
        # Track moves from previous round (since last turn of current player)
        self._all_moves: List[tuple[int, Move, int]] = []  # List of (player_index, move, turn_number) tuples
        self._last_player_turn: Dict[int, int] = {}  # Track last turn number for each player

    def _supports_colors(self) -> bool:
        """Check if terminal supports colors."""
        return hasattr(os, 'isatty') and os.isatty(1)

    def _init_color_map(self) -> Dict[Color, str]:
        """Initialize color mapping for card colors with brighter colors."""
        if not self.use_colors:
            return {color: "" for color in Color}

        return {
            Color.RED: Colors.BRIGHT_RED,
            Color.BLUE: Colors.BRIGHT_BLUE,
            Color.GREEN: Colors.BRIGHT_GREEN,
            Color.YELLOW: Colors.BRIGHT_YELLOW,
            Color.WHITE: Colors.BRIGHT_WHITE,
            Color.MULTI: Colors.BRIGHT_MAGENTA,
        }

    def clear_screen(self) -> None:
        """Clear the console screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def _card_to_short_notation(self, card_str: str) -> str:
        """
        Convert Card(COLOR, NUMBER) to short notation (e.g., Card(GREEN, 1) -> G1).

        Args:
            card_str: String like "Card(GREEN, 1)"

        Returns:
            Short notation like "G1"
        """
        import re
        from hanabi.core.enums import Color

        # Match Card(COLOR, NUMBER)
        match = re.match(r'Card\((\w+),\s*(\d+)\)', card_str)
        if match:
            color_name = match.group(1)
            number = match.group(2)
            try:
                color_enum = Color[color_name]
                # Get first letter of color name for short notation
                # WHITE -> W, RED -> R, YELLOW -> Y, GREEN -> G, BLUE -> B
                color_short = color_name[0]
                return f"{color_short}{number}"
            except KeyError:
                return card_str
        return card_str

    def _shorten_card_notation(self, message: str) -> str:
        """
        Replace Card(COLOR, NUMBER) with short notation (e.g., G1) in a message.

        Args:
            message: Message string that may contain Card() notation

        Returns:
            Message with Card() replaced by short notation
        """
        import re

        # Replace Card(COLOR, NUMBER) with short notation
        card_pattern = r'Card\((\w+),\s*(\d+)\)'
        def replace_card(match):
            return self._card_to_short_notation(match.group(0))

        return re.sub(card_pattern, replace_card, message)

    def _colorize_message(self, message: str) -> str:
        """
        Add color codes to move result messages.

        Colors:
        - Card names (Card(COLOR, NUMBER)): Use card's color
        - Player numbers: Bright cyan
        - Color names: Use that color
        - Numbers: Bright white
        - Success keywords: Bright green
        - Error keywords: Bright red
        - Important info (tokens, lives): Bright cyan/yellow
        """
        import re
        from hanabi.core.enums import Color

        if not self.use_colors:
            return message

        result = message

        # Colorize short card notation (e.g., G1, R5) - do this before colorizing standalone color names
        # Match patterns like G1, R5, W3, etc.
        short_card_pattern = r'\b([WRYGB])(\d)\b'
        def colorize_short_card(match):
            color_letter = match.group(1)
            number = match.group(2)
            # Map first letter to color enum
            color_map = {'W': Color.WHITE, 'R': Color.RED, 'Y': Color.YELLOW,
                        'G': Color.GREEN, 'B': Color.BLUE}
            if color_letter in color_map:
                color_enum = color_map[color_letter]
                color_code = self._color_map.get(color_enum, Colors.BRIGHT_WHITE)
                return f"{color_code}{color_letter}{number}{Colors.RESET}"
            return match.group(0)
        result = re.sub(short_card_pattern, colorize_short_card, result)

        # Also colorize full Card(COLOR, NUMBER) format (for current player's moves)
        card_pattern = r'Card\((\w+),\s*(\d+)\)'
        def colorize_card(match):
            color_name = match.group(1)
            number = match.group(2)
            try:
                color_enum = Color[color_name]
                color_code = self._color_map.get(color_enum, Colors.BRIGHT_WHITE)
                # Color the entire card string with the card's color
                return f"{color_code}Card({color_name}, {number}){Colors.RESET}"
            except KeyError:
                return match.group(0)
        result = re.sub(card_pattern, colorize_card, result)

        # Mark Card() sections to prevent re-coloring (use a placeholder approach)
        # Actually, since Card() is already colorized, the negative lookbehind should work

        # Colorize player numbers: "player 1", "player 2", etc.
        result = re.sub(r'\bplayer (\d+)\b',
                       lambda m: f"{Colors.BRIGHT_CYAN}player {Colors.BRIGHT_WHITE}{m.group(1)}{Colors.RESET}",
                       result, flags=re.IGNORECASE)

        # Colorize color names (standalone): RED, YELLOW, GREEN, BLUE, WHITE (uppercase)
        # and red, yellow, green, blue, white (lowercase)
        # Also colorize numbers that follow color names (e.g., "red 1" - both words in red)
        # Do this after card names to avoid double-coloring
        for color_name_upper in ['RED', 'YELLOW', 'GREEN', 'BLUE', 'WHITE']:
            try:
                color_enum = Color[color_name_upper]
                color_code = self._color_map.get(color_enum, Colors.BRIGHT_WHITE)
                color_name_lower = color_name_upper.lower()
                # Match both uppercase and lowercase color names
                # Match color name only if it's not part of "Card(COLOR, NUMBER)"
                result = re.sub(rf'(?<!Card\()\b{color_name_upper}\b(?!,\s*\d+\))',
                               f"{color_code}{color_name_upper}{Colors.RESET}",
                               result)
                # Match lowercase color name followed by space and number - color both
                # Pattern: color_name + space + number (but not if part of Card(...))
                # Do this BEFORE matching standalone color names to avoid double matching
                result = re.sub(rf'(?<!Card\()\b{color_name_lower}\b(?!,\s*\d+\))\s+(\d+)(?![^\s])',
                               f"{color_code}{color_name_lower} {color_code}\\1{Colors.RESET}",
                               result)
                # Match lowercase color name (standalone, not followed by number)
                # Use negative lookahead to ensure it's not already colorized
                result = re.sub(rf'(?<!Card\()\b{color_name_lower}\b(?!,\s*\d+\))(?!\s+\d+)(?<!{re.escape(color_code)})(?<!{re.escape(Colors.RESET)})',
                               f"{color_code}{color_name_lower}{Colors.RESET}",
                               result)
            except KeyError:
                pass

        # Colorize success keywords
        success_words = ['Successfully', 'completed', 'Bonus']
        for word in success_words:
            result = re.sub(rf'\b{word}\b',
                           f"{Colors.BRIGHT_GREEN}{word}{Colors.RESET}",
                           result, flags=re.IGNORECASE)

        # Colorize error keywords
        error_words = ['Invalid', 'discarded', 'Lost']
        for word in error_words:
            result = re.sub(rf'\b{word}\b',
                           f"{Colors.BRIGHT_RED}{word}{Colors.RESET}",
                           result, flags=re.IGNORECASE)

        # Colorize important info (do this last to avoid conflicts)
        result = re.sub(r'(Hint tokens?):\s*(\d+)',
                       lambda m: f"{Colors.BRIGHT_CYAN}{m.group(1)}: {Colors.BRIGHT_WHITE}{m.group(2)}{Colors.RESET}",
                       result, flags=re.IGNORECASE)
        result = re.sub(r'(Lives remaining):\s*(\d+)',
                       lambda m: f"{Colors.BRIGHT_YELLOW}{m.group(1)}: {Colors.BRIGHT_WHITE}{m.group(2)}{Colors.RESET}",
                       result, flags=re.IGNORECASE)
        result = re.sub(r'(indices?):\s*([\d,\s]+)',
                       lambda m: f"{Colors.BRIGHT_CYAN}{m.group(1)}: {Colors.BRIGHT_WHITE}{m.group(2)}{Colors.RESET}",
                       result, flags=re.IGNORECASE)

        # Colorize standalone numbers (do this last, but avoid numbers already colored)
        # Match numbers that aren't already inside color codes
        result = re.sub(r'(?<!\[)(?<!\d)\b(\d+)\b(?!\d)(?!\s*(?:/|remaining|tokens|indices))',
                       lambda m: f"{Colors.BRIGHT_WHITE}{m.group(1)}{Colors.RESET}",
                       result)

        return result

    def display_game_state(self, game: Game, player_index: int) -> None:
        """
        Display the game state from a player's perspective.

        Args:
            game: The game instance
            player_index: Index of the current player
        """
        state = game.state
        common_view = state.commonView
        settings = game.settings

        print("\n" + "=" * 70)
        print(f"{Colors.BRIGHT_CYAN}HANABI - Player {player_index + 1}'s Turn{Colors.RESET}")
        print("=" * 70)

        # Display moves from previous round (all players' moves since this player's last turn)
        self._display_previous_round_moves(player_index)

        # Display tokens
        self._display_tokens(common_view, settings)

        # Display current score
        current_score = game.getScore()
        max_score = 25  # Perfect score
        print(f"\n{Colors.BRIGHT_WHITE}Current Score: {Colors.BRIGHT_CYAN}{current_score}/{max_score}{Colors.RESET}")

        # Display fireworks (played cards)
        self._display_fireworks(common_view)

        # Display discard pile details (reconstruct from common view)
        discard_pile = []
        for color, suit in common_view.cardsDiscarded.items():
            for number, count in suit.cards.items():
                for _ in range(count):
                    discard_pile.append(Card(color, number))
        self._display_discard_pile(discard_pile)

        # Display draw deck count (make it more visible)
        deck_count = common_view.cardsToDraw
        if deck_count == 0:
            # Deck is exhausted - show warning
            # Check if this is the final turn phase (deck exhausted but game not finished)
            if not game.isFinished:
                # Other players get their final turn
                print(f"\n{Colors.BRIGHT_RED}⚠️  Draw deck is empty! This is your FINAL TURN! ⚠️{Colors.RESET}")
            else:
                print(f"\n{Colors.BRIGHT_YELLOW}⚠️  Draw deck is empty. Final turn phase.{Colors.RESET}")
            print(f"{Colors.BRIGHT_CYAN}Draw Deck: {deck_count} cards{Colors.RESET}")
        else:
            print(f"\n{Colors.BRIGHT_CYAN}Draw Deck: {deck_count} cards{Colors.RESET}")

        # Display other players' hands (starting from the next player)
        print(f"\n{Colors.BRIGHT_WHITE}Other Players' Hands:{Colors.RESET}")
        # Get player view directly from state (same as _getPlayerView but we can access it here)
        from hanabi.core.game import PlayerView
        state = game.state
        teammates: Dict[int, Hand] = {}
        for i, hand in enumerate(state.playerHands):
            if i != player_index:
                teammates[i] = hand
        player_view = PlayerView(teammates)
        num_players = game.settings.numPlayers

        # Reorder teammates to start from the next player after current player
        teammates_list = list(player_view.teammates.items())
        ordered_teammates = []

        # Start from the next player (player_index + 1) and wrap around
        for offset in range(1, num_players):
            other_idx = (player_index + offset) % num_players
            if other_idx in player_view.teammates:
                ordered_teammates.append((other_idx, player_view.teammates[other_idx]))

        # Display in the reordered sequence
        for other_idx, hand in ordered_teammates:
            self._display_other_player_hand(other_idx, hand)

        # Display current player's hand with hints
        print(f"\n{Colors.BRIGHT_WHITE}Your Hand:{Colors.RESET}")
        own_hand = state.playerHands[player_index]
        from hanabi.core.player import HintTrackingPlayer
        player = game.team.players[player_index]
        player_hints = player.getHints() if isinstance(player, HintTrackingPlayer) else {}
        self._display_own_hand_with_hints(own_hand, player_hints)

        print("\n" + "=" * 70)

    def _display_tokens(self, common_view: CommonView, settings: GameSettings) -> None:
        """Display hint and life tokens with emojis (uniform width with spacing)."""
        hint_tokens = common_view.hintTokens
        life_tokens = common_view.liveTokens
        max_hints = settings.maxHintTokens
        max_lives = settings.maxLiveTokens

        # Emoji for hint tokens (💡 = lightbulb)
        hint_emoji = "💡"
        hint_empty = "⚪"

        # Emoji for life tokens: single firecracker with fuse length
        # The length of the fuse line indicates remaining lives
        # 🧨 = firecracker, ━ = fuse segment, 🔥 = fire, 💥 = explosion
        if life_tokens == max_lives:
            # All lives remaining: long unburned fuse
            life_emoji_str = "🧨━━━"
        elif life_tokens == max_lives - 1:
            # One life lost: medium fuse with fire approaching
            life_emoji_str = "🧨━━🔥"
        elif life_tokens == 1:
            # Two lives lost: short fuse with fire very close
            life_emoji_str = "🧨━🔥"
        else:  # life_tokens == 0
            # All lives lost: exploded
            life_emoji_str = "💥"

        # Build hint emoji string with consistent single-space spacing
        hint_list = [hint_emoji] * hint_tokens + [hint_empty] * (max_hints - hint_tokens)
        hint_emoji_str = " ".join(hint_list)

        # Calculate the actual string length of emoji strings (for padding calculation)
        # Note: We use actual string length, not "visual width", because emoji width
        # can vary by terminal/font, and we'll align the counts instead
        hint_str_len = len(hint_emoji_str)
        life_str_len = len(life_emoji_str)
        max_emoji_str_len = max(hint_str_len, life_str_len)

        # Pad emoji strings to same length so they align
        hint_pad = " " * (max_emoji_str_len - hint_str_len)
        life_pad = " " * (max_emoji_str_len - life_str_len)

        # Format count strings with fixed width for perfect alignment
        # Calculate max width needed for count format "(X/Y)"
        max_count_width = max(len(f"({max_hints}/{max_hints})"), len(f"({max_lives}/{max_lives})"))
        hint_count_str = f"({hint_tokens}/{max_hints})"
        life_count_str = f"({life_tokens}/{max_lives})"

        print(f"\n{Colors.BRIGHT_WHITE}Tokens:{Colors.RESET}")
        print(f"  {Colors.BRIGHT_CYAN}Hints:{Colors.RESET} {hint_emoji_str}{hint_pad} {hint_count_str:>{max_count_width}}")
        print(f"  {Colors.BRIGHT_RED}Lives:{Colors.RESET} {life_emoji_str}{life_pad} {life_count_str:>{max_count_width}}")

    def _display_fireworks(self, common_view: CommonView) -> None:
        """Display the fireworks (played cards)."""
        print(f"\n{Colors.BRIGHT_WHITE}Fireworks (Played Cards):{Colors.RESET}")
        cards_played = common_view.cardsPlayed

        # Display each color
        for color in [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]:
            color_code = self._color_map.get(color, "")
            color_name = color.name
            if color in cards_played:
                number = cards_played[color].value
                # Use the same color for the number as the card color
                print(f"  {color_code}{color_name:8s}{Colors.RESET}: {color_code}{number}{Colors.RESET}")
            else:
                print(f"  {color_code}{color_name:8s}{Colors.RESET}: {Colors.BRIGHT_BLACK}-{Colors.RESET}")

    def _display_discard_pile(self, discard_pile: List[Card]) -> None:
        """Display the discard pile with all cards grouped by color, showing actual card numbers."""
        if not discard_pile:
            print(f"\n{Colors.BRIGHT_BLACK}Discard Pile: (empty){Colors.RESET}")
            return

        # Group cards by color, keeping list of numbers (not counts)
        from collections import defaultdict
        grouped = defaultdict(list)

        for card in discard_pile:
            grouped[card.color].append(card.number.value)

        # Sort numbers for each color
        for color in grouped:
            grouped[color].sort()

        print(f"\n{Colors.BRIGHT_WHITE}Discard Pile ({len(discard_pile)} cards):{Colors.RESET}")

        # Display each color group
        for color in [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]:
            if color in grouped:
                color_code = self._color_map.get(color, "")
                color_name = color.name
                # Show all numbers as a string like "1124", with each number in the card's color
                numbers_str = "".join(f"{color_code}{n}{Colors.RESET}" for n in grouped[color])
                print(f"  {color_code}{color_name:8s}{Colors.RESET}: {numbers_str}")

    def _display_other_player_hand(self, player_index: int, hand: Hand) -> None:
        """Display another player's hand with indices and cards on separate lines."""
        print(f"\n  {Colors.BRIGHT_CYAN}Player {player_index + 1}:{Colors.RESET}")
        cards = hand.cards
        if not cards:
            print(f"    {Colors.BRIGHT_BLACK}(empty){Colors.RESET}")
        else:
            # Fixed column width for each card (visual width, not including ANSI codes)
            col_width = 6  # Enough for "[1]  " or "  Y2 "

            # Display indices on first line (1-based) with fixed width columns
            index_parts = []
            for i in range(len(cards)):
                index_str = f"{Colors.BRIGHT_CYAN}[{i+1}]{Colors.RESET}"
                # Pad to fixed visual width (ANSI codes don't count)
                visual_width = len(f"[{i+1}]")  # "[1]" = 3 chars
                padding = " " * (col_width - visual_width)
                index_parts.append(f"{index_str}{padding}")
            indices_line = "".join(index_parts)
            print(f"    {indices_line}")

            # Display cards on second line, aligned with same column width
            card_parts = []
            for card in cards:
                color_code = self._color_map.get(card.color, "")
                card_str = f"{color_code}{card.color.name[0]}{card.number.value}{Colors.RESET}"
                # Pad to fixed visual width (ANSI codes don't count)
                # Card is 2 chars, pad to match index column width
                visual_width = 2  # "Y2" is 2 chars
                padding = " " * (col_width - visual_width)
                card_parts.append(f"{card_str}{padding}")
            cards_line = "".join(card_parts)
            print(f"    {cards_line}")

    def _display_own_hand_with_hints(self, hand: Hand, hints: Dict[int, Dict[str, any]]) -> None:
        """
        Display the current player's hand with partial info from hints (1-based indices).

        IMPORTANT: The hints dict uses 0-based indices that correspond to the current
        card positions in the hand. This ensures hints are always aligned with the
        correct cards, even after cards are played/discarded and indices shift.
        """
        cards = hand.cards
        if not cards:
            print(f"  {Colors.BRIGHT_BLACK}(empty){Colors.RESET}")
        else:
            # Fixed column width for each card (visual width, not including ANSI codes)
            col_width = 6  # Enough for "[1]  " or "  ?? "

            # Display indices on first line (1-based for UI) with fixed width columns
            index_parts = []
            for i in range(len(cards)):
                index_str = f"{Colors.BRIGHT_CYAN}[{i+1}]{Colors.RESET}"
                # Pad to fixed visual width (ANSI codes don't count)
                visual_width = len(f"[{i+1}]")  # "[1]" = 3 chars
                padding = " " * (col_width - visual_width)
                index_parts.append(f"{index_str}{padding}")
            indices_line = "".join(index_parts)
            print(f"  {indices_line}")

            # Display hint info on second line, aligned with same column width
            # IMPORTANT: Use 0-based index i to match hints dict keys
            hint_parts = []
            for i in range(len(cards)):
                # Hints are stored with 0-based indices matching current card positions
                card_hints = hints.get(i, {})
                color_hint = card_hints.get("color")
                number_hint = card_hints.get("number")

                # Build display string with hints
                # If both color and number hints are present, show both in the color hint's color
                if color_hint and number_hint:
                    # Both hints present: use color hint's color for both characters
                    color_code = self._color_map.get(color_hint, "")
                    hint_str = f"{color_code}{color_hint.name[0]}{number_hint.value}{Colors.RESET}"
                elif color_hint:
                    # Only color hint: show color letter, number as ?
                    color_code = self._color_map.get(color_hint, "")
                    hint_str = f"{color_code}{color_hint.name[0]}{Colors.RESET}?"
                elif number_hint:
                    # Only number hint: show ? for color, number in white
                    hint_str = f"?{Colors.BRIGHT_WHITE}{number_hint.value}{Colors.RESET}"
                else:
                    # No hints: show ??
                    hint_str = "??"
                # Pad to fixed visual width (ANSI codes don't count)
                # Hint is 2 chars, pad to match index column width
                visual_width = 2  # "??" or "R3" is 2 chars
                padding = " " * (col_width - visual_width)
                hint_parts.append(f"{hint_str}{padding}")
            hints_line = "".join(hint_parts)
            print(f"  {hints_line}")

    def _display_move_history(self, game: Game, player_index: int) -> None:
        """Display the most recent moves from all other players."""
        # Move history is not currently tracked in Game class
        # This can be added later if needed
        pass

    def display_available_moves(self, game: Game, player_index: int) -> None:
        """Display available moves for the current player."""
        state = game.state
        common_view = state.commonView
        hand = state.playerHands[player_index]
        num_players = game.settings.numPlayers

        print(f"\n{Colors.BRIGHT_WHITE}Available Moves:{Colors.RESET}")

        # Play a card
        if hand.cards:
            print(f"  {Colors.BRIGHT_GREEN}p<index> or play <index>{Colors.RESET} - Play a card (indices 1-{len(hand.cards)})")
            print(f"    Examples: {Colors.BRIGHT_GREEN}p1{Colors.RESET}, {Colors.BRIGHT_GREEN}play 1{Colors.RESET}")

        # Discard a card (only available if hint tokens are not at maximum)
        if hand.cards and common_view.hintTokens < game.settings.maxHintTokens:
            print(f"  {Colors.BRIGHT_YELLOW}d<index> or discard <index>{Colors.RESET} - Discard a card (indices 1-{len(hand.cards)})")
            print(f"    Examples: {Colors.BRIGHT_YELLOW}d2{Colors.RESET}, {Colors.BRIGHT_YELLOW}discard 2{Colors.RESET}")
        elif hand.cards and common_view.hintTokens >= game.settings.maxHintTokens:
            print(f"  {Colors.BRIGHT_BLACK}discard (not available - hint tokens at maximum){Colors.RESET}")

        # Give a hint
        if common_view.hintTokens > 0:
            if num_players == 2:
                print(f"  {Colors.BRIGHT_CYAN}h<value>{Colors.RESET} - Give a hint to other player")
                print(f"    Examples: {Colors.BRIGHT_CYAN}h3{Colors.RESET} (number 3), {Colors.BRIGHT_CYAN}hr{Colors.RESET} (red), {Colors.BRIGHT_CYAN}hy{Colors.RESET} (yellow)")
            else:
                print(f"  {Colors.BRIGHT_CYAN}h<player><value> or hint <player> <color|number> <value>{Colors.RESET}")
                print(f"    Examples: {Colors.BRIGHT_CYAN}h23{Colors.RESET} (player 2, number 3), {Colors.BRIGHT_CYAN}h1r{Colors.RESET} (player 1, red)")
                print(f"    Available players: {', '.join(str(i+1) for i in range(num_players) if i != player_index)}")
        else:
            print(f"  {Colors.BRIGHT_BLACK}hint (not available - no hint tokens){Colors.RESET}")

    def display_move_result(self, success: bool, message: str) -> None:
        """Display the result of a move."""
        # Colorize the message content
        colorized_msg = self._colorize_message(message)

        if success:
            # Wrap in green for success, but message itself is already colorized
            print(f"\n{Colors.BRIGHT_GREEN}{colorized_msg}{Colors.RESET}\n")
        else:
            # Wrap in red for error, but message itself is already colorized
            print(f"\n{Colors.BRIGHT_RED}{colorized_msg}{Colors.RESET}\n")

    def display_game_end(self, game: Game) -> None:
        """Display game end information with score and rating."""
        state = game.state
        score = game.getScore()
        max_score = 25  # Perfect score

        print("\n" + "=" * 70)
        print(f"{Colors.BRIGHT_CYAN}GAME OVER{Colors.RESET}")
        print("=" * 70)

        # Determine game end reason and score comment
        if state.commonView.liveTokens <= 0:
            end_reason = f"{Colors.BRIGHT_RED}You lost! Ran out of life tokens.{Colors.RESET}"
        elif score == max_score:
            end_reason = f"{Colors.BRIGHT_GREEN}Perfect Score! All fireworks completed!{Colors.RESET}"
        elif game.settings.autoEndWhenNoPointsPossible and state._isNoMorePointsPossible():
            end_reason = f"{Colors.BRIGHT_YELLOW}Game ended. No more points possible (all needed cards discarded).{Colors.RESET}"
        else:
            end_reason = f"{Colors.BRIGHT_YELLOW}Game ended.{Colors.RESET}"

        print(end_reason)
        print()

        # Display score with rating comment
        score_comment = self._get_score_comment(score, max_score)
        print(f"{Colors.BRIGHT_WHITE}Final Score: {Colors.BRIGHT_CYAN}{score}/{max_score}{Colors.RESET}")
        print(f"{Colors.BRIGHT_WHITE}Rating: {score_comment}{Colors.RESET}")
        print()

        # Display final fireworks
        self._display_fireworks(state.commonView)
        print("=" * 70 + "\n")

    def _get_score_comment(self, score: int, max_score: int) -> str:
        """
        Get a comment/rating based on the final score.

        Based on the official Hanabi rules (Artisan League Of Fireworks Technicians reference scale):
        - 25: legendary, everyone left speechless, stars in their eyes!
        - 21-24: amazing, they will be talking about it for weeks!
        - 16-20: excellent, crowd pleasing.
        - 11-15: honorable attempt, but quickly forgotten...
        - 6-10: mediocre, just a hint of scattered applause...
        - <=5: horrible, booed by the crowd...
        """
        if score == max_score:
            return f"{Colors.BRIGHT_GREEN}legendary, everyone left speechless, stars in their eyes!{Colors.RESET}"
        elif score >= 21:
            return f"{Colors.BRIGHT_GREEN}amazing, they will be talking about it for weeks!{Colors.RESET}"
        elif score >= 16:
            return f"{Colors.BRIGHT_CYAN}excellent, crowd pleasing.{Colors.RESET}"
        elif score >= 11:
            return f"{Colors.BRIGHT_YELLOW}honorable attempt, but quickly forgotten...{Colors.RESET}"
        elif score >= 6:
            return f"{Colors.YELLOW}mediocre, just a hint of scattered applause...{Colors.RESET}"
        else:
            return f"{Colors.BRIGHT_BLACK}horrible, booed by the crowd...{Colors.RESET}"

    def record_move(self, player_index: int, move: Move, turn_number: int) -> None:
        """
        Record a move for tracking previous round moves.

        Args:
            player_index: Index of the player who made the move
            move: The move that was made
            turn_number: Turn number when the move was made
        """
        # Record this move with turn number
        self._all_moves.append((player_index, move, turn_number))
        # Update last turn: store the turn number BEFORE this move
        # So when the player comes back, we show moves with turn > (turn_number - 1)
        # This includes their own move from the previous turn
        self._last_player_turn[player_index] = turn_number - 1

    def _display_previous_round_moves(self, current_player_index: int) -> None:
        """
        Display all moves from the previous round (since current player's last turn).

        Args:
            current_player_index: Index of the current player
        """
        # Get the last turn number before this player's last move
        # We want to show all moves that happened after that turn
        # (including the current player's own move from their previous turn)
        last_turn = self._last_player_turn.get(current_player_index, -1)

        # Filter moves that happened after the turn before the current player's last move
        # This includes the current player's own move from their previous turn
        previous_round_moves = [
            (player_idx, move, turn_num)
            for player_idx, move, turn_num in self._all_moves
            if turn_num > last_turn
        ]

        if not previous_round_moves:
            # First turn or no moves since last turn
            return

        print(f"\n{Colors.BRIGHT_WHITE}Previous Round Moves:{Colors.RESET}")

        # Display moves in order of turn number
        for player_idx, move, turn_num in previous_round_moves:
            # Format the move nicely
            move_str = self._format_move_for_display(move, player_idx)
            print(f"  {move_str}")

    def _format_move_for_display(self, move: Move, player_index: int) -> str:
        """
        Format a move for display in the previous round moves section.

        Args:
            move: The move to format
            player_index: Index of the player who made the move

        Returns:
            Formatted string representation of the move
        """
        from hanabi.core.moves import Play, Discard, ColorHint, NumberHint

        player_label = f"{Colors.BRIGHT_CYAN}Player {player_index + 1}{Colors.RESET}"

        if isinstance(move, Play):
            return f"{player_label}: {Colors.BRIGHT_GREEN}Played{Colors.RESET} card at position {move.card}"
        elif isinstance(move, Discard):
            return f"{player_label}: {Colors.BRIGHT_YELLOW}Discarded{Colors.RESET} card at position {move.card}"
        elif isinstance(move, ColorHint):
            color_name = move.color.name
            color_code = self._color_map.get(move.color, Colors.BRIGHT_WHITE)
            cards_str = ", ".join(str(c) for c in move.cards)
            return f"{player_label}: {Colors.BRIGHT_MAGENTA}Hinted{Colors.RESET} {color_code}{color_name}{Colors.RESET} to Player {move.teammate + 1} (cards: {cards_str})"
        elif isinstance(move, NumberHint):
            number = move.number.value
            cards_str = ", ".join(str(c) for c in move.cards)
            return f"{player_label}: {Colors.BRIGHT_MAGENTA}Hinted{Colors.RESET} number {Colors.BRIGHT_WHITE}{number}{Colors.RESET} to Player {move.teammate + 1} (cards: {cards_str})"
        else:
            return f"{player_label}: {move}"

    def clear_previous_round_moves(self) -> None:
        """Clear the previous round moves (e.g., at start of new game)."""
        self._all_moves = []
        self._last_player_turn = {}

    def display_prompt(self, player_index: int) -> None:
        """Display input prompt."""
        print(f"{Colors.BRIGHT_CYAN}Player {player_index + 1}, enter your move: {Colors.RESET}", end="")

