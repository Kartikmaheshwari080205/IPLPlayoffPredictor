from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROBABILITY_FILE = ROOT / "probabilities.txt"
TEAM_ORDER = ["MI", "CSK", "RCB", "KKR", "RR", "DC", "PBKS", "SRH", "GT", "LSG"]
MAX_FEASIBLE_REMAINING_MATCHES = 27


def parse_snapshot() -> dict[str, Any]:
    if not PROBABILITY_FILE.exists():
        return {
            "status": "unavailable",
            "message": "probabilities snapshot not found",
            "lastUpdated": None,
            "remainingMatches": None,
            "probabilities": [],
        }

    lines = [line.strip() for line in PROBABILITY_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 3:
        return {
            "status": "invalid",
            "message": "snapshot file format is invalid",
            "lastUpdated": None,
            "remainingMatches": None,
            "probabilities": [],
        }

    def parse_kv(raw: str) -> tuple[str, str]:
        if "=" not in raw:
            return "", ""
        key, value = raw.split("=", 1)
        return key.strip(), value.strip()

    k1, v1 = parse_kv(lines[0])
    k2, v2 = parse_kv(lines[1])
    k3, v3 = parse_kv(lines[2])

    if k1 != "lastUpdated" or k2 != "status" or k3 != "remainingMatches":
        return {
            "status": "invalid",
            "message": "snapshot headers are invalid",
            "lastUpdated": None,
            "remainingMatches": None,
            "probabilities": [],
        }

    try:
        remaining_matches = int(v3)
    except ValueError:
        remaining_matches = None

    probability_values: list[float] = []
    for raw_value in lines[3:]:
        try:
            probability_values.append(float(raw_value))
        except ValueError:
            return {
                "status": "invalid",
                "message": "snapshot probabilities are invalid",
                "lastUpdated": v1,
                "remainingMatches": remaining_matches,
                "probabilities": [],
            }

    return {
        "status": v2,
        "lastUpdated": v1,
        "remainingMatches": remaining_matches,
        "probabilities": probability_values,
    }


def build_response_payload() -> tuple[dict[str, Any], int]:
    snapshot = parse_snapshot()

    if snapshot["status"] in {"unavailable", "invalid"}:
        return snapshot, 503

    remaining_matches = snapshot.get("remainingMatches")
    if remaining_matches is None:
        return {
            "status": "invalid",
            "message": "remainingMatches is missing or invalid",
        }, 503

    if remaining_matches > MAX_FEASIBLE_REMAINING_MATCHES:
        return {
            "status": "unfeasible",
            "message": "unfeasible to compute at the moment",
            "lastUpdated": snapshot.get("lastUpdated"),
            "remainingMatches": remaining_matches,
        }, 200

    probabilities = snapshot.get("probabilities", [])
    mapped_probabilities: dict[str, float] = {}
    for idx, team in enumerate(TEAM_ORDER):
        mapped_probabilities[team] = probabilities[idx] if idx < len(probabilities) else 0.0

    return {
        "status": "computed",
        "lastUpdated": snapshot.get("lastUpdated"),
        "remainingMatches": remaining_matches,
        "teamOrder": TEAM_ORDER,
        "probabilities": probabilities,
        "mappedProbabilities": mapped_probabilities,
    }, 200


class PredictorHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict[str, Any], status_code: int) -> None:
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json({"status": "ok"}, 200)
            return

        if self.path == "/probabilities":
            payload, status_code = build_response_payload()
            self._send_json(payload, status_code)
            return

        self._send_json({"status": "not_found", "message": "endpoint not found"}, 404)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), PredictorHandler)
    print(f"API server listening on http://localhost:{port}")
    server.serve_forever()
