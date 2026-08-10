import sys

sys.path.insert(0, "src")
from config import today_et
from track_picks import PickTracker
from update_results import ResultsUpdater

tracker = PickTracker()
updater = ResultsUpdater()


def get_stats():

    return tracker.get_stats()


def get_recent_picks(limit=20):

    picks = tracker.get_recent_picks(limit)
    return picks.to_dict("records")


def update_results():

    try:
        updated_count = updater.update_pending_results(today_et())
        stats = tracker.get_stats()
        return {"status": "success", "updated_count": updated_count, "stats": stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}
