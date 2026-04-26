from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent
MATCHES_FILE = ROOT / "matches.txt"
H2H_FILE = ROOT / "h2h.txt"
JSON_DIR = ROOT / "ipl_json"
CRICSHEET_URL = "https://cricsheet.org/downloads/ipl_json.zip"

TEAM_ORDER = ["MI", "CSK", "RCB", "KKR", "RR", "DC", "PBKS", "SRH", "GT", "LSG"]
TEAM_SET = set(TEAM_ORDER)

TEAM_ALIASES = {
    "MI": "MI",
    "MUMBAI INDIANS": "MI",
    "CSK": "CSK",
    "CHENNAI SUPER KINGS": "CSK",
    "RCB": "RCB",
    "ROYAL CHALLENGERS BANGALORE": "RCB",
    "ROYAL CHALLENGERS BENGALURU": "RCB",
    "BANGALORE": "RCB",
    "BENGALURU": "RCB",
    "KKR": "KKR",
    "KOLKATA KNIGHT RIDERS": "KKR",
    "RR": "RR",
    "RAJASTHAN ROYALS": "RR",
    "DC": "DC",
    "DELHI CAPITALS": "DC",
    "DELHI DAREDEVILS": "DC",
    "DELHI": "DC",
    "PBKS": "PBKS",
    "PUNJAB KINGS": "PBKS",
    "KINGS XI PUNJAB": "PBKS",
    "PUNJAB": "PBKS",
    "SRH": "SRH",
    "SUNRISERS HYDERABAD": "SRH",
    "SUNRISERS": "SRH",
    "GT": "GT",
    "GUJARAT TITANS": "GT",
    "LSG": "LSG",
    "LUCKNOW SUPER GIANTS": "LSG",
}


def normalize_team_name(raw: str) -> Optional[str]:
    normalized = raw.strip().upper()
    if normalized in TEAM_SET:
        return normalized
    return TEAM_ALIASES.get(normalized)


def detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def download_and_extract_json_archive() -> None:
    if JSON_DIR.exists():
        shutil.rmtree(JSON_DIR)
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
        temp_zip_path = Path(tmp_file.name)
        with urllib.request.urlopen(CRICSHEET_URL) as response:
            shutil.copyfileobj(response, tmp_file)

    try:
        with zipfile.ZipFile(temp_zip_path) as archive:
            for member in archive.namelist():
                if not member.lower().endswith(".json"):
                    continue
                archive.extract(member, JSON_DIR)
    finally:
        temp_zip_path.unlink(missing_ok=True)


def load_matches() -> tuple[list[dict[str, object]], str]:
    if not MATCHES_FILE.exists():
        raise FileNotFoundError(f"Missing matches file: {MATCHES_FILE}")

    raw_text = MATCHES_FILE.read_text(encoding="utf-8")
    newline = detect_newline(raw_text)
    entries: list[dict[str, object]] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            entries.append({"kind": "passthrough", "line": line})
            continue

        parts = stripped.split()
        if len(parts) != 4:
            raise ValueError(f"Invalid matches.txt line: {line}")

        team1 = normalize_team_name(parts[0])
        team2 = normalize_team_name(parts[1])
        if team1 is None or team2 is None:
            raise ValueError(f"Invalid team in matches.txt line: {line}")

        entries.append(
            {
                "kind": "match",
                "team1": team1,
                "team2": team2,
                "match_id": parts[2],
                "result": parts[3],
            }
        )

    return entries, newline


def write_matches(entries: list[dict[str, object]], newline: str) -> None:
    lines: list[str] = []
    for entry in entries:
        if entry["kind"] == "passthrough":
            lines.append(str(entry["line"]))
        else:
            lines.append(
                f'{entry["team1"]} {entry["team2"]} {entry["match_id"]} {entry["result"]}'
            )
    MATCHES_FILE.write_text(newline.join(lines) + newline, encoding="utf-8")


def load_h2h() -> tuple[list[str], dict[str, dict[str, int]], list[str], str]:
    if not H2H_FILE.exists():
        raise FileNotFoundError(f"Missing h2h file: {H2H_FILE}")

    raw_text = H2H_FILE.read_text(encoding="utf-8")
    newline = detect_newline(raw_text)
    comment_lines: list[str] = []
    data_lines: list[str] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            comment_lines.append(line)
            continue
        if stripped.startswith("#"):
            comment_lines.append(line)
            continue
        data_lines.append(line)

    if len(data_lines) != 11:
        raise ValueError("h2h.txt must contain a header row plus 10 team rows")

    header_tokens = data_lines[0].split()
    if header_tokens[0].upper() != "TEAM" or len(header_tokens) != 11:
        raise ValueError("Invalid h2h header format")

    columns: list[str] = []
    matrix: dict[str, dict[str, int]] = {team: {} for team in TEAM_ORDER}
    for token in header_tokens[1:]:
        team = normalize_team_name(token)
        if team is None:
            raise ValueError(f"Invalid team in h2h header: {token}")
        columns.append(team)

    if set(columns) != TEAM_SET:
        raise ValueError("h2h header must contain all 10 teams exactly once")

    for row in data_lines[1:]:
        tokens = row.split()
        if len(tokens) != 11:
            raise ValueError(f"Invalid h2h row: {row}")
        row_team = normalize_team_name(tokens[0])
        if row_team is None:
            raise ValueError(f"Invalid team in h2h row label: {tokens[0]}")

        for column_team, value in zip(columns, tokens[1:]):
            matrix[row_team][column_team] = int(value)

    return comment_lines, matrix, columns, newline


def write_h2h(comment_lines: list[str], matrix: dict[str, dict[str, int]], columns: list[str], newline: str) -> None:
    lines: list[str] = []
    lines.extend(comment_lines)
    lines.append("TEAM " + " ".join(columns))
    for row_team in TEAM_ORDER:
        values = [str(matrix[row_team][column_team]) for column_team in columns]
        lines.append(f"{row_team} " + " ".join(values))
    H2H_FILE.write_text(newline.join(lines) + newline, encoding="utf-8")


def find_first_pending_match(entries: list[dict[str, object]]) -> Optional[dict[str, object]]:
    for entry in entries:
        if entry["kind"] != "match":
            continue
        if str(entry["result"]).upper() == "PENDING":
            return entry
    return None


def find_pending_match(entries: list[dict[str, object]], team_a: str, team_b: str) -> Optional[dict[str, object]]:
    pair = {team_a, team_b}
    for entry in reversed(entries):
        if entry["kind"] != "match":
            continue
        if str(entry["result"]).upper() != "PENDING":
            continue
        if {str(entry["team1"]), str(entry["team2"])} == pair:
            return entry
    return None


def extract_result_from_json(path: Path) -> Optional[tuple[tuple[str, str], Optional[str]]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    info = data.get("info", {})
    teams = info.get("teams", [])
    if len(teams) != 2:
        return None

    team_a = normalize_team_name(str(teams[0]))
    team_b = normalize_team_name(str(teams[1]))
    if team_a is None or team_b is None:
        return None

    outcome = info.get("outcome", {}) or {}
    winner = outcome.get("winner")
    if winner:
        winner_team = normalize_team_name(str(winner))
        if winner_team is None:
            return None
        return (team_a, team_b), winner_team

    return (team_a, team_b), None


def update_from_recent_json(entries: list[dict[str, object]], matrix: dict[str, dict[str, int]]) -> tuple[int, int]:
    updated_matches = 0
    h2h_updates = 0

    json_files = sorted(
        [path for path in JSON_DIR.glob("*.json") if path.stem.isdigit()],
        key=lambda item: int(item.stem),
        reverse=True,
    )

    if not json_files:
        return 0, 0

    latest_match = extract_result_from_json(json_files[0])
    if latest_match is None:
        return 0, 0

    pending_match = find_first_pending_match(entries)
    if pending_match is None:
        return 0, 0

    (team_a, team_b), winner_team = latest_match
    pending_teams = {str(pending_match["team1"]), str(pending_match["team2"])}
    if pending_teams != {team_a, team_b}:
        return 0, 0

    if str(pending_match["result"]).upper() != "PENDING":
        return 0, 0

    pending_match["result"] = winner_team if winner_team is not None else "NR"
    updated_matches = 1

    if winner_team is not None:
        loser_team = team_b if winner_team == team_a else team_a
        matrix[winner_team][loser_team] += 1
        h2h_updates = 1

    return updated_matches, h2h_updates


def compile_and_run_predictor() -> int:
    executable = ROOT / "predictor.exe"
    compiler = shutil.which("g++")

    if not executable.exists():
        if compiler is None:
            raise RuntimeError("g++ was not found on PATH, so predictor.exe could not be built")
        subprocess.run(
            [compiler, "-std=c++17", "-O2", "predictor.cpp", "-o", str(executable.name)],
            cwd=ROOT,
            check=True,
        )

    completed = subprocess.run([str(executable)], cwd=ROOT)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh IPL JSON data and update matches.txt / h2h.txt")
    parser.add_argument(
        "--predict",
        action="store_true",
        help="Run predictor.exe after refreshing the data",
    )
    args = parser.parse_args()

    entries, matches_newline = load_matches()
    comment_lines, matrix, columns, h2h_newline = load_h2h()

    download_and_extract_json_archive()
    updated_matches, h2h_updates = update_from_recent_json(entries, matrix)

    write_matches(entries, matches_newline)
    write_h2h(comment_lines, matrix, columns, h2h_newline)

    print(f"Updated matches: {updated_matches}")
    print(f"H2H updates: {h2h_updates}")

    if args.predict:
        return compile_and_run_predictor()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())