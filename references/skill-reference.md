# Reflections — Skill Reference (v1.4.0)

Reflections preserves the same reflection/scoring role as Auto-Dream, uses memory-core-safe long-term surfaces, and applies profile-driven admission before durable promotion.

Canonical reference for the Reflections consolidator's architecture, autonomous runtime behavior, configuration schema, script inventory, gating/scoring internals, and orchestration flow.

For manual operator use, see `SKILL.md`.
For installation and setup, see `INSTALL.md`.
For package overview, see `README.md`.

---

## Architecture Overview

See title one-liner.

It is not a plugin. It does not own active memory recall, promotion, or dreaming. See `README.md` for the full ownership boundary.

---

## Core Files

| File | Purpose | Mutability |
|------|---------|------------|
| `$CONFIG_PATH` (reflections.json) | Consolidation mode configuration | User-editable |
| `RTMEMORY.md` | Reflective long-horizon continuity (decisions, lessons, identity/relationship shifts) | Append, update, archive |
| `PROCEDURES.md` | Reusable workflows, tool usage, stable operating patterns | Append, update |
| `episodes/*.md` | Project narratives | Append only |
| `memory/TRENDS.md` (v1.3.0+) | Repeated reality/pattern (recurring ops conditions, accumulated symptom patterns) | Upsert per `trendKey` |
| `runtime/reflections-metadata.json` | Runtime entry metadata (v1.0.0 schema, trend entries have `memoryType: "trend"`) | Rebuilt each consolidation |
| `memory/.reflections-log.md` | Consolidation report log | Append only |
| `memory/.reflections-archive.md` | Low-importance compressed archive | Append only |

Optional: LCM plugin (Working Memory layer). If not installed, prompt the user:
> "Recommended: install the LCM plugin for working memory: `openclaw plugins install @martian-engineering/lossless-claw`"

Do not auto-install plugins or modify config.

---

## Runtime Profile

Reflections reads thresholds from the resolved `$CONFIG_PATH`.
Profile selection is setup-time only and is persisted in the `"profile"` field.
The gate logic reads config generically.

---

## Consolidation Modes

Four modes control **consolidation dispatch frequency** — how often the cron prompt fires extraction + consolidation. An entry's importance score is computed in every flow; its role differs by mode:

- **Parity mode** (`strictMode: false`, default for personal-assistant): importance is used **post-consolidation** for archival decisions (forgetting curve), not as a pre-consolidation blocker. All extracted candidates promote.
- **Strict mode** (`strictMode: true`, default for business-employee): importance is used **pre-consolidation** as a quality gate. The `minScore`/`minRecallCount`/`minUnique` thresholds per mode gate admission. In **strict-without-durability** (durability.enabled=false), only gate-qualified candidates proceed to consolidation; gate-deferred candidates are recorded in the deferred store. In **strict-with-durability** (v1.3.0, durability.enabled=true), gate_status is an intermediate signal — Step 1.8 then assigns the final `route` (`promote` / `merge` / `compress` / `defer` / `reject`), which may rescue-promote gate-deferred candidates that carry hard-promote semantic triggers. Step 2 dispatches per-route, not per gate_status alone.

**strictMode is profile-driven; personal-assistant defaults `false`, business-employee defaults `true`.**

Default thresholds vary by profile. The values below are the **personal-assistant** defaults. See `profiles/business-employee.md` for business defaults.

| Mode | Interval (elapsed-gate) | minScore | minRecallCount | minUnique | Purpose |
|------|-------------------------|----------|----------------|-----------|---------|
| `off` | Disabled | — | — | — | No consolidation |
| `core` | 24h | 0.72 | 2 | 1 | Daily sweep — full pass when due |
| `rem` | 6h | 0.85 | 2 | 2 | High-frequency — fast pass for hot logs |
| `deep` | 12h | 0.80 | 2 | 2 | Mid-frequency — catches warm logs with cross-day breadth |

Interval values are **hardcoded in `scripts/dispatch.py`** (`MODE_INTERVALS = {rem: 6, deep: 12, core: 24}`), compared against each mode's `lastRun` timestamp. They are not configurable via `reflections.json`. The host cron cadence (when the prompt fires at all) is separately controlled by top-level `dispatchCadence`.

### Gate Definitions

- **minScore** — minimum `importance` score (0.0–1.0) computed from `base_weight * recency * reference_boost / 8.0`. See `references/scoring.md`.
- **minRecallCount** — minimum `referenceCount` in `runtime/reflections-metadata.json`. How many times this entry has been referenced across any context.
- **minUnique** — minimum uniqueness count. The meaning of "unique" depends on `uniqueMode`.

### uniqueMode

Controls how `minUnique` is evaluated:

| uniqueMode | Behavior |
|------------|----------|
| `day_or_session` | **(default)** Prefer `uniqueDayCount` when available, fall back to `uniqueSessionCount` |
| `day` | Use `uniqueDayCount` only |
| `session` | Use `uniqueSessionCount` only (legacy behavior) |
| `channel` | Use `uniqueChannelCount` only |
| `max` | Use the highest of day, session, and channel counts |

`day_or_session` is the default for both profiles. It allows day-based reinforcement — if the same truth is referenced on different days, it counts even if the sessions overlap. This is important for narrow-topology agents (personal assistants, home-automation) where the owner is the primary interaction source.

### Fast-path Markers

Entries with specific markers can bypass the regular AND gate through a softer fast-path check. The fast-path requires either:

- **Score + recall pass:** `importance >= fastPathMinScore AND referenceCount >= fastPathMinRecallCount`
- **Marker match:** entry marker is in `fastPathMarkers` list

`PERMANENT` still bypasses all gates unconditionally. Fast-path is a softer bypass for high-salience entries that don't quite meet the regular gate thresholds.

Available markers: `HIGH`, `PIN`, `PREFERENCE`, `ROUTINE`, `PROCEDURE`. Which markers are active depends on the profile preset written during setup.

### Mode Dispatch (Single Cron)

One cron runs 4 times daily at profile-driven slots (see `dispatchCadence`):
- **personal-assistant**: 04:30, 10:30, 16:30, 22:30 (`30 4,10,16,22 * * *`)
- **business-employee**: 05:30, 12:30, 18:30, 22:30 (`30 5,12,18,22 * * *`)

On each trigger, the consolidation prompt reads `reflections.json` and checks elapsed time since last run of each mode:

```
elapsed_since_last_rem  >= 6h  -> run rem gates on candidate entries
elapsed_since_last_deep >= 12h -> run deep gates on candidate entries
elapsed_since_last_core >= 24h -> run core gates on candidate entries
```

Multiple modes can fire in a single cycle (e.g., at 3 AM, all three may be due). Entries are deduplicated — if an entry passes `rem` gates, it is not re-processed by `core` in the same cycle.

### How Modes Stack

`rem` catches hot items fast. `deep` catches warm items at medium frequency. `core` catches everything else daily. Together they form a consolidation pipeline where the most important memories reach long-term storage fastest.

Entries that fail all gates remain in daily logs and will be re-evaluated on the next cycle. They are NOT deleted — they simply haven't qualified yet.

---

## Configuration Schema

### reflections.json

Location: resolved via `$CONFIG_PATH` (default: `~/.openclaw/reflections/reflections.json`)

See `references/memory-template.md` for the full JSON presets (both `personal-assistant` and `business-employee` profiles) and the complete field reference table.

### Changing Modes

Agent can update `reflections.json` on user request:

| Command | Action |
|---------|--------|
| "Set consolidation mode to core only" | Set `activeModes: ["core"]`, disable rem/deep |
| "Enable all consolidation modes" | Set `activeModes: ["core", "rem", "deep"]` |
| "Disable consolidation" | Set `activeModes: []` or set all modes `enabled: false` |
| "Lower rem threshold to 0.80" | Update `modes.rem.minScore` to 0.80 |

Always confirm changes with user before writing to conf.

---

## Consolidation Cycle Flow

Each consolidation runs in an isolated session (see `runtime/reflections-prompt.md`). The flow is **profile-driven**: personal-assistant runs the parity flow; business-employee runs the strict scored-promotion flow. `strictMode` in `reflections.json` selects the branch.

### Step 0: Load Config + Mode Dispatch
Read `reflections.json`. Check `lastRun` timestamps against current time. Determine which modes are due. Read `STRICT_MODE` and `SCAN_DAYS` (`scanWindowDays`) from config for use in later steps. If no modes are due, go to Step 0-B (Skip With Recall).

### Step 0-B: Smart Skip + Recall
Check if any unconsolidated daily logs exist in the last `SCAN_DAYS` (profile-driven: 7 for personal-assistant, 3 for business-employee; absent-field fallback `7`). All processed and no modes due → surface an old memory ("N days ago, you decided...") and show streak count. Never send a blank "nothing to do" message.

### Step 0.5: Snapshot BEFORE
Count RTMEMORY.md lines, decisions, lessons, open threads, total entries.

### Step 1: Collect
Read unconsolidated daily logs (last `SCAN_DAYS` — profile-driven). Extract decisions, operational context updates, progress, lessons, and todos into a candidate set at `$TMPDIR/reflections-candidates.json`.

### Step 1.2: Load deferred state (strict-mode only)
If `STRICT_MODE == true`, load the persisted deferred store via `deferred.py --all` as LLM context for semantic-dedup judgment in Step 2. Skipped in parity mode.

### Step 1.3: Annotate candidates (strict-mode only)
If `STRICT_MODE == true`, invoke `deferred.py --annotate --write-back`. This mutates the candidates file in place, writing on each candidate:
- `fingerprint` (rewording-stable identity, source + target_section scoped)
- `candidate_hash` (v1.1.2-compat exact-string identity)
- `deferred_status: "persisted" | "fresh"` — deterministic suppression verdict
- `deferred_matched_by: "existingId" | "fingerprint" | "candidate_hash" | null`

Skipped in parity mode.

### Step 1.5: Branch on strictMode
- `STRICT_MODE == false` → skip Step 1.6; candidates proceed directly to Step 2. This is the parity flow (upstream Auto-Dream Lite's consolidate-all behavior).
- `STRICT_MODE == true` → proceed to Step 1.6 (scored admission gate).

### Step 1.6: Score + Gate (strict-mode only)
1. `score.py --candidates ... --write-back` — compute `importance` for each candidate (recency fallback: lastReferenced → created → 0).
2. `gate.py --candidates ... --modes $MODE_CSV --write-back --emit-deferred $TMPDIR/reflections-deferred-new.json` — applies quality gates. Writes `gate_status: "qualified" | "deferred"`, `gate_promoted_by`, `gate_bypass`, `gate_fail_reasons` onto each candidate, and emits the deferred subset to a separate file in `deferred.py --append` schema.
3. `deferred.py --append $TMPDIR/reflections-deferred-new.json` — persists deferred records. The append payload comes from gate.py's emission; no LLM-constructed JSON is involved.

### Step 1.7: Durability Annotation (strict-mode AND durability.enabled)
**[LLM]** Semantic review of the candidate set. Scope is qualified candidates **plus** a rescue subset of structurally-deferred candidates (those with `gate_bypass` set, `marker in {HIGH, PERMANENT, PIN}`, or a high-meaning memory type — decision, lesson, obligation, relationship, identity, architecture). The LLM writes `$TMPDIR/reflections-durability.json` — one annotation record per in-scope candidate with the semantic flags that drive Step 1.8's router. The LLM does semantic judgment only; no routing happens here.

### Step 1.8: Durability Routing (strict-mode AND durability.enabled)
**[SCRIPT]** `durability.py --candidates ... --annotations ... --config ... --index ... --write-back --emit-defer-subset $TMPDIR/reflections-durability-deferred.json` — deterministic second-stage router. Writes `route`, `destination`, `durabilityScore`, `noisePenalty`, `promotionReason`, `memoryType`, `durabilityClass`, `mergeKey`, `trendKey`, `duplicateOfExisting`, `mergedInto` (v1.3.0), `promotedFromTrend` (v1.3.0), `compressionReason` (v1.3.0), `supportCount`, `durabilityComponents` onto each candidate. Emits defer-subset for `deferred.py --append` to persist.

Deterministic precedence (v1.3.0 full route set): hard-suppress → hard-promote (duplicates allowed; trend-to-durable link when trend promotion criteria met) → **merge** (resolved duplicate_of_existing, no hard-trigger) → defer (unresolved duplicate) → **compress** (trendKey on weak ops material) → net-score banding.

### Step 2: Consolidate (per-log)
Process daily logs one at a time. For each daily log, dispatch per-candidate based on the `route` field written by Step 1.8 (strict+durability mode) or fall back to legacy semantic routing (parity / strict-without-durability).

**Route-driven dispatch (strict+durability mode, v1.3.0):**
| `route` | Step 2 action |
|---------|--------------|
| `promote` | New durable node. Append to RTMEMORY/PROCEDURES/episodes per `destination`; call `index.py --add` with full durability field payload. |
| `merge` | Reinforce existing durable node (no surface write). Call `index.py --reinforce <mergedInto> --from $TMPDIR/merge.json`. |
| `compress` | Upsert trend node. Call `index.py --compress-trend <trendKey> --from $TMPDIR/trend.json`. Also update `memory/TRENDS.md` section. |
| `defer` | No Step 2 action — already persisted by `deferred.py --append` at end of Step 1.8. |
| `reject` | Discarded. No action. |

**Promotion eligibility (mode-aware):**
- **Parity mode** (`STRICT_MODE == false`): every candidate proceeds via legacy semantic routing. No `route` field present.
- **Strict mode, durability disabled** (`STRICT_MODE == true`, `durability.enabled == false`): promotion-eligible when `deferred_status != "persisted"` AND `gate_status == "qualified"` (behaves as v1.1.6). No `route` field present.
- **Strict mode, durability enabled** (business-employee default, v1.3.0): `route`-driven per the table above.

**Per-log marking (mode-aware):**
- **Parity mode**: mark `<!-- consolidated -->` immediately after a log's extractable entries have been successfully consolidated and indexed.
- **Strict mode**: mark `<!-- consolidated -->` when every extractable item from the log is either **promoted** (passed the gate this cycle) OR **deferred and recorded** in the persisted store (this cycle or any earlier cycle). A log with unreached items is left unmarked; the next cycle retries only the unhandled items.

### Step 2.5: Snapshot AFTER
Count the same metrics again after changes. Calculate deltas.

### Step 2.8: Stale Thread Detection
Scan Open Threads for items stale >14 days. Include top 3 in notification with context.

### Step 3: Evaluate + Archival
Compute 5-metric health score via `health.py`. Then run `score.py --index --check-archival` on the metadata to find entries eligible for the forgetting curve: >90 days unreferenced AND importance < 0.3, excluding PERMANENT and PIN. Archive eligible entries via `index.py --archive`.

### Step 3.5: Generate Report + Persist Stats
Append cycle report to `memory/.reflections-log.md` with change list, insights, and suggestions. Then persist `healthScore`, `healthMetrics`, `insights`, and cycle route counters to `runtime/reflections-metadata.json` via `index.py --update-stats` (bumps `lastDream` and appends to `healthHistory`).

### Step 4: Notify with Growth Metrics
Send a consolidation report showing:
- Which modes fired this cycle
- Consolidated count (entries consolidated from N logs)
- Before -> after comparison (entries, decisions, lessons)
- Cumulative growth ("142 -> 145 entries, +2.1%")
- Consolidation streak count
- Archived count (entries moved to archive this cycle via forgetting curve)
- Milestones when hit
- Top 3 stale reminders (if any)
- Weekly summary on Sundays

### Notification Principles
1. **Every notification must deliver value** -- never send empty "nothing happened" messages
2. **Show growth, not just changes** -- cumulative stats show the system evolving
3. **Surface forgotten context** -- stale thread reminders and old memory recalls
4. **Show consolidation activity** -- user sees what was added, updated, archived
5. **Celebrate milestones** -- streak counts and entry milestones build habit

---

## Deterministic Scripts

All arithmetic, threshold checks, date math, and graph algorithms are offloaded to Python scripts. The LLM orchestrates -- calling scripts, reading their JSON output, then making judgment calls where needed.

### Script Inventory

| Script | Purpose | When Called |
|--------|---------|-------------|
| `scripts/dispatch.py` | Mode dispatch -- which modes are due based on `lastRun` timestamps | Step 0 |
| `scripts/scan.py` | Find unconsolidated daily logs in the scan window | Step 0-A |
| `scripts/snapshot.py` | Count before/after metrics for RTMEMORY.md state | Step 0.5, Step 2.5 |
| `scripts/score.py --index --check-archival` | Score metadata entries; flag archival candidates | Step 3 |
| `scripts/index.py` | Index CRUD — add entries, assign IDs, update sessions, **reinforce existing entries (v1.3.0 merge)**, **compress-trend upsert (v1.3.0)**, archive | Step 2, Step 3 |
| `scripts/health.py` | Compute 5-metric health score with BFS reachability | Step 3 |
| `scripts/stale.py` | Detect stale Open Threads with exact day counts | Step 2.8 |
| `scripts/append_memory_log.py` | Append structured telemetry event to unified memory log | Post-flight |
| `scripts/score.py --candidates` | **(strictMode=true)** Enrich pre-consolidation candidates with importance | Default for business-employee; skipped in parity mode |
| `scripts/gate.py` | **(strictMode=true)** Apply quality gate thresholds to candidates; `--write-back` commits `gate_status`; `--emit-deferred` hands off to deferred.py | Default for business-employee; skipped in parity mode |
| `scripts/deferred.py` | **(strictMode=true)** Persisted deferred-candidate store CRUD + `--annotate` for deterministic suppression | Default for business-employee; skipped in parity mode |
| `scripts/durability.py` | **(strictMode=true AND durability.enabled=true)** Second-stage semantic router. v1.3.0 full route set: `promote` / `merge` / `compress` / `defer` / `reject`. Writes route + destination + `mergedInto`/`promotedFromTrend`/`compressionReason` onto candidates; emits defer subset for deferred.py | Default for business-employee in v1.2.0+; skipped in parity mode or when `durability.enabled == false` |

### What Stays LLM-Driven

| Operation | Why |
|-----------|-----|
| Extract insights from daily logs | Understanding meaning, not text |
| Semantic deduplication | "Set price to P5K" = "pricing at five thousand pesos" |
| Route to correct memory layer | Procedural? Episodic? Long-term? Requires judgment |
| Relation linking | Which entries are semantically connected |
| Insight generation | Pattern recognition across the full corpus |
| Report / notification writing | Natural language composition |

### Hybrid Consolidation Cycle Flow

```
CRON FIRES (4x daily: 5:30/12:00/18:30/22:30)
       |
       v
  scripts/dispatch.py            <- Python: which modes are due? (exit 0 idle or active)
       |
       v
  scripts/scan.py                <- Python: which daily logs need processing? (exit 0 idle or active)
       |
       v
  scripts/snapshot.py --save before  <- Python: count before-state
       |
       v
  LLM: Read logs, extract candidates   <- LLM: understand content, classify per log
       |
       v
  LLM: Consolidate per-log       <- LLM: semantic dedup + route (RTMEMORY / PROCEDURES / episodes)
       |
       v
  scripts/index.py               <- Python: assign IDs, update sessions, archive
       |
       v
  LLM: Mark log <!-- consolidated --> (IMMEDIATELY, per-log, before next log)
       |
       v
  scripts/stale.py               <- Python: detect stale threads
       |
       v
  scripts/health.py              <- Python: 5-metric health + BFS reachability
       |
       v
  scripts/score.py --check-archival  <- Python: flag entries for forgetting curve
       |
       v
  scripts/index.py --archive     <- Python: archive eligible entries
       |
       v
  scripts/snapshot.py --delta    <- Python: compute before/after deltas
       |
       v
  LLM: Generate insights + write report  <- LLM: compose consolidation report
       |
       v
  scripts/index.py --update-stats   <- Python: persist health + route counters
       |
       v
  scripts/dispatch.py --update   <- Python: write lastRun timestamps
       |
       v
  LLM: Notify via memory-state gate  <- Check sendReport before chat delivery
       |
       v
  scripts/append_memory_log.py   <- Python: write telemetry event (always unconditional)
```

**Strict-mode (profile-driven: personal-assistant=false, business-employee=true)** inserts `deferred.py --annotate` (Step 1.3), `score.py --candidates` + `gate.py --write-back --emit-deferred` (Step 1.6), and — when `durability.enabled == true` — `durability.py --write-back --emit-defer-subset` (Steps 1.7–1.8) between "extract candidates" and "Consolidate per-log". The branch is a first-class runtime step in `runtime/reflections-prompt.md`, not an appendix.

Step 2 dispatch is mode-aware:

| Mode | Step 2 dispatch |
|------|----------------|
| **Parity** (`strictMode: false`) | All extracted candidates proceed via legacy semantic routing. |
| **Strict-without-durability** (`strictMode: true`, `durability.enabled: false`) | Only candidates with `gate_status == "qualified"` AND `deferred_status != "persisted"` proceed. Matches v1.1.6 behavior. |
| **Strict-with-durability (v1.3.0)** | Route-aware. Each candidate dispatches per `route` field produced by Step 1.8: `promote` → write new durable node; `merge` → reinforce existing node via `index.py --reinforce`; `compress` → upsert trend node via `index.py --compress-trend`; `defer` → already persisted in Step 1.8, no Step 2 action; `reject` → discarded. Rescue-promoted deferreds (gate_status=deferred with route=promote via hard-promote trigger) DO proceed. gate_status alone is not the final filter — `route` is. |

---

## Runtime Prompts

| Prompt | Purpose |
|--------|---------|
| `runtime/reflections-prompt.md` | Recurring cron executor (compact prompt with mode dispatch) |
| `runtime/first-reflections-prompt.md` | First Reflection: post-install full scan (bypasses gates) |

---

## Reference Files

| File | Purpose |
|------|---------|
| `references/scoring.md` | Importance scoring, quality gates, forgetting curve, health score algorithms |
| `references/memory-template.md` | File templates (reflections.json, RTMEMORY.md, reflections-metadata.json, etc.) |
| `references/runtime-templates.md` | Runtime artifact schemas, telemetry log format, path model |
| `references/dashboard-template.html` | HTML dashboard template |

---

## Safety Rules

1. **Never delete daily logs** -- only mark with `<!-- consolidated -->`
2. **Never remove PERMANENT items** -- user-protected markers
3. **Backup before major changes** -- if RTMEMORY.md changes >30%, save .bak first
4. **Config backup** -- backup reflections.json -> reflections.json.bak before mode changes
5. **Index backup** -- backup reflections-metadata.json -> reflections-metadata.json.bak before each consolidation
6. **Sensitive data policy** -- only consolidate sensitive info already present in RTMEMORY.md
7. **Daily logs are never deleted** -- marked with `<!-- consolidated -->` per-log when the mode-aware rule is satisfied. **Parity mode**: marked immediately after a log's entries are consolidated and indexed. **Strict mode**: marked only when every extractable item is either promoted this cycle or already recorded in the persisted deferred store. Unmarked logs are retried on the next cycle.
