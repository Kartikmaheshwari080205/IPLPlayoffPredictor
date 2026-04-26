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


# 🔥 FIXED FUNCTION
def download_and_extract_json_archive() -> None:
    if JSON_DIR.exists():
        shutil.rmtree(JSON_DIR)
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
        temp_zip_path = Path(tmp_file.name)

        # Add User-Agent to avoid blocking
        req = urllib.request.Request(
            CRICSHEET_URL,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(req) as response:
            content_type = response.headers.get("Content-Type")
            print("Download Content-Type:", content_type)

            shutil.copyfileobj(response, tmp_file)

    # Validate ZIP before extracting
    if not zipfile.is_zipfile(temp_zip_path):
        with open(temp_zip_path, "rb") as f:
            preview = f.read(300)

        raise ValueError(
            "Downloaded file is not a valid ZIP.\n"
            f"Preview:\n{preview}"
        )

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
        if not stripped or stripped.startswith("#"):
            comment_lines.append(line)
        else:
            data_lines.append(line)

    header_tokens = data_lines[0].split()
    columns: list[str] = []
    matrix: dict[str, dict[str, int]] = {team: {} for team in TEAM_ORDER}

    for token in header_tokens[1:]:
        team = normalize_team_name(token)
        columns.append(team)

    for row in data_lines[1:]:
        tokens = row.split()
        row_team = normalize_team_name(tokens[0])
        for column_team, value in zip(columns, tokens[1:]):
            matrix[row_team][column_team] = int(value)

    return comment_lines, matrix, columns, newline


def write_h2h(comment_lines, matrix, columns, newline):
    lines = comment_lines[:]
    lines.append("TEAM " + " ".join(columns))
    for row_team in TEAM_ORDER:
        values = [str(matrix[row_team][col]) for col in columns]
        lines.append(f"{row_team} " + " ".join(values))
    H2H_FILE.write_text("\n".join(lines) + "\n")


def extract_result_from_json(path: Path):
    data = json.load(open(path))
    info = data.get("info", {})
    match_id = str(info.get("event", {}).get("match_number"))

    teams = info.get("teams", [])
    team_a = normalize_team_name(teams[0])
    team_b = normalize_team_name(teams[1])

    winner = info.get("outcome", {}).get("winner")
    winner_team = normalize_team_name(winner) if winner else None

    return match_id, (team_a, team_b), winner_team


def update_from_recent_json(entries, matrix):
    updated = 0
    h2h_updates = 0

    json_files = sorted(JSON_DIR.glob("*.json"), key=lambda x: int(x.stem), reverse=True)

    for file in json_files:
        match_id, (a, b), winner = extract_result_from_json(file)

        for entry in entries:
            if entry["kind"] == "match" and entry["match_id"] == match_id:
                if entry["result"] != "PENDING":
                    continue

                entry["result"] = winner if winner else "NR"
                updated += 1

                if winner:
                    loser = b if winner == a else a
                    matrix[winner][loser] += 1
                    h2h_updates += 1

                break

    return updated, h2h_updates


def compile_and_run_predictor():
    subprocess.run(["g++", "-std=c++17", "-O2", "predictor.cpp", "-o", "predictor"])
    return subprocess.run(["./predictor"]).returncode


def main():
    entries, nl = load_matches()
    comments, matrix, cols, nl2 = load_h2h()

    download_and_extract_json_archive()
    updated, h2h_updates = update_from_recent_json(entries, matrix)

    write_matches(entries, nl)
    write_h2h(comments, matrix, cols, nl2)

    print("Updated matches:", updated)
    print("H2H updates:", h2h_updates)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())