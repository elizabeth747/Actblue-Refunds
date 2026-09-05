#!/bin/bash
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

pip install -q -r requirements.txt

# Regenerate accounts.yaml from persistent ACTBLUE_* environment variables
# (set in this environment's settings, so they survive container rebuilds)
# if it isn't already checked out. Credentials themselves
# (ACTBLUE_<KEY>_CLIENT_UUID / _CLIENT_SECRET) are read directly from the
# environment by actblue_refunds/accounts.py, so no .env file is needed as
# long as those variables are set at the environment level.
if [ ! -f accounts.yaml ]; then
  python3 - <<'PYEOF'
import os
import re

pattern = re.compile(r"^ACTBLUE_(.+)_CLIENT_UUID$")
keys = sorted(
    m.group(1).lower()
    for var in os.environ
    if (m := pattern.match(var))
)

if keys:
    lines = ["accounts:"]
    for key in keys:
        name = os.environ.get(f"ACTBLUE_{key.upper()}_NAME") or key.replace("_", " ").title()
        lines.append(f"  - key: {key}")
        lines.append(f"    name: \"{name}\"")
    with open("accounts.yaml", "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote accounts.yaml with {len(keys)} account(s) from environment variables.")
else:
    print("No ACTBLUE_*_CLIENT_UUID environment variables found; accounts.yaml not created.")
PYEOF
fi
