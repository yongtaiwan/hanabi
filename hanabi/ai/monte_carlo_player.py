"""
Monte Carlo AI player for Hanabi game.

This player uses Monte Carlo simulation to evaluate moves:
1. Samples possible worlds (our hand + deck) consistent with hints and visible cards
2. For each world, evaluates all candidate moves via rollouts
3. Selects the move with the highest average final score
4. Uses time-based adaptive N (number of simulations) based on 1-2 second budget
"""

import time
import random
import copy
import logging
import sys
from typing import List, Dict, Set, Optional, TYPE_CHECKING
from collections import Counter

from hanabi.core.player import HintTrackingPlayer
from hanabi.core.game import PlayerView, CommonView, GameSettings
from hanabi.core.moves import Move, Play, Discard, ColorHint, NumberHint
from hanabi.core.enums import Color, Number
from hanabi.core.card import Card, Suit
from hanabi.core.move_generation import generate_all_valid_moves
from hanabi.core.hint_rules import is_legal_hint_against_hand_cards

# Set up logger for debug output
# Use full module path to ensure it matches the logger name set in GUI
logger = logging.getLogger("hanabi.ai.monte_carlo_player")

if TYPE_CHECKING:
    pass


class MonteCarloConfig:
    """Configuration for Monte Carlo player."""

    def __init__(
        self,
        min_think_time_s: float = 1.0,
        max_think_time_s: float = 5.0,
        min_simulations: int = 10,
        max_simulations: int = 300,
        rollout_mc_steps: int = 1,
        rng_seed: Optional[int] = None,
        verbose: bool = False,
    ):
        """
        Initialize Monte Carlo configuration.

        Args:
            min_think_time_s: Minimum thinking time per turn (seconds)
            max_think_time_s: Maximum thinking time per turn (seconds)
            min_simulations: Minimum number of simulations per move
            max_simulations: Maximum number of simulations per move
            rollout_mc_steps: Number of steps in rollout to use MC evaluation (0 = pure random)
            rng_seed: Random seed for reproducibility (None for random)
            verbose: Whether to print debug output to stderr (default: False)
        """
        self.min_think_time_s = min_think_time_s
        self.max_think_time_s = max_think_time_s
        self.min_simulations = min_simulations
        self.max_simulations = max_simulations
        self.rollout_mc_steps = rollout_mc_steps
        self.rng_seed = rng_seed
        self.verbose = verbose


class MCGameState:
    """
    Internal game state for Monte Carlo simulations.

    This is a simplified, fully-determinized version of GameState where
    all cards are known (including our hand and deck).
    """

    def __init__(
        self,
        settings: GameSettings,
        hands: List[List[Card]],
        deck: List[Card],
        current_player: int,
        live_tokens: int,
        hint_tokens: int,
        cards_played: Dict[Color, Number],
        cards_discarded: Dict[Color, Dict[Number, int]],
        cards_to_draw: int,
        turns_left: Optional[int],
    ):
        """
        Initialize Monte Carlo game state.

        Args:
            settings: Game settings
            hands: List of hands (each hand is a list of Cards)
            deck: Remaining deck as a list of Cards
            current_player: Current player index
            live_tokens: Current live tokens
            hint_tokens: Current hint tokens
            cards_played: Dictionary mapping Color to highest Number played
            cards_discarded: Dictionary mapping Color to Dict[Number, count]
            cards_to_draw: Number of cards remaining to draw
            turns_left: Number of turns left (None if deck not exhausted)
        """
        self._settings = settings
        self._hands = [hand.copy() for hand in hands]
        self._deck = deck.copy()
        self._current_player = current_player
        self._live_tokens = live_tokens
        self._hint_tokens = hint_tokens
        self._cards_played = cards_played.copy()
        self._cards_discarded = {color: counts.copy() for color, counts in cards_discarded.items()}
        self._cards_to_draw = cards_to_draw
        self._turns_left = turns_left
        self._deck_index = 0  # Track position in deck

    def clone(self) -> "MCGameState":
        """Create a deep copy of this state."""
        cloned = MCGameState(
            settings=self._settings,
            hands=self._hands,
            deck=self._deck,
            current_player=self._current_player,
            live_tokens=self._live_tokens,
            hint_tokens=self._hint_tokens,
            cards_played=self._cards_played,
            cards_discarded=self._cards_discarded,
            cards_to_draw=self._cards_to_draw,
            turns_left=self._turns_left,
        )
        # Copy deck_index which tracks position in deck
        cloned._deck_index = self._deck_index
        return cloned

    @property
    def settings(self) -> GameSettings:
        """Get game settings."""
        return self._settings

    @property
    def hands(self) -> List[List[Card]]:
        """Get list of hands."""
        return [hand.copy() for hand in self._hands]

    @property
    def current_player(self) -> int:
        """Get current player index."""
        return self._current_player

    @property
    def live_tokens(self) -> int:
        """Get current live tokens."""
        return self._live_tokens

    @property
    def hint_tokens(self) -> int:
        """Get current hint tokens."""
        return self._hint_tokens

    def is_finished(self) -> bool:
        """Check if game is finished."""
        # 1. All life tokens lost
        if self._live_tokens <= 0:
            return True

        # 2. All fireworks completed (perfect score)
        if len(self._cards_played) == 5:
            all_fives = all(num == Number.FIVE for num in self._cards_played.values())
            if all_fives:
                return True

        # 3. Deck exhausted and all players took final turn
        if self._turns_left == 0:
            return True

        # 4. Auto-end when no more points possible (if enabled)
        if self._settings.auto_end_when_no_points_possible:
            if self._is_no_more_points_possible():
                return True

        return False

    def _is_no_more_points_possible(self) -> bool:
        """Check if no more points are possible."""
        for color in [Color.WHITE, Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]:
            # Determine next card needed
            if color in self._cards_played:
                current_highest = self._cards_played[color]
                if current_highest == Number.FIVE:
                    continue  # Complete
                next_needed = Number(current_highest.value + 1)
            else:
                next_needed = Number.ONE

            # Get total count from settings
            suit = self._settings.cards.get(color)
            assert suit is not None, f"Suit for color {color} should exist in game settings"
            total_count = suit.cards.get(next_needed, 0)

            # Count discarded
            discarded_count = self._cards_discarded.get(color, {}).get(next_needed, 0)

            # If not all copies discarded, can still progress
            if discarded_count < total_count:
                return False

        return True

    def score(self) -> int:
        """Calculate current game score."""
        score = 0
        for number in self._cards_played.values():
            score += number.value
        return score

    def advance_player(self) -> None:
        """Advance to next player's turn."""
        self._current_player = (self._current_player + 1) % self._settings.num_players

        # If deck exhausted, decrement turns left
        if self._turns_left is not None:
            if self._turns_left > 0:
                self._turns_left -= 1

    def apply_move(self, player_index: int, move: Move) -> None:
        """Apply a move to this state (in-place update)."""
        if isinstance(move, Play):
            self._apply_play(player_index, move)
        elif isinstance(move, Discard):
            self._apply_discard(player_index, move)
        elif isinstance(move, (ColorHint, NumberHint)):
            self._apply_hint(player_index, move)
        else:
            assert False, f"Unknown move type: {type(move)}"

    def _apply_play(self, player_index: int, move: Play) -> None:
        """Apply a play move."""
        hand = self._hands[player_index]
        assert 0 <= move.card < len(hand), f"Invalid card index: {move.card}"

        card = hand[move.card]

        # Check if valid play
        if card.color not in self._cards_played:
            is_valid = card.number == Number.ONE
        else:
            next_number_value = self._cards_played[card.color].value + 1
            is_valid = card.number.value == next_number_value

        if is_valid:
            # Valid play
            self._hands[player_index].pop(move.card)
            self._cards_played[card.color] = card.number

            # Check if firework completed (gain hint token)
            if card.number == Number.FIVE:
                previous = self._cards_played.get(card.color)
                if previous == Number.FOUR:
                    if self._hint_tokens < self._settings.max_hint_tokens:
                        self._hint_tokens += 1

            # Draw new card
            self._draw_card(player_index)
        else:
            # Invalid play - lose life, discard card
            self._hands[player_index].pop(move.card)
            self._add_to_discard(card)
            self._live_tokens -= 1
            self._draw_card(player_index)

    def _apply_discard(self, player_index: int, move: Discard) -> None:
        """Apply a discard move."""
        hand = self._hands[player_index]
        assert 0 <= move.card < len(hand), f"Invalid card index: {move.card}"

        card = hand[move.card]
        self._hands[player_index].pop(move.card)
        self._add_to_discard(card)

        # Gain hint token
        if self._hint_tokens < self._settings.max_hint_tokens:
            self._hint_tokens += 1

        # Draw new card
        self._draw_card(player_index)

    def _apply_hint(self, player_index: int, move: Move) -> None:
        """Apply a hint move."""
        # Use hint token
        assert self._hint_tokens > 0, "No hint tokens available"
        self._hint_tokens -= 1

        # Check if deck exhausted (hints don't draw cards)
        if self._cards_to_draw == 0 and self._turns_left is None:
            self._turns_left = self._settings.num_players

    def _draw_card(self, player_index: int) -> None:
        """Draw a card from deck to player's hand."""
        if self._deck_index < len(self._deck):
            card = self._deck[self._deck_index]
            self._deck_index += 1
            self._cards_to_draw = len(self._deck) - self._deck_index
            self._hands[player_index].insert(0, card)

            # Check if deck exhausted
            if self._cards_to_draw == 0 and self._turns_left is None:
                self._turns_left = self._settings.num_players
        else:
            # Deck exhausted
            if self._turns_left is None:
                self._turns_left = self._settings.num_players

    def _add_to_discard(self, card: Card) -> None:
        """Add a card to discard pile."""
        if card.color not in self._cards_discarded:
            self._cards_discarded[card.color] = {}
        if card.number not in self._cards_discarded[card.color]:
            self._cards_discarded[card.color][card.number] = 0
        self._cards_discarded[card.color][card.number] += 1

    def to_player_view(self, player_index: int) -> PlayerView:
        """Convert to PlayerView for a specific player."""
        from hanabi.core.game import Hand

        teammates: Dict[int, Hand] = {}
        for i, hand in enumerate(self._hands):
            if i != player_index:
                teammates[i] = Hand(hand.copy())

        own_hand_size = len(self._hands[player_index])
        return PlayerView(teammates, own_hand_size)

    def to_common_view(self) -> CommonView:
        """Convert to CommonView."""
        from hanabi.core.game import CommonView

        # Convert cards_discarded to Suit format
        discarded_suits: Dict[Color, Suit] = {}
        for color, counts in self._cards_discarded.items():
            discarded_suits[color] = Suit(counts.copy())

        return CommonView(
            live_tokens=self._live_tokens,
            hint_tokens=self._hint_tokens,
            cards_to_draw=self._cards_to_draw,
            cards_discarded=discarded_suits,
            cards_played=self._cards_played.copy(),
        )

    def generate_valid_moves(self) -> List[Move]:
        """Generate valid moves for current player."""
        player_view = self.to_player_view(self._current_player)
        common_view = self.to_common_view()
        return generate_all_valid_moves(
            player_view=player_view,
            common_view=common_view,
            game_settings=self._settings,
            player_index=self._current_player,
        )


class MonteCarloPlayer(HintTrackingPlayer):
    """
    Monte Carlo AI player.

    Uses Monte Carlo simulation to evaluate moves by:
    1. Sampling possible worlds (our hand + deck)
    2. Evaluating each candidate move via rollouts
    3. Selecting move with highest average score
    """

    def __init__(self, player_index: int, config: Optional[MonteCarloConfig] = None):
        """
        Initialize Monte Carlo player.

        Args:
            player_index: Index of this player
            config: Configuration (None for defaults)
        """
        super().__init__(player_index)
        self._config = config or MonteCarloConfig()
        self._rng = random.Random(self._config.rng_seed)
        self._verbose = self._config.verbose
        self._last_decision_summary: Optional[str] = None

    def play(self, player_view: PlayerView) -> Move:
        """
        Make a move using Monte Carlo evaluation.

        Args:
            player_view: Current view of the game

        Returns:
            Best move according to Monte Carlo evaluation
        """
        # Generate all candidate moves
        candidate_moves = generate_all_valid_moves(
            player_view=player_view,
            common_view=self.common_view,
            game_settings=self.game_settings,
            player_index=self._player_index,
        )

        # Filter to actually valid moves
        candidate_moves = [m for m in candidate_moves if self.is_move_legal(player_view, m)]

        # In Hanabi, there should always be multiple valid moves
        assert len(candidate_moves) > 1, (
            f"No valid moves or only one move available (impossible in Hanabi). Found {len(candidate_moves)} moves."
        )

        # Log context for debugging (use both logger and print for visibility)
        debug_msg = f"[MonteCarloPlayer {self._player_index}] Current game state:"
        logger.debug(debug_msg)
        if self._verbose:
            print(debug_msg, file=sys.stderr)

        debug_msg = f"  Score: {self.common_view.cards_played}"
        logger.debug(debug_msg)
        if self._verbose:
            print(debug_msg, file=sys.stderr)

        debug_msg = (
            f"  Hint tokens: {self.common_view.hint_tokens}, "
            f"Live tokens: {self.common_view.live_tokens}"
        )
        logger.debug(debug_msg)
        if self._verbose:
            print(debug_msg, file=sys.stderr)

        debug_msg = f"  Own hand size: {player_view.own_hand_size}"
        logger.debug(debug_msg)
        if self._verbose:
            print(debug_msg, file=sys.stderr)

        debug_msg = f"  Candidate moves: {len(candidate_moves)}"
        logger.debug(debug_msg)
        if self._verbose:
            print(debug_msg, file=sys.stderr)

        # Show which moves are play moves (these are the ones we care about for hinted cards)
        play_moves = [m for m in candidate_moves if isinstance(m, Play)]
        if play_moves:
            debug_msg = f"  Play moves: {[f'Play({m.card})' for m in play_moves]}"
            logger.debug(debug_msg)
            if self._verbose:
                print(debug_msg, file=sys.stderr)

        # Evaluate moves with Monte Carlo
        best_move = self._evaluate_moves_monte_carlo(player_view, candidate_moves)

        return best_move

    def _evaluate_moves_monte_carlo(self, player_view: PlayerView, moves: List[Move]) -> Move:
        """
        Evaluate moves using Monte Carlo simulation.

        Args:
            player_view: Current player view
            moves: List of candidate moves

        Returns:
            Best move (highest average score)
        """
        num_moves = len(moves)

        # Initialize score accumulators
        scores_sum = [0.0] * num_moves
        counts = [0] * num_moves

        # --- Pilot: single batch (1 determinization, all moves) ---
        start = time.perf_counter()
        debug_msg = f"[MonteCarloPlayer {self._player_index}] Starting evaluation of {num_moves} candidate moves"
        logger.debug(debug_msg)
        if self._verbose:
            print(debug_msg, file=sys.stderr)
        self._run_one_world_batch(player_view, moves, scores_sum, counts)
        elapsed = time.perf_counter() - start

        # Calculate time per evaluation
        evals_done = num_moves
        assert evals_done > 0, f"No evaluations done (impossible). num_moves={num_moves}"
        assert elapsed > 0, f"Elapsed time should be > 0, got {elapsed}"

        t_per_eval = elapsed / evals_done

        # --- Compute total number of evaluations under time budget ---
        # CRITICAL: Ensure we meet minimum simulations requirement first
        min_total_evals = self._config.min_simulations * num_moves
        max_total_evals_capped = self._config.max_simulations * num_moves

        # Calculate time-based target
        target_time = (self._config.min_think_time_s + self._config.max_think_time_s) / 2.0
        time_based_evals = int(target_time / t_per_eval)

        # Ensure we get at least min_simulations per move, but don't exceed max
        # If time budget allows more, use that; otherwise, use minimum
        max_total_evals = max(min_total_evals, time_based_evals)
        max_total_evals = min(max_total_evals, max_total_evals_capped)

        remaining_evals = max_total_evals - evals_done
        additional_worlds = max(0, remaining_evals // num_moves)

        # CRITICAL: Ensure we meet minimum simulations per move
        # This takes priority over time limits
        min_worlds_needed = self._config.min_simulations - 1  # -1 because pilot already counted
        additional_worlds = max(additional_worlds, min_worlds_needed)

        # Ensure we use at least the minimum thinking time
        # If we haven't used enough time yet, run more simulations
        current_elapsed = time.perf_counter() - start
        if current_elapsed < self._config.min_think_time_s:
            # Need more time - estimate how many more worlds we can run
            time_remaining = self._config.min_think_time_s - current_elapsed
            assert t_per_eval > 0, f"Time per evaluation should be > 0, got {t_per_eval}"
            additional_worlds_needed = max(1, int(time_remaining / (t_per_eval * num_moves)))
            additional_worlds = max(additional_worlds, additional_worlds_needed)

        # Cap additional worlds to not exceed max_think_time_s
        # BUT: if we haven't met min_simulations yet, prioritize that over time limit
        estimated_total_time = current_elapsed + (additional_worlds * t_per_eval * num_moves)
        total_sims_per_move = 1 + additional_worlds  # pilot + additional
        if estimated_total_time > self._config.max_think_time_s and total_sims_per_move >= self._config.min_simulations:
            # We've met minimum simulations, so cap to max time
            time_available = self._config.max_think_time_s - current_elapsed
            # If we've already exceeded max time, set time_available to 0
            if time_available <= 0:
                # Already exceeded max time, but we've met min simulations
                # Set additional_worlds to 0 (we'll still have the pilot simulation)
                additional_worlds = 0
            else:
                assert t_per_eval > 0, f"Time per evaluation should be > 0, got {t_per_eval}"
                additional_worlds = max(0, int(time_available / (t_per_eval * num_moves)))
                # But still ensure we meet minimum (may exceed max time if necessary)
                # However, if we've already exceeded max time, don't force more worlds
                if current_elapsed < self._config.max_think_time_s:
                    additional_worlds = max(additional_worlds, min_worlds_needed)

        # --- Additional worlds ---
        if additional_worlds > 0:
            debug_msg = (
                f"[MonteCarloPlayer {self._player_index}] Running {additional_worlds} additional world batches..."
            )
            logger.debug(debug_msg)
            if self._verbose:
                print(debug_msg, file=sys.stderr)
        for world_num in range(additional_worlds):
            # Check time before starting each batch - don't start if we're already at or near max time
            current_elapsed = time.perf_counter() - start
            if current_elapsed >= self._config.max_think_time_s * 0.9:  # Stop if we're at 90% of max time
                debug_msg = (
                    f"[MonteCarloPlayer {self._player_index}] Skipping remaining batches "
                    f"(already at {current_elapsed:.3f}s, approaching max time {self._config.max_think_time_s:.3f}s)"
                )
                logger.debug(debug_msg)
                if self._verbose:
                    print(debug_msg, file=sys.stderr)
                break

            self._run_one_world_batch(player_view, moves, scores_sum, counts)

            # Check if we've exceeded max time during execution
            # For GUI mode with low min_simulations, strictly enforce max time
            current_elapsed = time.perf_counter() - start
            current_sims_per_move = 1 + (world_num + 1)  # pilot + completed additional worlds

            # Strictly enforce max time - stop immediately if exceeded
            if current_elapsed >= self._config.max_think_time_s:
                if current_sims_per_move >= self._config.min_simulations:
                    # Met minimum and exceeded max time - stop
                    debug_msg = (
                        f"[MonteCarloPlayer {self._player_index}] Stopped early at world "
                        f"{world_num + 1}/{additional_worlds} (exceeded max time: "
                        f"{current_elapsed:.3f}s >= {self._config.max_think_time_s:.3f}s, "
                        f"met min_simulations: {current_sims_per_move} >= {self._config.min_simulations})"
                    )
                    logger.debug(debug_msg)
                    if self._verbose:
                        print(debug_msg, file=sys.stderr)
                    break
                else:
                    # Haven't met minimum but exceeded max time
                    # Only continue if min_simulations is very low (1-2) and we're close
                    if (
                        self._config.min_simulations <= 2
                        and current_sims_per_move >= self._config.min_simulations - 1
                    ):
                        # Very close to minimum, allow one more iteration
                        continue
                    else:
                        # Stop even if we haven't met minimum - time limit is strict
                        debug_msg = (
                            f"[MonteCarloPlayer {self._player_index}] Stopped at world "
                            f"{world_num + 1}/{additional_worlds} (exceeded max time: "
                            f"{current_elapsed:.3f}s >= {self._config.max_think_time_s:.3f}s, "
                            f"simulations: {current_sims_per_move} < {self._config.min_simulations})"
                        )
                        logger.debug(debug_msg)
                        if self._verbose:
                            print(debug_msg, file=sys.stderr)
                        break

        # --- Choose move with best average score ---
        # Pure Monte Carlo: select move with highest average score from simulations
        # No hardcoded heuristics - rely on the Monte Carlo evaluation
        best_idx = 0
        best_avg = float("-inf")
        move_stats = []

        for i, move in enumerate(moves):
            assert counts[i] > 0, f"Move {move} has 0 simulation counts (impossible - all moves should be evaluated)"
            avg = scores_sum[i] / counts[i]
            move_stats.append((move, avg, counts[i], scores_sum[i]))
            if avg > best_avg:
                best_avg = avg
                best_idx = i

        # Debug logging: show simulation results (use both logger and print for visibility)
        total_simulations = sum(counts)
        actual_time = time.perf_counter() - start

        debug_msg = f"[MonteCarloPlayer {self._player_index}] Evaluated {len(moves)} candidate moves"
        logger.debug(debug_msg)
        if self._verbose:
            print(debug_msg, file=sys.stderr)

        debug_msg = (
            f"[MonteCarloPlayer {self._player_index}] Total simulations: {total_simulations} "
            f"(target: {target_time:.2f}s, actual: {actual_time:.3f}s)"
        )
        logger.debug(debug_msg)
        if self._verbose:
            print(debug_msg, file=sys.stderr)

        debug_msg = (
            f"[MonteCarloPlayer {self._player_index}] Simulations per move: "
            f"pilot={evals_done // num_moves}, additional={additional_worlds}"
        )
        logger.debug(debug_msg)
        if self._verbose:
            print(debug_msg, file=sys.stderr)

        # Log stats for each move
        if self._verbose:
            print(f"[MonteCarloPlayer {self._player_index}] Move evaluation results:", file=sys.stderr)
        for move, avg_score, sim_count, total_score in sorted(move_stats, key=lambda x: x[1], reverse=True):
            move_str = str(move)
            debug_msg = f"  {move_str:30s} avg={avg_score:6.2f}  sims={sim_count:3d}  total={total_score:8.1f}"
            logger.debug(
                f"[MonteCarloPlayer {self._player_index}]   {move_str:30s} "
                f"avg={avg_score:6.2f}  sims={sim_count:3d}  total={total_score:8.1f}"
            )
            if self._verbose:
                print(debug_msg, file=sys.stderr)

        selected_move = moves[best_idx]
        debug_msg = f"[MonteCarloPlayer {self._player_index}] Selected: {selected_move} (avg score: {best_avg:.2f})"
        logger.debug(debug_msg)
        if self._verbose:
            print(debug_msg, file=sys.stderr)

        # Store decision summary: top 3 moves with their avg scores
        top_3 = sorted(move_stats, key=lambda x: x[1], reverse=True)[:3]
        summary_parts = []
        for move, avg_score, sim_count, total_score in top_3:
            move_str = self._format_move_concise(move)
            summary_parts.append(f"{move_str} (avg: {avg_score:.2f})")
        self._last_decision_summary = ", ".join(summary_parts)

        return selected_move

    def _format_move_concise(self, move: Move) -> str:
        """
        Format a move in concise format for decision summary.

        Args:
            move: The move to format

        Returns:
            Concise string representation (e.g., "play 0", "discard 1", "hint P2 1", "hint P3 blue")
        """
        from hanabi.core.moves import Play, Discard, ColorHint, NumberHint

        if isinstance(move, Play):
            return f"play {move.card}"
        elif isinstance(move, Discard):
            return f"discard {move.card}"
        elif isinstance(move, ColorHint):
            return f"hint P{move.teammate + 1} {move.color.name.lower()}"
        elif isinstance(move, NumberHint):
            return f"hint P{move.teammate + 1} {move.number.value}"
        else:
            return str(move)

    def get_decision_summary(self) -> Optional[str]:
        """
        Get a summary of the last decision made (top 3 actions and their avg scores).

        Returns:
            Summary string describing top 3 moves with scores, or None if no decision made yet
        """
        return self._last_decision_summary

    def _run_one_world_batch(
        self,
        player_view: PlayerView,
        moves: List[Move],
        scores_sum: List[float],
        counts: List[int],
    ) -> None:
        """
        Run one determinized world and evaluate all moves.

        This samples ONE world and evaluates ALL moves on that same world.
        This is correct for Monte Carlo: we want to compare moves in the same scenario.

        Args:
            player_view: Current player view
            moves: List of candidate moves
            scores_sum: List to accumulate scores (modified in-place)
            counts: List to accumulate counts (modified in-place)
        """
        # Sample a single determinized world
        # CRITICAL: We use the SAME world for all moves to ensure fair comparison
        world = self._sample_determinized_state(player_view)

        # For each move, clone world, apply move, advance player, rollout, accumulate scores
        for i, move in enumerate(moves):
            # CRITICAL: Clone the world for each move to avoid mutating the original
            sim_state = world.clone()

            # Debug: log what card we're playing
            if isinstance(move, Play):
                # Access hands directly (not via property) to avoid copying
                hand = sim_state._hands[self._player_index]
                assert move.card < len(hand), f"Card index {move.card} out of range for hand size {len(hand)}"
                card_being_played = hand[move.card]
                debug_msg = (
                    f"[MonteCarloPlayer {self._player_index}] Evaluating {move}: "
                    f"playing {card_being_played} from hand {[str(c) for c in hand]}"
                )
                logger.debug(debug_msg)
                if self._verbose:
                    print(debug_msg, file=sys.stderr)

            # Apply the move to the cloned state
            sim_state.apply_move(self._player_index, move)

            # Debug: log score immediately after applying move (before rollout)
            score_after_move = sim_state.score()
            if isinstance(move, Play):
                debug_msg = (
                    f"[MonteCarloPlayer {self._player_index}] After {move}, score BEFORE rollout: {score_after_move}"
                )
                logger.debug(debug_msg)
                if self._verbose:
                    print(debug_msg, file=sys.stderr)

            sim_state.advance_player()  # Advance to next player before rollout

            # Rollout to terminal and get final score
            final_score = self._rollout_to_terminal(sim_state)

            # Debug: log the score we got
            debug_msg = f"[MonteCarloPlayer {self._player_index}] {move} -> score: {final_score}"
            logger.debug(debug_msg)
            if self._verbose:
                print(debug_msg, file=sys.stderr)

            # Accumulate scores
            scores_sum[i] += final_score
            counts[i] += 1

    def _sample_determinized_state(self, player_view: PlayerView) -> MCGameState:
        """
        Sample a determinized game state consistent with current information.

        Args:
            player_view: Current player view

        Returns:
            A fully determinized MCGameState
        """
        # 1. Build global card multiset from settings
        all_cards: List[Card] = []
        for color, suit in self.game_settings.cards.items():
            for number, quantity in suit.cards.items():
                for _ in range(quantity):
                    all_cards.append(Card(color, number))

        card_multiset = Counter(all_cards)

        # 2. Subtract known cards (teammates' hands, discarded, played)
        # Teammates' hands
        for teammate_idx, hand in player_view.teammates.items():
            for card in hand.cards:
                if card_multiset[card] > 0:
                    card_multiset[card] -= 1

        # Discarded cards
        for color, suit in self.common_view.cards_discarded.items():
            for number, count in suit.cards.items():
                card = Card(color, number)
                for _ in range(count):
                    if card_multiset[card] > 0:
                        card_multiset[card] -= 1

        # Played cards (need to subtract all numbers up to highest)
        for color, highest_number in self.common_view.cards_played.items():
            for num_value in range(1, highest_number.value + 1):
                number = Number(num_value)
                card = Card(color, number)
                if card_multiset[card] > 0:
                    card_multiset[card] -= 1

        # 3. Get candidate sets for our hand positions using hints
        hand_size = player_view.own_hand_size
        candidate_sets: List[Set[Card]] = []

        # Get hints we've received
        hints = self.get_hints()

        # Debug: log all hints to help diagnose hint tracking issues
        if hints:
            debug_msg = f"[MonteCarloPlayer {self._player_index}] Hints when sampling: {hints}"
            logger.debug(debug_msg)
            if self._verbose:
                print(debug_msg, file=sys.stderr)

        # Build candidate sets for each position based on hints
        for pos in range(hand_size):
            candidate_set = set()
            pos_hints = hints.get(pos, {})

            # If we have hints for this position, filter by them
            if pos_hints:
                color_hint = pos_hints.get("color")
                number_hint = pos_hints.get("number")

                # Filter cards by hints AND availability (count > 0)
                for card, count in card_multiset.items():
                    # Only consider cards that are actually available
                    if count <= 0:
                        continue
                    # Must match color hint if present
                    if color_hint is not None and card.color != color_hint:
                        continue
                    # Must match number hint if present
                    if number_hint is not None and card.number != number_hint:
                        continue
                    # Card matches all hints and is available
                    candidate_set.add(card)
            else:
                # No hints for this position - all remaining cards with count > 0 are candidates
                for card, count in card_multiset.items():
                    if count > 0:
                        candidate_set.add(card)

            candidate_sets.append(candidate_set)

        # 4. Sample our hand from the multiset
        # CRITICAL: Sample positions with complete hints (both color and number) FIRST
        # to ensure those constraints are satisfied before other positions use those cards
        own_hand: List[Card] = [None] * hand_size  # Pre-allocate list
        remaining_multiset = card_multiset.copy()

        # Determine sampling order: positions with complete hints first, then others
        sampling_order = []
        # First: positions with both color and number hints (most constrained)
        for pos in range(hand_size):
            pos_hints = hints.get(pos, {})
            if pos_hints.get("color") is not None and pos_hints.get("number") is not None:
                sampling_order.append(pos)
        # Then: positions with one hint (color or number)
        for pos in range(hand_size):
            if pos not in sampling_order:
                pos_hints = hints.get(pos, {})
                if pos_hints.get("color") is not None or pos_hints.get("number") is not None:
                    sampling_order.append(pos)
        # Finally: positions with no hints
        for pos in range(hand_size):
            if pos not in sampling_order:
                sampling_order.append(pos)

        # Sample in the determined order
        for pos in sampling_order:
            # Get candidates for this position (intersect with remaining multiset)
            candidates = [card for card in candidate_sets[pos] if remaining_multiset[card] > 0]

            # In Hanabi, there should always be candidates available
            # If hints are inconsistent with available cards, this indicates a bug in hint tracking
            turn_info = (
                player_view.teammates.get(0, "N/A") if player_view.teammates else "N/A"
            )
            assert len(candidates) > 0, (
                f"No candidates for hand position {pos} (impossible in Hanabi). "
                f"This likely indicates a bug in hint tracking - hints may be at wrong positions.\n"
                f"Player: {self._player_index}, Turn: {turn_info}\n"
                f"Hand size: {hand_size}\n"
                f"Remaining multiset: {dict(remaining_multiset)}\n"
                f"Candidate set for position {pos}: {candidate_sets[pos]}\n"
                f"Candidate set size: {len(candidate_sets[pos])}\n"
                f"Hints for position {pos}: {hints.get(pos, {})}\n"
                f"All hints: {hints}\n"
                f"Sampling order: {sampling_order}\n"
                f"Already sampled hand so far: {[card for card in own_hand if card is not None]}"
            )

            # Sample uniformly
            card = self._rng.choice(candidates)
            own_hand[pos] = card
            remaining_multiset[card] -= 1

        # 5. Build deck from remaining multiset
        deck_cards: List[Card] = []
        for card, count in remaining_multiset.items():
            deck_cards.extend([card] * count)
        self._rng.shuffle(deck_cards)

        # 6. Build hands for all players
        hands: List[List[Card]] = []
        for i in range(self.game_settings.num_players):
            if i == self._player_index:
                hands.append(own_hand.copy())
            else:
                # Get teammate's hand
                assert i in player_view.teammates, f"Teammate {i} should exist in player_view.teammates"
                teammate_hand = player_view.teammates[i]
                hands.append([card for card in teammate_hand.cards])

        # 7. Build cards_discarded dict
        cards_discarded: Dict[Color, Dict[Number, int]] = {}
        for color, suit in self.common_view.cards_discarded.items():
            cards_discarded[color] = suit.cards.copy()

        # 8. Create MCGameState
        # Estimate turns_left: None if deck not exhausted, else approximate
        turns_left = None
        if len(deck_cards) == 0:
            turns_left = self.game_settings.num_players

        return MCGameState(
            settings=self.game_settings,
            hands=hands,
            deck=deck_cards,
            current_player=self._player_index,
            live_tokens=self.common_view.live_tokens,
            hint_tokens=self.common_view.hint_tokens,
            cards_played=self.common_view.cards_played.copy(),
            cards_discarded=cards_discarded,
            cards_to_draw=len(deck_cards),
            turns_left=turns_left,
        )

    def _rollout_to_terminal(self, state: MCGameState) -> int:
        """
        Rollout game to terminal using hybrid policy:
        - First N steps: Use Monte Carlo evaluation (if rollout_mc_steps > 0)
        - Remaining steps: Pure random policy

        Args:
            state: Starting game state

        Returns:
            Final game score
        """
        max_depth = 200  # Safety limit to prevent infinite rollouts
        depth = 0
        mc_steps_remaining = self._config.rollout_mc_steps

        while not state.is_finished() and depth < max_depth:
            depth += 1

            # Get valid moves for current player
            moves = state.generate_valid_moves()

            # Filter to actually valid moves (check hint tokens, etc.)
            valid_moves = []
            for move in moves:
                if self._is_move_valid_in_state(state, move):
                    valid_moves.append(move)

            # In Hanabi, there should always be valid moves if game is not finished
            assert len(valid_moves) > 0, (
                f"No valid moves available (impossible in Hanabi). "
                f"Game finished: {state.is_finished()}, "
                f"Generated moves: {len(moves)}, "
                f"Depth: {depth}"
            )

            # Select move: use MC evaluation for first N steps, then pure random
            if mc_steps_remaining > 0:
                # Use Monte Carlo evaluation for this step
                move = self._select_move_with_mc_in_rollout(state, valid_moves)
                mc_steps_remaining -= 1
            else:
                # Pure random for remaining steps (pure Monte Carlo, no heuristics)
                move = self._rng.choice(valid_moves)

            # Apply move
            state.apply_move(state.current_player, move)

            # Advance player after move
            state.advance_player()

        return state.score()

    def _select_move_with_mc_in_rollout(self, state: MCGameState, valid_moves: List[Move]) -> Move:
        """
        Select a move using fast Monte Carlo evaluation during rollout.

        This is a lightweight version that samples one world and evaluates all moves
        with a single rollout each, then picks the best.

        Args:
            state: Current game state
            valid_moves: List of valid moves to choose from

        Returns:
            Best move according to fast MC evaluation
        """
        # In Hanabi, there should always be multiple valid moves
        assert len(valid_moves) > 1, (
            f"Only one valid move in rollout (impossible in Hanabi). Found {len(valid_moves)} moves."
        )

        # Sample one world (the current state is already determinized, so we just use it)
        # For each move, clone state, apply move, do a quick random rollout, get score
        best_move = valid_moves[0]
        best_score = float("-inf")

        for move in valid_moves:
            # Clone state and apply move
            test_state = state.clone()
            test_state.apply_move(state.current_player, move)
            test_state.advance_player()

            # Quick random rollout to terminal
            final_score = self._quick_random_rollout(test_state)

            if final_score > best_score:
                best_score = final_score
                best_move = move

        return best_move

    def _quick_random_rollout(self, state: MCGameState) -> int:
        """
        Fast random rollout to terminal (used during MC evaluation in rollout).

        Pure random policy - no heuristics.

        Args:
            state: Starting game state

        Returns:
            Final game score
        """
        max_depth = 200
        depth = 0

        while not state.is_finished() and depth < max_depth:
            depth += 1

            moves = state.generate_valid_moves()
            valid_moves = [m for m in moves if self._is_move_valid_in_state(state, m)]

            # In Hanabi, there should always be valid moves if game is not finished
            assert len(valid_moves) > 0, (
                f"No valid moves in quick rollout (impossible in Hanabi). "
                f"Game finished: {state.is_finished()}, "
                f"Generated moves: {len(moves)}, "
                f"Depth: {depth}"
            )

            # Pure random selection (pure Monte Carlo, no heuristics)
            move = self._rng.choice(valid_moves)

            state.apply_move(state.current_player, move)
            state.advance_player()

        return state.score()

    def _is_move_valid_in_state(self, state: MCGameState, move: Move) -> bool:
        """
        Check if a move is valid in the given MCGameState.

        Args:
            state: Game state to check
            move: Move to validate

        Returns:
            True if move is valid
        """
        if isinstance(move, Play):
            hand = state.hands[state.current_player]
            if move.card < 0 or move.card >= len(hand):
                return False
            return True

        if isinstance(move, Discard):
            hand = state.hands[state.current_player]
            if move.card < 0 or move.card >= len(hand):
                return False
            if state.hint_tokens >= state.settings.max_hint_tokens:
                return False
            return True

        if isinstance(move, (ColorHint, NumberHint)):
            if state.hint_tokens <= 0:
                return False

            if move.teammate < 0 or move.teammate >= len(state.hands):
                return False

            if move.teammate == state.current_player:
                return False

            if not move.cards:
                return False

            teammate_hand = state.hands[move.teammate]
            return is_legal_hint_against_hand_cards(move, teammate_hand)

        return False
