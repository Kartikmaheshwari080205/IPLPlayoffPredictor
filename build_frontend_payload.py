from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

TEAM_ORDER = ["MI", "CSK", "RCB", "KKR", "RR", "DC", "PBKS", "SRH", "GT", "LSG"]
DEFAULT_THRESHOLD = 27


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


def build_payload(snapshot: dict[str, Any], threshold: int) -> dict[str, Any]:
    remaining_matches = int(snapshot["remainingMatches"])
    probabilities = [float(value) for value in snapshot.get("probabilities", [])]

    base = {
        "lastUpdated": snapshot["lastUpdated"],
        "remainingMatches": remaining_matches,
        "teamOrder": TEAM_ORDER,
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
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help="Feasibility threshold")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    snapshot = parse_snapshot(input_path)
    payload = build_payload(snapshot, args.threshold)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote payload to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
