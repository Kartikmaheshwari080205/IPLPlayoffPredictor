from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MATCHES_FILE = ROOT / "matches.txt"
PROBABILITY_FILE = ROOT / "probabilities.txt"
REFRESH_SCRIPT = ROOT / "refresh_ipl_data.py"
DEFAULT_THRESHOLD = 27
TEAM_COUNT = 10


def now_timestamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def count_remaining_matches(matches_file: Path) -> int:
    if not matches_file.exists():
        raise FileNotFoundError(f"matches file not found: {matches_file}")

    pending = 0
    with matches_file.open("r", encoding="utf-8") as fin:
        for raw_line in fin:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 4:
                raise ValueError(f"invalid matches row: {line}")

            result_token = parts[3].strip().upper()
            if result_token in {"PENDING", "NOTPLAYED", "-1"}:
                pending += 1

    return pending


def write_unfeasible_snapshot(remaining_matches: int) -> None:
    with PROBABILITY_FILE.open("w", encoding="utf-8") as fout:
        fout.write(f"lastUpdated={now_timestamp()}\n")
        fout.write("status=unfeasible\n")
        fout.write(f"remainingMatches={remaining_matches}\n")
        for _ in range(TEAM_COUNT):
            fout.write("0\n")


def resolve_predictor_command() -> list[str]:
    predictor_exe = ROOT / "predictor.exe"
    predictor_bin = ROOT / "predictor"

    if predictor_exe.exists():
        return [str(predictor_exe)]

    if predictor_bin.exists():
        return [str(predictor_bin)]

    raise FileNotFoundError(
        "predictor executable not found. Build predictor.cpp first "
        "(e.g. g++ -std=c++17 -O2 predictor.cpp -o predictor.exe)."
    )


def run_step(command: list[str], title: str) -> int:
    print(f"[{now_timestamp()}] {title}")
    print("$", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT)
    print(f"[{now_timestamp()}] exit={completed.returncode}\n")
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run nightly backend orchestration: refresh data, check remaining "
            "matches, and run predictor only when feasible."
        )
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help="Maximum remaining matches allowed to run predictor (default: 27).",
    )
    args = parser.parse_args()

    refresh_cmd = [sys.executable, str(REFRESH_SCRIPT)]
    refresh_code = run_step(refresh_cmd, "Refreshing IPL data")
    if refresh_code != 0:
        print("Refresh step failed; not proceeding to predictor.")
        return refresh_code

    try:
        remaining_matches = count_remaining_matches(MATCHES_FILE)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to compute remaining matches: {exc}")
        return 1

    print(f"Remaining matches: {remaining_matches}")

    if remaining_matches > args.threshold:
        print(
            f"Remaining matches > {args.threshold}. "
            "Skipping predictor and writing unfeasible snapshot."
        )
        write_unfeasible_snapshot(remaining_matches)
        print(f"Updated snapshot: {PROBABILITY_FILE}")
        return 0

    try:
        predictor_cmd = resolve_predictor_command()
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    predictor_code = run_step(predictor_cmd, "Running predictor")
    if predictor_code != 0:
        print("Predictor step failed.")
        return predictor_code

    if not PROBABILITY_FILE.exists():
        print("Warning: predictor finished, but probabilities.txt was not created.")
    else:
        print(f"Snapshot ready: {PROBABILITY_FILE}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
