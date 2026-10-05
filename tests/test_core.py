import unittest

from src.decks import is_land_type_line
from src.clustering import shared_slots, build_similarity_matrix, transitive_clusters
from src.profiles import parse_color_prefix, canonical_color_name, infer_raw_colors
from src.vv_crawler import _parse_full_result_text, parse_record


class CoreTests(unittest.TestCase):
    def test_land_detection(self):
        self.assertTrue(is_land_type_line("Basic Land — Island"))
        self.assertTrue(is_land_type_line("Artifact Land"))
        self.assertFalse(is_land_type_line("Creature — Island Fish"))

    def test_shared_slots_counts_copies(self):
        a = {"Bolt": 4, "Brainstorm": 4, "Ponder": 3}
        b = {"Bolt": 4, "Brainstorm": 3, "Ponder": 4}
        self.assertEqual(shared_slots(a, b), 10)

    def test_transitive_clustering(self):
        decks = {
            "A": {"nonlands": {"x": 2}},
            "B": {"nonlands": {"x": 2, "y": 2}},
            "C": {"nonlands": {"y": 2}},
        }
        sims = build_similarity_matrix(decks)
        clusters = transitive_clusters(decks.keys(), sims, threshold=2)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0], frozenset({"A", "B", "C"}))

    def test_color_alias(self):
        colors, stem = parse_color_prefix("UW Affinity")
        self.assertEqual(colors, {"W", "U"})
        self.assertEqual(stem, "Affinity")
        self.assertEqual(canonical_color_name(colors), "Azorius")

    def test_color_inference_uses_mana_base_not_split_spell_colors(self):
        import json
        import tempfile
        from pathlib import Path

        payload = {
            "mainboard": {
                "Island": {
                    "quantity": 18,
                    "card": {
                        "name": "Island",
                        "type_line": "Basic Land — Island",
                        "produced_mana": ["U"],
                        "color_identity": ["U"],
                    },
                },
                "Mystic Sanctuary": {
                    "quantity": 1,
                    "card": {
                        "name": "Mystic Sanctuary",
                        "type_line": "Land — Island",
                        "produced_mana": ["U"],
                        "color_identity": ["U"],
                    },
                },
                "Expansion // Explosion": {
                    "quantity": 1,
                    "card": {
                        "name": "Expansion // Explosion",
                        "type_line": "Instant // Instant",
                        "colors": ["U", "R"],
                        "color_identity": ["U", "R"],
                    },
                },
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(infer_raw_colors(path), {"U"})

    def test_small_real_splash_is_kept(self):
        import json
        import tempfile
        from pathlib import Path

        payload = {
            "mainboard": {
                "Island": {
                    "quantity": 16,
                    "card": {
                        "name": "Island",
                        "type_line": "Basic Land — Island",
                        "produced_mana": ["U"],
                    },
                },
                "Steam Vents": {
                    "quantity": 4,
                    "card": {
                        "name": "Steam Vents",
                        "type_line": "Land — Island Mountain",
                        "produced_mana": ["U", "R"],
                    },
                },
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(infer_raw_colors(path), {"U", "R"})

    def test_paper_result_without_player(self):
        parsed = _parse_full_result_text("1st Burn (2-0)", "", 1)
        self.assertEqual(parsed, (1, "", "2-0", "Burn"))

    def test_paper_result_without_placement(self):
        parsed = _parse_full_result_text("Benji L (2-0-1) Merfolk", "", 4)
        self.assertEqual(parsed, (4, "Benji L", "2-0-1", "Merfolk"))

    def test_colon_period_and_slash_record_formats(self):
        self.assertEqual(
            _parse_full_result_text("1st: Michael S. (4/0) Infect", "", 1),
            (1, "Michael S.", "4/0", "Infect"),
        )
        self.assertEqual(
            _parse_full_result_text("6th. Jacob W. (2/1/1) Gruul Mid", "", 1),
            (6, "Jacob W.", "2/1/1", "Gruul Mid"),
        )
        self.assertEqual(parse_record("2/1/1"), (2, 1, 1))


if __name__ == "__main__":
    unittest.main()
