from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import requests


ROOT = Path(__file__).resolve().parent
MATCHES_FILE = ROOT / "matches.txt"
H2H_FILE = ROOT / "h2h.txt"
JSON_DIR = ROOT / "ipl_json"
CRICSHEET_URL = "https://cricsheet.org/downloads/ipl_json.zip"
FALLBACK_GITHUB_URL = "https://codeload.github.com/GokulGowthamS/Cricsheet/zip/refs/heads/main"

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


def _stream_download_to_temp_zip(url: str, headers: Optional[dict[str, str]] = None) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
        temp_zip_path = Path(tmp_file.name)

        response = requests.get(url, headers=headers or {}, stream=True, timeout=120)

        print("Download URL:", url)
        print("Status Code:", response.status_code)
        print("Content-Type:", response.headers.get("Content-Type"))

        if response.status_code != 200:
            raise RuntimeError(f"Download failed: {response.status_code}")

        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                tmp_file.write(chunk)

    if not zipfile.is_zipfile(temp_zip_path):
        with open(temp_zip_path, "rb") as f:
            preview = f.read(300)
        temp_zip_path.unlink(missing_ok=True)
        raise ValueError(f"Invalid ZIP download from {url}\nPreview:\n{preview}")

    return temp_zip_path


def _extract_json_files_from_archive(archive_path: Path, target_dir: Path) -> int:
    extracted = 0
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            member_lower = member.lower()

            if not member_lower.endswith(".json"):
                continue

            # Primary path for fallback mirror and expected paths from IPL ZIP archives.
            is_fallback_ipl_path = "raw_json_files/ipl_data/" in member_lower
            is_cricsheet_ipl_path = "/ipl_json/" in member_lower
            is_flat_json = "/" not in member.strip("/")

            if not (is_fallback_ipl_path or is_cricsheet_ipl_path or is_flat_json):
                continue

            filename = Path(member).name
            if not filename:
                continue

            with archive.open(member) as src, open(target_dir / filename, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted += 1

    return extracted


def download_and_extract_json_archive() -> None:
    sources: list[tuple[str, Optional[dict[str, str]]]] = [
        (
            CRICSHEET_URL,
            {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/zip,application/octet-stream,*/*",
                "Referer": "https://cricsheet.org/",
            },
        ),
        (FALLBACK_GITHUB_URL, {"User-Agent": "Mozilla/5.0"}),
    ]

    temp_extract_dir = Path(tempfile.mkdtemp(prefix="ipl_json_extract_"))
    last_error: Optional[Exception] = None

    try:
        for url, headers in sources:
            temp_zip_path: Optional[Path] = None
            try:
                temp_zip_path = _stream_download_to_temp_zip(url, headers)
                extracted_count = _extract_json_files_from_archive(temp_zip_path, temp_extract_dir)
                if extracted_count == 0:
                    raise RuntimeError(f"No JSON files extracted from: {url}")

                if JSON_DIR.exists():
                    shutil.rmtree(JSON_DIR)
                JSON_DIR.mkdir(parents=True, exist_ok=True)

                for json_file in temp_extract_dir.glob("*.json"):
                    shutil.move(str(json_file), JSON_DIR / json_file.name)

                print(f"Extracted {extracted_count} JSON files from {url}")
                return
            except Exception as exc:
                last_error = exc
                print(f"Download source failed: {url} -> {exc}")
            finally:
                if temp_zip_path:
                    temp_zip_path.unlink(missing_ok=True)
                for json_file in temp_extract_dir.glob("*.json"):
                    json_file.unlink(missing_ok=True)

        raise RuntimeError(f"All download sources failed. Last error: {last_error}")
    finally:
        shutil.rmtree(temp_extract_dir, ignore_errors=True)


def load_matches():
    raw = MATCHES_FILE.read_text()
    entries = []

    for line in raw.splitlines():
        if not line.strip() or line.startswith("#"):
            entries.append({"kind": "passthrough", "line": line})
            continue

        t1, t2, mid, res = line.split()
        entries.append({
            "kind": "match",
            "team1": normalize_team_name(t1),
            "team2": normalize_team_name(t2),
            "match_id": mid,
            "result": res
        })

    return entries, "\n"


def write_matches(entries, nl):
    lines = []
    for e in entries:
        if e["kind"] == "passthrough":
            lines.append(e["line"])
        else:
            lines.append(f"{e['team1']} {e['team2']} {e['match_id']} {e['result']}")
    MATCHES_FILE.write_text("\n".join(lines) + "\n")


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
        r = normalize_team_name(parts[0])
        for c, val in zip(header, parts[1:]):
            matrix[r][normalize_team_name(c)] = int(val)

    return comments, matrix, header, "\n"


def write_h2h(comments, matrix, cols, nl):
    lines = comments[:]
    lines.append("TEAM " + " ".join(cols))
    for t in TEAM_ORDER:
        lines.append(f"{t} " + " ".join(str(matrix[t][c]) for c in cols))
    H2H_FILE.write_text("\n".join(lines) + "\n")


def extract_result_from_json(path):
    data = json.load(open(path))
    info = data.get("info", {})

    match_id = str(info.get("event", {}).get("match_number"))
    teams = info.get("teams", [])
    dates = info.get("dates", [])

    match_year: Optional[int] = None
    if dates:
        # Cricsheet date values are typically ISO strings like YYYY-MM-DD.
        first_date = str(dates[0])
        try:
            match_year = int(first_date[:4])
        except (TypeError, ValueError):
            match_year = None

    a = normalize_team_name(teams[0])
    b = normalize_team_name(teams[1])

    winner = info.get("outcome", {}).get("winner")
    winner = normalize_team_name(winner) if winner else None

    return match_id, (a, b), winner, match_year


def update_from_recent_json(entries, matrix):
    updated = 0
    h2h_updates = 0
    current_year = dt.date.today().year

    files = sorted(JSON_DIR.glob("*.json"), key=lambda x: int(x.stem), reverse=True)

    seen_any = False

    for f in files:
        match_id, (a, b), winner, match_year = extract_result_from_json(f)

        if match_year != current_year:
            continue

        if match_id == "1" and seen_any:
            break
        seen_any = True

        for e in entries:
            if e["kind"] == "match" and e["match_id"] == match_id:
                if e["result"] != "PENDING":
                    continue
                if {e["team1"], e["team2"]} != {a, b}:
                    continue
                if winner and winner not in {a, b}:
                    continue

                e["result"] = winner if winner else "NR"
                updated += 1

                if winner:
                    loser = b if winner == a else a
                    matrix[winner][loser] += 1
                    h2h_updates += 1
                break

    return updated, h2h_updates


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