# Monte Carlo Player Integration

## Overview

The Monte Carlo player has been integrated into both the CLI (console) and GUI game interfaces.

## Integration Details

### Console Game (`hanabi/console/console_game.py`)

- Added MonteCarloPlayer as option 3 in the AI selection menu
- Uses a fast config (300-500ms per turn) for interactive play
- Selection prompt updated to accept choices 1-3

**Usage:**
```bash
python -m hanabi.console.console_game
# Select "1-player mode"
# Choose option 3 for MonteCarlo
```

### GUI Game (`hanabi/gui/gui_game.py`)

- Added MonteCarloPlayer as the third button in the AI selection dialog
- Uses a fast config (300-500ms per turn) for interactive play
- Appears when selecting "Single Player" mode and choosing number of AIs

**Usage:**
```bash
python -m hanabi.gui.gui_game
# Click "Single Player" → Select number of AIs → Choose "MonteCarlo"
```

## Configuration for Interactive Play

Both interfaces use a **fast config** optimized for interactive play:

```python
MonteCarloConfig(
    min_think_time_s=0.3,   # 300ms
    max_think_time_s=0.5,   # 500ms
    min_simulations=2,
    max_simulations=50,
)
```

This provides:
- **Fast response time**: 300-500ms per turn (vs 1-2s for default)
- **Reasonable decision quality**: Still uses Monte Carlo evaluation
- **Good user experience**: Games complete in 5-15 seconds instead of 30-60+ seconds

## Available AI Players

1. **Random**: Makes random valid moves
2. **CommonSense**: Uses heuristic rules
3. **MonteCarlo**: Uses Monte Carlo simulation (NEW)

## Performance Notes

- The fast config is optimized for interactive play
- For production experiments, use the default config (1-2s per turn) for better decisions
- The fast config still provides better decisions than Random or CommonSense in many cases

## Future Enhancements

- Could add a configuration dialog to let users choose between fast/medium/default configs
- Could show thinking progress indicator during Monte Carlo evaluation
- Could add option to use default (slower but better) config for users who want maximum quality


