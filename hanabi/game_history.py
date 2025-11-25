"""
Game history tracking for Hanabi game replay.
"""

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    import json

from datetime import datetime
from typing import List, Dict, Any, Optional
from .game_engine import GameEngine
from .moves import Move, Play, Discard, ColorHint, NumberHint


class GameHistory:
    """Tracks and saves game history for replay."""
    
    def __init__(self, settings: Dict[str, Any]):
        """
        Initialize game history.
        
        Args:
            settings: Game settings dictionary
        """
        self._settings = settings
        self._moves: List[Dict[str, Any]] = []
        self._initial_state: Optional[Dict[str, Any]] = None
        self._start_time = datetime.now()
    
    def record_initial_state(self, engine: GameEngine) -> None:
        """Record the initial game state."""
        self._initial_state = self._serialize_state(engine, concise=True)
    
    def record_move(self, player_index: int, move: Move, result: str, engine: GameEngine) -> None:
        """
        Record a move and the resulting game state.
        
        Args:
            player_index: Index of the player who made the move
            move: The move that was made
            result: Result message
            engine: The game engine after the move
        """
        move_record = {
            "p": player_index,  # Short field name
            "m": self._serialize_move(move),  # Short field name
            "r": result,  # Short field name
            "s": self._serialize_state(engine, concise=True)  # Short field name, concise format
        }
        self._moves.append(move_record)
    
    def _card_to_short(self, card) -> str:
        """Convert a card to short notation (e.g., G5)."""
        from .enums import Color
        color_map = {Color.WHITE: 'W', Color.RED: 'R', Color.YELLOW: 'Y', 
                    Color.GREEN: 'G', Color.BLUE: 'B', Color.MULTI: 'M'}
        return f"{color_map.get(card.color, '?')}{card.number.value}"
    
    def _serialize_move(self, move: Move) -> Dict[str, Any]:
        """Serialize a move to a dictionary (concise format)."""
        if isinstance(move, Play):
            return {"t": "p", "c": move.card}  # type: play, card index
        elif isinstance(move, Discard):
            return {"t": "d", "c": move.card}  # type: discard, card index
        elif isinstance(move, ColorHint):
            return {
                "t": "ch",  # type: color_hint
                "tm": move.teammate,  # teammate
                "cl": move.color.name[0],  # color (first letter)
                "cs": move.cards  # cards (indices)
            }
        elif isinstance(move, NumberHint):
            return {
                "t": "nh",  # type: number_hint
                "tm": move.teammate,  # teammate
                "n": move.number.value,  # number
                "cs": move.cards  # cards (indices)
            }
        else:
            return {"t": "?", "m": str(move)}
    
    def _serialize_state(self, engine: GameEngine, concise: bool = False) -> Dict[str, Any]:
        """Serialize game state to a dictionary."""
        state = engine.gameState
        common_view = state.commonView
        
        if concise:
            # Concise format: use short notation and compact field names
            # Serialize player hands as short notation (e.g., ["G5", "B3", "R1"])
            player_hands = []
            for hand in state.playerHands:
                cards = [self._card_to_short(card) for card in hand.cards]
                player_hands.append(cards)
            
            # Serialize player hints (only non-empty, compact format)
            # Omit empty hint dictionaries to save space
            player_hints = []
            for player_idx in range(engine.settings.numPlayers):
                hints = engine.getPlayerHints(player_idx)
                hints_dict = {}
                for card_idx, hint_data in hints.items():
                    hint_parts = []
                    if hint_data.get("color"):
                        hint_parts.append(hint_data["color"].name[0])  # First letter
                    if hint_data.get("number"):
                        hint_parts.append(str(hint_data["number"].value))
                    if hint_parts:
                        hints_dict[card_idx] = "".join(hint_parts)  # e.g., "G" or "3" or "G3"
                # Only add if non-empty (saves space)
                player_hints.append(hints_dict if hints_dict else None)
            
            # Serialize cards played as short notation (e.g., {"G": 5, "R": 3})
            cards_played = {}
            for color, number in common_view.cardsPlayed.items():
                color_map = {Color.WHITE: 'W', Color.RED: 'R', Color.YELLOW: 'Y', 
                            Color.GREEN: 'G', Color.BLUE: 'B', Color.MULTI: 'M'}
                cards_played[color_map.get(color, '?')] = number.value
            
            # Serialize discard pile as short notation list (e.g., ["G5", "R3", "B1"])
            discard_pile = [self._card_to_short(card) for card in engine.getDiscardPile()]
            
            return {
                "cp": engine.currentPlayer,  # current_player
                "ht": common_view.hintTokens,  # hint_tokens
                "lt": common_view.liveTokens,  # live_tokens
                "cd": common_view.cardsToDraw,  # cards_to_draw
                "ph": player_hands,  # player_hands
                "h": player_hints,  # hints
                "pl": cards_played,  # cards_played (pl = played)
                "dp": discard_pile,  # discard_pile
                "sc": engine.getScore(),  # score
                "f": engine.isFinished()  # finished
            }
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
            
            player_hints = []
            for player_idx in range(engine.settings.numPlayers):
                hints = engine.getPlayerHints(player_idx)
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
            
            discard_pile = []
            for card in engine.getDiscardPile():
                discard_pile.append({
                    "color": card.color.name,
                    "number": card.number.value
                })
            
            return {
                "current_player": engine.currentPlayer,
                "hint_tokens": common_view.hintTokens,
                "live_tokens": common_view.liveTokens,
                "cards_to_draw": common_view.cardsToDraw,
                "player_hands": player_hands,
                "player_hints": player_hints,
                "cards_played": cards_played,
                "discard_pile": discard_pile,
                "score": engine.getScore(),
                "is_finished": engine.isFinished()
            }
    
    def save_to_file(self, filename: Optional[str] = None) -> str:
        """
        Save game history to a YAML file (or JSON if YAML is not available).
        
        Args:
            filename: Optional filename. If None, generates a timestamped filename.
            
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
        
        history_data = {
            "s": self._settings,  # settings
            "st": self._start_time.isoformat(),  # start_time
            "et": datetime.now().isoformat(),  # end_time
            "i": self._initial_state,  # initial_state
            "m": self._moves,  # moves
            "tm": len(self._moves)  # total_moves
        }
        
        with open(filename, 'w') as f:
            if YAML_AVAILABLE:
                # Use custom dumper with flow style for lists to make it more compact
                class CompactListDumper(yaml.SafeDumper):
                    def represent_list(self, data):
                        # Use flow style for lists (more compact)
                        return self.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)
                
                CompactListDumper.add_representer(list, CompactListDumper.represent_list)
                yaml.dump(history_data, f, Dumper=CompactListDumper, 
                         default_flow_style=False, sort_keys=False, allow_unicode=True)
            else:
                json.dump(history_data, f, indent=2)
        
        return filename
    
    def load_from_file(self, filename: str) -> Dict[str, Any]:
        """
        Load game history from a YAML or JSON file.
        
        Args:
            filename: The filename to load from
            
        Returns:
            The loaded history data
        """
        with open(filename, 'r') as f:
            if (filename.endswith('.yaml') or filename.endswith('.yml')) and YAML_AVAILABLE:
                return yaml.safe_load(f)
            else:
                # Fallback to JSON
                if not YAML_AVAILABLE:
                    import json
                return json.load(f)

