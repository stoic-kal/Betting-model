import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from pipeline import dataset_append


class DatasetAppendDedupTests(unittest.TestCase):
    def test_resolver_recovers_ids_when_legacy_file_has_no_game_pk_column(self):
        frame = pd.DataFrame([
            {"date": "2026-04-13", "home_team": "NYY", "away_team": "CLE",
             "home_sp_name": "Schmidt", "away_sp_name": "Carrasco"},
        ])
        truth = SimpleNamespace(
            game_pk=202, game_date="2026-04-13", home_team="NYY", away_team="CLE",
            home_sp_name="Schmidt", away_sp_name="Carrasco", game_type="R",
        )

        with patch.object(dataset_append, "_game_index_lookups",
                          return_value=({202: truth}, {"2026-04-13|NYY|CLE": 202})):
            cleaned, report = dataset_append.resolve_dataset(frame)

        self.assertEqual(int(cleaned.iloc[0]["game_pk"]), 202)
        self.assertEqual(report["recovered_game_pks"], 1)

    def test_existing_identity_uses_game_pk_and_preserves_doubleheaders(self):
        existing = pd.DataFrame([
            {"date": "2026-07-01", "game_pk": 101, "home_team": "CHC", "away_team": "STL"},
            {"date": "2026-07-02", "game_pk": pd.NA, "home_team": "BOS", "away_team": "NYY"},
        ])

        game_pks, legacy_matchups = dataset_append.load_existing_identities(existing)

        self.assertEqual(game_pks, {101})
        self.assertNotIn(("2026-07-01", "CHC", "STL"), legacy_matchups)
        self.assertIn(("2026-07-02", "BOS", "NYY"), legacy_matchups)
        self.assertNotIn(102, game_pks)  # a second CHC/STL game remains eligible

    def test_resolver_prefers_row_matching_actual_starters(self):
        frame = pd.DataFrame([
            {"date": "2026-04-13", "game_pk": 202, "home_team": "NYY", "away_team": "CLE",
             "home_sp_name": "Wrong Home", "away_sp_name": "Wrong Away", "feature": 1.0},
            {"date": "2026-04-13", "game_pk": 202, "home_team": "NYY", "away_team": "CLE",
             "home_sp_name": "Schmidt", "away_sp_name": "Carrasco", "feature": 2.0},
        ])
        truth = SimpleNamespace(
            game_pk=202, game_date="2026-04-13", home_team="NYY", away_team="CLE",
            home_sp_name="Schmidt", away_sp_name="Carrasco", game_type="R",
        )

        with patch.object(dataset_append, "_game_index_lookups", return_value=({202: truth}, {})):
            cleaned, report = dataset_append.resolve_dataset(frame)

        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned.iloc[0]["feature"], 2.0)
        self.assertEqual(report["duplicate_rows_removed"], 1)
        self.assertEqual(report["duplicates_resolved_by_statcast_starters"], 1)

    def test_resolver_excludes_exhibition_games(self):
        frame = pd.DataFrame([
            {"date": "2026-03-10", "game_pk": 303, "home_team": "SEA", "away_team": "SD",
             "home_sp_name": "Home", "away_sp_name": "Away"},
        ])
        truth = SimpleNamespace(
            game_pk=303, game_date="2026-03-10", home_team="SEA", away_team="SD",
            home_sp_name="Home", away_sp_name="Away",
            game_type=next(iter(dataset_append.EXHIBITION_GAME_TYPES)),
        )

        with patch.object(dataset_append, "_game_index_lookups", return_value=({303: truth}, {})):
            cleaned, report = dataset_append.resolve_dataset(frame)

        self.assertTrue(cleaned.empty)
        self.assertEqual(report["exhibition_rows_removed"], 1)


if __name__ == "__main__":
    unittest.main()
