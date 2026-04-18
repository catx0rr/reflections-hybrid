#!/usr/bin/env bash
set -euo pipefail

# Reflections — Operator Install Script
#
# Installs the Reflections skill and initializes the workspace topology.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/catx0rr/reflections/main/install.sh | bash
#
# Override defaults:
#   CONFIG_ROOT="$HOME/.openclaw" \
#   WORKSPACE="$HOME/.openclaw/workspace" \
#   SKILLS_PATH="$HOME/.openclaw/workspace/skills" \
#   curl -fsSL https://raw.githubusercontent.com/catx0rr/reflections/main/install.sh | bash

REPO_URL="https://github.com/catx0rr/reflections.git"

CONFIG_ROOT="${CONFIG_ROOT:-$HOME/.openclaw}"
WORKSPACE="${WORKSPACE:-$HOME/.openclaw/workspace}"
SKILLS_PATH="${SKILLS_PATH:-$HOME/.openclaw/workspace/skills}"
SKILL_ROOT="$SKILLS_PATH/reflections"

echo "Reflections installer"
echo "---------------------"
echo "  CONFIG_ROOT:  $CONFIG_ROOT"
echo "  WORKSPACE:    $WORKSPACE"
echo "  SKILLS_PATH:  $SKILLS_PATH"
echo "  SKILL_ROOT:   $SKILL_ROOT"
echo ""

# ── A. Install/update the repo ──────────────────────────────────────

mkdir -p "$SKILLS_PATH"

if [ -d "$SKILL_ROOT/.git" ]; then
    echo "[repo] Existing installation found. Updating..."
    cd "$SKILL_ROOT"
    git pull --ff-only || {
        echo "Warning: fast-forward pull failed. Manual resolution may be needed."
        echo "Location: $SKILL_ROOT"
        exit 1
    }
    echo "[repo] Updated successfully."
elif [ -d "$SKILL_ROOT" ]; then
    echo "Error: Directory exists but is not a git repo: $SKILL_ROOT"
    echo "Remove it manually or choose a different SKILLS_PATH, then re-run."
    exit 1
else
    echo "[repo] Cloning Reflections..."
    git clone "$REPO_URL" "$SKILL_ROOT"
    echo "[repo] Cloned successfully."
fi

if [ ! -f "$SKILL_ROOT/SKILL.md" ]; then
    echo "Error: SKILL.md not found at $SKILL_ROOT/SKILL.md"
    echo "Installation may be incomplete."
    exit 1
fi

# ── B. Initialize workspace topology ────────────────────────────────

echo ""
echo "[init] Initializing workspace topology..."

mkdir -p "$CONFIG_ROOT/reflections"
mkdir -p "$WORKSPACE/episodes"
mkdir -p "$WORKSPACE/memory"
mkdir -p "$WORKSPACE/runtime"

# Curated root-level surfaces
if [ ! -f "$WORKSPACE/RTMEMORY.md" ]; then
    echo "[init] Creating RTMEMORY.md"
    echo "# RTMEMORY.md — Reflective Memory" > "$WORKSPACE/RTMEMORY.md"
    echo "" >> "$WORKSPACE/RTMEMORY.md"
    echo "_Last updated: $(date +%Y-%m-%d)_" >> "$WORKSPACE/RTMEMORY.md"
fi

if [ ! -f "$WORKSPACE/PROCEDURES.md" ]; then
    echo "[init] Creating PROCEDURES.md"
    echo "# Procedures — How I Do Things" > "$WORKSPACE/PROCEDURES.md"
    echo "" >> "$WORKSPACE/PROCEDURES.md"
    echo "_Last updated: $(date +%Y-%m-%d)_" >> "$WORKSPACE/PROCEDURES.md"
fi

# Trend surface (workspace root — v1.5.0)
if [ ! -f "$WORKSPACE/TRENDS.md" ]; then
    echo "[init] Creating TRENDS.md"
    {
        echo "# Trends"
        echo ""
        echo "_Observed patterns without stable method._"
        echo ""
        echo "---"
    } > "$WORKSPACE/TRENDS.md"
fi

# Runtime-owned surfaces
if [ ! -f "$WORKSPACE/runtime/reflections-metadata.json" ]; then
    echo "[init] Creating runtime/reflections-metadata.json"
    cat > "$WORKSPACE/runtime/reflections-metadata.json" <<'METAEOF'
{
  "version": "1.0.0",
  "lastDream": null,
  "entries": [],
  "stats": {
    "totalEntries": 0,
    "avgImportance": 0,
    "lastPruned": null,
    "healthScore": 0,
    "healthMetrics": {
      "freshness": 0,
      "coverage": 0,
      "coherence": 0,
      "efficiency": 0,
      "reachability": 0
    },
    "insights": [],
    "healthHistory": [],
    "gateStats": {
      "lastCycleQualified": 0,
      "lastCycleDeferred": 0,
      "lastCycleBreakdown": { "rem": 0, "deep": 0, "core": 0 }
    }
  }
}
METAEOF
fi

# Memory-plane surfaces
if [ ! -f "$WORKSPACE/memory/.reflections-log.md" ]; then
    echo "[init] Creating memory/.reflections-log.md"
    touch "$WORKSPACE/memory/.reflections-log.md"
fi

if [ ! -f "$WORKSPACE/memory/.reflections-archive.md" ]; then
    echo "[init] Creating memory/.reflections-archive.md"
    cat > "$WORKSPACE/memory/.reflections-archive.md" <<'ARCHEOF'
# Memory Archive

_Compressed entries that fell below importance threshold._

---

<!-- Format: [id] (created → archived) One-line summary -->
ARCHEOF
fi

# ── C. Initialize shared runtime state ──────────────────────────────

MEMORY_STATE="$WORKSPACE/runtime/memory-state.json"

if [ ! -f "$MEMORY_STATE" ]; then
    echo "[init] Creating runtime/memory-state.json (default: report to operator via last channel)"
    cat > "$MEMORY_STATE" <<'HARNEOF'
{
  "reflections": {
    "reporting": {
      "sendReport": true,
      "delivery": {
        "channel": "last",
        "to": null
      }
    }
  }
}
HARNEOF
elif ! python3 -c "import json,sys; d=json.load(open('$MEMORY_STATE')); sys.exit(0 if 'reflections' in d else 1)" 2>/dev/null; then
    echo "[init] Merging reflections namespace into existing memory-state.json (default: report to operator via last channel)"
    python3 -c "
import json, sys
with open('$MEMORY_STATE', 'r') as f:
    d = json.load(f)
d['reflections'] = {
    'reporting': {
        'sendReport': True,
        'delivery': {'channel': 'last', 'to': None}
    }
}
with open('$MEMORY_STATE', 'w') as f:
    json.dump(d, f, indent=2)
"
else
    echo "[init] memory-state.json already contains reflections namespace — preserving existing operator routing"
fi

# ── Done ────────────────────────────────────────────────────────────

echo ""
echo "Reflections installed and initialized."
echo ""
echo "  Skill root:  $SKILL_ROOT"
echo "  SKILL.md:    $SKILL_ROOT/SKILL.md"
echo "  Workspace:   $WORKSPACE"
echo ""
echo "Next step:"
echo "  Tell your agent to read INSTALL.md in the reflections skill directory."
echo ""
echo "  Example:"
echo "    \"Read INSTALL.md in $SKILL_ROOT and follow every step.\""
echo ""
