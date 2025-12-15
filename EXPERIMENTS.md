# Experiment Directory Structure

This document describes how game records and statistics are organized for experiments.

## Directory Structure

When you run an experiment using `GameField.run_experiment()`, all results are organized in a structured directory layout:

```
game_records/
  experiment_<ID>/
    settings.yaml          # Game settings (same for all games in experiment)
    statistics.yaml         # Aggregated statistics for all runs
    games/
      all-games/           # All game records stored here
        run_000_ai_RandomPlayer.yaml
        run_000_ai_StrategyAlpha.yaml
        run_001_ai_RandomPlayer.yaml
        run_001_ai_StrategyAlpha.yaml
        ...
      000/                 # Symlinks to all games from run 0
        run_000_ai_RandomPlayer.yaml -> ../all-games/run_000_ai_RandomPlayer.yaml
        run_000_ai_StrategyAlpha.yaml -> ../all-games/run_000_ai_StrategyAlpha.yaml
      001/                 # Symlinks to all games from run 1
        run_001_ai_RandomPlayer.yaml -> ../all-games/run_001_ai_RandomPlayer.yaml
        ...
    ai/
      RandomPlayer/        # Symlinks to all RandomPlayer games
        run_000_ai_RandomPlayer.yaml -> ../games/all-games/run_000_ai_RandomPlayer.yaml
        run_001_ai_RandomPlayer.yaml -> ../games/all-games/run_001_ai_RandomPlayer.yaml
        ...
      StrategyAlpha/       # Symlinks to all StrategyAlpha games
        run_000_ai_StrategyAlpha.yaml -> ../games/all-games/run_000_ai_StrategyAlpha.yaml
        ...
```

### Directory Components

1. **`game_records/`** - Root directory for all experiments
   - Shared with regular game records from GUI/console play
   - Created automatically if it doesn't exist

2. **`experiment_<ID>/`** - Individual experiment directory
   - Named using the `experiment_id` parameter (defaults to timestamp)
   - Contains all data for a single experiment run

3. **`settings.yaml`** - Game settings for the experiment
   - Same settings used for all games in the experiment
   - Contains: num_players, max_live_tokens, max_hint_tokens, max_cards_in_hand

4. **`statistics.yaml`** - Aggregated experiment statistics
   - Contains summary statistics for each AI
   - Includes per-run results and aggregated metrics
   - Format: YAML (or JSON if YAML unavailable)

5. **`games/all-games/`** - All game record files
   - One file per game: `run_<ID>_ai_<AI_NAME>.yaml`
   - Run ID is zero-padded (000, 001, 002, ...)
   - AI name is the key from the `ai_factories` dictionary
   - Each file contains full game replay data (deck, moves, final score)

6. **`games/<run_id>/`** - Run-specific directories
   - One directory per run (000, 001, 002, ...)
   - Contains symlinks to all games from that run
   - Useful for analyzing all AIs' performance on the same deck

7. **`ai/<ai_name>/`** - AI-specific directories
   - One directory per AI type
   - Contains symlinks to all games played by that AI
   - Useful for analyzing a single AI's performance across all runs

## Usage Example

```python
from hanabi.core.game import create_standard_game_settings
from hanabi.core.game_field import GameField
from hanabi.ai.random_player import RandomPlayer

# Create settings
settings = create_standard_game_settings(3)

# Create GameField
game_field = GameField.create_from_settings(settings)

# Define AI factories
ai_factories = {
    "RandomPlayer": lambda i: RandomPlayer(i),
}

# Run experiment
results = game_field.run_experiment(
    ai_factories=ai_factories,
    num_runs=100,
    save_records=True,
    experiment_id="my_experiment"
)

# Save statistics (saves to game_records/experiment_my_experiment/statistics.yaml)
stats_path = game_field.save_statistics(results)
print(f"Statistics saved to: {stats_path}")
```

## File Naming

### Settings File
- **Name**: `settings.yaml` (or `.json`)
- **Location**: `game_records/experiment_<ID>/settings.yaml`
- **Content**: Game settings used for all games in the experiment

### Statistics File
- **Name**: `statistics.yaml` (or `.json`)
- **Location**: `game_records/experiment_<ID>/statistics.yaml`
- **Custom**: You can specify a custom filename, which will be saved in the experiment directory

### Game Records
- **Format**: `run_<RUN_ID>_ai_<AI_NAME>.<ext>`
- **Example**: `run_042_ai_RandomPlayer.yaml`
- **Location**: `game_records/experiment_<ID>/games/all-games/`
- **Symlinks**: Also accessible via `games/<run_id>/` and `ai/<ai_name>/` directories
- **Run ID**: Zero-padded to 3 digits (000-999)

## Symlinks

The directory structure uses symbolic links for organization:

- **Run directories** (`games/000/`, `games/001/`, ...): Symlinks to all games from that run
- **AI directories** (`ai/RandomPlayer/`, `ai/StrategyAlpha/`, ...): Symlinks to all games by that AI

**Note**: On systems where symlinks are not supported (e.g., Windows without admin rights), the system will create `.link` text files containing the target path instead.

## Statistics File Contents

The statistics file contains:

```yaml
experiment_id: "my_experiment"
settings:
  num_players: 3
  max_live_tokens: 3
  max_hint_tokens: 8
  max_cards_in_hand: 5
num_runs: 100
timestamp: "2025-12-14T14:30:22.123456"
runs:
  - run_id: 0
    deck_seed: 42
    ai_results:
      RandomPlayer:
        score: 18
        moves_count: 45
        duration_seconds: 0.123
        end_reason: "deck_exhausted"
        game_record_path: "game_records/experiment_my_experiment/games/all-games/run_000_ai_RandomPlayer.yaml"
  - run_id: 1
    ...
summary:
  RandomPlayer:
    games_played: 100
    average_score: 15.23
    best_score: 25
    worst_score: 8
    win_rate: 0.05
    std_dev: 3.45
    average_moves: 42.1
    average_duration: 0.125
```

## Benefits of This Structure

1. **Organization**: Each experiment is self-contained in its own directory
2. **Easy Navigation**:
   - Browse all games from a specific run: `games/042/`
   - Browse all games by a specific AI: `ai/RandomPlayer/`
   - Find all games: `games/all-games/`
3. **Easy Cleanup**: Delete an entire experiment by removing its directory
4. **Reproducibility**: Deck seeds are stored for each run
5. **Analysis**: All data for an experiment is in one place
6. **Scalability**: Can run many experiments without cluttering the root directory
7. **Settings Reuse**: Settings are saved once per experiment, not per game

## Legacy Directories

Note: The `game_records/` directory is shared with:
- Individual game records from GUI/console play (saved directly to `game_records/`)
- Experiment data (saved to `game_records/experiment_<ID>/`)

This keeps all game-related data in one place while maintaining clear organization.
