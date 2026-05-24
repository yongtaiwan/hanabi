"""
Summarize 4p mini-rec imperfect games from experiment statistics + game records.

Usage (from repo root):
    python3 tools/analyze_4p_losses.py [statistics.json]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]


def _move_mix(moves: List[str]) -> Dict[str, float]:
    hints = sum(1 for m in moves if m.startswith("h"))
    plays = sum(1 for m in moves if m.startswith("p"))
    discards = sum(1 for m in moves if m.startswith("d"))
    total = hints + plays + discards
    return {
        "hints": hints,
        "plays": plays,
        "discards": discards,
        "total": total,
        "hint_frac": hints / total if total else 0.0,
    }


def _load_rows(stats: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    perfect: List[Dict[str, Any]] = []
    imperfect: List[Dict[str, Any]] = []
    for run in stats["runs"]:
        ar = run["ai_results"]["FourPlayerRecommendationPlayer"]
        record_path = REPO_ROOT / ar["game_record_path"]
        record = json.loads(record_path.read_text())
        mix = _move_mix(record["moves"])
        row = {
            "score": record["final_score"],
            "missing": 25 - record["final_score"],
            "end_reason": ar["end_reason"],
            **mix,
        }
        if 25 == row["score"]:
            perfect.append(row)
        else:
            imperfect.append(row)
    return perfect, imperfect


def main() -> None:
    stats_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        REPO_ROOT / "game_records/exp_ai_comparison/20260510_200124/4p/statistics.json"
    )
    if not stats_path.is_file():
        print(f"Missing {stats_path}")
        sys.exit(1)

    stats = json.loads(stats_path.read_text())
    perfect, imperfect = _load_rows(stats)
    n_imp = len(imperfect)

    print(f"Experiment: {stats['experiment_id']}")
    print(f"Games: {len(perfect) + n_imp}  perfect: {len(perfect)}  imperfect: {n_imp}")
    print(f"End reasons (all): {dict(Counter(r['end_reason'] for r in imperfect + perfect))}")
    print()

    if not imperfect:
        return

    print("Points short of 25:", dict(sorted(Counter(r["missing"] for r in imperfect).items())))
    print()

    def avg(rows: List[Dict[str, Any]], key: str) -> float:
        return sum(r[key] for r in rows) / len(rows)

    print("Per-game means:")
    for key in ("hints", "plays", "discards", "total", "hint_frac"):
        print(f"  {key}: imperfect={avg(imperfect, key):.2f}  perfect={avg(perfect, key):.2f}")


if __name__ == "__main__":
    main()
