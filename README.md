# Hanabi Game Implementation

A Python implementation of the Hanabi card game with support for different player strategies.

## Project Structure

```
hanabi/
├── hanabi/
│   ├── __init__.py          # Package initialization and exports
│   ├── enums.py             # Color and Number enumerations
│   ├── card.py              # Card and Suit classes
│   ├── game.py              # Game state classes (GameSettings, CommonView, PlayerView, Hand)
│   ├── moves.py             # Move classes (Move, Hint, CardMove, Play, Discard, etc.)
│   ├── observer.py          # Observer interface
│   └── player.py            # Player classes (BasePlayer, HumanPlayer, RandomPlayer, StrategyAlphaPlayer)
├── README.md
└── requirements.txt
```

## Classes Overview

### Enumerations
- **Color**: MULTI, WHITE, RED, YELLOW, GREEN, BLUE
- **Number**: ONE, TWO, THREE, FOUR, FIVE

### Core Classes
- **Card**: Represents a single card with color and number
- **Suit**: Represents a suit with cards mapping numbers to quantities
- **Hand**: Represents a player's hand of cards
- **GameSettings**: Game configuration (players, tokens, cards)
- **CommonView**: Common game state visible to all players
- **PlayerView**: Game state from a player's perspective

### Move Classes
- **Move**: Base class for all moves
- **Hint**: Base class for hint moves
  - **ColorHint**: Hint indicating a specific color
  - **NumberHint**: Hint indicating a specific number
- **CardMove**: Base class for card moves
  - **Play**: Move to play a card
  - **Discard**: Move to discard a card

### Player Classes
- **Observer**: Interface for observing game state
- **Player**: Interface for making moves
- **BasePlayer**: Base class implementing both Observer and Player
- **HumanPlayer**: Player requiring manual input
- **RandomPlayer**: Player making random moves
- **StrategyAlphaPlayer**: Player implementing Alpha strategy

## Usage Example

```python
from hanabi import (
    GameSettings, CommonView, PlayerView, Hand, Card,
    Color, Number, RandomPlayer
)

# Create game settings
settings = GameSettings(
    num_players=4,
    max_live_tokens=3,
    max_hint_tokens=8,
    max_cards_in_hand=5,
    cards={}  # Initialize with actual card distribution
)

# Create a player
player = RandomPlayer(player_index=0)
player.set_game_settings(settings)

# Create player view
teammates = {
    1: Hand([Card(Color.RED, Number.ONE)]),
    2: Hand([Card(Color.BLUE, Number.TWO)]),
    3: Hand([Card(Color.GREEN, Number.THREE)])
}
player_view = PlayerView(teammates)

# Make a move
move = player.play(player_view)
print(f"Player made move: {move}")
```

## Installation

```bash
pip install -r requirements.txt
```

## Development

This project follows the class diagram design with:
- Type hints for better code clarity
- Abstract base classes for interfaces
- Property-based accessors matching the diagram's method signatures
- Immutable data structures where appropriate

## Next Steps

- Implement game engine/logic
- Complete strategy implementations
- Add game state management
- Create game loop and turn management
- Add unit tests

## TODO

- Implement indirect hinting convention

- **Document game record format**: Create comprehensive documentation for the concise YAML/JSON game record format, including:
  - Field name mappings (short names and their meanings)
  - Card notation format (e.g., G5 for GREEN 5)
  - Move format specifications
  - State representation
  - Versioning information
  - Example files
  - Consider publishing as a potential community standard (no widely adopted format currently exists)

