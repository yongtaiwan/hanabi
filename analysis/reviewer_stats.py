"""Reproduce reviewer-requested rates and outcome counts without changing any bot.

Run from the repository root: python analysis/reviewer_stats.py
The experiment uses the paper's 500 seeds (42..541). Output contains every deck,
move, end state summary and denominator, with raw and zero-on-third-error scores.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hanabi.ai.common_sense_cheater import CommonSenseCheater
from hanabi.ai.dynamic_recommendation_3p import DynamicRecommendation3P
from hanabi.ai.three_player_recommendation import ThreePlayerRecommendationPlayer
from hanabi.ai.four_player_recommendation import FourPlayerRecommendationPlayer
from hanabi.ai.five_player_recommendation import FivePlayerRecommendationPlayer
from hanabi.core.enums import CardKind
from hanabi.core.game import create_ai_simulation_game_settings
from hanabi.core.game_field import GameField
from hanabi.core.game_history import GameHistory
from hanabi.core.moves import Discard, Play
from hanabi.core.player import PlayerTeam


def outcome(perfect, lives, last_copy_lost):
    """Exclusive hierarchy, not a causal attribution of every point lost."""
    if perfect:
        return "perfect"
    if lives == 0:
        return "all_lives_lost"
    if last_copy_lost:
        return "needed_last_copy_lost"
    return "tempo"


def wilson(successes, n):
    z = 1.959963984540054
    p = successes / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return [center - half, center + half]


def play_one(n, seed, label, factory):
    settings = create_ai_simulation_game_settings(n)
    start = GameField._create_start_position(settings, seed)
    game = GameField._create_game_from_start_position(start, PlayerTeam([factory(i) for i in range(n)]))
    turns = []
    history = GameHistory({})
    last_copy_lost = False
    def on_move(player, move, old, new):
        nonlocal last_copy_lost
        failed = new.common_view.live_tokens < old.common_view.live_tokens
        removed_needed = False
        if isinstance(move, Discard) or (isinstance(move, Play) and failed):
            card = old.player_hands[player].cards[move.card]
            kind = old.common_view.card_kind(card, settings)
            removed_needed = kind == CardKind.CRITICAL or (
                kind == CardKind.PLAYABLE and
                old.common_view._rank_copies_remaining_for_fireworks(card.color, card.number, settings) == 1
            )
            last_copy_lost |= removed_needed
        why = move.why() if callable(getattr(move, "why", None)) else ""
        turns.append({"player": player, "move": history._move_to_short(move),
                      "hint_tokens_before": old.common_view.hint_tokens,
                      "lives_before": old.common_view.live_tokens,
                      "failed_play": failed, "needed_last_copy_lost": removed_needed,
                      "last_resort_play": isinstance(move, Play) and "last resort" in why.lower(),
                      "why": why})
    game._on_move = on_move
    game.play()
    lives = game.state.common_view.live_tokens
    raw_score = game.get_score()
    final_score = 0 if lives == 0 else raw_score
    category = outcome(final_score == 25, lives, last_copy_lost)
    if category == "tempo":
        assert game.state.turns_left == 0, "Residual outcome is not clock exhaustion"
    playable_left = sum(game.state.common_view.card_kind(c, settings) == CardKind.PLAYABLE
                        for h in game.state.player_hands for c in h.cards)
    return {"strategy": label, "players": n, "seed": seed, "raw_score": raw_score,
            "paper_score": final_score, "lives_remaining": lives, "category": category,
            "needed_last_copy_lost": last_copy_lost, "playable_cards_left": playable_left,
            "deck": [history._card_to_short(c) for c in start.draw_deck.cards], "turns": turns}


def summarize(rows):
    groups = {}
    for r in rows:
        groups.setdefault((r["players"], r["strategy"]), []).append(r)
    output = []
    for (n, strategy), games in groups.items():
        turns = [t for g in games for t in g["turns"]]
        wins = sum(g["paper_score"] == 25 for g in games)
        scores = [g["paper_score"] for g in games]
        counts = Counter(g["category"] for g in games)
        zero_turns = sum(t["hint_tokens_before"] == 0 for t in turns)
        zero_games = sum(any(t["hint_tokens_before"] == 0 for t in g["turns"]) for g in games)
        fallback = sum(t["last_resort_play"] for t in turns)
        output.append({"players": n, "strategy": strategy, "games": len(games),
                       "wins": wins, "win_rate": wins/len(games), "win_rate_95ci": wilson(wins,len(games)),
                       "mean": statistics.mean(scores), "sd": statistics.stdev(scores),
                       "min": min(scores), "raw_mean": statistics.mean(g["raw_score"] for g in games),
                       "outcomes": dict(counts), "turns": len(turns), "zero_hint_turns": zero_turns,
                       "zero_hint_games": zero_games, "last_resort_plays": fallback,
                       "last_resort_games": sum(any(t["last_resort_play"] for t in g["turns"]) for g in games),
                       "failed_plays": sum(t["failed_play"] for t in turns),
                       "needed_last_copy_loss_games": sum(g["needed_last_copy_lost"] for g in games),
                       "all_lives_and_last_copy_loss_games": sum(g["needed_last_copy_lost"] and g["lives_remaining"]==0 for g in games),
                       "tempo_without_playable_card_in_hand": sum(g["category"]=="tempo" and g["playable_cards_left"]==0 for g in games)})
    for n in (3,4,5):
        same_n = [g for g in rows if g["players"]==n]
        baseline = {g["seed"]:g for g in same_n if g["strategy"]=="Cheater"}
        for r in output:
            if r["players"]!=n or r["strategy"]=="Cheater":
                continue
            games=groups[(n,r["strategy"])]
            for g in games:
                assert g["deck"]==baseline[g["seed"]]["deck"]
            subset=[g for g in games if g["paper_score"]<25 and baseline[g["seed"]]["paper_score"]==25]
            r["baseline_perfect_nonperfect_subject_count"]=len(subset)
            r["baseline_perfect_outcomes"]=dict(Counter(g["category"] for g in subset))
    return output


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--games",type=int,default=500)
    parser.add_argument("--output",type=Path,default=ROOT/"analysis"/"reviewer-stats-2026-09-12")
    args=parser.parse_args()
    assert args.games>1
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[]
    simple={3:ThreePlayerRecommendationPlayer,4:FourPlayerRecommendationPlayer,5:FivePlayerRecommendationPlayer}
    for n in (3,4,5):
        factories={"Simple":simple[n],"Cheater":CommonSenseCheater}
        if n==3:
            factories["Dynamic"]=DynamicRecommendation3P
        for label,factory in factories.items():
            for seed in range(42,42+args.games):
                rows.append(play_one(n,seed,label,factory))
            print(f"Finished {n}p {label}: {args.games} games",flush=True)
    summary=summarize(rows)
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    payload={"engine_commit":commit,"seed_start":42,"games_per_strategy":args.games,
             "score_rule":"0 on third error; otherwise sum of fireworks; raw_score retained",
             "settings":"standard 50-card deck; auto_end_when_no_points_possible=True",
             "summary":summary,"games":rows}
    (args.output/"evidence.json").write_text(json.dumps(payload,separators=(",",":")))
    (args.output/"summary.json").write_text(json.dumps({k:v for k,v in payload.items() if k!="games"},indent=2))
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
