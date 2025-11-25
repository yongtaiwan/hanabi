# Hanabi Game Architecture - Design Proposal for Extensibility

## Executive Summary

This document proposes architectural improvements to make the Hanabi game implementation more extensible, supporting:
1. Multiple AI player interfaces
2. Flexible game rules and variants
3. Pluggable UI (console/GUI) with shared engine
4. Simulation and statistics collection
5. Game replay with full visibility

---

## Current Architecture Analysis

### Strengths
- Clean separation of game logic (`GameEngine`) from display (`ConsoleDisplay`)
- Well-defined interfaces (`Player`, `Observer`)
- Immutable game state structures
- History/replay system already in place

### Areas for Improvement
1. **Hardcoded game rules**: Standard 5-color game is hardcoded
2. **Tight coupling**: Console game directly uses `ConsoleDisplay` and `ConsoleInput`
3. **Limited AI support**: Player interface exists but not optimized for AI integration
4. **No statistics framework**: No infrastructure for batch simulations
5. **Replay mode**: History exists but no replay viewer with full card visibility

---

## Proposed Architecture

### 1. Game Rules & Variants System

#### 1.1 Rule Configuration Interface

```python
# hanabi/rules.py

from abc import ABC, abstractmethod
from typing import Dict, List
from .enums import Color, Number
from .card import Suit
from .game import GameSettings

class RuleSet(ABC):
    """Abstract base class for game rule sets."""
    
    @abstractmethod
    def create_settings(self, num_players: int) -> GameSettings:
        """Create game settings for a given number of players."""
        pass
    
    @abstractmethod
    def get_variant_name(self) -> str:
        """Get the name of this variant."""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Get description of this variant."""
        pass

class StandardRuleSet(RuleSet):
    """Standard 5-color Hanabi rules."""
    
    def create_settings(self, num_players: int) -> GameSettings:
        # Current create_standard_game_settings logic
        pass
    
    def get_variant_name(self) -> str:
        return "Standard"
    
    def get_description(self) -> str:
        return "Standard 5-color Hanabi (White, Red, Yellow, Green, Blue)"

class RainbowRuleSet(RuleSet):
    """Rainbow variant: 6th color (Rainbow/Multi) acts as wildcard."""
    
    def create_settings(self, num_players: int) -> GameSettings:
        # Rainbow variant logic
        pass

class MultiColorRuleSet(RuleSet):
    """Multi-color variant: 6th color with special rules."""
    
    def create_settings(self, num_players: int) -> GameSettings:
        # Multi-color variant logic
        pass

class SixSuitsRuleSet(RuleSet):
    """6 suits variant: adds a 6th color."""
    
    def create_settings(self, num_players: int) -> GameSettings:
        # 6 suits variant logic
        pass

class CustomRuleSet(RuleSet):
    """Custom rule set with configurable parameters."""
    
    def __init__(
        self,
        colors: List[Color],
        distribution: Dict[Number, int],
        max_live_tokens: int = 3,
        max_hint_tokens: int = 8,
        cards_per_hand: Dict[int, int] = None  # num_players -> cards
    ):
        self._colors = colors
        self._distribution = distribution
        self._max_live_tokens = max_live_tokens
        self._max_hint_tokens = max_hint_tokens
        self._cards_per_hand = cards_per_hand or {2: 5, 3: 5, 4: 4, 5: 4}
    
    def create_settings(self, num_players: int) -> GameSettings:
        cards: Dict[Color, Suit] = {}
        for color in self._colors:
            cards[color] = Suit(self._distribution.copy())
        
        max_cards = self._cards_per_hand.get(
            num_players, 
            self._cards_per_hand.get(max(self._cards_per_hand.keys()))
        )
        
        return GameSettings(
            num_players=num_players,
            max_live_tokens=self._max_live_tokens,
            max_hint_tokens=self._max_hint_tokens,
            max_cards_in_hand=max_cards,
            cards=cards
        )
```

#### 1.2 Variant Registry

```python
# hanabi/variants.py

from typing import Dict
from .rules import RuleSet, StandardRuleSet, RainbowRuleSet, MultiColorRuleSet, SixSuitsRuleSet

class VariantRegistry:
    """Registry for game variants."""
    
    _variants: Dict[str, RuleSet] = {}
    
    @classmethod
    def register(cls, name: str, rule_set: RuleSet) -> None:
        """Register a variant."""
        cls._variants[name.lower()] = rule_set
    
    @classmethod
    def get(cls, name: str) -> RuleSet:
        """Get a variant by name."""
        return cls._variants.get(name.lower())
    
    @classmethod
    def list_all(cls) -> List[str]:
        """List all registered variants."""
        return list(cls._variants.keys())
    
    @classmethod
    def initialize_defaults(cls) -> None:
        """Initialize default variants."""
        cls.register("standard", StandardRuleSet())
        cls.register("rainbow", RainbowRuleSet())
        cls.register("multicolor", MultiColorRuleSet())
        cls.register("sixsuits", SixSuitsRuleSet())
```

---

### 2. AI Player Interface System

#### 2.1 Enhanced Player Interface

```python
# hanabi/player.py (enhanced)

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, Dict, Any

if TYPE_CHECKING:
    from .game import PlayerView
    from .moves import Move

class Player(ABC):
    """Interface for a player in Hanabi."""
    
    @abstractmethod
    def play(self, player_view: 'PlayerView') -> 'Move':
        """Make a move based on the current player view."""
        pass
    
    def get_name(self) -> str:
        """Get the player's name/identifier."""
        return self.__class__.__name__
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about this player (for statistics)."""
        return {"type": self.__class__.__name__}

class AIPlayer(Player):
    """Base class for AI players with additional capabilities."""
    
    def __init__(self, player_index: int, name: Optional[str] = None):
        self._player_index = player_index
        self._name = name or self.__class__.__name__
        self._metadata = {}
    
    def get_name(self) -> str:
        return self._name
    
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "type": self.__class__.__name__,
            "name": self._name,
            **self._metadata
        }
    
    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata for statistics collection."""
        self._metadata[key] = value

class HumanPlayer(Player):
    """Human player interface - delegates to UI layer."""
    pass

# Example AI implementations
class RandomAIPlayer(AIPlayer, BasePlayer):
    """Random AI player."""
    pass

class StrategyAlphaAIPlayer(AIPlayer, BasePlayer):
    """Alpha strategy AI player."""
    pass

class MCTSAIPlayer(AIPlayer, BasePlayer):
    """Monte Carlo Tree Search AI player."""
    pass

class NeuralNetworkAIPlayer(AIPlayer, BasePlayer):
    """Neural network-based AI player."""
    pass
```

#### 2.2 AI Factory Pattern

```python
# hanabi/ai_factory.py

from typing import Dict, Type, Optional
from .player import AIPlayer

class AIFactory:
    """Factory for creating AI players."""
    
    _ai_classes: Dict[str, Type[AIPlayer]] = {}
    
    @classmethod
    def register(cls, name: str, ai_class: Type[AIPlayer]) -> None:
        """Register an AI player class."""
        cls._ai_classes[name.lower()] = ai_class
    
    @classmethod
    def create(cls, name: str, player_index: int, **kwargs) -> AIPlayer:
        """Create an AI player instance."""
        ai_class = cls._ai_classes.get(name.lower())
        if ai_class is None:
            raise ValueError(f"Unknown AI type: {name}")
        return ai_class(player_index, **kwargs)
    
    @classmethod
    def list_available(cls) -> List[str]:
        """List all available AI types."""
        return list(cls._ai_classes.keys())
```

---

### 3. UI Abstraction Layer

#### 3.1 Display Interface

```python
# hanabi/ui/display.py

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..game_engine import GameEngine

class Display(ABC):
    """Abstract interface for game display."""
    
    @abstractmethod
    def display_game_state(self, engine: 'GameEngine', player_index: int) -> None:
        """Display the current game state."""
        pass
    
    @abstractmethod
    def display_move_result(self, success: bool, message: str) -> None:
        """Display the result of a move."""
        pass
    
    @abstractmethod
    def display_game_end(self, engine: 'GameEngine') -> None:
        """Display game end information."""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Clear the display."""
        pass

class ConsoleDisplay(Display):
    """Console-based display (current implementation)."""
    pass

class GUIDisplay(Display):
    """GUI-based display (future implementation)."""
    pass

class ReplayDisplay(Display):
    """Display for replay mode with all cards visible."""
    
    def display_game_state(self, engine: 'GameEngine', player_index: int) -> None:
        # Show all cards, not just hints
        pass
```

#### 3.2 Input Interface

```python
# hanabi/ui/input.py

from abc import ABC, abstractmethod
from typing import Optional, Tuple
from ..moves import Move

class InputHandler(ABC):
    """Abstract interface for input handling."""
    
    @abstractmethod
    def get_move(self, player_index: int) -> Optional[Move]:
        """Get a move from the player."""
        pass
    
    @abstractmethod
    def display_prompt(self, player_index: int) -> None:
        """Display input prompt."""
        pass

class ConsoleInput(InputHandler):
    """Console-based input (current implementation)."""
    pass

class GUIInput(InputHandler):
    """GUI-based input (future implementation)."""
    pass

class ReplayInput(InputHandler):
    """Input for replay mode (step through moves)."""
    pass
```

#### 3.3 Game Controller

```python
# hanabi/ui/game_controller.py

from typing import List, Optional
from ..game_engine import GameEngine
from ..player import Player
from .display import Display
from .input import InputHandler

class GameController:
    """Controller that orchestrates game play with pluggable UI."""
    
    def __init__(
        self,
        engine: GameEngine,
        players: List[Player],
        display: Display,
        input_handler: Optional[InputHandler] = None
    ):
        self._engine = engine
        self._players = players
        self._display = display
        self._input_handler = input_handler
    
    def play(self) -> None:
        """Main game loop."""
        self._engine.initialize()
        
        while not self._engine.isFinished():
            current_player_idx = self._engine.currentPlayer
            player = self._players[current_player_idx]
            
            # Display game state
            self._display.display_game_state(self._engine, current_player_idx)
            
            # Get move
            if isinstance(player, HumanPlayer):
                # Human player uses input handler
                if self._input_handler is None:
                    raise ValueError("Input handler required for human players")
                move = self._input_handler.get_move(current_player_idx)
            else:
                # AI player makes move directly
                player_view = self._engine.getPlayerView(current_player_idx)
                move = player.play(player_view)
            
            # Process move
            success, result_msg = self._engine.processMove(current_player_idx, move)
            self._display.display_move_result(success, result_msg)
            
            if success:
                self._engine.advanceTurn()
        
        # Game finished
        self._display.display_game_end(self._engine)
```

---

### 4. Simulation & Statistics System

#### 4.1 Statistics Collector

```python
# hanabi/statistics.py

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from .game_engine import GameEngine
from .player import Player

@dataclass
class GameStatistics:
    """Statistics for a single game."""
    game_id: str
    variant: str
    num_players: int
    players: List[str]  # Player names/types
    final_score: int
    max_score: int
    moves_count: int
    duration_seconds: float
    end_reason: str  # "perfect_score", "lives_lost", "deck_exhausted", etc.
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PlayerStatistics:
    """Statistics for a specific player type."""
    player_type: str
    games_played: int
    total_score: int
    average_score: float
    best_score: int
    worst_score: int
    wins: int  # Perfect scores
    metadata: Dict[str, Any] = field(default_factory=dict)

class StatisticsCollector:
    """Collects and aggregates game statistics."""
    
    def __init__(self):
        self._games: List[GameStatistics] = []
    
    def record_game(
        self,
        engine: GameEngine,
        players: List[Player],
        variant: str,
        duration: float,
        end_reason: str
    ) -> None:
        """Record statistics for a completed game."""
        stats = GameStatistics(
            game_id=f"game_{len(self._games) + 1}",
            variant=variant,
            num_players=engine.settings.numPlayers,
            players=[p.get_name() for p in players],
            final_score=engine.getScore(),
            max_score=self._calculate_max_score(engine),
            moves_count=len(engine._move_history),
            duration_seconds=duration,
            end_reason=end_reason
        )
        self._games.append(stats)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        if not self._games:
            return {}
        
        return {
            "total_games": len(self._games),
            "average_score": sum(g.final_score for g in self._games) / len(self._games),
            "best_score": max(g.final_score for g in self._games),
            "worst_score": min(g.final_score for g in self._games),
            "perfect_scores": sum(1 for g in self._games if g.final_score == g.max_score),
            "by_variant": self._group_by_variant(),
            "by_player_type": self._group_by_player_type()
        }
    
    def _calculate_max_score(self, engine: GameEngine) -> int:
        """Calculate maximum possible score."""
        return len(engine.settings.cards) * 5  # 5 cards per color
    
    def _group_by_variant(self) -> Dict[str, Dict[str, Any]]:
        """Group statistics by variant."""
        # Implementation
        pass
    
    def _group_by_player_type(self) -> Dict[str, PlayerStatistics]:
        """Group statistics by player type."""
        # Implementation
        pass
    
    def export_to_csv(self, filename: str) -> None:
        """Export statistics to CSV."""
        pass
    
    def export_to_json(self, filename: str) -> None:
        """Export statistics to JSON."""
        pass
```

#### 4.2 Simulation Runner

```python
# hanabi/simulation.py

import time
from typing import List, Optional
from .game_engine import GameEngine
from .player import Player
from .statistics import StatisticsCollector
from .rules import RuleSet

class SimulationRunner:
    """Runs multiple game simulations and collects statistics."""
    
    def __init__(
        self,
        rule_set: RuleSet,
        players: List[Player],
        statistics_collector: Optional[StatisticsCollector] = None
    ):
        self._rule_set = rule_set
        self._players = players
        self._statistics = statistics_collector or StatisticsCollector()
    
    def run_single_game(self, num_players: int) -> GameEngine:
        """Run a single game and return the engine."""
        settings = self._rule_set.create_settings(num_players)
        engine = GameEngine(settings, self._players[:num_players])
        engine.initialize()
        
        start_time = time.time()
        
        while not engine.isFinished():
            current_player_idx = engine.currentPlayer
            player = self._players[current_player_idx]
            player_view = engine.getPlayerView(current_player_idx)
            move = player.play(player_view)
            
            success, _ = engine.processMove(current_player_idx, move)
            if success:
                engine.advanceTurn()
        
        duration = time.time() - start_time
        end_reason = self._determine_end_reason(engine)
        
        self._statistics.record_game(
            engine, self._players[:num_players],
            self._rule_set.get_variant_name(),
            duration, end_reason
        )
        
        return engine
    
    def run_batch(
        self,
        num_players: int,
        num_games: int,
        progress_callback: Optional[callable] = None
    ) -> StatisticsCollector:
        """Run multiple games and collect statistics."""
        for i in range(num_games):
            self.run_single_game(num_players)
            if progress_callback:
                progress_callback(i + 1, num_games)
        
        return self._statistics
    
    def _determine_end_reason(self, engine: GameEngine) -> str:
        """Determine why the game ended."""
        if engine.gameState.commonView.liveTokens <= 0:
            return "lives_lost"
        elif engine.getScore() == len(engine.settings.cards) * 5:
            return "perfect_score"
        elif engine.isDeckExhausted():
            return "deck_exhausted"
        else:
            return "unknown"
```

---

### 5. Replay System Enhancement

#### 5.1 Replay Controller

```python
# hanabi/replay.py

from typing import Optional, List
from .game_history import GameHistory
from .game_engine import GameEngine
from .ui.display import Display
from .ui.input import InputHandler

class ReplayController:
    """Controller for replaying games with full card visibility."""
    
    def __init__(
        self,
        history_file: str,
        display: Display,
        input_handler: Optional[InputHandler] = None
    ):
        self._history = GameHistory({})
        self._history_data = self._history.load_from_file(history_file)
        self._display = display
        self._input_handler = input_handler or ReplayInput()
        self._engine: Optional[GameEngine] = None
        self._current_move_index = 0
    
    def load_game(self) -> None:
        """Load the game from history."""
        # Reconstruct game engine from history
        # This would require deserialization logic
        pass
    
    def play(self, auto_advance: bool = False, delay: float = 1.0) -> None:
        """Play through the replay."""
        self.load_game()
        
        moves = self._history_data.get("m", [])
        
        for move_data in moves:
            # Display state with all cards visible
            self._display.display_game_state(
                self._engine,
                move_data["p"],  # player index
                show_all_cards=True  # New parameter
            )
            
            if not auto_advance:
                # Wait for user input to advance
                self._input_handler.get_move(move_data["p"])
            else:
                time.sleep(delay)
            
            # Apply move
            # ... reconstruct and apply move
    
    def step_forward(self) -> None:
        """Step forward one move."""
        pass
    
    def step_backward(self) -> None:
        """Step backward one move."""
        pass
    
    def jump_to_move(self, move_index: int) -> None:
        """Jump to a specific move."""
        pass
```

#### 5.2 Enhanced Display for Replay

```python
# hanabi/ui/replay_display.py

from .display import Display
from ..game_engine import GameEngine

class ReplayDisplay(Display):
    """Display for replay mode showing all cards."""
    
    def display_game_state(
        self,
        engine: GameEngine,
        player_index: int,
        show_all_cards: bool = True
    ) -> None:
        """Display game state with all cards visible."""
        # Similar to ConsoleDisplay but shows actual cards, not hints
        state = engine.gameState
        
        for player_idx, hand in enumerate(state.playerHands):
            if show_all_cards:
                # Show actual cards
                print(f"Player {player_idx + 1}: {hand.cards}")
            else:
                # Show hints only (normal mode)
                hints = engine.getPlayerHints(player_idx)
                # ... display with hints
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1-2)
1. Create `RuleSet` interface and implement standard variant
2. Create `VariantRegistry`
3. Refactor `GameSettings` creation to use `RuleSet`
4. Create UI abstraction interfaces (`Display`, `InputHandler`)

### Phase 2: AI & Simulation (Week 3-4)
1. Enhance `Player` interface with metadata support
2. Create `AIFactory` for AI player creation
3. Implement `StatisticsCollector`
4. Implement `SimulationRunner`
5. Create example AI implementations

### Phase 3: UI Separation (Week 5)
1. Refactor `ConsoleDisplay` to implement `Display` interface
2. Refactor `ConsoleInput` to implement `InputHandler` interface
3. Create `GameController` to orchestrate game play
4. Update `console_game.py` to use new architecture

### Phase 4: Variants & Replay (Week 6)
1. Implement variant rule sets (Rainbow, Multi-color, 6 Suits)
2. Enhance replay system with full card visibility
3. Create `ReplayController` and `ReplayDisplay`
4. Add replay viewer command-line tool

### Phase 5: Testing & Documentation (Week 7)
1. Write unit tests for new components
2. Create integration tests
3. Update documentation
4. Create example scripts for common use cases

---

## File Structure

```
hanabi/
├── __init__.py
├── enums.py
├── card.py
├── moves.py
├── game.py
├── game_engine.py
├── game_history.py
├── observer.py
├── player.py              # Enhanced with AI support
├── rules.py               # NEW: Rule sets and variants
├── variants.py            # NEW: Variant registry
├── ai_factory.py          # NEW: AI player factory
├── statistics.py          # NEW: Statistics collection
├── simulation.py          # NEW: Simulation runner
├── replay.py              # NEW: Replay controller
├── ui/                    # NEW: UI abstraction layer
│   ├── __init__.py
│   ├── display.py         # Display interface
│   ├── input.py           # Input interface
│   ├── game_controller.py # Game controller
│   ├── console_display.py # Console implementation
│   ├── console_input.py   # Console implementation
│   └── replay_display.py  # Replay display
├── console_game.py        # Refactored to use new architecture
└── __main__.py
```

---

## Usage Examples

### Example 1: Play with Different Variant

```python
from hanabi import VariantRegistry, GameController, GameEngine
from hanabi.ui import ConsoleDisplay, ConsoleInput
from hanabi.player import HumanPlayer

# Get variant
variant = VariantRegistry.get("rainbow")
settings = variant.create_settings(num_players=3)

# Create players
players = [HumanPlayer(i) for i in range(3)]

# Create engine
engine = GameEngine(settings, players)

# Create UI
display = ConsoleDisplay()
input_handler = ConsoleInput(engine)

# Play game
controller = GameController(engine, players, display, input_handler)
controller.play()
```

### Example 2: Run AI Simulation

```python
from hanabi import VariantRegistry, SimulationRunner, StatisticsCollector
from hanabi.player import RandomAIPlayer, StrategyAlphaAIPlayer

# Get variant
variant = VariantRegistry.get("standard")

# Create AI players
players = [
    RandomAIPlayer(0),
    StrategyAlphaAIPlayer(1),
    RandomAIPlayer(2)
]

# Run simulation
collector = StatisticsCollector()
runner = SimulationRunner(variant, players, collector)
runner.run_batch(num_players=3, num_games=100)

# Get statistics
stats = collector.get_summary()
print(f"Average score: {stats['average_score']}")
print(f"Best score: {stats['best_score']}")
```

### Example 3: Replay Game with Full Visibility

```python
from hanabi.replay import ReplayController
from hanabi.ui import ReplayDisplay, ReplayInput

display = ReplayDisplay()
input_handler = ReplayInput()
controller = ReplayController("hanabi_game_20251124_001515.yaml", display, input_handler)
controller.play(auto_advance=False)  # Step through manually
```

---

## Benefits of This Architecture

1. **Extensibility**: Easy to add new variants, AI players, and UI implementations
2. **Testability**: Clear separation of concerns makes testing easier
3. **Maintainability**: Well-defined interfaces and responsibilities
4. **Flexibility**: Can mix and match components (e.g., GUI with AI players)
5. **Scalability**: Statistics and simulation infrastructure supports research

---

## Migration Strategy

1. **Backward Compatibility**: Keep existing `create_standard_game_settings()` function that wraps `StandardRuleSet`
2. **Gradual Migration**: Refactor one component at a time
3. **Deprecation Warnings**: Add warnings for old APIs before removing them
4. **Documentation**: Update all examples to use new architecture

---

## Open Questions

1. **Variant Rules**: Need to confirm exact rules for the 4 variants mentioned in the PDF
2. **AI Interface**: Should AI players have access to full game state for learning, or only `PlayerView`?
3. **Statistics Format**: What statistics are most valuable for AI evaluation?
4. **Replay Format**: Should replay files be backward compatible with current format?

---

## Next Steps

1. Review this proposal and discuss any concerns
2. Confirm variant rules from PDF
3. Prioritize features for initial implementation
4. Begin Phase 1 implementation

