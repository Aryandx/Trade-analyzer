"""
Auto-push daemon — keeps the website live throughout the trading day.

Every 5 minutes:
  - Re-scores all stocks using cached data + live sector momentum
  - If picks changed, writes morning_picks.json and git pushes (triggers Vercel redeploy)
  - Shows a live status line in the terminal

Run once and leave it:
  python auto_push.py

Ctrl+C to stop.
"""

import os
import sys
import time
import json
import subprocess
import warnings
from datetime import datetime, date

warnings.filterwarnings("ignore")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
WEBAPP_PICKS     = os.path.join(BASE_DIR, "webapp", "public", "data", "morning_picks.json")
WEEKLY_LOG_PATH  = os.path.join(BASE_DIR, "results", "weekly_pnl.json")
INTERVAL_SEC     = 300   # 5 minutes

# Import scanner internals directly to avoid subprocess overhead
sys.path.insert(0, BASE_DIR)


def _load_weekly() -> dict:
    try:
        with open(WEEKLY_LOG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"goal": 4000, "entries": []}


def _picks_changed(new_picks: list, old_path: str) -> bool:
    """True if top symbols differ from last push."""
    try:
        with open(old_path) as f:
            old = json.load(f)
        old_syms = [p["symbol"] for p in old.get("picks", [])]
        new_syms = [p["symbol"] for p in new_picks]
        return old_syms != new_syms
    except Exception:
        return True


def _git_push(picks: list, capital: int) -> bool:
    """Write webapp JSON, commit, push. Returns True on success."""
    try:
        log   = _load_weekly()
        done  = sum(e["pnl"] for e in log.get("entries", []))
        payload = {
            "date":         date.today().isoformat(),
            "generated_at": datetime.now().isoformat(timespec="minutes"),
            "capital":      capital,
            "weekly_goal":  4000,
            "week_banked":  done,
            "week_entries": log.get("entries", []),
            "picks":        picks,
        }
        os.makedirs(os.path.dirname(WEBAPP_PICKS), exist_ok=True)
        with open(WEBAPP_PICKS, "w") as f:
            json.dump(payload, f, indent=2)

        os.chdir(BASE_DIR)
        subprocess.run(["git", "add", "webapp/public/data/morning_picks.json"],
                       check=True, capture_output=True)
        ts = datetime.now().strftime("%H:%M")
        msg = f"auto: intraday picks update {date.today()} {ts}"
        subprocess.run(["git", "commit", "-m", msg],
                       check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"],
                       check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        # Nothing changed in git — that's fine
        return False
    except Exception as e:
        print(f"  push error: {e}")
        return False


def run_scan_quiet(capital: int) -> list:
    """Run morning scanner silently, return top picks list."""
    from morning_scanner import _sector_momentum, _load_cache, _score_stock
    from config import STOCK_UNIVERSE

    sec_mom = _sector_momentum()
    results = []
    for sym in STOCK_UNIVERSE:
        df = _load_cache(sym)
        if df is None:
            continue
        r = _score_stock(sym, df, sec_mom, capital)
        if r:
            results.append(r)
    results.sort(key=lambda x: -x["score"])
    return results[:3]


def _market_open() -> bool:
    """True during NSE market hours (9:00 AM – 3:35 PM IST, Mon–Fri)."""
    now = datetime.now()
    if now.weekday() >= 5:   # Saturday, Sunday
        return False
    h, m = now.hour, now.minute
    return (9, 0) <= (h, m) <= (15, 35)


def _run_eod_retrain() -> None:
    """Refresh daily cache + retrain ML model. Runs once after market close."""
    try:
        print(f"\n  [EOD] Refreshing data cache + retraining model...")
        result = subprocess.run(
            ["python", "main.py", "--refresh-only"],
            capture_output=True, text=True, cwd=BASE_DIR, timeout=600
        )
        if result.returncode != 0:
            # main.py may not support --refresh-only; fall back to ml_retrainer directly
            subprocess.run(["python", "ml_retrainer.py"], cwd=BASE_DIR,
                           capture_output=True, timeout=300)
        print(f"  [EOD] Retrain complete.")
    except Exception as e:
        print(f"  [EOD] Retrain error: {e}")


def _next_run_msg(interval: int) -> str:
    mins = interval // 60
    return f"next refresh in {mins} min"


def main():
    capital = 32_000

    # Parse --capital flag
    if "--capital" in sys.argv:
        idx = sys.argv.index("--capital")
        if idx + 1 < len(sys.argv):
            try:
                capital = int(sys.argv[idx + 1])
            except ValueError:
                pass

    print(f"\n  Auto-push daemon started — capital ₹{capital:,}")
    print(f"  Refreshes every {INTERVAL_SEC // 60} min during market hours (9:00–15:35 IST)")
    print(f"  Ctrl+C to stop\n")

    last_push_syms: list[str] = []
    eod_done_date: str = ""   # tracks which date EOD retrain already ran

    while True:
        now_str = datetime.now().strftime("%H:%M:%S")
        today   = date.today().isoformat()

        if not _market_open():
            h, m = datetime.now().hour, datetime.now().minute
            # Trigger EOD retrain once per day, between 15:40–16:30, weekdays
            if (h == 15 and m >= 40) or (h == 16 and m <= 30):
                if datetime.now().weekday() < 5 and eod_done_date != today:
                    eod_done_date = today
                    _run_eod_retrain()

            if h >= 15 or h < 9:
                print(f"\r  [{now_str}] Market closed. Waiting for 9:00 AM...        ", end="", flush=True)
            else:
                print(f"\r  [{now_str}] Weekend — sleeping...                         ", end="", flush=True)
            time.sleep(60)
            continue

        print(f"\r  [{now_str}] Scanning...                                   ", end="", flush=True)

        try:
            picks = run_scan_quiet(capital)

            if not picks:
                print(f"\r  [{now_str}] No setups found — market may be choppy. {_next_run_msg(INTERVAL_SEC)}", end="", flush=True)
            else:
                new_syms = [p["symbol"] for p in picks]
                changed  = new_syms != last_push_syms

                if changed:
                    pushed = _git_push(picks, capital)
                    status = "pushed" if pushed else "no change"
                    syms_str = " · ".join(s.replace(".NS", "") for s in new_syms)
                    print(f"\r  [{now_str}] {syms_str} — {status}. {_next_run_msg(INTERVAL_SEC)}        ")
                    if pushed:
                        last_push_syms = new_syms
                else:
                    syms_str = " · ".join(s.replace(".NS", "") for s in new_syms)
                    print(f"\r  [{now_str}] {syms_str} — unchanged. {_next_run_msg(INTERVAL_SEC)}       ", end="", flush=True)

        except Exception as e:
            print(f"\r  [{now_str}] Error: {e}. Retrying in 1 min.                  ", end="", flush=True)
            time.sleep(60)
            continue

        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Stopped.\n")
