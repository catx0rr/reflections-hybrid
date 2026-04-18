# Reflections — Installation and Setup Guide

Single authoritative guide for installing, configuring, and bootstrapping Reflections. This is the agent-facing setup authority.

---

## Path Terminology

| Variable | Meaning |
|----------|---------|
| `SKILLS_PATH` | Parent directory containing all installed skills |
| `SKILL_ROOT` | The Reflections repo directory itself: `$SKILLS_PATH/reflections` |
| `SKILL.md` | Located at `$SKILL_ROOT/SKILL.md` — the manual-use skill file |
| `WORKSPACE_ROOT` | The active workspace root (current working directory) |

---

## Prerequisites

- Python 3.9+
- Git
- OpenClaw installed with a workspace

---

## Step 1: Verify Installation

If the operator ran `install.sh`, Reflections is already cloned and the workspace topology is initialized. Verify:

```bash
ls "$SKILL_ROOT/SKILL.md"
```

If the skill is not installed, the operator should run `install.sh` first (see README.md).

### Manual clone (if install.sh was not used)

```bash
export SKILL_PARENT="$HOME/.openclaw/workspace/skills"
export SKILL_ROOT="$SKILL_PARENT/reflections"
mkdir -p "$SKILL_PARENT"
git clone https://github.com/catx0rr/reflections.git "$SKILL_ROOT"
```

---

## Step 2: Register `extraDirs` (if needed)

Skip this step if you installed into the default workspace skill root.

```bash
openclaw config set skills.load.extraDirs "[
  \"$SKILL_PARENT\"
]" --strict-json
```

---

## Step 3: Select Agent Profile

**Check for pre-selected profile first:**

If the environment variable `REFLECTIONS_PROFILE` is set, use that value without prompting:

```bash
# Non-interactive (fleet rollout / automation)
export REFLECTIONS_PROFILE=personal-assistant
# or
export REFLECTIONS_PROFILE=business-employee
```

If `REFLECTIONS_PROFILE` is not set, **ask the operator which profile to use:**

| Profile | File | Best for |
|---------|------|----------|
| `personal-assistant` | `profiles/personal-assistant.md` | Personal assistants, family assistants, butler/concierge, home-automation agents |
| `business-employee` | `profiles/business-employee.md` | Supervisor/owner DM, small GC teams, bounded operational workflows |

Read the selected profile to understand the recommended thresholds and markers.

**Home-automation assistants use the `personal-assistant` profile by default.**

---

## Step 4: Initialize Directories and Files

If the operator ran `install.sh`, directories and canonical files may already exist. Only create what is missing.

Working Directory: the active workspace root.

```bash
mkdir -p ~/.openclaw/reflections
mkdir -p episodes
mkdir -p runtime
```

### Create Configuration

Create `reflections.json` using the preset from the selected profile.

**For personal-assistant profile:**

Write to `~/.openclaw/reflections/reflections.json` using the preset from `profiles/personal-assistant.md`.

**For business-employee profile:**

Write to `~/.openclaw/reflections/reflections.json` using the preset from `profiles/business-employee.md`.

See `references/memory-template.md` for full JSON presets and field reference.

**If updating an existing install:** preserve existing `timezone`, `notificationLevel`, `instanceName`, and `lastRun` values. Do not silently overwrite custom thresholds unless the operator explicitly asks to reprofile/reset.

### Initialize Memory Files

Ensure the following files exist (create from `references/memory-template.md` templates if missing):

- `RTMEMORY.md`
- `runtime/reflections-metadata.json`
- `PROCEDURES.md`
- `memory/.reflections-log.md`
- `memory/.reflections-archive.md`

### Initialize Shared Runtime State

Ensure `$WORKSPACE_ROOT/runtime/memory-state.json` exists and contains the Reflections reporting namespace. This is a shared file — do not overwrite it. Merge the namespace if the file already exists.

**Default reporting intent:** The default namespace below enables reporting (`sendReport: true`) with `delivery.channel: "last"` so that the Reflections report is sent back to the operator on the last active chat channel unless explicitly changed. The operator is the intended recipient of the default report.

```bash
mkdir -p "$WORKSPACE_ROOT/runtime"
```

If `$WORKSPACE_ROOT/runtime/memory-state.json` does not exist, create it with:

```json
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
```

If `$WORKSPACE_ROOT/runtime/memory-state.json` already exists but does not contain a `reflections` key, merge the `reflections` namespace into the existing file using the default above. Preserve all other namespaces unconditionally. Do not use `cat >` to overwrite.

If the `reflections` key already exists, skip — do not overwrite existing operator routing or reporting state.

---

## Step 5: Resolve Skill Path

Before creating the cron, resolve the actual installed path of the Reflections skill so the cron payload uses an absolute path — not a hardcoded relative one.

### 5a. Try standard skill roots first

```bash
for root in \
  "$HOME/.openclaw/workspace/skills" \
  "$HOME/.openclaw/workspace/.agents/skills" \
  "$HOME/.agents/skills" \
  "$HOME/.openclaw/skills"
do
  if [ -f "$root/reflections/runtime/reflections-prompt.md" ]; then
    export SKILL_ROOT="$root/reflections"
    break
  fi
done
```

### 5b. If not found, check configured `extraDirs`

```bash
if [ -z "${SKILL_ROOT:-}" ]; then
  for root in $(openclaw config get skills.load.extraDirs --json 2>/dev/null | python3 -c "import json,sys; [print(d) for d in json.load(sys.stdin)]" 2>/dev/null); do
    if [ -f "$root/reflections/runtime/reflections-prompt.md" ]; then
      export SKILL_ROOT="$root/reflections"
      break
    fi
  done
fi
```

### 5c. Fail if still unresolved

```bash
if [ -z "${SKILL_ROOT:-}" ] || [ ! -f "$SKILL_ROOT/runtime/reflections-prompt.md" ]; then
  echo "Could not locate reflections skill directory."
  echo "Install the skill first or ensure skills.load.extraDirs includes its parent root."
  exit 1
fi

echo "Using SKILL_ROOT=$SKILL_ROOT"
```

---

## Step 6: Create Cron Job

A single cron job runs the recurring prompt on a profile-driven cadence. Mode dispatch logic is inside the prompt itself — the cron simply fires the prompt at the configured wake slots.

### 6.1 Resolve cadence from the selected profile

Read `dispatchCadence` from the resolved `reflections.json`:

```bash
DISPATCH_CADENCE=$(python3 -c "import json; print(json.load(open('$CONFIG_PATH')).get('dispatchCadence',''))")

if [ -z "$DISPATCH_CADENCE" ]; then
  echo "ERROR: dispatchCadence is required in reflections.json. See references/memory-template.md for the profile preset that must be written at install time." && exit 1
fi
```

**Profile defaults:**

| Profile | `dispatchCadence` | Wake slots (local) |
|---------|-------------------|--------------------|
| `personal-assistant` | `30 4,10,16,22 * * *` | 04:30, 10:30, 16:30, 22:30 |
| `business-employee` | `30 5,12,18,22 * * *` | 05:30, 12:30, 18:30, 22:30 |

Cadences are intentionally different so two profiles co-hosted on the same machine don't fire at the same minute. Operators can override `dispatchCadence` in `reflections.json` for bespoke schedules.

### 6.2 Construct the cron payload

Use the resolved `$SKILL_ROOT` and `$DISPATCH_CADENCE` to build the cron job:

```
name: "reflections-consolidation"
schedule: { kind: "cron", expr: "<DISPATCH_CADENCE>", tz: "<timezone from reflections.json>" }
payload: {
    kind: "agentTurn",
    message: "Run auto memory consolidation.\n\nRead <RESOLVED_SKILL_ROOT>/runtime/reflections-prompt.md and follow every step strictly.\n\nConfig: <RESOLVED_CONFIG_PATH>\nWorking directory: <RESOLVED_WORKSPACE_PATH>"
    timeoutSeconds: 1200
}
sessionTarget: "isolated"
delivery: { mode: "announce", channel: <last channel the operator used>, to: <the operator specific id of last channel used> }
```

Replace `<DISPATCH_CADENCE>`, `<RESOLVED_SKILL_ROOT>`, and `<RESOLVED_WORKSPACE_PATH>` with fully resolved absolute values. No `~`, no `$HOME`, no placeholders in the created cron payload.

Only the **cadence** varies by profile. The payload (prompt path, config path, workspace path, session target, timeout, delivery model) is unchanged.

---

## Step 7: Run First Reflection

After setup is complete, DO NOT wait for the cron schedule. Run the first consolidation immediately:

1. Read `runtime/first-reflections-prompt.md`
2. Execute every step in the current session (not isolated — the operator should see it happen)
3. First Reflection bypasses quality gates — consolidates everything to bootstrap the memory
4. Follow the output report template as a rule when reporting

---

## Prompt Ownership

After setup, two prompts govern runtime behavior:

| Prompt | Role | When |
|--------|------|------|
| `runtime/first-reflections-prompt.md` | One-time bootstrap | Run once during initial setup (Step 7) |
| `runtime/reflections-prompt.md` | Recurring cron executor | Fired by cron 4x daily after setup |

The cron job always points to `runtime/reflections-prompt.md`. The first-reflections prompt is a one-time run.

---

## Step 8: Verify

- [ ] Profile selected and `reflections.json` contains `"profile"` field
- [ ] Cron job created and enabled
- [ ] `~/.openclaw/reflections/reflections.json` exists with profile-specific mode settings
- [ ] `RTMEMORY.md` exists with section headers
- [ ] `runtime/reflections-metadata.json` exists
- [ ] `PROCEDURES.md` exists
- [ ] `memory/.reflections-log.md` exists
- [ ] First consolidation has run successfully

---

## Boundary Statement

Reflections writes to:
- `RTMEMORY.md` — reflective long-horizon continuity
- `PROCEDURES.md` — reusable workflows and operating patterns
- `episodes/*.md` — bounded event/project narratives
- `runtime/reflections-metadata.json` — consolidation metadata and health stats
- `memory/.reflections-log.md` — human-readable consolidation cycle reports
- `TELEMETRY_ROOT/memory-log-YYYY-MM-DD.jsonl` — unified machine telemetry

Reflections reads from:
- Daily logs (`memory/YYYY-MM-DD.md`)
- Its own config (`~/.openclaw/reflections/reflections.json`)

Reflections does not own:
- `MEMORY.md` (owned by memory-core)
- Active recall, promotion, or dreaming (owned by the host memory pipeline)
- Wiki compilation (owned by memory-wiki, if installed)
- Agent identity or user profile surfaces (canonical in IDENTITY.md, USER.md)

---

## Step 9: Cleanup

Remove non-runtime files from the installed skill directory:
- [ ] `.git`
- [ ] `LICENSE`
- [ ] `README.md`
- [ ] `install.sh`
- [ ] `INSTALL.md`

---

## Important Notes

- The install location of the skill is **operator-chosen**
- Prompts **discover the skill location dynamically** at runtime
- No external dependencies beyond Python 3.9+ and OpenClaw
- Runtime config is stored at `~/.openclaw/reflections/reflections.json`
- Telemetry surfaces are defined in `references/runtime-templates.md`
- Full operational reference in `references/skill-reference.md`
