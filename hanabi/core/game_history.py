"""
Game history tracking for Hanabi game replay.
"""

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    import json

import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from .game import Game, Deck, StartPosition
from .moves import Move, Play, Discard, ColorHint, NumberHint
from .enums import Color, Number
from .card import Card


class GameHistory:
    """Tracks and saves game history for replay."""

    # Subdirectory for ad-hoc game records (single games, GUI/CLI saves, etc.)
    # Organized separately from structured experiment outputs.
    RECORDS_DIR = os.path.join("game_records", "ad_hoc")

    @staticmethod
    def _get_records_dir() -> str:
        """Get the path to the game records directory, creating it if necessary."""
        records_dir = GameHistory.RECORDS_DIR
        if not os.path.exists(records_dir):
            os.makedirs(records_dir)
        return records_dir

    @staticmethod
    def _get_file_path(filename: str) -> str:
        """
        Get the full path for a game record file.
        If filename is already a full path, returns it as-is.
        Otherwise, places it in the game_records subdirectory.
        """
        # If filename is already a full path (contains path separator), use it as-is
        if os.path.sep in filename or (os.path.altsep and os.path.altsep in filename):
            return filename

        # Otherwise, place it in the game_records subdirectory
        records_dir = GameHistory._get_records_dir()
        return os.path.join(records_dir, filename)

    def __init__(self, settings: Dict[str, Any]):
        """
        Initialize game history.

        Args:
            settings: Game settings dictionary
        """
        self._settings = settings
        self._moves: List[str] = []  # List of short format move strings
        self._deck: Optional[List[str]] = None
        self._players: Optional[List[str]] = None
        self._start_time = datetime.now()
        self._final_score: Optional[int] = None

    def record_initial_state(self, game: Game) -> None:
        """Record the initial game state - only the deck is needed for replay."""
        state = game.state
        deck = state.startPosition.drawDeck
        # Store deck directly (no initial_state wrapper)
        self._deck = [self._card_to_short(card) for card in deck.cards]

        # Record player class names (not in settings, will be at root level)
        self._players = []
        for player in game.team.players:
            class_name = player.__class__.__name__
            self._players.append(class_name)

    def record_move(self, player_index: int, move: Move, result: str, game: Game) -> None:
        """
        Record a move in short format (state can be reconstructed during replay).

        Args:
            player_index: Index of the player who made the move (not saved - deterministic)
            move: The move that was made
            result: Result message (not saved to file)
            game: The game after the move (not used, kept for compatibility)
        """
        # Convert move to short format string
        move_str = self._move_to_short(move)
        self._moves.append(move_str)

    def _card_to_short(self, card) -> str:
        """Convert a card to short notation (e.g., G5)."""
        color_map = {Color.WHITE: 'W', Color.RED: 'R', Color.YELLOW: 'Y',
                    Color.GREEN: 'G', Color.BLUE: 'B', Color.MULTI: 'M'}
        return f"{color_map.get(card.color, '?')}{card.number.value}"

    @staticmethod
    def _short_to_card(short: str) -> Card:
        """Convert short notation (e.g., G5) to a Card."""
        color_map = {'W': Color.WHITE, 'R': Color.RED, 'Y': Color.YELLOW,
                    'G': Color.GREEN, 'B': Color.BLUE, 'M': Color.MULTI}
        if len(short) < 2:
            raise ValueError(f"Invalid card notation: {short}")
        color_char = short[0]
        number_str = short[1:]
        color = color_map.get(color_char)
        if color is None:
            raise ValueError(f"Invalid color: {color_char}")
        try:
            number = Number(int(number_str))
        except (ValueError, KeyError):
            raise ValueError(f"Invalid number: {number_str}")
        return Card(color, number)

    @staticmethod
    def _short_to_move(move_str: str, current_player: int, game: Game) -> Optional[Move]:
        """
        Parse a short format move string to a Move object.

        Args:
            move_str: Short format string (e.g., "p3", "d4", "h11", "h4w")
            current_player: Index of the current player (0-based)
            game: Game instance (needed to determine which cards match hints)

        Returns:
            Move object or None if invalid
        """
        if not move_str or len(move_str) < 2:
            return None

        cmd = move_str[0].lower()
        rest = move_str[1:]

        if cmd == 'p':  # play
            try:
                card_index_ui = int(rest)  # 1-based
                card_index = card_index_ui - 1  # Convert to 0-based
                return Play(card_index)
            except ValueError:
                return None

        elif cmd == 'd':  # discard
            try:
                card_index_ui = int(rest)  # 1-based
                card_index = card_index_ui - 1  # Convert to 0-based
                return Discard(card_index)
            except ValueError:
                return None

        elif cmd == 'h':  # hint
            if not rest or len(rest) < 2:
                return None

            # Parse teammate (1-based, first digit)
            # Format: h<teammate><hint_value>
            # Examples: h14 (teammate 1, number 4), h2w (teammate 2, white), h53 (teammate 5, number 3)
            try:
                teammate_ui = int(rest[0])  # 1-based
                teammate = teammate_ui - 1  # Convert to 0-based
                hint_value = rest[1:]  # Rest is the hint value
            except (ValueError, IndexError):
                return None

            # Check if hint value is a number or color
            if hint_value.isdigit():
                # Number hint: h<teammate><number>
                try:
                    number_value = int(hint_value)
                    if number_value < 1 or number_value > 5:
                        return None
                    number = Number(number_value)
                    # Find matching cards in teammate's hand
                    state = game.state
                    if teammate >= len(state.playerHands):
                        return None
                    teammate_hand = state.playerHands[teammate]
                    matching = [i for i, c in enumerate(teammate_hand.cards) if c.number == number]
                    if not matching:
                        # Log error for debugging
                        import logging
                        logger = logging.getLogger(__name__)
                        hand_desc = ", ".join([f"{c.color.name[0]}{c.number.value}" for c in teammate_hand.cards]) if teammate_hand.cards else "empty"
                        logger.error(f"Replay: Cannot create hint '{move_str}': No {number_value} cards in player {teammate + 1}'s hand. "
                                    f"Hand ({len(teammate_hand.cards)} cards): [{hand_desc}]")
                        return None
                    return NumberHint(teammate, matching, number)
                except (ValueError, KeyError):
                    return None
            else:
                # Color hint: h<teammate><color>
                color_map = {'w': Color.WHITE, 'r': Color.RED, 'y': Color.YELLOW,
                            'g': Color.GREEN, 'b': Color.BLUE, 'm': Color.MULTI}
                color_char = hint_value[0].lower()
                color = color_map.get(color_char)
                if color is None:
                    return None
                # Find matching cards in teammate's hand
                state = game.state
                if teammate >= len(state.playerHands):
                    return None
                teammate_hand = state.playerHands[teammate]
                matching = [i for i, c in enumerate(teammate_hand.cards) if c.color == color]
                if not matching:
                    # Log error for debugging
                    import logging
                    logger = logging.getLogger(__name__)
                    hand_desc = ", ".join([f"{c.color.name[0]}{c.number.value}" for c in teammate_hand.cards]) if teammate_hand.cards else "empty"
                    logger.error(f"Replay: Cannot create hint '{move_str}': No {color.name.lower()} cards in player {teammate + 1}'s hand. "
                                f"Hand ({len(teammate_hand.cards)} cards): [{hand_desc}]")
                    return None
                return ColorHint(teammate, matching, color)

        return None

    def _move_to_short(self, move: Move) -> str:
        """Convert a move to short format string (e.g., p3, d4, h11, h4w)."""
        if isinstance(move, Play):
            return f"p{move.card + 1}"
        if isinstance(move, Discard):
            return f"d{move.card + 1}"
        if isinstance(move, ColorHint):
            color_map = {Color.WHITE: 'w', Color.RED: 'r', Color.YELLOW: 'y',
                        Color.GREEN: 'g', Color.BLUE: 'b', Color.MULTI: 'm'}
            color_char = color_map.get(move.color, 'r')
            return f"h{move.teammate + 1}{color_char}"
        if isinstance(move, NumberHint):
            return f"h{move.teammate + 1}{move.number.value}"
        assert False, f"unexpected move type in _move_to_short: {type(move)}"

    def _serialize_state(self, game: Game, concise: bool = False, include_deck: bool = False) -> Dict[str, Any]:
        """Serialize game state to a dictionary."""
        state = game.state
        common_view = state.commonView

        if concise:
            # Concise format: use short notation and compact field names
            # Serialize player hands as short notation (e.g., ["G5", "B3", "R1"])
            player_hands = []
            for hand in state.playerHands:
                cards = [self._card_to_short(card) for card in hand.cards]
                player_hands.append(cards)

            # Serialize cards played as short notation (e.g., {"G": 5, "R": 3})
            cards_played = {}
            for color, number in common_view.cardsPlayed.items():
                color_map = {Color.WHITE: 'W', Color.RED: 'R', Color.YELLOW: 'Y',
                            Color.GREEN: 'G', Color.BLUE: 'B', Color.MULTI: 'M'}
                cards_played[color_map.get(color, '?')] = number.value

            # Serialize discard pile as short notation list (reconstruct from common view)
            discard_pile = []
            for color, suit in common_view.cardsDiscarded.items():
                for number, count in suit.cards.items():
                    for _ in range(count):
                        discard_pile.append(self._card_to_short(Card(color, number)))

            result = {
                "current_player": game.currentPlayer,
                "hint_tokens": common_view.hintTokens,
                "live_tokens": common_view.liveTokens,
                "cards_to_draw": common_view.cardsToDraw,
                "player_hands": player_hands,
                "cards_played": cards_played,
                "discard_pile": discard_pile,
                "score": game.getScore(),
                "is_finished": game.isFinished
            }

            # Include deck in initial state for replay
            if include_deck:
                deck = state.startPosition.drawDeck
                result["deck"] = [self._card_to_short(card) for card in deck.cards]

            return result
        else:
            # Original verbose format (for backward compatibility)
            player_hands = []
            for hand in state.playerHands:
                cards = []
                for card in hand.cards:
                    cards.append({
                        "color": card.color.name,
                        "number": card.number.value
                    })
                player_hands.append(cards)

            from .player import HintTrackingPlayer
            player_hints = []
            for player_idx in range(game.settings.numPlayers):
                player = game.team.players[player_idx]
                hints = player.getHints() if isinstance(player, HintTrackingPlayer) else {}
                hints_dict = {}
                for card_idx, hint_data in hints.items():
                    hint_entry = {}
                    if hint_data.get("color"):
                        hint_entry["color"] = hint_data["color"].name
                    if hint_data.get("number"):
                        hint_entry["number"] = hint_data["number"].value
                    if hint_entry:
                        hints_dict[card_idx] = hint_entry
                player_hints.append(hints_dict if hints_dict else {})

            cards_played = {}
            for color, number in common_view.cardsPlayed.items():
                cards_played[color.name] = number.value

            # Reconstruct discard pile from common view
            discard_pile = []
            for color, suit in common_view.cardsDiscarded.items():
                for number, count in suit.cards.items():
                    for _ in range(count):
                        discard_pile.append({
                            "color": color.name,
                            "number": number.value
                        })

            return {
                "current_player": game.currentPlayer,
                "hint_tokens": common_view.hintTokens,
                "live_tokens": common_view.liveTokens,
                "cards_to_draw": common_view.cardsToDraw,
                "player_hands": player_hands,
                "player_hints": player_hints,
                "cards_played": cards_played,
                "discard_pile": discard_pile,
                "score": game.getScore(),
                "is_finished": game.isFinished
            }

    def record_final_score(self, game: Game) -> None:
        """Record the final score when the game ends."""
        self._final_score = game.getScore()

    def save_to_file(self, filename: Optional[str] = None, final_score: Optional[int] = None) -> str:
        """
        Save game history to a YAML file (or JSON if YAML is not available).

        Args:
            filename: Optional filename. If None, generates a timestamped filename.
            final_score: Optional final score. If None, uses recorded final score.

        Returns:
            The filename where the history was saved.
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if YAML_AVAILABLE:
                filename = f"hanabi_game_{timestamp}.yaml"
            else:
                filename = f"hanabi_game_{timestamp}.json"
        elif not filename.endswith('.yaml') and not filename.endswith('.json') and not filename.endswith('.yml'):
            # Add appropriate extension if none provided
            if YAML_AVAILABLE:
                filename = filename + '.yaml'
            else:
                filename = filename + '.json'
        elif filename.endswith('.json') and YAML_AVAILABLE:
            # Convert .json to .yaml if YAML is available
            filename = filename[:-5] + '.yaml'
        elif (filename.endswith('.yaml') or filename.endswith('.yml')) and not YAML_AVAILABLE:
            # Convert .yaml to .json if YAML is not available
            filename = filename.rsplit('.', 1)[0] + '.json'

        # Get the full path (in game_records subdirectory if not already a full path)
        filepath = self._get_file_path(filename)

        # Use provided final_score or recorded one
        score = final_score if final_score is not None else self._final_score

        history_data = {
            "settings": self._settings,
            "time": {
                "begin": self._start_time.isoformat(),
                "end": datetime.now().isoformat()
            },
            "deck": self._deck,
            "players": self._players,
            "moves": self._moves  # List of strings like ["p3", "d4", "h11", "h4w"]
        }

        # Add final score if available
        if score is not None:
            history_data["final_score"] = score

        with open(filepath, 'w') as f:
            if YAML_AVAILABLE:
                # Custom dumper to use flow style for leaf arrays (hands, card indices)
                class FlowStyleDumper(yaml.SafeDumper):
                    def represent_list(self, data):
                        # Use flow style for simple lists (leaf arrays)
                        # Check if it's a list of strings/numbers (leaf array)
                        if data and all(isinstance(x, (str, int)) for x in data):
                            return self.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)
                        # Otherwise use block style
                        return self.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=False)

                FlowStyleDumper.add_representer(list, FlowStyleDumper.represent_list)
                yaml.dump(history_data, f, Dumper=FlowStyleDumper, sort_keys=False,
                         allow_unicode=True, width=120)
            else:
                json.dump(history_data, f, indent=2)

        return filepath

    def load_from_file(self, filename: str) -> Dict[str, Any]:
        """
        Load game history from a YAML or JSON file.

        Args:
            filename: The filename to load from (can be just filename or full path)

        Returns:
            The loaded history data
        """
        # Try the filename as-is first (in case it's a full path from file dialog)
        filepath = filename
        if not os.path.exists(filepath):
            # If not found, try in the game_records subdirectory
            filepath = self._get_file_path(filename)
            if not os.path.exists(filepath):
                # If still not found, try in the root directory (for backward compatibility)
                if not os.path.exists(filename):
                    raise FileNotFoundError(f"Game history file not found: {filename}")
                filepath = filename

        with open(filepath, 'r') as f:
            if (filename.endswith('.yaml') or filename.endswith('.yml')) and YAML_AVAILABLE:
                return yaml.safe_load(f)
            else:
                # Fallback to JSON
                if not YAML_AVAILABLE:
                    import json
                return json.load(f)

    @staticmethod
    def create_game_from_history(history_data: dict, team, on_move=None) -> Game:
        """
        Create a Game instance from history data for replay.

        Args:
            history_data: The loaded history data dictionary
            team: PlayerTeam to use for the game
            on_move: Optional move callback

        Returns:
            A Game instance reconstructed from history
        """
        from .game import create_standard_game_settings
        from .game import create_deck_from_settings, Hand, CommonView, GameState

        # Get deck from root level
        deck_short = history_data.get("deck", [])
        if not deck_short:
            raise ValueError("History data missing deck")

        # Get settings
        settings_dict = history_data.get("settings", {})
        num_players = settings_dict.get("num_players", 3)
        settings = create_standard_game_settings(num_players)
        # Reconstruct deck from saved cards
        deck_cards = [GameHistory._short_to_card(short) for short in deck_short]
        deck = Deck(deck_cards)

        # Create start position with the reconstructed deck
        start_position = StartPosition(settings, deck)

        # Reconstruct initial player hands from deck (deal cards in order)
        player_hands = []
        draw_deck_index = 0
        deck_cards = deck.cards
        cards_per_player = settings.maxCardsInHand

        for player_idx in range(num_players):
            hand_cards = []
            for _ in range(cards_per_player):
                if draw_deck_index < len(deck_cards):
                    hand_cards.append(deck_cards[draw_deck_index])
                    draw_deck_index += 1
                else:
                    raise ValueError(f"Not enough cards in deck to deal to player {player_idx}")
            player_hands.append(Hand(hand_cards))

        # Initialize common view
        remaining_cards = len(deck_cards) - draw_deck_index
        common_view = CommonView(
            live_tokens=settings.maxLiveTokens,
            hint_tokens=settings.maxHintTokens,
            cards_to_draw=remaining_cards,
            cards_discarded={},
            cards_played={}
        )

        # Reconstruct initial game state
        state = GameState(
            start_position=start_position,
            common_view=common_view,
            player_hands=player_hands,
            draw_deck_index=draw_deck_index,
            turn_number=0,
            current_player=0,
            turns_left=None
        )

        # Create game instance
        game = Game(start_position, team, on_move)
        game._turns.append(state)
        game._set_common_view_for_players()

        return game

