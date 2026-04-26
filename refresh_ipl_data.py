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


# ✅ FIXED DOWNLOAD FUNCTION
def download_and_extract_json_archive() -> None:
    if JSON_DIR.exists():
        shutil.rmtree(JSON_DIR)
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
        temp_zip_path = Path(tmp_file.name)

        req = urllib.request.Request(
            CRICSHEET_URL,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(req) as response:
            content_type = response.headers.get("Content-Type")
            print("Download Content-Type:", content_type)

            shutil.copyfileobj(response, tmp_file)

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
                if member.lower().endswith(".json"):
                    archive.extract(member, JSON_DIR)
    finally:
        temp_zip_path.unlink(missing_ok=True)


def load_matches() -> tuple[list[dict[str, object]], str]:
    raw_text = MATCHES_FILE.read_text(encoding="utf-8")
    newline = detect_newline(raw_text)

    entries = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            entries.append({"kind": "passthrough", "line": line})
            continue

        t1, t2, mid, res = stripped.split()
        entries.append({
            "kind": "match",
            "team1": normalize_team_name(t1),
            "team2": normalize_team_name(t2),
            "match_id": mid,
            "result": res
        })

    return entries, newline


def write_matches(entries, newline):
    lines = []
    for e in entries:
        if e["kind"] == "passthrough":
            lines.append(e["line"])
        else:
            lines.append(f"{e['team1']} {e['team2']} {e['match_id']} {e['result']}")
    MATCHES_FILE.write_text(newline.join(lines) + newline)


def load_h2h():
    raw = H2H_FILE.read_text()
    lines = raw.splitlines()

    comments = []
    data = []
    for l in lines:
        if not l.strip() or l.startswith("#"):
            comments.append(l)
        else:
            data.append(l)

    header = data[0].split()[1:]
    matrix = {t: {} for t in TEAM_ORDER}

    for row in data[1:]:
        parts = row.split()
        rteam = normalize_team_name(parts[0])
        for cteam, val in zip(header, parts[1:]):
            matrix[rteam][normalize_team_name(cteam)] = int(val)

    return comments, matrix, header, "\n"


def write_h2h(comments, matrix, cols, newline):
    lines = comments[:]
    lines.append("TEAM " + " ".join(cols))
    for t in TEAM_ORDER:
        row = [str(matrix[t][c]) for c in cols]
        lines.append(f"{t} " + " ".join(row))
    H2H_FILE.write_text("\n".join(lines) + "\n")


def extract_result_from_json(path: Path):
    data = json.load(open(path))
    info = data.get("info", {})

    match_id = str(info.get("event", {}).get("match_number"))

    teams = info.get("teams", [])
    a = normalize_team_name(teams[0])
    b = normalize_team_name(teams[1])

    winner = info.get("outcome", {}).get("winner")
    winner = normalize_team_name(winner) if winner else None

    return match_id, (a, b), winner


def update_from_recent_json(entries, matrix):
    updated = 0
    h2h_updates = 0

    json_files = sorted(JSON_DIR.glob("*.json"), key=lambda x: int(x.stem), reverse=True)

    seen_any = False

    for file in json_files:
        match_id, (a, b), winner = extract_result_from_json(file)

        if match_id == "1" and seen_any:
            break
        seen_any = True

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
    updated, h2h = update_from_recent_json(entries, matrix)

    write_matches(entries, nl)
    write_h2h(comments, matrix, cols, nl2)

    print("Updated matches:", updated)
    print("H2H updates:", h2h)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())