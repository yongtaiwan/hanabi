"""
GameField class for managing multiple games.

This module is used for AI performance comparisons and batch game simulations.
GUI/CLI games use Game directly, not GameField.
"""

from __future__ import annotations

import os
import time
import random
import statistics
from datetime import datetime
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass, field, asdict

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    import json

from .game import Game, StartPosition, GameSettings, create_deck_from_settings, Hand, CommonView, GameState
from .player import PlayerTeam, BasePlayer
from .game_history import GameHistory


@dataclass
class GameResult:
    """Result from a single game."""

    score: int
    moves_count: int
    duration_seconds: float
    end_reason: str
    game_record_path: Optional[str] = None


@dataclass
class RunResult:
    """Results from one deck shuffle across all AIs."""

    run_id: int
    deck_seed: Optional[int]
    ai_results: Dict[str, GameResult] = field(default_factory=dict)


@dataclass
class AIStatistics:
    """Aggregated statistics for one AI."""

    games_played: int
    average_score: float
    best_score: int
    worst_score: int
    win_rate: float  # Perfect scores (25 points)
    std_dev: float
    average_moves: float
    average_duration: float


@dataclass
class ExperimentResults:
    """Results from running multiple experiments."""

    experiment_id: str
    settings: Dict[str, Any]
    num_runs: int
    runs: List[RunResult] = field(default_factory=list)
    summary: Dict[str, AIStatistics] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class GameField:
    """Manages multiple games and game initialization for AI performance comparisons."""

    # Root directory for all AI comparison experiments.
    # Layout:
    #   game_records/
    #     exp_ai_comparison/
    #       <timestamp>/
    #         2p/
    #           settings.yaml
    #           statistics.yaml
    #           games/
    #             all-games/
    #             <run_id>/
    #           ai/
    #             <ai_name>/
    #         3p/
    #         4p/
    #         5p/
    EXPERIMENTS_BASE_DIR = os.path.join("game_records", "exp_ai_comparison")

    @staticmethod
    def _get_experiment_dir(experiment_id: str) -> str:
        """
        Get the path to a specific experiment directory, creating it if necessary.

        Creates the following structure under EXPERIMENTS_BASE_DIR:
            <experiment_id>/
              settings.yaml
              statistics.yaml
              games/
                all-games/
                <run_id>/
              ai/
                <ai_name>/

        Args:
            experiment_id: The experiment identifier

        Returns:
            Path to the experiment directory
        """
        base_dir = GameField.EXPERIMENTS_BASE_DIR
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        # experiment_id may contain subdirectories (e.g., "<timestamp>/2p")
        experiment_dir = os.path.join(base_dir, experiment_id)
        if not os.path.exists(experiment_dir):
            os.makedirs(experiment_dir)
            # Create games/all-games subdirectory
            all_games_dir = os.path.join(experiment_dir, "games", "all-games")
            os.makedirs(all_games_dir, exist_ok=True)
            # Create ai subdirectory (will be populated with AI subdirs as needed)
            ai_dir = os.path.join(experiment_dir, "ai")
            os.makedirs(ai_dir, exist_ok=True)
        return experiment_dir

    @staticmethod
    def _get_experiment_all_games_dir(experiment_id: str) -> str:
        """
        Get the path to the all-games subdirectory for an experiment.

        Args:
            experiment_id: The experiment identifier

        Returns:
            Path to the all-games subdirectory
        """
        experiment_dir = GameField._get_experiment_dir(experiment_id)
        return os.path.join(experiment_dir, "games", "all-games")

    @staticmethod
    def _get_experiment_run_dir(experiment_id: str, run_id: int) -> str:
        """
        Get the path to a run-specific directory, creating it if necessary.

        Args:
            experiment_id: The experiment identifier
            run_id: The run ID

        Returns:
            Path to the run directory
        """
        experiment_dir = GameField._get_experiment_dir(experiment_id)
        run_dir = os.path.join(experiment_dir, "games", f"{run_id:03d}")
        if not os.path.exists(run_dir):
            os.makedirs(run_dir)
        return run_dir

    @staticmethod
    def _get_experiment_ai_dir(experiment_id: str, ai_name: str) -> str:
        """
        Get the path to an AI-specific directory, creating it if necessary.

        Args:
            experiment_id: The experiment identifier
            ai_name: The AI name

        Returns:
            Path to the AI directory
        """
        experiment_dir = GameField._get_experiment_dir(experiment_id)
        ai_dir = os.path.join(experiment_dir, "ai", ai_name)
        if not os.path.exists(ai_dir):
            os.makedirs(ai_dir)
        return ai_dir

    @staticmethod
    def _create_symlink(target: str, link_path: str) -> bool:
        """
        Create a symbolic link from link_path to target.

        Args:
            target: Path to the target file (absolute or relative)
            link_path: Path where the symlink should be created

        Returns:
            True if successful, False otherwise
        """
        try:
            # Remove existing link if it exists
            if os.path.exists(link_path) or os.path.islink(link_path):
                os.remove(link_path)

            # Ensure target is absolute for relative path calculation
            if not os.path.isabs(target):
                target = os.path.abspath(target)
            if not os.path.isabs(link_path):
                link_path = os.path.abspath(link_path)

            # Calculate relative path from link location to target
            try:
                rel_target = os.path.relpath(target, os.path.dirname(link_path))
                os.symlink(rel_target, link_path)
            except (OSError, ValueError) as e:
                # If relative path fails, try absolute path
                try:
                    os.symlink(target, link_path)
                except OSError:
                    # Symlinks not supported - create a text file with the path
                    with open(link_path + ".link", "w") as f:
                        f.write(target)
            return True
        except (OSError, AttributeError, Exception):
            # Symlinks not supported (e.g., Windows without admin rights)
            # Fallback: create a text file with the path
            try:
                with open(link_path + ".link", "w") as f:
                    f.write(os.path.abspath(target))
                return True
            except Exception:
                return False

    @staticmethod
    def _create_start_position(settings: GameSettings, seed: Optional[int] = None) -> StartPosition:
        """
        Create a StartPosition with a shuffled deck.

        Args:
            settings: Game settings
            seed: Optional random seed for deck shuffling (for reproducibility)

        Returns:
            A StartPosition with a shuffled deck
        """
        deck = create_deck_from_settings(settings)
        if seed is not None:
            random.seed(seed)
        deck.shuffle()
        if seed is not None:
            random.seed()  # Reset to system randomness
        return StartPosition(settings, deck)

    @staticmethod
    def _create_game_from_start_position(start_position: StartPosition, team: PlayerTeam) -> Game:
        """
        Create and initialize a Game from a StartPosition.

        This is similar to Game.create but uses an existing StartPosition instead
        of creating a new shuffled deck.

        Args:
            start_position: The starting position (settings and initial deck)
            team: The team of players

        Returns:
            A new initialized Game instance
        """
        settings = start_position.settings
        deck_cards = start_position.draw_deck.cards

        # Deal cards to players
        num_players = settings.num_players
        cards_per_player = settings.max_cards_in_hand
        player_hands: List[Hand] = []
        draw_deck_index = 0

        # Assert we have enough cards to deal
        required_cards = num_players * cards_per_player
        assert len(deck_cards) >= required_cards, (
            f"Not enough cards in deck: need {required_cards}, have {len(deck_cards)}"
        )

        for player_idx in range(num_players):
            hand_cards = []
            for _ in range(cards_per_player):
                assert draw_deck_index < len(deck_cards), f"Ran out of cards while dealing to player {player_idx}"
                hand_cards.append(deck_cards[draw_deck_index])
                draw_deck_index += 1
            player_hands.append(Hand(hand_cards))

        # Initialize common view
        remaining_cards = len(deck_cards) - draw_deck_index
        common_view = CommonView(
            live_tokens=settings.max_live_tokens,
            hint_tokens=settings.max_hint_tokens,
            cards_to_draw=remaining_cards,
            cards_discarded={},
            cards_played={},
        )

        # Initialize game state
        state = GameState(
            start_position=start_position,
            common_view=common_view,
            player_hands=player_hands,
            draw_deck_index=draw_deck_index,
            turn_number=0,
            current_player=0,
            turns_left=None,
        )

        # Create game instance
        game = Game(start_position, team, on_move=None)

        # Add initial state to turns
        game._turns.append(state)

        # Set common view for all players
        game._set_common_view_for_players()

        return game

    def __init__(self, start_position: StartPosition):
        """
        Initialize a game field.

        Args:
            start_position: The starting position (settings and initial deck)
        """
        self._start_position = start_position
        self._games: Dict[str, Game] = {}

    @staticmethod
    def create_from_settings(settings: GameSettings, seed: Optional[int] = None) -> GameField:
        """
        Create a GameField from game settings.

        Args:
            settings: Game settings
            seed: Optional random seed for deck shuffling

        Returns:
            A new GameField instance
        """
        start_position = GameField._create_start_position(settings, seed=seed)
        return GameField(start_position)

    @property
    def start_position(self) -> StartPosition:
        """Get the starting position."""
        return self._start_position

    @property
    def games(self) -> Dict[str, Game]:
        """Get the dictionary of games."""
        return self._games.copy()

    def _play_game_with_team(
        self,
        team: PlayerTeam,
        save_record: bool = True,
        experiment_id: Optional[str] = None,
        run_id: Optional[int] = None,
        ai_name: Optional[str] = None,
    ) -> GameResult:
        """
        Play a single game with a team of players using the same StartPosition.

        Args:
            team: The team of players
            save_record: Whether to save the game record
            experiment_id: Optional experiment ID for organizing saved records
            run_id: Optional run ID for organizing saved records
            ai_name: Optional AI name for organizing saved records

        Returns:
            GameResult with game statistics
        """
        # Record game history if requested
        history = None
        if save_record:
            # Convert settings to dict for GameHistory
            settings_dict = {
                "num_players": self._start_position.settings.num_players,
                "max_live_tokens": self._start_position.settings.max_live_tokens,
                "max_hint_tokens": self._start_position.settings.max_hint_tokens,
                "max_cards_in_hand": self._start_position.settings.max_cards_in_hand,
            }
            history = GameHistory(settings_dict)

        # Create game from the shared start position
        game = self._create_game_from_start_position(self._start_position, team)

        # Set up move callback to record moves if saving history
        if save_record:

            def on_move_callback(player_index: int, move, old_state, new_state):
                if history:
                    # Record move in history
                    result = "success"  # Simplified - actual result would need more analysis
                    history.record_move(player_index, move, result, game)

            game._on_move = on_move_callback
            history.record_initial_state(game)

        # Play the game and time it
        start_time = time.time()
        game.play()
        duration = time.time() - start_time

        # Get final score
        final_score = game.get_score()

        # Determine end reason
        state = game.state
        if state.common_view.live_tokens <= 0:
            end_reason = "lives_lost"
        elif 25 == final_score:
            end_reason = "perfect_score"
        elif 0 == state.turns_left:
            end_reason = "deck_exhausted"
        else:
            end_reason = "unknown"

        # Count moves (number of turns)
        moves_count = len(game._turns) - 1  # Subtract initial state

        # Save game record if requested
        game_record_path = None
        if save_record and history:
            history.record_final_score(game)
            # Generate filename with experiment context if available
            if experiment_id is not None and run_id is not None and ai_name is not None:
                filename = (
                    f"run_{run_id:03d}_ai_{ai_name}.yaml" if YAML_AVAILABLE else f"run_{run_id:03d}_ai_{ai_name}.json"
                )
                # Save to all-games directory
                all_games_dir = GameField._get_experiment_all_games_dir(experiment_id)
                filepath = os.path.join(all_games_dir, filename)
                # Override GameHistory's default path by using full path
                game_record_path = history.save_to_file(filename=filepath, final_score=final_score)

                # Create symlinks in run directory and AI directory
                run_dir = GameField._get_experiment_run_dir(experiment_id, run_id)
                ai_dir = GameField._get_experiment_ai_dir(experiment_id, ai_name)

                # Symlink in run directory
                run_link_path = os.path.join(run_dir, filename)
                GameField._create_symlink(filepath, run_link_path)

                # Symlink in AI directory
                ai_link_path = os.path.join(ai_dir, filename)
                GameField._create_symlink(filepath, ai_link_path)
            else:
                # Fallback to default location
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = (
                    f"experiment_game_{timestamp}.yaml" if YAML_AVAILABLE else f"experiment_game_{timestamp}.json"
                )
                game_record_path = history.save_to_file(filename=filename, final_score=final_score)

        return GameResult(
            score=final_score,
            moves_count=moves_count,
            duration_seconds=duration,
            end_reason=end_reason,
            game_record_path=game_record_path,
        )

    def run_experiment(
        self,
        ai_factories: Dict[str, Callable[[int], BasePlayer]],
        num_runs: int = 100,
        save_records: bool = True,
        random_seed: Optional[int] = None,
        experiment_id: Optional[str] = None,
    ) -> ExperimentResults:
        """
        Run an experiment: shuffle a deck, then let different AIs play the same deck.

        Args:
            ai_factories: Dictionary mapping AI name to factory function that creates a player
                         Factory signature: (player_index: int) -> BasePlayer
            num_runs: Number of experiment runs (each with a new deck shuffle)
            save_records: Whether to save individual game records
            random_seed: Optional seed for the first run (subsequent runs use sequential seeds)
            experiment_id: Optional experiment ID (defaults to timestamp)

        Returns:
            ExperimentResults with all run results and aggregated statistics
        """
        if experiment_id is None:
            experiment_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save settings.yaml for this experiment
        self.save_settings(experiment_id, self._start_position.settings)

        # Convert settings to dict for serialization
        settings_dict = {
            "num_players": self._start_position.settings.num_players,
            "max_live_tokens": self._start_position.settings.max_live_tokens,
            "max_hint_tokens": self._start_position.settings.max_hint_tokens,
            "max_cards_in_hand": self._start_position.settings.max_cards_in_hand,
        }

        runs: List[RunResult] = []
        all_scores: Dict[str, List[int]] = {ai_name: [] for ai_name in ai_factories.keys()}
        all_moves: Dict[str, List[int]] = {ai_name: [] for ai_name in ai_factories.keys()}
        all_durations: Dict[str, List[float]] = {ai_name: [] for ai_name in ai_factories.keys()}
        wins: Dict[str, int] = {ai_name: 0 for ai_name in ai_factories.keys()}

        # Run experiments
        for run_id in range(num_runs):
            # Create a new shuffled deck for this run
            deck_seed = (random_seed + run_id) if random_seed is not None else None
            start_position = self._create_start_position(self._start_position.settings, seed=deck_seed)

            # Create a temporary GameField for this run
            run_field = GameField(start_position)

            run_result = RunResult(run_id=run_id, deck_seed=deck_seed)
            runs.append(run_result)

            # Play the same deck with each AI
            for ai_name, factory in ai_factories.items():
                # Create team of AI players
                num_players = self._start_position.settings.num_players
                players = [factory(i) for i in range(num_players)]
                team = PlayerTeam(players)

                # Play game
                game_result = run_field._play_game_with_team(
                    team, save_record=save_records, experiment_id=experiment_id, run_id=run_id, ai_name=ai_name
                )
                run_result.ai_results[ai_name] = game_result

                # Collect statistics
                all_scores[ai_name].append(game_result.score)
                all_moves[ai_name].append(game_result.moves_count)
                all_durations[ai_name].append(game_result.duration_seconds)
                if 25 == game_result.score:
                    wins[ai_name] += 1

        # Calculate aggregated statistics
        summary: Dict[str, AIStatistics] = {}
        for ai_name in ai_factories.keys():
            scores = all_scores[ai_name]
            if scores:
                summary[ai_name] = AIStatistics(
                    games_played=len(scores),
                    average_score=statistics.mean(scores),
                    best_score=max(scores),
                    worst_score=min(scores),
                    win_rate=wins[ai_name] / len(scores) if scores else 0.0,
                    std_dev=statistics.stdev(scores) if len(scores) > 1 else 0.0,
                    average_moves=statistics.mean(all_moves[ai_name]),
                    average_duration=statistics.mean(all_durations[ai_name]),
                )

        return ExperimentResults(
            experiment_id=experiment_id, settings=settings_dict, num_runs=num_runs, runs=runs, summary=summary
        )

    def save_settings(self, experiment_id: str, settings: GameSettings) -> str:
        """
        Save experiment settings to settings.yaml in the experiment directory.

        Args:
            experiment_id: The experiment identifier
            settings: The game settings

        Returns:
            The path where settings were saved
        """
        experiment_dir = self._get_experiment_dir(experiment_id)
        filepath = os.path.join(experiment_dir, "settings.yaml" if YAML_AVAILABLE else "settings.json")

        # Convert settings to dict
        settings_dict = {
            "num_players": settings.num_players,
            "max_live_tokens": settings.max_live_tokens,
            "max_hint_tokens": settings.max_hint_tokens,
            "max_cards_in_hand": settings.max_cards_in_hand,
        }

        with open(filepath, "w") as f:
            if YAML_AVAILABLE:
                yaml.dump(settings_dict, f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(settings_dict, f, indent=2)

        return filepath

    def save_statistics(self, results: ExperimentResults, filename: Optional[str] = None) -> str:
        """
        Save experiment statistics to a file in the experiment directory.

        Args:
            results: The experiment results to save
            filename: Optional filename (defaults to "statistics.yaml" or "statistics.json")

        Returns:
            The path where statistics were saved
        """
        # Get experiment directory
        experiment_dir = self._get_experiment_dir(results.experiment_id)

        if filename is None:
            filename = "statistics.yaml" if YAML_AVAILABLE else "statistics.json"

        if os.path.isabs(filename):
            # If absolute path, use as-is
            filepath = filename
        else:
            # If relative path, save in experiment directory
            filepath = os.path.join(experiment_dir, filename)

        # Convert to dict for serialization
        data = asdict(results)

        with open(filepath, "w") as f:
            if YAML_AVAILABLE:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(data, f, indent=2)

        return filepath

    def __repr__(self) -> str:
        return f"GameField(start_position={self._start_position}, games={len(self._games)})"
