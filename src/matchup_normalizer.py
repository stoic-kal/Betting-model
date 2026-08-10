import unicodedata
from difflib import SequenceMatcher


class MatchupNormalizer:

    @staticmethod
    def remove_diacritics(text):

        nfd = unicodedata.normalize("NFD", text)
        return "".join(char for char in nfd if unicodedata.category(char) != "Mn")

    @staticmethod
    def extract_team(name):

        words = name.split()
        if words:
            return words[-1].lower()
        return name.lower()

    @staticmethod
    def normalize_matchup(matchup_str):

        parts = matchup_str.split(" @ ")
        if len(parts) != 2:
            return None

        away = MatchupNormalizer.extract_team(parts[0])
        home = MatchupNormalizer.extract_team(parts[1])

        return f"{away} @ {home}"

    @staticmethod
    def fuzzy_match(name1, name2, threshold=0.85):

        ratio = SequenceMatcher(None, name1, name2).ratio()
        return ratio >= threshold

    @staticmethod
    def find_best_match(db_matchup, api_matchups):

        norm_db = MatchupNormalizer.normalize_matchup(db_matchup)

        if not norm_db:
            return None

        for api_matchup in api_matchups:
            norm_api = MatchupNormalizer.normalize_matchup(api_matchup)
            if norm_db == norm_api:
                return api_matchup

        for api_matchup in api_matchups:
            norm_api = MatchupNormalizer.normalize_matchup(api_matchup)
            if MatchupNormalizer.fuzzy_match(norm_db, norm_api, threshold=0.8):
                return api_matchup

        return None
