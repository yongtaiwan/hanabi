# Monte Carlo Player Performance Guide

## Performance Characteristics

The Monte Carlo player's performance depends on its configuration:

### Default Config (Production)
- **Thinking time per turn**: 1-2 seconds
- **Expected game duration**: 30-60+ seconds per game (depending on number of turns)
- **Use case**: Production experiments where quality of decisions matters
- **Simulations per move**: Adaptive, typically 10-100+ depending on move complexity

### Fast Config (Testing/Development)
- **Thinking time per turn**: 100-200ms
- **Expected game duration**: 1-3 seconds per game
- **Use case**: Quick testing and development
- **Simulations per move**: Adaptive, typically 1-20

### Medium Config (Balanced)
- **Thinking time per turn**: 300-500ms
- **Expected game duration**: 5-15 seconds per game
- **Use case**: Balanced testing with reasonable decision quality
- **Simulations per move**: Adaptive, typically 2-50

## Why It's Slow

1. **Per-turn thinking time**: Each turn, the player:
   - Samples possible worlds (our hand + deck)
   - For each world, evaluates all candidate moves via rollouts
   - Repeats this N times (where N is computed to fit the time budget)

2. **Rollout depth**: Each rollout simulates the game to completion using random moves. With a pure random policy, games can take 20-50+ moves to finish.

3. **Single-threaded**: Currently runs on a single thread. Future improvement: parallelize simulations.

## Performance Optimizations Added

1. **Rollout depth limit**: Added a maximum depth of 200 moves to prevent infinite or extremely long rollouts
2. **Time-based adaptive N**: Uses pilot simulation to estimate time, then computes optimal N
3. **Fast config option**: Allows quick testing with reduced thinking time

## Usage Recommendations

### For Testing/Development
```python
from hanabi.ai.monte_carlo_player import MonteCarloPlayer, MonteCarloConfig

# Fast config for testing
config = MonteCarloConfig(
    min_think_time_s=0.1,   # 100ms
    max_think_time_s=0.2,   # 200ms
    min_simulations=1,
    max_simulations=20,
)
player = MonteCarloPlayer(player_index=0, config=config)
```

### For Production Experiments
```python
# Default config (1-2s per turn)
player = MonteCarloPlayer(player_index=0)
```

### For Balanced Testing
```python
config = MonteCarloConfig(
    min_think_time_s=0.3,   # 300ms
    max_think_time_s=0.5,   # 500ms
    min_simulations=2,
    max_simulations=50,
)
player = MonteCarloPlayer(player_index=0, config=config)
```

## Test Scripts

- **`test_monte_carlo_minimal.py`**: Minimal tests (single move, one turn, short game)
- **`test_monte_carlo_progressive.py`**: Progressive tests scaling from fast to default config
- **`test_monte_carlo.py`**: Standard test with fast config (completes in ~4 seconds)

## Expected Performance

| Config | Time per Turn | Time per Game (2 players) | Time per Game (5 players) |
|--------|---------------|---------------------------|---------------------------|
| Fast   | 100-200ms     | 1-3 seconds               | 2-5 seconds               |
| Medium | 300-500ms     | 5-15 seconds              | 10-30 seconds             |
| Default| 1-2 seconds   | 30-60 seconds             | 60-120 seconds            |

## Future Optimizations

1. **Parallelization**: Run simulations in parallel across multiple threads/processes
2. **Smarter rollout policy**: Use simple heuristics in rollouts (e.g., "play definitely playable cards") to finish games faster
3. **Early termination**: Stop rollouts early if score is clearly bad
4. **Caching**: Reuse determinized worlds across moves within the same turn


