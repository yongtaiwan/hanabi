# Hanabi Game Architecture

## Separation of Concerns

The codebase follows a clear separation between **game logic** and **I/O (Input/Output)**:

### Game Logic Layer (Pure, No I/O)

**`hanabi/game_engine.py`** - `GameEngine` class
- Contains all game logic and state management
- **NO I/O operations** (no print, input, display, etc.)
- Pure functions that process moves and update state
- Returns data structures, not formatted strings for display
- Can be used by any UI (CLI, GUI, web, etc.)

**Key Methods:**
- `processMove(player_index, move)` → `(success: bool, message: str)`
- `advanceTurn()` → updates internal state
- `isFinished()` → `bool`
- `getScore()` → `int`
- `gameState` → `GameState` (read-only property)

### I/O Layer (Display and Input)

**CLI (Console Interface):**
- `hanabi/console_game.py` - Main game loop for console
- `hanabi/console_display.py` - ConsoleDisplay class (handles all console output)
- `hanabi/console_input.py` - ConsoleInput class (handles all console input parsing)

**GUI (Graphical Interface):**
- `hanabi/gui_game.py` - GUIGame class (main game controller)
- `hanabi/gui_display.py` - GUIDisplay class (handles all GUI rendering)
- `hanabi/gui_input.py` - GUIInput class (handles all GUI input)

## Game Flow Pattern (Both CLI and GUI)

Both interfaces follow the same pattern for processing moves:

### 1. Process Move
```python
success, message = engine.processMove(current_player, move)
```

### 2. Record in History (if successful)
```python
if success:
    history.record_move(current_player, move, message, engine)
```

### 3. Update Display (Table State)
```python
display.display_game_state(engine, current_player)
```

### 4. Log Move Result (Game Events)
```python
display.display_move_result(success, message, current_player)
```

### 5. Advance Turn
```python
engine.advanceTurn()
```

### 6. Check if Game Finished
```python
if engine.isFinished():
    display.display_game_end(engine)
    # End game
```

## Key Principles

1. **Game Engine is Pure Logic**: No I/O, no dependencies on display/input systems
2. **Display Classes Handle All Output**: ConsoleDisplay and GUIDisplay are responsible for all visual representation
3. **Input Classes Handle All Input**: ConsoleInput and GUIInput parse and validate user input
4. **Game Controllers Orchestrate**: console_game.py and gui_game.py coordinate between engine, display, and input
5. **Consistent Flow**: Both CLI and GUI follow the same sequence of operations

## Example: Last Move Before Game Over

Both CLI and GUI ensure:
1. Last move is processed
2. Game state is updated
3. Display shows updated state
4. Move result is logged
5. Then "Game Over" is shown

This ensures the final game state is visible and the last move is recorded before the game ends.

