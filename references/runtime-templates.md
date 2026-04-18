# Runtime Templates — Reflections v1.4.0

Reflections preserves the same reflection/scoring role as Auto-Dream, uses memory-core-safe long-term surfaces, and applies profile-driven admission before durable promotion.

Defines the runtime artifacts, schemas, paths, and initialization model for Reflections.
Runtime prompts say how the run behaves. This document defines what the run produces.

---

## Path Model

### Resolution Rules

All paths are resolved dynamically at runtime. No hardcoded absolute paths in execution logic.

| Root | Resolution | Purpose |
|------|-----------|---------|
| `SKILL_ROOT` | Parent of `runtime/` (resolved by the prompt at execution time) | Installed skill location |
| `WORKSPACE_ROOT` | Current working directory | Live workspace with memory files |
| `TELEMETRY_ROOT` | Resolution ladder (see below) | Observability output |
| `SCRIPTS_DIR` | `$SKILL_ROOT/scripts` | Derived from SKILL_ROOT |

### Telemetry Root Resolution Ladder

```
1. Explicit CLI flag (--telemetry-dir)
2. REFLECTIONS_TELEMETRY_ROOT env var
3. MEMORY_TELEMETRY_ROOT env var
4. ~/.openclaw/telemetry fallback
```

### Workspace vs Telemetry Separation

| Plane | Root | Contains |
|-------|------|----------|
| **Workspace runtime** | `<workspace>/` | RTMEMORY.md, PROCEDURES.md, memory/, episodes/, runtime/reflections-metadata.json |
| **Observability** | `<telemetry-root>/` | memory-log-YYYY-MM-DD.jsonl (machine-readable, append-only) |

These are separate planes. Do not store telemetry in the workspace. Do not store live memory state in the telemetry root.

### Timestamp Discipline

| Field | Rule |
|-------|------|
| `timestamp` | Local timezone-aware ISO 8601 with numeric offset — primary for human-facing use |
| `timestamp_utc` | UTC ISO 8601 with Z suffix — companion for machine correlation |

The local timestamp is resolved from the host system's configured timezone at runtime. `append_memory_log.py` calls `datetime.now().astimezone()` which uses the host's `TZ` environment variable or OS timezone setting. If the host timezone must be overridden, set `TZ` before invoking the script.

### Reporting Rule

Notifications and chat reports use local time only. Machine telemetry includes both local and UTC for observability and correlation.

---

## Unified Memory Telemetry Log

### Target

```
TELEMETRY_ROOT/memory-log-YYYY-MM-DD.jsonl
```

One JSON line per Reflections run. Daily-sharded by local date. Append-only, never modified. Written unconditionally regardless of notification or reporting settings.

Every cron fire produces a telemetry event — including skipped runs where no modes are due. Skipped runs use `event: "run_skipped"` and `status: "skipped"`. A skipped run is a valid outcome, not a failure.

### Writer

Telemetry vocabulary is **mode-aware** — field names reflect actual branch behavior:

| Flow | Required detail fields | Optional |
|------|------------------------|----------|
| **First-reflection** (bypasses all gates) | `logs_scanned`, `entries_extracted`, `entries_consolidated` | — |
| **Parity flow** (`strictMode: false`, personal-assistant default) | `logs_scanned`, `entries_extracted`, `entries_consolidated` | `logs_marked_consolidated`, `writes.*`, `duration_ms` |
| **Strict flow, durability disabled** (`strictMode: true`, `durability.enabled: false`) | `logs_scanned`, `entries_extracted`, `entries_qualified`, `entries_deferred`, `entries_promoted` | `logs_marked_consolidated`, `writes.*`, `duration_ms` |
| **Strict flow, durability enabled** (`strictMode: true`, `durability.enabled: true`, business-employee default in v1.2.0+) v1.3.0 route set | `logs_scanned`, `entries_extracted`, `entries_qualified`, `entries_deferred`, `entries_durable_promoted`, `entries_durable_merged`, `entries_durable_compressed`, `entries_durable_deferred`, `entries_durable_rejected` | `logs_marked_consolidated`, `writes.*`, `duration_ms` |

**Parity flow example (personal-assistant):**

```bash
python3 $SCRIPTS_DIR/append_memory_log.py \
  --telemetry-dir $TELEMETRY_ROOT \
  --status ok \
  --event run_completed \
  --profile personal-assistant \
  --mode scheduled \
  --agent-id main \
  --details-json '{"logs_scanned": 7, "entries_extracted": 12, "entries_consolidated": 12}'
```

**Strict flow example (business-employee, durability enabled — v1.3.0+):**

```bash
python3 $SCRIPTS_DIR/append_memory_log.py \
  --telemetry-dir $TELEMETRY_ROOT \
  --status ok \
  --event run_completed \
  --profile business-employee \
  --mode scheduled \
  --agent-id main \
  --details-json '{"logs_scanned": 3, "entries_extracted": 14, "entries_qualified": 6, "entries_deferred": 8, "entries_durable_promoted": 2, "entries_durable_merged": 1, "entries_durable_compressed": 1, "entries_durable_deferred": 1, "entries_durable_rejected": 1}'
```

Note: in a v1.3.0 strict+durability run, `entries_qualified` + `entries_deferred` sum to `entries_extracted` (gate partition). The five `entries_durable_*` buckets partition the semantic-review set (qualified candidates + rescue-promoted deferreds). `entries_durable_promoted` counts new durable nodes written; `entries_durable_merged` counts reinforcements of existing nodes; `entries_durable_compressed` counts trend-node upserts.

**Strict flow example (business-employee, durability disabled — legacy or opt-out):**

```bash
python3 $SCRIPTS_DIR/append_memory_log.py \
  --telemetry-dir $TELEMETRY_ROOT \
  --status ok \
  --event run_completed \
  --profile business-employee \
  --mode scheduled \
  --agent-id main \
  --details-json '{"logs_scanned": 3, "entries_extracted": 14, "entries_qualified": 6, "entries_deferred": 8, "entries_promoted": 5}'
```

Note: `entries_qualified` is the gate output; `entries_promoted` is qualified minus those suppressed via the deferred store. In the absence of deferred-store collisions they are equal, but business flows with prior-cycle deferrals will see `entries_promoted < entries_qualified`.

On error:

```bash
python3 $SCRIPTS_DIR/append_memory_log.py \
  --telemetry-dir $TELEMETRY_ROOT \
  --status error \
  --event run_failed \
  --error "Config file not found"
```

### Event Schema (strict flow, durability enabled — v1.3.0+ business-employee default)

```json
{
  "timestamp": "2026-04-18T13:15:22+08:00",
  "timestamp_utc": "2026-04-18T05:15:22Z",
  "domain": "memory",
  "component": "reflections.consolidator",
  "event": "run_completed",
  "run_id": "refl-2026-04-18T13-15-22-xyz789",
  "status": "ok",
  "agent": "main",
  "profile": "business-employee",
  "mode": "scheduled",
  "details": {
    "logs_scanned": 3,
    "logs_marked_consolidated": 2,
    "entries_extracted": 14,
    "entries_qualified": 6,
    "entries_deferred": 8,
    "entries_durable_promoted": 2,
    "entries_durable_merged": 1,
    "entries_durable_compressed": 1,
    "entries_durable_deferred": 1,
    "entries_durable_rejected": 1,
    "writes": {
      "rtmemory": 2,
      "procedures": 0,
      "episodes": 0,
      "trends": 1,
      "index_updates": 4
    },
    "duration_ms": 5142
  }
}
```

### Event Schema (strict flow, durability disabled — legacy or opt-out)

```json
{
  "timestamp": "2026-04-16T03:15:22+08:00",
  "timestamp_utc": "2026-04-15T19:15:22Z",
  "domain": "memory",
  "component": "reflections.consolidator",
  "event": "run_completed",
  "run_id": "refl-2026-04-16T03-15-22-abc123",
  "status": "ok",
  "agent": "main",
  "profile": "business-employee",
  "mode": "scheduled",
  "details": {
    "logs_scanned": 3,
    "logs_marked_consolidated": 2,
    "entries_extracted": 14,
    "entries_qualified": 6,
    "entries_deferred": 8,
    "entries_promoted": 5,
    "writes": {
      "rtmemory": 3,
      "procedures": 1,
      "episodes": 1,
      "index_updates": 5
    },
    "duration_ms": 4821
  }
}
```

### Event Schema (parity flow example)

```json
{
  "timestamp": "2026-04-16T03:15:22+08:00",
  "timestamp_utc": "2026-04-15T19:15:22Z",
  "domain": "memory",
  "component": "reflections.consolidator",
  "event": "run_completed",
  "run_id": "refl-2026-04-16T03-15-22-def456",
  "status": "ok",
  "agent": "main",
  "profile": "personal-assistant",
  "mode": "scheduled",
  "details": {
    "logs_scanned": 7,
    "logs_marked_consolidated": 7,
    "entries_extracted": 12,
    "entries_consolidated": 12,
    "writes": {
      "rtmemory": 8,
      "procedures": 2,
      "episodes": 2,
      "index_updates": 12
    },
    "duration_ms": 3142
  }
}
```

### Event Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timestamp` | string | yes | Local timezone-aware ISO 8601 with numeric offset — used for human-facing observability and local reporting |
| `timestamp_utc` | string | yes | Canonical UTC ISO 8601 with Z suffix — used for machine correlation across systems |
| `domain` | string | yes | Always `"memory"` for this log |
| `component` | string | yes | `"reflections.consolidator"` |
| `event` | string | yes | Event type: `run_completed`, `run_skipped`, `run_failed` |
| `run_id` | string | yes | Deterministic ID derived from timestamp |
| `status` | string | yes | `"ok"`, `"skipped"`, or `"error"` |
| `agent` | string | yes | Agent identifier (default: `"main"`) |
| `profile` | string | yes | Active profile: `"personal-assistant"` or `"business-employee"` |
| `mode` | string | yes | Run mode: `"scheduled"`, `"manual"`, `"first-reflection"` |
| `details` | object | no | Run metrics (see below) |
| `error` | string | no | Error message when `status` is `"error"` |

### Details Object (when present)

| Field | Type | Flow | Description |
|-------|------|------|-------------|
| `logs_scanned` | number | all | Daily logs checked |
| `logs_marked_consolidated` | number | all | Logs marked with consolidated comment |
| `entries_extracted` | number | all | Total entries extracted from logs |
| `entries_consolidated` | number | parity / first-reflection | Entries written to durable surfaces (parity: equals `entries_extracted`; first-reflection: bypasses all gates by design) |
| `entries_qualified` | number | strict | Entries that passed quality gates |
| `entries_deferred` | number | strict | Entries that failed the gate and were recorded in the deferred store |
| `entries_promoted` | number | strict (durability disabled) | Qualified entries actually written (= `entries_qualified` minus any suppressed via prior-cycle deferred-store collisions) |
| `entries_durable_promoted` | number | strict (durability enabled, v1.2.0+) | Candidates that durability.py routed `promote` (including rescue-promoted deferreds). New durable nodes written to RTMEMORY/PROCEDURES/episodes. |
| `entries_durable_merged` | number | strict (durability enabled, v1.3.0+) | Candidates that durability.py routed `merge`. Reinforced existing durable nodes via `index.py --reinforce`. No new surface entries. |
| `entries_durable_compressed` | number | strict (durability enabled, v1.3.0+) | Candidates that durability.py routed `compress`. Upserted trend nodes via `index.py --compress-trend` (reinforced an existing trend or created a new one). |
| `entries_durable_deferred` | number | strict (durability enabled, v1.2.0+) | Candidates that durability.py routed `defer` (unresolved duplicates, borderline net scores). Recorded in the deferred store. |
| `entries_durable_rejected` | number | strict (durability enabled, v1.2.0+) | Candidates that durability.py routed `reject` (hard-suppress triggers or net below defer threshold). Discarded, not persisted. |
| `writes.rtmemory` | number | all | Entries written to RTMEMORY.md |
| `writes.trends` | number | strict (durability enabled, v1.3.0+) | Trend nodes created or reinforced via `index.py --compress-trend` |
| `writes.procedures` | number | all | Entries written to PROCEDURES.md |
| `writes.episodes` | number | all | Entries written to episodes |
| `writes.index_updates` | number | all | Index entries added or updated |
| `duration_ms` | number | all | Total run duration in milliseconds |

---

## Human-Readable Reflection Log

### Target

```
<workspace>/memory/.reflections-log.md
```

Append-only markdown log of reflection reports. One report section per run. This is a human-readable surface, not canonical telemetry.

### Report Template

```markdown
## Reflection Report -- YYYY-MM-DD HH:MM (local time)

### Mode Dispatch
- Modes fired: {list}
- Gate results: {QUALIFIED}/{TOTAL} qualified
  - rem: {n} | deep: {n} | core: {n}
- Deferred: {DEFERRED} entries

### Stats
- Scanned: N files | New: N | Updated: N | Pruned: N
- RTMEMORY.md: N lines | Episodes: N | Procedures: N entries

### Health: XX/100
- Freshness: XX% | Coverage: XX% | Coherence: XX% | Efficiency: XX% | Reachability: XX%

### Insights
- [Pattern] <observation>
- [Trend] <pattern>
- [Gap] <missing area>

### Changes
- [New] (via {mode}) <description>
- [Updated] (via {mode}) <description>
- [Archived] <description>

### Suggestions
- <actionable suggestion>
```

---

## Shared Runtime State

### Target

```
<workspace>/runtime/memory-state.json
```

Shared runtime state file, namespaced by package. Multiple packages (Reflections, truth-control, etc.) store their state under separate top-level keys. This file is merge-safe and not owned exclusively by Reflections.

### Reflections Namespace

```json
{
  "reflections": {
    "reporting": {
      "sendReport": false,
      "delivery": {
        "channel": "last",
        "to": null
      }
    }
  }
}
```

### Reporting Rules

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `reflections.reporting.sendReport` | boolean | `false` | Controls whether chat notification is sent after a run |
| `reflections.reporting.delivery.channel` | string | `"last"` | Delivery channel for notifications |
| `reflections.reporting.delivery.to` | string/null | `null` | Explicit delivery target (null = use channel default) |

### Behavior

- `sendReport: true` — send chat notification after the run
- `sendReport: false` — skip chat notification
- File missing, unreadable, or malformed — default to `sendReport: false`
- Field absent — default to `sendReport: false`

**`sendReport` controls chat delivery only.** It does not control:
- Whether telemetry is written (always written)
- Whether run artifacts are produced (always produced)
- Whether the run is considered complete (always completes)

### Initialization

Do not use `cat >` to write this file (destroys other namespaces). Use a safe merge pattern:
- Create if file is missing
- Merge namespace if file exists but `reflections` key is absent
- Skip if namespace already present
- Preserve all other namespaces unconditionally

---

## Reflections Configuration

### Target

```
$CONFIG_PATH (default: ~/.openclaw/reflections/reflections.json)
```

### Schema

See `references/memory-template.md` for the full configuration schema including mode thresholds, profile presets, and field reference.

---

## Memory Index

### Target

```
<workspace>/runtime/reflections-metadata.json
```

### Schema

See `references/memory-template.md` for the full v1.0.0 index schema including entry fields, stats block, and health history.

---

## Initialization Model

First-time setup creates:

| Artifact | Location | Created By |
|----------|----------|-----------|
| `reflections.json` | `$CONFIG_PATH` (default: `~/.openclaw/reflections/`) | INSTALL.md step 4 |
| `RTMEMORY.md` | `<workspace>/` | INSTALL.md step 4 |
| `runtime/reflections-metadata.json` | `<workspace>/runtime/` | INSTALL.md step 4 |
| `PROCEDURES.md` | `<workspace>/` | INSTALL.md step 4 |
| `memory/.reflections-log.md` | `<workspace>/memory/` | INSTALL.md step 4 |
| `memory/.reflections-archive.md` | `<workspace>/memory/` | INSTALL.md step 4 |
| `episodes/` | `<workspace>/` | INSTALL.md step 4 |
| Cron job | Host cron system | INSTALL.md step 6 |

Telemetry log files are created on first write by `append_memory_log.py`. No pre-initialization needed.
