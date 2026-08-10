import sys
import time

import schedule

sys.path.insert(0, "src")

from datetime import datetime

from track_picks import PickTracker
from update_results import ResultsUpdater


class ProductionRunner:

    def __init__(self):
        self.tracker = PickTracker()
        self.updater = ResultsUpdater()

    def daily_picks(self):

        print(f"\n{'='*80}")
        print(f"DAILY PICK GENERATION: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

        try:
            from services.pick_service import generate_picks

            result = generate_picks()
            if result.get("status") != "success":
                print(f"{result.get('message', 'No predictions available today')}")
                return
            print(f"Generated {result['moneyline_count']} Moneyline picks")
            print(f"Generated {result['totals_count']} Totals picks")
            if result.get("unavailable"):
                print(
                    f" {len(result['unavailable'])} games lacked complete markets or were locked"
                )

        except Exception as e:
            print(f"Error generating picks: {e}")

    def daily_results_update(self):

        print(f"\n{'='*80}")
        print(f"DAILY RESULTS UPDATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

        try:
            from config import today_et

            self.updater.update_pending_results(today_et())

            stats = self.tracker.get_stats()
            print(f"\nUpdated Performance:")
            print(f"   Wins: {stats['wins']}")
            print(f"   Losses: {stats['losses']}")
            print(f"   Win rate: {stats['win_rate']:.1f}%")
            print(f"   Profit/Loss: ${stats['total_profit']:.2f}")
            print(f"   ROI: {stats['roi']:.1f}%\n")

        except Exception as e:
            print(f"Error updating results: {e}")

    def run(self):

        print("PRODUCTION RUNNER STARTED\n")

        schedule.every().day.at("02:00").do(self.daily_results_update)
        schedule.every(1).minutes.do(self.automation_tick)

        print("⏰ Scheduled tasks:")
        print("   Automatic forecast stages - morning / lineup / final lock")
        print("   02:00 AM - Update yesterday's results\n")
        print("   Every minute - live results + guarded pregame CLV\n")
        print("   09:00 / 12:00 / 15:00 - timestamped market snapshots\n")

        while True:
            schedule.run_pending()
            time.sleep(60)

    def automation_tick(self):

        try:
            from services.automation_service import run_automation_tick

            return run_automation_tick()
        except Exception as exc:
            print(f"Automation tick failed: {exc}")


if __name__ == "__main__":
    runner = ProductionRunner()
    runner.run()
