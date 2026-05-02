from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

TEAM_ORDER = ["MI", "CSK", "RCB", "KKR", "RR", "DC", "PBKS", "SRH", "GT", "LSG"]
DEFAULT_THRESHOLD = 27
TEAM_INDEX = {team: idx for idx, team in enumerate(TEAM_ORDER)}


def parse_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"snapshot file not found: {path}")

    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 3:
        raise ValueError("snapshot format is invalid: expected at least 3 metadata lines")

    def parse_kv(raw: str) -> tuple[str, str]:
        if "=" not in raw:
            raise ValueError(f"invalid metadata line: {raw}")
        key, value = raw.split("=", 1)
        return key.strip(), value.strip()

    k1, v1 = parse_kv(lines[0])
    k2, v2 = parse_kv(lines[1])
    k3, v3 = parse_kv(lines[2])

    if k1 != "lastUpdated" or k2 != "status" or k3 != "remainingMatches":
        raise ValueError("snapshot headers must be: lastUpdated, status, remainingMatches")

    remaining_matches = int(v3)
    probabilities: list[float] = []
    for raw in lines[3:]:
        probabilities.append(float(raw))

    return {
        "lastUpdated": v1,
        "status": v2,
        "remainingMatches": remaining_matches,
        "probabilities": probabilities,
    }


def parse_matches(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"matches file not found: {path}")

    points = {team: 0 for team in TEAM_ORDER}
    matches_played = {team: 0 for team in TEAM_ORDER}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"invalid matches row: {line}")

        team1, team2, _match_id, result = parts[:4]
        team1 = team1.upper()
        team2 = team2.upper()
        result = result.upper()

        if team1 not in TEAM_INDEX or team2 not in TEAM_INDEX:
            raise ValueError(f"invalid team in matches row: {line}")

        if result == "PENDING":
            continue

        matches_played[team1] += 1
        matches_played[team2] += 1

        if result in {"NR", "0"}:
            points[team1] += 1
            points[team2] += 1
        elif result in {team1, "1"}:
            points[team1] += 2
        elif result in {team2, "2"}:
            points[team2] += 2
        else:
            raise ValueError(f"invalid result in matches row: {line}")

    rows = [
        {
            "team": team,
            "matchesPlayed": matches_played[team],
            "points": points[team],
        }
        for team in TEAM_ORDER
    ]
    rows.sort(key=lambda row: (-row["points"], TEAM_INDEX[row["team"]]))
    return rows


def parse_h2h(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"h2h file not found: {path}")

    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data_lines = [line for line in lines if not line.startswith("#")]
    if len(data_lines) < 2:
        raise ValueError("h2h format is invalid: expected header and at least one row")

    header_tokens = data_lines[0].split()
    if len(header_tokens) != len(TEAM_ORDER) + 1 or header_tokens[0].upper() != "TEAM":
        raise ValueError("h2h header is invalid")

    h2h_team_order = [token.upper() for token in header_tokens[1:]]
    if h2h_team_order != TEAM_ORDER:
        raise ValueError("h2h team order does not match expected teams")

    rows: list[dict[str, Any]] = []
    for raw_row in data_lines[1:]:
        tokens = raw_row.split()
        if len(tokens) != len(TEAM_ORDER) + 1:
            raise ValueError(f"invalid h2h row: {raw_row}")

        row_team = tokens[0].upper()
        if row_team not in TEAM_INDEX:
            raise ValueError(f"invalid h2h team label: {raw_row}")

        values = [int(value) for value in tokens[1:]]
        rows.append({"team": row_team, "values": values})

    rows.sort(key=lambda row: TEAM_INDEX[row["team"]])
    return {"teamOrder": TEAM_ORDER, "rows": rows}


def build_payload(snapshot: dict[str, Any], threshold: int, matches_path: Path, h2h_path: Path) -> dict[str, Any]:
    remaining_matches = int(snapshot["remainingMatches"])
    probabilities = [float(value) for value in snapshot.get("probabilities", [])]
    points_table = parse_matches(matches_path)
    h2h = parse_h2h(h2h_path)

    base = {
        "lastUpdated": snapshot["lastUpdated"],
        "remainingMatches": remaining_matches,
        "teamOrder": TEAM_ORDER,
        "pointsTable": points_table,
        "h2h": h2h,
    }

    if remaining_matches > threshold or snapshot.get("status") == "unfeasible":
        base.update(
            {
                "status": "unfeasible",
                "message": "unfeasible to compute at the moment",
                "probabilities": [],
                "mappedProbabilities": {},
            }
        )
        return base

    mapped_probabilities: dict[str, float] = {}
    normalized_probabilities: list[float] = []
    for idx, team in enumerate(TEAM_ORDER):
        value = probabilities[idx] if idx < len(probabilities) else 0.0
        mapped_probabilities[team] = value
        normalized_probabilities.append(value)

    base.update(
        {
            "status": "computed",
            "probabilities": normalized_probabilities,
            "mappedProbabilities": mapped_probabilities,
        }
    )
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="Build frontend JSON payload from probabilities snapshot.")
    parser.add_argument("--input", default="probabilities.txt", help="Path to probabilities.txt")
    parser.add_argument("--output", default="playoff_snapshot.json", help="Output JSON path")
    parser.add_argument("--matches", default="matches.txt", help="Path to matches.txt")
    parser.add_argument("--h2h", default="h2h.txt", help="Path to h2h.txt")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help="Feasibility threshold")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    matches_path = Path(args.matches)
    h2h_path = Path(args.h2h)

    snapshot = parse_snapshot(input_path)
    payload = build_payload(snapshot, args.threshold, matches_path, h2h_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote payload to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
