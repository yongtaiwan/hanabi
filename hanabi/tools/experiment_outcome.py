"""
Replay experiment game records and classify outcomes (perfect vs cheater baseline vs AI gap).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

from hanabi.core.enums import CardKind, Number
from hanabi.core.game import Game, GameSettings
from hanabi.core.game_field import ExperimentResults
from hanabi.core.game_history import GameHistory
from hanabi.core.moves import Discard, Move, Play
from hanabi.core.player import HumanPlayer, PlayerTeam

OutcomeCode = Literal["perfect", "2.1", "2.2", "2.3", "2.4", "3.1", "3.2", "3.3", "3.4"]

OUTCOME_CODES_ORDER: Tuple[OutcomeCode, ...] = (
    "perfect",
    "2.1",
    "2.2",
    "2.3",
    "2.4",
    "3.1",
    "3.2",
    "3.3",
    "3.4",
)

# Concise labels for reports (internal keys remain 2.1–3.4 in code). "Baseline" = cheater replay.
OUTCOME_CODE_DESCRIPTIONS: Dict[str, str] = {
    "perfect": "Max score",
    "2.1": "Both < max — baseline: all lives lost + critical lost",
    "2.2": "Both < max — baseline: all lives lost, no critical lost",
    "2.3": "Both < max — baseline: critical lost, lives remain",
    "2.4": "Both < max — baseline: tempo (no critical, lives remain)",
    "3.1": "Baseline max — subject: all lives lost + critical lost",
    "3.2": "Baseline max — subject: all lives lost, no critical lost",
    "3.3": "Baseline max — subject: critical lost, lives remain",
    "3.4": "Baseline max — subject: tempo (no critical, lives remain)",
}


def outcome_code_description(code: str) -> str:
    """Short outcome label for ``code`` (defaults to ``code`` if unknown)."""
    return OUTCOME_CODE_DESCRIPTIONS.get(code, code)


def top_non_perfect_reason_summary(rows: List[Dict[str, Any]]) -> Optional[str]:
    """
    One-line summary of the most frequent non-perfect outcome (for experiment reports).

    ``rows`` must match the ``outcomes`` list from :func:`outcome_breakdown_to_yaml_dict`
    (nonzero counts only). Returns ``None`` when every game was a max score.
    """
    non_perfect = [r for r in rows if "perfect" != r.get("code")]
    if not non_perfect:
        return None
    max_count = max(int(r["count"]) for r in non_perfect)
    top = [r for r in non_perfect if int(r["count"]) == max_count]
    order = {c: i for i, c in enumerate(OUTCOME_CODES_ORDER)}
    top.sort(key=lambda r: order.get(str(r.get("code")), 99))
    if 1 == len(top):
        return f"{top[0]['description']} ({max_count} games)"
    joined = "; ".join(str(r["description"]) for r in top)
    return f"Tied at {max_count} games: {joined}"


def perfect_score_total(settings: GameSettings) -> int:
    """Maximum score when every color reaches rank five."""
    return 5 * len(settings.cards)


def load_history_file(path: str) -> Dict[str, Any]:
    """Load a YAML/JSON game record using :class:`GameHistory` path resolution."""
    return GameHistory({}).load_from_file(path)


@dataclass(frozen=True)
class ReplaySummary:
    """Result of replaying one saved game."""

    score: int
    perfect: bool
    lost_all_lives: bool
    lost_critical: bool
    end_reason: str


def _play_would_succeed(game: Game, player_index: int, card_index: int) -> bool:
    state = game.state
    hand = state.player_hands[player_index]
    card = hand.cards[card_index]
    cards_played = state.common_view.cards_played
    if card.color not in cards_played:
        return Number.ONE == card.number
    return card.number.value == cards_played[card.color].value + 1


def _maybe_mark_lost_critical_before_move(game: Game, player_index: int, move: Move) -> bool:
    """
    Return True if this discard or failing play removes a card that was CRITICAL
    (per :meth:`CommonView.card_kind`) immediately before the move.
    """
    state = game.state
    settings = game.settings
    cv = state.common_view
    if isinstance(move, Discard):
        card = state.player_hands[player_index].cards[move.card]
        return CardKind.CRITICAL == cv.card_kind(card, settings)
    if isinstance(move, Play):
        if _play_would_succeed(game, player_index, move.card):
            return False
        card = state.player_hands[player_index].cards[move.card]
        return CardKind.CRITICAL == cv.card_kind(card, settings)
    return False


def compute_end_reason(game: Game) -> str:
    """Align with experiment tooling: lives, perfect target from settings, deck, optional auto-end."""
    state = game.state
    final_score = game.get_score()
    target = perfect_score_total(game.settings)
    if state.common_view.live_tokens <= 0:
        return "lives_lost"
    if final_score == target:
        return "perfect_score"
    if 0 == state.turns_left:
        return "deck_exhausted"
    if game.settings.auto_end_when_no_points_possible and state._is_no_more_points_possible():
        return "no_points_possible"
    return "unknown"


def replay_summary(history_data: Dict[str, Any]) -> ReplaySummary:
    """
    Reconstruct a game from ``history_data`` and apply recorded moves with a HumanPlayer team.

    Tracks whether the team ever discarded (or misplayed) a CRITICAL card and how the game ended.
    """
    moves: List[str] = history_data.get("moves", [])
    settings = GameHistory.settings_from_history_dict(history_data)
    n = settings.num_players
    team = PlayerTeam([HumanPlayer(i) for i in range(n)])
    game = GameHistory.create_game_from_history(history_data, team)

    lost_critical = False
    for move_str in moves:
        current_player = game.state.current_player
        move = GameHistory._short_to_move(move_str, current_player, game)
        assert move is not None, f"replay: could not parse move {move_str!r}"
        if _maybe_mark_lost_critical_before_move(game, current_player, move):
            lost_critical = True
        game.process_move(current_player, move)
        game._advance_turn()

    assert game.is_finished, "replay: moves ended before game.is_finished"
    state = game.state
    score = game.get_score()
    target = perfect_score_total(settings)
    perfect = score == target
    lost_all_lives = state.common_view.live_tokens <= 0
    end_reason = compute_end_reason(game)

    if "no_points_possible" == end_reason:
        assert 0 < state.common_view.live_tokens, "auto-end implies lives remain"
        assert lost_critical, "no_points_possible implies critical loss on the path"

    recorded = history_data.get("final_score")
    if recorded is not None:
        assert recorded == score, f"replay final_score {recorded} != recomputed {score}"

    return ReplaySummary(
        score=score,
        perfect=perfect,
        lost_all_lives=lost_all_lives,
        lost_critical=lost_critical,
        end_reason=end_reason,
    )


def _sub_index(summary: ReplaySummary) -> int:
    if summary.lost_all_lives and summary.lost_critical:
        return 1
    if summary.lost_all_lives and not summary.lost_critical:
        return 2
    if not summary.lost_all_lives and summary.lost_critical:
        return 3
    return 4


def classify_experiment_pair(
    ai: ReplaySummary,
    cheater: ReplaySummary,
    *,
    perfect_target: int,
) -> OutcomeCode:
    """
    Mutually exclusive outcome for one run (same deck) comparing AI vs all-cheater baseline.

    Category 2 subcodes use the cheater replay; category 3 subcodes use the AI replay.
    """
    assert ai.score <= perfect_target
    assert cheater.score <= perfect_target

    if ai.score == perfect_target:
        return "perfect"

    if cheater.score < perfect_target:
        bucket2: Tuple[OutcomeCode, ...] = ("2.1", "2.2", "2.3", "2.4")
        s = _sub_index(cheater)
        if 4 == s:
            assert not cheater.lost_all_lives and not cheater.lost_critical
        return bucket2[s - 1]

    bucket3: Tuple[OutcomeCode, ...] = ("3.1", "3.2", "3.3", "3.4")
    s = _sub_index(ai)
    if 4 == s:
        assert not ai.lost_all_lives and not ai.lost_critical
    return bucket3[s - 1]


def classify_pair_from_history_files(ai_path: str, cheater_path: str) -> OutcomeCode:
    """Load two record files (same run, different AI) and return the outcome code."""
    ai_data = load_history_file(ai_path)
    cheater_data = load_history_file(cheater_path)
    return classify_pair_from_histories(ai_data, cheater_data)


def classify_pair_from_histories(ai_data: Dict[str, Any], cheater_data: Dict[str, Any]) -> OutcomeCode:
    assert ai_data.get("deck") == cheater_data.get("deck"), "paired histories must share the same deck"
    assert ai_data.get("settings") == cheater_data.get("settings"), "paired histories must share the same settings"
    settings = GameHistory.settings_from_history_dict(ai_data)
    target = perfect_score_total(settings)
    return classify_experiment_pair(
        replay_summary(ai_data),
        replay_summary(cheater_data),
        perfect_target=target,
    )


@dataclass(frozen=True)
class OutcomeRunRef:
    """One run classified against the baseline AI, with paths to both saved replays."""

    run_id: int
    subject_record_path: str
    baseline_record_path: str


@dataclass(frozen=True)
class OutcomeBreakdown:
    """Per-subject counts and non-perfect run paths vs a baseline (typically CommonSenseCheater)."""

    subject_ai: str
    baseline_ai: str
    counts: Dict[str, int]
    non_perfect_runs: Dict[str, List[OutcomeRunRef]]


def outcome_breakdown_vs_baseline(
    results: ExperimentResults,
    *,
    subject_ai: str,
    baseline_ai: str = "CommonSenseCheater",
) -> Optional[OutcomeBreakdown]:
    """
    Classify each run for ``subject_ai`` vs ``baseline_ai`` using saved game records.

    Returns ``None`` if either AI name is missing from the experiment (e.g. cheater not in ``--ais``).
    Requires each :class:`~hanabi.core.game_field.GameResult` to have ``game_record_path`` set.
    """
    if subject_ai == baseline_ai:
        return None
    if baseline_ai not in results.summary or subject_ai not in results.summary:
        return None

    counts: Dict[str, int] = {c: 0 for c in OUTCOME_CODES_ORDER}
    non_perfect: Dict[str, List[OutcomeRunRef]] = {}

    for run in results.runs:
        sub = run.ai_results.get(subject_ai)
        base = run.ai_results.get(baseline_ai)
        assert sub is not None, f"run {run.run_id}: missing results for subject {subject_ai!r}"
        assert base is not None, f"run {run.run_id}: missing results for baseline {baseline_ai!r}"
        sp, bp = sub.game_record_path, base.game_record_path
        assert sp is not None and bp is not None, (
            f"run {run.run_id}: need game_record_path for {subject_ai!r} and {baseline_ai!r} (enable save_records)"
        )
        code: OutcomeCode = classify_pair_from_history_files(sp, bp)
        counts[code] += 1
        if "perfect" != code:
            non_perfect.setdefault(code, []).append(OutcomeRunRef(run.run_id, sp, bp))

    return OutcomeBreakdown(
        subject_ai=subject_ai,
        baseline_ai=baseline_ai,
        counts=counts,
        non_perfect_runs=non_perfect,
    )


def build_experiment_outcome_categories_payload(
    results: ExperimentResults,
    *,
    baseline_ai: str = "CommonSenseCheater",
) -> Optional[Dict[str, Any]]:
    """
    Build a nested dict for ``outcome_categories.yaml`` (all non-baseline AIs vs ``baseline_ai``).

    Returns ``None`` if ``baseline_ai`` did not run or no other subjects produced a breakdown.
    """
    if baseline_ai not in results.summary:
        return None
    subjects: Dict[str, Any] = {}
    for subject_ai in sorted(results.summary.keys()):
        if subject_ai == baseline_ai:
            continue
        bd = outcome_breakdown_vs_baseline(results, subject_ai=subject_ai, baseline_ai=baseline_ai)
        if bd is None:
            continue
        subjects[subject_ai] = outcome_breakdown_to_yaml_dict(bd)
    if not subjects:
        return None
    return {"baseline": baseline_ai, "subjects": subjects}


def outcome_breakdown_to_yaml_dict(breakdown: OutcomeBreakdown) -> Dict[str, Any]:
    """Structure suitable for YAML/JSON: one row per nonzero outcome with description and optional game numbers."""
    rows: List[Dict[str, Any]] = []
    for code in OUTCOME_CODES_ORDER:
        count = breakdown.counts[code]
        if 0 == count:
            continue
        row: Dict[str, Any] = {
            "code": code,
            "description": OUTCOME_CODE_DESCRIPTIONS[code],
            "count": count,
        }
        if "perfect" != code:
            refs = breakdown.non_perfect_runs.get(code, [])
            row["game_numbers"] = sorted(r.run_id for r in refs)
        rows.append(row)
    return {
        "subject_ai": breakdown.subject_ai,
        "baseline_ai": breakdown.baseline_ai,
        "outcomes": rows,
        "top_non_perfect_reason": top_non_perfect_reason_summary(rows),
    }
