"""
Lightweight startup notifier — reads saved analysis JSON and shows a Windows popup.
Add this to Windows startup via setup_startup.py.
"""
import os
import sys
import json
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_JSON = os.path.join(BASE_DIR, "results", "latest_analysis.json")
REPORT_HTML = os.path.join(BASE_DIR, "results", "market_report.html")


def show_toast(title: str, message: str, duration: int = 15) -> None:
    # Try plyer first, fall back to PowerShell toast
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Stock Analyzer",
            timeout=duration,
        )
        return
    except Exception:
        pass

    # PowerShell fallback (works on all Windows 10/11 without extra packages)
    ps_cmd = f"""
$ErrorActionPreference = 'SilentlyContinue'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template)
$text = $xml.GetElementsByTagName("text")
$text[0].AppendChild($xml.CreateTextNode("{title}")) | Out-Null
$text[1].AppendChild($xml.CreateTextNode("{message}")) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Stock Analyzer")
$notifier.Show($toast)
"""
    try:
        subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            capture_output=True, timeout=10
        )
    except Exception:
        pass


def show_msgbox(title: str, message: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
    except Exception:
        pass


def main():
    if not os.path.exists(REPORT_JSON):
        show_msgbox(
            "Stock Analyzer — No Data",
            "No analysis found. Run main.py first to generate the report."
        )
        return

    with open(REPORT_JSON) as f:
        data = json.load(f)

    ts = data.get("generated_at", "N/A")
    regime = data.get("regime", {})
    picks = data.get("top_picks", [])
    market_sent = data.get("market_sentiment", {})

    reg_name = regime.get("regime", "UNKNOWN")
    nifty = regime.get("nifty_close", "?")

    if not picks:
        show_toast("📊 Stock Analyzer", f"Regime: {reg_name} | Nifty: {nifty}\nNo picks today. Check report.")
        return

    top = picks[0]
    sym = top["symbol"].replace(".NS", "")
    price = top["price"]
    target = top["target"]
    stop = top["stop_loss"]
    score = top["total_score"]
    tgt_pct = top["target_pct"]

    lines = [
        f"🏆 #{1}: {sym} @ ₹{price}",
        f"   🎯 Target ₹{target} (+{tgt_pct}%) | 🛑 Stop ₹{stop}",
    ]
    if len(picks) > 1:
        p2 = picks[1]
        lines.append(f"🥈 #{2}: {p2['symbol'].replace('.NS','')} @ ₹{p2['price']} → ₹{p2['target']} (+{p2['target_pct']}%)")
    if len(picks) > 2:
        p3 = picks[2]
        lines.append(f"🥉 #{3}: {p3['symbol'].replace('.NS','')} @ ₹{p3['price']} → ₹{p3['target']} (+{p3['target_pct']}%)")

    lines.append(f"\nRegime: {reg_name} | Nifty: {nifty} | Last update: {str(ts)[:16]}")
    message = "\n".join(lines)

    show_toast(f"📊 Market Analysis — Budget ₹5,000", message, duration=20)

    # Also open HTML report if market is open (Mon-Fri 9-16 IST)
    now = datetime.now()
    if now.weekday() < 5 and 8 <= now.hour <= 16:
        try:
            os.startfile(REPORT_HTML)
        except Exception:
            pass


if __name__ == "__main__":
    main()
