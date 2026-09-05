#!/usr/bin/env bash
# One-command demo: clean state, seeded rules, all four real contracts audited,
# dashboard open and ready to walk through.
#
#   ./scripts/demo.sh            # start backend (8000) + frontend (3000), run the audit, open the browser
#   ./scripts/demo.sh --check    # headless: boot backend, run the audit, print the radar, exit
#   ./scripts/demo.sh --stop     # stop servers started by this script
#
# Optional: put ANTHROPIC_API_KEY (or OPENAI_API_KEY) in backend/.env to run
# the LLM path. Without a key the deterministic engine runs alone.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
RUN="$ROOT/.demo"
mkdir -p "$RUN"

stop() {
  for f in "$RUN"/backend.pid "$RUN"/frontend.pid; do
    if [ -f "$f" ]; then kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"; fi
  done
  echo "demo servers stopped"
}
if [ "${1:-}" = "--stop" ]; then stop; exit 0; fi

# --- backend ---------------------------------------------------------------
if [ ! -x "$BACKEND/.venv/bin/python" ]; then
  echo "▸ creating backend virtualenv"
  python3 -m venv "$BACKEND/.venv"
  "$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt"
fi
if [ -f "$BACKEND/.env" ]; then set -a; . "$BACKEND/.env"; set +a; fi
export CERTO_SEED_MODE="${CERTO_SEED_MODE:-curated}"
unset DATABASE_URL   # demo always runs on the clean in-memory store

stop >/dev/null 2>&1 || true
echo "▸ starting backend on :8000 (clean in-memory state)"
( cd "$BACKEND" && exec .venv/bin/uvicorn main:app --port 8000 ) > "$RUN/backend.log" 2>&1 &
echo $! > "$RUN/backend.pid"
for i in $(seq 1 40); do
  if curl -sf localhost:8000/api/health >/dev/null; then break; fi
  sleep 0.25
done
curl -sf localhost:8000/api/health >/dev/null || { echo "backend failed to start; see $RUN/backend.log"; exit 1; }

# --- seed audit ------------------------------------------------------------
"$BACKEND/.venv/bin/python" - <<'PY'
import json, urllib.request
def get(p):  return json.load(urllib.request.urlopen("http://localhost:8000"+p))
def post(p,b):
    r=urllib.request.Request("http://localhost:8000"+p, data=json.dumps(b).encode(), headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(r))
h=get("/api/health"); print(f"▸ engine={h['mode']} rules={h['events']} store={h['store']}")
for d in get("/api/documents"):
    a=post("/api/audit/document", {"document": d})
    radar=" ".join(f"{s['jurisdiction']}={s['status']}({s['critical_count']}c/{s['warning_count']}w/{s['compliant_count']}p)" for s in a["radar"])
    print(f"▸ audited {d['title'][:58]!r}: {radar}")
PY

if [ "${1:-}" = "--check" ]; then stop; exit 0; fi

# --- frontend --------------------------------------------------------------
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "▸ installing frontend dependencies"
  ( cd "$FRONTEND" && npm install --silent )
fi
echo "▸ starting frontend on :3000"
( cd "$FRONTEND" && exec npm run dev ) > "$RUN/frontend.log" 2>&1 &
echo $! > "$RUN/frontend.pid"
for i in $(seq 1 80); do
  if curl -sf localhost:3000 >/dev/null; then break; fi
  sleep 0.5
done
echo "▸ dashboard: http://localhost:3000   (logs in $RUN/, stop with ./scripts/demo.sh --stop)"
if command -v open >/dev/null 2>&1; then open http://localhost:3000; fi
