# Monte Carlo Player Implementation

## Overview

The Monte Carlo player (`MonteCarloPlayer`) uses Monte Carlo simulation to evaluate moves by:
1. Sampling possible worlds (our hand + deck) consistent with hints and visible cards
2. For each world, evaluating all candidate moves via rollouts
3. Selecting the move with the highest average final score
4. Using time-based adaptive N (number of simulations) based on 1-2 second budget

## Design Decisions

### World Sampling
- Only our hand and the deck are unknown (we can see all teammates' hands)
- Sample one random legal world each time (no need to enumerate all worlds)
- Each player may pick a different world when thinking

### Rollout Policy
- Pure Monte Carlo: all players use the same random policy in rollouts
- No heuristics or existing strategies
- No nested Monte Carlo (to avoid recursion and keep it fast)

### Time Management
- Pilot: 1 simulation per move to estimate time per evaluation
- Compute N such that total time is between 1-2 seconds
- Minimum and maximum bounds on number of simulations

## Files Created

- `hanabi/ai/monte_carlo_player.py`: Main implementation
  - `MonteCarloConfig`: Configuration class
  - `MCGameState`: Internal game state for simulations
  - `MonteCarloPlayer`: Main player class

## Testing

A test script `test_monte_carlo.py` was created to verify the implementation works correctly.

## Usage Example

```python
from hanabi.ai.monte_carlo_player import MonteCarloPlayer

# Create a player
player = MonteCarloPlayer(player_index=0)

# Or with custom config
from hanabi.ai.monte_carlo_player import MonteCarloConfig
config = MonteCarloConfig(
    min_think_time_s=1.0,
    max_think_time_s=2.0,
    min_simulations=5,
    max_simulations=10000,
    rng_seed=42
)
player = MonteCarloPlayer(player_index=0, config=config)
```

## Performance

- Average thinking time per turn: 1-2 seconds (configurable)
- The player makes decisions by simulating many possible game outcomes
- Performance improves with more simulations, but is bounded by time budget

## Future Improvements

1. **Hint-aware world sampling**: Currently uses all remaining cards as candidates. Could filter by hints received to be more accurate.

2. **Smarter rollout policy**: While keeping it "pure Monte Carlo", could add simple rules like "always play a definitely playable card" when perfect information is available in rollouts.

3. **Parallelization**: Simulations are embarrassingly parallel and could be run on multiple threads/processes.

4. **Caching**: Reuse determinized worlds across moves within the same turn to reduce variance.


