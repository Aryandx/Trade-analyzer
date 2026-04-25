"""
One-time setup script.
Run this ONCE:  python setup_startup.py

What it does:
  1. Installs required packages
  2. Creates a daily scheduled task (Task Scheduler) for full analysis
  3. Adds notifier to Windows startup folder (shows popup on login)
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable


def step(msg: str) -> None:
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def install_packages() -> None:
    step("Installing required packages")
    req_file = os.path.join(BASE_DIR, "requirements.txt")
    result = subprocess.run(
        [PYTHON, "-m", "pip", "install", "-r", req_file, "--quiet"],
        capture_output=False,
    )
    if result.returncode == 0:
        print("✓ All packages installed successfully")
    else:
        print("⚠ Some packages may have failed. Check output above.")


def add_startup_notifier() -> None:
    step("Adding notifier to Windows startup")
    startup_folder = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    bat_path = startup_folder / "stock_analyzer_notify.bat"

    notifier_path = os.path.join(BASE_DIR, "notifier.py")
    bat_content = f"""@echo off
cd /d "{BASE_DIR}"
start /min "" "{PYTHON}" "{notifier_path}"
"""
    with open(bat_path, "w") as f:
        f.write(bat_content)
    print(f"✓ Startup notifier created: {bat_path}")
    print("  The notification will appear every time you log in to Windows.")


def create_scheduled_task() -> None:
    step("Creating daily analysis task (Task Scheduler)")
    task_name = "StockAnalyzerDaily"
    main_py = os.path.join(BASE_DIR, "main.py")

    # XML-based task creation for reliability
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T07:30:00</StartBoundary>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>{PYTHON}</Command>
      <Arguments>"{main_py}"</Arguments>
      <WorkingDirectory>{BASE_DIR}</WorkingDirectory>
    </Exec>
  </Actions>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd></IdleSettings>
    <ExecutionTimeLimit>PT3H</ExecutionTimeLimit>
  </Settings>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
</Task>"""

    xml_path = os.path.join(BASE_DIR, "task_schedule.xml")
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(xml)

    result = subprocess.run(
        ["schtasks", "/Create", "/TN", task_name, "/XML", xml_path, "/F"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"✓ Daily task '{task_name}' created — runs at 07:30 every day")
        print("  You can also run manually: python main.py")
    else:
        print(f"⚠ Task creation failed: {result.stderr}")
        print("  You can still run manually: python main.py")

    # Clean up temp xml
    try:
        os.remove(xml_path)
    except Exception:
        pass


def create_run_batch() -> None:
    step("Creating run_analysis.bat (double-click shortcut)")
    bat_path = os.path.join(BASE_DIR, "run_analysis.bat")
    content = f"""@echo off
title Stock Market Analyzer
echo Starting Indian Market Analysis...
echo This may take 30-60 minutes for full analysis.
echo Press Ctrl+C to stop.
cd /d "{BASE_DIR}"
"{PYTHON}" main.py
pause
"""
    with open(bat_path, "w") as f:
        f.write(content)
    print(f"✓ Created run_analysis.bat — double-click to run analysis anytime")


def run_first_analysis() -> None:
    step("Running first analysis (quick mode — 30 stocks)")
    print("This gives you your first set of recommendations.")
    print("For a full deep analysis, run: python main.py\n")
    result = subprocess.run(
        [PYTHON, os.path.join(BASE_DIR, "main.py"), "--quick"],
        cwd=BASE_DIR,
    )
    if result.returncode == 0:
        print("\n✓ First analysis complete! Check the HTML report that opened.")
    else:
        print("\n⚠ Analysis encountered errors. Check output above.")


if __name__ == "__main__":
    print("\n🚀 Stock Analyzer — One-Time Setup")
    print("="*60)

    install_packages()
    create_run_batch()

    try:
        add_startup_notifier()
    except Exception as e:
        print(f"⚠ Could not add startup notifier: {e}")

    try:
        create_scheduled_task()
    except Exception as e:
        print(f"⚠ Could not create scheduled task: {e}")

    print("\n" + "="*60)
    answer = input("\nRun first quick analysis now? (y/n): ").strip().lower()
    if answer == "y":
        run_first_analysis()
    else:
        print("\nRun 'python main.py' when ready for the full analysis.")
        print("Run 'python main.py --quick' for a faster 30-stock preview.")

    print("\n✅ Setup complete!")
    print("\nHow to use:")
    print("  • Full analysis:   python main.py")
    print("  • Quick preview:   python main.py --quick")
    print("  • Show popup now:  python notifier.py")
    print("  • Startup popup:   Automatic on Windows login")
    print("  • Daily refresh:   Automatic at 07:30 via Task Scheduler")
