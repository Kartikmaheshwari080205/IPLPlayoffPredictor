# IPL Playoff Predictor

This project simulates IPL playoff qualification probabilities for 10 teams based on:

- Current and remaining matches from `matches.txt`
- Head-to-head matrix from `h2h.txt`

Two C++ programs are included:

- `predictor.cpp`: Uses memoization to merge identical point-table end states before computing top-4 probabilities.
- `temp.cpp`: Simulates all branches directly.

Both programs:

- Parse human-editable input files
- Compute pairwise win probabilities using H2H
- Simulate all pending matches
- Print qualification probabilities
- Print total execution time in milliseconds

## Team List

The code expects exactly these teams:

- MI
- CSK
- RCB
- KKR
- RR
- DC
- PBKS
- SRH
- GT
- LSG

## Input Files

### matches.txt

Format per non-comment line:

```text
<team1> <team2> <matchid> <result>
```

Rules:

- `team1` and `team2`: team names (case-insensitive)
- `matchid`: integer
- `result` can be:
  - `PENDING` (match not played)
  - `NR` (no result/draw)
  - winner team name (must be one of `team1` or `team2`)

Notes:

- Lines starting with `#` are ignored.
- Numeric legacy values are also accepted by parser:
  - `-1` -> `PENDING`
  - `0` -> `NR`
  - `1` -> `team1` win
  - `2` -> `team2` win

### h2h.txt

Format is a labeled matrix for easy editing:

```text
TEAM MI CSK RCB KKR RR DC PBKS SRH GT LSG
MI   0  21  19  25  15 17 18   10  5  6
CSK  19 0   21  21  16 20 17   15  4  3
...
```

Rules:

- First row is column header (`TEAM` + 10 team labels)
- Each next row starts with row team label + 10 integers
- Lines starting with `#` are ignored
- Exactly 10 team rows are required

## Build

Use any C++17 compiler.

### Windows (g++)

```powershell
g++ -std=c++17 -O2 predictor.cpp -o predictor.exe
g++ -std=c++17 -O2 temp.cpp -o temp.exe
```

## Run

From project root:

```powershell
./predictor.exe
./temp.exe
```

Each run prints:

- Parsed match list
- Current points table
- Remaining matches
- Pairwise probabilities
- Final playoff qualification probabilities
- `Time taken: <ms> ms`

## API Endpoint

A lightweight API server is available in `api_server.py`.

Start it from project root:

```powershell
python api_server.py
```

The server listens on port `8000` by default (override with environment variable `PORT`).

Available endpoints:

- `GET /health` -> simple health check
- `GET /probabilities` -> returns latest snapshot from `probabilities.txt`

`/probabilities` behavior:

- If `remainingMatches > 27`, returns status `unfeasible` with message `unfeasible to compute at the moment`
- Otherwise returns:
  - `teamOrder`
  - `probabilities` (same fixed order as predictor/temp)
  - `mappedProbabilities` (team -> probability)
  - `lastUpdated`, `remainingMatches`, `status`

## Nightly Orchestration

Use `nightly_job.py` to run backend workflow in one step:

1. Run `refresh_ipl_data.py`
2. Count remaining matches from `matches.txt`
3. If `remainingMatches > 27`, write unfeasible snapshot to `probabilities.txt`
4. Otherwise run predictor executable to compute and store probabilities

Run manually:

```powershell
python nightly_job.py
```

Optional threshold override:

```powershell
python nightly_job.py --threshold 27
```

For deployment, schedule this script at 1am server time (Task Scheduler on Windows or cron/systemd timer on Linux).

## GitHub Actions Nightly Publish

You can run the nightly backend flow on GitHub Actions and publish the latest snapshot directly into your frontend repo.

Workflow file:

- `.github/workflows/nightly-publish-frontend.yml`

What it does nightly:

1. Builds `predictor.cpp` on Ubuntu runner
2. Runs `nightly_job.py`
3. Builds frontend payload JSON via `build_frontend_payload.py`
4. Clones frontend repo and updates payload file
5. Commits and pushes only if content changed

Required GitHub Secrets (in backend repo):

- `FRONTEND_REPO`: `<owner>/<repo>` for frontend repository
- `FRONTEND_REPO_PAT`: Personal access token with repo write permission to frontend repository

Optional GitHub Variables (in backend repo):

- `FRONTEND_BRANCH` (default: `main`)
- `FRONTEND_DATA_PATH` (default: `src/data/playoff_snapshot.json`)

Schedule:

- Default cron is `30 19 * * *` (1:00 AM IST)
- Adjust cron if your timezone differs

## How Probability Is Computed

For team A vs team B:

```text
P(A beats B) = (H2H[A][B] + 1) / (H2H[A][B] + H2H[B][A] + 2)
```

This is Laplace smoothing on H2H outcomes.

## Troubleshooting

If input parsing fails:

- Verify team labels are valid
- Verify each `matches.txt` row has 4 tokens
- Verify `h2h.txt` has header + 10 complete rows
- Ensure winner team in a row matches one of the two teams in that row

The programs print line-specific validation errors to help fix formatting issues quickly.
