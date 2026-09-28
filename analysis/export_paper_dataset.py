"""Export the frozen paper evidence as deterministic, documented CSV datasets."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "analysis/reviewer-stats-2026-09-12/evidence.json.gz"
DEST = ROOT / "datasets/hanabi-500-games"
GROUPS = [("Simple", 3), ("Simple", 4), ("Simple", 5), ("Dynamic", 3),
          ("Cheater", 3), ("Cheater", 4), ("Cheater", 5)]
FIELDS = ["game_id", "strategy", "players", "seed", "paper_score", "raw_score",
          "perfect_game", "lives_remaining", "category", "needed_last_copy_lost",
          "playable_cards_left", "moves", "hints", "plays", "discards",
          "failed_plays", "zero_hint_moves", "last_resort_plays", "deck_sha256"]
SUMMARY_FIELDS = ["strategy", "players", "games", "mean_score", "sample_sd",
                  "min_score", "max_score", "perfect_games", "perfect_game_rate",
                  "perfect", "all_lives_lost", "needed_last_copy_lost", "tempo"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def csv_bytes(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def build():
    compressed = SOURCE.read_bytes()
    evidence = json.loads(gzip.decompress(compressed))
    games = evidence["games"]
    assert len(games) == 3500
    assert {(g["strategy"], g["players"]) for g in games} == set(GROUPS)
    summary_source = {(r["strategy"], r["players"]): r for r in evidence["summary"]}
    rows, summaries, files, decks = [], [], {}, {}
    card_counts = Counter(c + str(rank) for c in "RYGBW" for rank, count in
                          [(1, 3), (2, 2), (3, 2), (4, 2), (5, 1)] for _ in range(count))
    for strategy, players in GROUPS:
        group = sorted((g for g in games if (g["strategy"], g["players"]) ==
                        (strategy, players)), key=lambda g: g["seed"])
        assert [g["seed"] for g in group] == list(range(42, 542))
        exported = []
        for g in group:
            assert Counter(g["deck"]) == card_counts
            key = (players, g["seed"])
            assert key not in decks or decks[key] == g["deck"]
            decks[key] = g["deck"]
            score = g["paper_score"]
            assert 0 <= score <= 25 and 0 <= g["raw_score"] <= 25
            assert score == (0 if g["lives_remaining"] == 0 else g["raw_score"])
            category = ("perfect" if score == 25 else "all_lives_lost"
                        if g["lives_remaining"] == 0 else "needed_last_copy_lost"
                        if g["needed_last_copy_lost"] else "tempo")
            assert g["category"] == category
            turns = g["turns"]
            counts = Counter(t["move"][0] for t in turns)
            assert set(counts) <= {"h", "p", "d"}
            assert all(0 <= t["player"] < players and 0 <= t["hint_tokens_before"] <= 8
                       and 1 <= t["lives_before"] <= 3 for t in turns)
            row = {k: g[k] for k in ["strategy", "players", "seed", "paper_score",
                   "raw_score", "lives_remaining", "category", "playable_cards_left"]}
            row.update(game_id=f"{strategy.lower()}-{players}p-{g['seed']}",
                       perfect_game=int(score == 25),
                       needed_last_copy_lost=int(g["needed_last_copy_lost"]),
                       moves=len(turns), hints=counts["h"], plays=counts["p"], discards=counts["d"],
                       failed_plays=sum(t["failed_play"] for t in turns),
                       zero_hint_moves=sum(t["hint_tokens_before"] == 0 for t in turns),
                       last_resort_plays=sum(t["last_resort_play"] for t in turns),
                       deck_sha256=digest(" ".join(g["deck"]).encode("ascii")))
            assert row["failed_plays"] == 3 - row["lives_remaining"]
            exported.append(row)
        scores = [g["paper_score"] for g in group]
        outcomes = Counter(g["category"] for g in group)
        reference = summary_source[(strategy, players)]
        mean, sd = statistics.mean(scores), statistics.stdev(scores)
        assert abs(mean - reference["mean"]) < 1e-12
        assert abs(sd - reference["sd"]) < 1e-12
        assert dict(outcomes) == reference["outcomes"]
        assert outcomes["perfect"] == reference["wins"]
        summaries.append(dict(strategy=strategy, players=players, games=len(group),
                              mean_score=mean, sample_sd=sd, min_score=min(scores),
                              max_score=max(scores), perfect_games=outcomes["perfect"],
                              perfect_game_rate=outcomes["perfect"] / len(group),
                              **{k: outcomes[k] for k in
                                 ["perfect", "all_lives_lost", "needed_last_copy_lost", "tempo"]}))
        files[f"{strategy.lower()}-{players}p.csv"] = csv_bytes(exported, FIELDS)
        rows.extend(exported)
    assert len({r["game_id"] for r in rows}) == 3500
    files["games.csv"] = csv_bytes(rows, FIELDS)
    files["summary.csv"] = csv_bytes(summaries, SUMMARY_FIELDS)
    manifest = {
        "dataset": "Hanabi paper simulations: 500 games per bot configuration",
        "schema_version": "1.0.0", "frozen_run": "2026-09-12",
        "games": len(rows), "moves": sum(r["moves"] for r in rows),
        "games_per_configuration": 500, "seed_start": 42, "seed_end_inclusive": 541,
        "engine_commit": evidence["engine_commit"],
        "evidence_commit": "b041097a1c64086460a9b54f11a02e2310ba545a",
        "score_rule": evidence["score_rule"], "settings": evidence["settings"],
        "source": {"path": str(SOURCE.relative_to(ROOT)), "sha256": digest(compressed)},
        "files": {name: {"sha256": digest(content),
                         "rows": len(list(csv.DictReader(io.StringIO(content.decode()))))}
                  for name, content in sorted(files.items())},
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without writing files")
    args = parser.parse_args()
    files = build()
    if args.check:
        for name, expected in files.items():
            assert (DEST / name).read_bytes() == expected, f"Dataset differs: {name}"
    else:
        DEST.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (DEST / name).write_bytes(content)
    print(f"{'Verified' if args.check else 'Exported'} 3,500 games across 7 configurations; "
          "500 distinct seeds each. Frozen scores, outcomes and paired decks agree.")


if __name__ == "__main__":
    main()
