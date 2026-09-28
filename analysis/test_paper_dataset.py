"""Read the exported CSVs independently and reconcile them with frozen records."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets/hanabi-500-games"


class PaperDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(ROOT / "analysis/reviewer-stats-2026-09-12/evidence.json.gz", "rt") as f:
            cls.source = json.load(f)
        with (DATASET / "games.csv").open(newline="") as f:
            cls.rows = list(csv.DictReader(f))

    def test_all_source_games_preserved(self):
        source = {(g["strategy"], g["players"], g["seed"]): g for g in self.source["games"]}
        self.assertEqual(len(self.rows), 3500)
        keys = set()
        for row in self.rows:
            key = (row["strategy"], int(row["players"]), int(row["seed"]))
            self.assertNotIn(key, keys)
            keys.add(key)
            g = source[key]
            for field in ("paper_score", "raw_score", "lives_remaining", "playable_cards_left"):
                self.assertEqual(int(row[field]), g[field])
            self.assertEqual(row["category"], g["category"])
            self.assertEqual(int(row["moves"]), len(g["turns"]))
            self.assertEqual(sum(int(row[k]) for k in ("hints", "plays", "discards")), len(g["turns"]))
        self.assertEqual(keys, set(source))

    def test_split_files_and_checksums(self):
        manifest = json.loads((DATASET / "manifest.json").read_text())
        self.assertEqual(manifest["games"], len(self.rows))
        self.assertEqual(manifest["moves"], sum(int(r["moves"]) for r in self.rows))
        self.assertEqual(hashlib.sha256((ROOT / manifest["source"]["path"]).read_bytes()).hexdigest(),
                         manifest["source"]["sha256"])
        combined = []
        for name, metadata in manifest["files"].items():
            self.assertEqual(hashlib.sha256((DATASET / name).read_bytes()).hexdigest(), metadata["sha256"])
            with (DATASET / name).open(newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), metadata["rows"])
            if name not in ("games.csv", "summary.csv"):
                self.assertEqual(len(rows), 500)
                self.assertEqual({int(r["seed"]) for r in rows}, set(range(42, 542)))
                combined.extend(rows)
        self.assertEqual(sorted(combined, key=lambda r: r["game_id"]),
                         sorted(self.rows, key=lambda r: r["game_id"]))


if __name__ == "__main__":
    unittest.main()
