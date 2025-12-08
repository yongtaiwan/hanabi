# Hanabi GUI Design and Implementation

## Overview

The GUI implementation provides a visual interface for playing Hanabi that mimics the physical game setup on a round table. It shares the same game engine (`GameEngine`) as the CLI version, ensuring consistency and maintainability.

## Design Decisions

### 1. Framework Choice: tkinter
- **Rationale**: Built-in Python library, simple, robust, and easy to understand
- **No external dependencies**: Works out of the box with Python standard library
- **Cross-platform**: Works on Windows, macOS, and Linux

### 2. Round Table Layout
- **Center**: Fireworks (played cards), tokens, deck count, discard pile
- **Around edges**: Player hands positioned in a circle
- **Current player**: Hand at bottom, facing the player
- **Other players**: Hands visible with actual cards (as in physical game)

### 3. Card Graphics
Based on the official Hanabi rules PDF:
- **Card colors**: White, Red, Yellow, Green, Blue (matching PDF colors)
- **Card numbers**: 1-5 displayed prominently
- **Player's own cards**: Show back with hints (color/number badges)
- **Other players' cards**: Show front (colored with number)
- **Selection**: Gold outline for selected cards

### 4. Token Display
- **Blue Clock Tokens (Hints)**: Circular tokens, blue when available, dark when used
- **Black Fuse Tokens (Lives)**: Circular tokens showing fuse state (brown/orange when active, black when used)

### 5. Fireworks Display
- Arranged in a circle around the center
- Each color shows a stack of played cards (1-5)
- Empty slots shown with dashed outline

### 6. Interaction Model
- **Card Selection**: Click on your own cards to select
- **Actions**: Buttons for Play, Discard, Give Color Hint, Give Number Hint
- **Hints**: Click "Give Color/Number Hint", then click on target player's card
- **Hot Seat**: Players take turns on the same computer

### 7. Replay Mode
- Load saved game files (YAML/JSON)
- Show all cards (full visibility)
- Step through moves with Previous/Next buttons
- Navigate to first/last move

## Architecture

### Components

1. **`GUIDisplay`** (`gui_display.py`)
   - Handles all visual rendering
   - Implements same interface as `ConsoleDisplay` (for compatibility)
   - Manages canvas drawing, card widgets, tokens, fireworks

2. **`GUIInput`** (`gui_input.py`)
   - Handles click-based input
   - Implements same interface as `ConsoleInput` (for compatibility)
   - Manages card selection, move callbacks

3. **`GUIGame`** (`gui_game.py`)
   - Main game controller
   - Integrates display, input, and engine
   - Manages game loop, replay mode, menu

### Integration with Existing Engine

The GUI uses the exact same `GameEngine` as the CLI:
- No modifications to game logic
- Same move validation
- Same game state management
- Same history/replay system

## Usage

### Launching the GUI

```bash
# Option 1: Direct script
python run_gui.py

# Option 2: Module with flag
python -m hanabi --gui

# Option 3: CLI (default)
python -m hanabi
```

### Playing a Game

1. **Start New Game**: Click "New Game" or File → New Game
2. **Select Players**: Choose 2-5 players
3. **Your Turn**:
   - Click on one of your cards (shown with hints/back)
   - Click "Play Selected Card" or "Discard Selected Card"
   - OR click "Give Color Hint" or "Give Number Hint", then click on a teammate's card
4. **Hot Seat**: Pass the computer to the next player when prompted

### Replay Mode

1. **Load Replay**: File → Load Replay or click "Load Replay"
2. **Navigate**: Use Previous/Next buttons to step through moves
3. **Full Visibility**: All cards are visible in replay mode

## File Structure

```
hanabi/
├── gui_display.py      # Visual rendering and display logic
├── gui_input.py        # Click handling and input logic
├── gui_game.py         # Main game controller
├── console_display.py  # CLI display (existing)
├── console_input.py   # CLI input (existing)
├── game_engine.py     # Shared game engine (used by both)
└── ...
```

## Design Principles

1. **Separation of Concerns**: Display, input, and game logic are separate
2. **Shared Engine**: Both CLI and GUI use the same `GameEngine`
3. **Interface Compatibility**: GUI components implement same interfaces as CLI
4. **Round Table Metaphor**: Layout mimics physical game setup
5. **Visual Clarity**: Clear color coding, selection feedback, status messages

## Future Enhancements

Potential improvements (not implemented):
- Card animations (play/discard)
- Sound effects
- Network multiplayer
- AI players in GUI
- Statistics dashboard
- Custom themes

## Testing

To test the GUI:
1. Run `python run_gui.py`
2. Start a new game with 2-3 players
3. Play a few turns to verify:
   - Card selection works
   - Moves are processed correctly
   - Display updates properly
   - Game end detection works

## Notes

- The GUI is designed for local hot-seat multiplayer
- All game rules are enforced by the shared `GameEngine`
- Replay mode requires full game state deserialization (simplified version included)

