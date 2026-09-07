# Hanabi Convention Lab

A Python Hanabi engine, strategy testbed, and browser-based teaching tool. The main research
strategies are the 3-, 4-, and 5-player **Simple Recommendation** conventions and the
score-maximizing 3-player **Dynamic Recommendation** convention.

## Convention Lab website

Open the hosted [Hanabi Convention Lab](https://hanabi-convention-lab.youtiisnoob.chatgpt.site). It runs the Python game engine and bot classes inside the browser, so no local server is required. The lab includes a custom-position analyzer, explained bot games, and replay loading. See `WEB_APP.md` for details and the optional local development route.

## Project structure

```
hanabi/
├── ai/             # Bot strategies and shared convention policy
├── console/        # Terminal game
├── core/           # Cards, moves, state, rules, players, and game history
├── gui/            # Desktop GUI
├── tools/          # Experiment and analysis helpers
└── web/            # Convention Lab web adapter and static interface
test/               # Unit and integration tests
run_ai_experiments.py
```

## Main strategies

- **Simple Recommendation (3 players):** mod 8, using all four hint directions across the two other seats.
- **Simple Recommendation (4 players):** mod 12, using all four hint directions across the three other seats.
- **Simple Recommendation (5 players):** mod 16, using all four hint directions across the four other seats.
- **Dynamic Recommendation (3 players):** a more complex convention intended to maximize score rather than minimize human bookkeeping.

The three Simple strategies share the same recommended-play safety gate and keep only one
current recommendation per seat. Their player-count-specific modules define the channel table,
hand recommendation mapping, and hint-strength thresholds.

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

## Development and verification

Run the regression suite from the repository root:

```bash
python3 -m unittest discover -s test -q
```

The repository targets Python 3.10 or newer. The web adapter uses only the standard library;
PyYAML is optional and needed only for YAML replay imports.
