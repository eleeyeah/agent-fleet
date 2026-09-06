#!/usr/bin/env bash
# Offline validation — everything that can be checked without the cluster:
#   1. shell script syntax
#   2. python syntax for all agents
#   3. YAML structural validity of every manifest / values file
#   4. unit tests for the fleet's pure logic
# The live Phase 0/1 gate criteria are in docs/PHASES.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== shell syntax"
for f in scripts/*.sh; do bash -n "$f" && echo "  ok $f"; done

echo "== python syntax"
python3 -m py_compile \
  agents/common/fleet_common/*.py agents/pm/app/*.py \
  agents/backend-dev/app/*.py agents/reviewer/app/*.py agents/tests/*.py
echo "  ok"

echo "== yaml manifests"
python3 - <<'EOF'
import sys, pathlib
try:
    import yaml
except ImportError:
    sys.path.insert(0, "/tmp/fleet-deps"); import yaml
bad = 0
for p in sorted(pathlib.Path(".").rglob("*.yaml")):
    if ".git" in p.parts:
        continue
    try:
        docs = list(yaml.safe_load_all(p.read_text()))
        assert any(d for d in docs), f"{p}: empty"
        print(f"  ok {p} ({len([d for d in docs if d])} docs)")
    except Exception as e:
        print(f"  FAIL {p}: {e}"); bad += 1
sys.exit(1 if bad else 0)
EOF

echo "== unit tests"
DEPS="${FLEET_DEPS:-/tmp/fleet-deps}"
export PYTHONPATH="$DEPS:agents/common:agents/pm/app:agents/backend-dev/app:agents/reviewer/app"
python3 -m pytest agents/tests -q

echo "ALL OFFLINE CHECKS PASSED"
