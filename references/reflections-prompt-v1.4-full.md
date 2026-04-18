# Reflections — Full Annotated Runtime Prompt (Archived Reference)

> ## 📚 ARCHIVED EXPLANATORY REFERENCE — NOT THE LIVE RUNTIME
>
> **This is the annotated long-form version** of the recurring runtime prompt, preserved for reference and teaching purposes. It contains rationale, cross-branch explanations, and architectural prose useful for understanding *why* the pipeline is shaped the way it is.
>
> **Runtime authority is `runtime/reflections-prompt.md`** (the trimmed execution-only version). Do not execute this file. Scripts, JSON schemas, and route dispatch rules are identical between the two files — this version just carries extra explanation.
>
> If you need to understand a design decision, read this. If you need to execute a cycle, read `runtime/reflections-prompt.md`.

---

Read USER.md to determine user's language. All output in that language.

## Path Resolution

Resolve these roots before any execution. Do not hardcode paths.

```
SKILL_ROOT     = absolute path of the parent of runtime/ (this file's parent dir)
SCRIPTS_DIR    = $SKILL_ROOT/scripts
WORKSPACE_ROOT = current working directory
CONFIG_PATH    = resolve by precedence:
                 1. REFLECTIONS_CONFIG env var
                 2. ~/.openclaw/reflections/reflections.json (local default)
TELEMETRY_ROOT = resolve by precedence:
                 1. REFLECTIONS_TELEMETRY_ROOT env var
                 2. MEMORY_TELEMETRY_ROOT env var
                 3. ~/.openclaw/telemetry fallback
TMPDIR         = system temp directory
```

## Canonical Surfaces

These are the authoritative file locations. Do not read from or write to old paths.

| Surface | Canonical Path |
|---------|---------------|
| Reflective memory | `RTMEMORY.md` |
| Procedures | `PROCEDURES.md` |
| Episodes | `episodes/*.md` |
| Trends (v1.3.0+) | `TRENDS.md` |
| Metadata/index | `runtime/reflections-metadata.json` |
| Reflections log | `memory/.reflections-log.md` |
| Archive | `memory/.reflections-archive.md` |
| Raw daily notes (input) | `memory/YYYY-MM-DD.md` |

**Rejected old paths** — do not use: `memory/index.json`, `memory/procedures.md`, `memory/.archive.md`

## Execution Guardrails

- **Execute this workflow directly.** Do not delegate any step to a sub-agent.
- Do not offload consolidation, file writes, telemetry, or reporting to a sub-agent.
- This job must run in the current isolated cron/session context only.
- Every step below is executed by the current agent.
- Do not narrate steps in chat.
- Do not send progress updates in chat.
- Do not explain tool usage in chat.
- Internal execution details go only to telemetry and log files.
- Chat emits only: the final Step 4.4 summary, a blocker message, or nothing when `sendReport == false`.

**Hybrid rule:** Call Python scripts for all arithmetic, thresholds, date math, and counting. Use LLM judgment only for semantic understanding, deduplication, routing, insight generation, and report writing.

---

## Step 0: Mode Dispatch [SCRIPT]

```bash
python3 $SCRIPTS_DIR/dispatch.py --config $CONFIG_PATH
```

Read the JSON output:
- `due_modes` → list of modes to run this cycle (with gate thresholds)
- `not_due` → modes not yet due (with `next_due_in`)
- `notification_level` → summary/full/silent

If `due_modes` is empty → go to Step 0-A.

**Derive runtime variables from config + Step 0 output** — use these in later steps; never hardcode:

- `MODE_CSV` = comma-separated string of the modes that will actually run this cycle, built from Step 0's `due_modes` array. Example: if `due_modes: ["core", "rem"]` then `MODE_CSV="core,rem"`. Use this for every `--modes` and `--update-lastrun` argument. **Never hardcode `rem,deep,core`.**
- `STRICT_MODE` = read `strictMode` field from the resolved config; treat as `false` if absent.
- `SCAN_DAYS` = read `scanWindowDays` field from the resolved config; default to `7` if absent. The scan window is **profile-driven** in this fork (personal-assistant=7, business-employee=3). The absent-field fallback of `7` is a fork convention for legacy/misconfigured installs — it is **not** upstream Auto-Dream Lite parity. Upstream Lite's recurring flow scans the last 3 days; this fork deliberately diverges to accommodate the personal-assistant's sparse-but-meaningful topology.

## Step 0-A: Scan for Work [SCRIPT]

The scan window is profile-driven via `SCAN_DAYS` (derived above). First-run (`first-reflections-prompt.md`) scans full history regardless.

```bash
python3 $SCRIPTS_DIR/scan.py --log-dir memory --days $SCAN_DAYS
```

Read the JSON output:
- `has_work` → true if unconsolidated logs exist
- `unconsolidated` → list of files with dates and sizes

If `has_work == false` AND `due_modes` is empty → go to Step 0-B (Skip With Recall).
If `has_work == true` BUT `due_modes` is empty → go to Step 0-B (still skip — no modes due).
If `due_modes` is not empty → proceed to Step 0.5.

## Step 0-B: Skip With Recall [LLM + SCRIPT]

A skipped run is a valid outcome, not a failure. It still writes telemetry and completes normally.

### 0-B.1: Write skip telemetry [SCRIPT]

Always append a skip event before composing the skip message:

```bash
python3 $SCRIPTS_DIR/append_memory_log.py \
  --telemetry-dir $TELEMETRY_ROOT \
  --status skipped \
  --event run_skipped \
  --profile <profile from config> \
  --mode scheduled
```

### 0-B.2: Compose skip message [LLM]

Scan RTMEMORY.md for Open Threads not marked [x] — find the oldest one with context. Check daily logs from 14+ days ago for matching topics.

```bash
python3 $SCRIPTS_DIR/stale.py --memory-file RTMEMORY.md --index runtime/reflections-metadata.json --threshold 14 --top 1
```

### 0-B.3: Check notify gate

Read `$WORKSPACE_ROOT/runtime/memory-state.json`. If `reflections.reporting.sendReport` is `true`, send the skip message. Otherwise skip chat delivery silently. If memory state is missing or malformed, default to no notification.

Skip message format (send only if sendReport is true):

```
💭 No modes due — skipped reflection

✨ From your memory:
   {N} days ago ({date}), {one-line context from stale result}.
   {Follow-up question if relevant}

📈 Memory: {total_entries} entries · Health {score}/100 · Streak: {N} reflections
⚙️ Active modes: {list} · Next due: {mode} in {time}
```

END here. Do not proceed to Step 0.5.

---

## Step 0.5: Snapshot BEFORE [SCRIPT]

```bash
python3 $SCRIPTS_DIR/snapshot.py --memory-file RTMEMORY.md --save-as before
```

Note the saved path (`$TMPDIR/reflections-snapshot-before.json`). Read the reflection count from output.

---

## Step 1: Collect [LLM]

Read all unconsolidated daily logs (from Step 0-A file list). Extract:
- Decisions (choices, direction changes)
- Operational context updates (data changes, technical details)
- Project progress (milestones, blockers, completions)
- Lessons (failures, wins)
- Todos (unfinished items)

Skip small talk and content already in RTMEMORY.md that hasn't changed.

Track the source daily log filename for each entry (serves as session ID and day source).

**Output:** Write extracted entries to `$TMPDIR/reflections-candidates.json` as a JSON array:

```json
[
  {
    "summary": "Decision to set dental clinic pilot pricing at ₱5,000/month",
    "source": "memory/2026-04-05.md",
    "category": "decision",
    "referenceCount": 1,
    "uniqueSessionCount": 1,
    "uniqueDayCount": 1,
    "marker": null,
    "target_section": "Key Decisions and Rationale",
    "existingId": "mem_042",
    "lastReferenced": "2026-04-03T10:00:00+08:00",
    "created": "2026-03-15",
    "tags": ["decision", "pricing"]
  }
]
```

**Field rules:**

- Required for every candidate: `summary`, `source`, `category`, `referenceCount`, `uniqueSessionCount`, `uniqueDayCount`, `marker`, `target_section`.
- Optional but required when matched to an existing index entry: `existingId` (the existing `mem_NNN`), `lastReferenced` (from the index record), `created` (from the index record). These are critical for correct recency scoring in strict-mode — without `lastReferenced`, `score.py` defaults to 0 days (perfect recency), which skews the gate toward over-qualification of old matches.
- Optional for any entry: `tags`.
- For entirely new entries (no existing index match), omit `existingId`, `lastReferenced`, and `created`.

---

## Step 1.2: Load deferred state [SCRIPT] (strictMode only)

If `STRICT_MODE == true`, load previously-deferred candidates for context:

```bash
python3 $SCRIPTS_DIR/deferred.py --all > $TMPDIR/reflections-deferred-current.json
```

This is the LLM-visible view of the deferred store. It informs semantic-dedup judgment in Step 2 (the LLM can see which items have been reconsidered before). For suppression, Step 1.3 applies deterministic filtering — the LLM does not decide suppression on its own.

If `STRICT_MODE == false`, skip this step entirely — deferred state has no role in the parity flow.

---

## Step 1.3: Annotate candidates with deferred status [SCRIPT] (strictMode only)

**Purpose:** Suppression must not rely on the model remembering to honor deferred state. This step applies deterministic filtering — every candidate gets a machine-computed `deferred_status` based on the persisted store.

If `STRICT_MODE == true`:

```bash
python3 $SCRIPTS_DIR/deferred.py --annotate $TMPDIR/reflections-candidates.json --write-back
```

This mutates `reflections-candidates.json` in place, writing on each candidate:
- `fingerprint` — rewording-stable identity (token-bag, source+section scoped)
- `candidate_hash` — v1.1.2-compat exact-string identity
- `deferred_status: "persisted" | "fresh"` — deterministic suppression verdict
- `deferred_matched_by: "existingId" | "fingerprint" | "candidate_hash" | null` — which identity layer matched

**Identity layering (strongest-first):**
1. `existingId` — matched-index entries are identified by their durable ID. Rewording the summary does not change identity.
2. `fingerprint` — normalized token bag scoped to `(source + target_section)`. Survives light rewording: capitalization, punctuation, whitespace, a small stopword set (the, a, is, was, to, for, ...), and word reordering.
3. `candidate_hash` — `sha256(source + "::" + summary)[:12]` from v1.1.2. Exact-string fallback; kept for audit/rollback.

After this step, every candidate carries an authoritative `deferred_status`:
- `"persisted"` → candidate is already recorded in the deferred store. **Do NOT promote.** Step 1.6 still runs the gate on this candidate (for reporting/telemetry) but the Step 2 consolidation skips any candidate with `deferred_status == "persisted"`.
- `"fresh"` → candidate has never been deferred under any of its identities. Normal gate + promotion path.

If `STRICT_MODE == false`, skip this step.

---

## Step 1.5: Read strictMode — branch decision

From the config loaded in Step 0, read `STRICT_MODE` (the value of the `strictMode` field; default `false` if absent).

- If `STRICT_MODE == false` → **skip Step 1.6**, proceed directly to **Step 2: Consolidate**. This is the default parity flow (upstream Auto-Dream Lite): all extracted candidates promote; archival happens post-consolidation in Step 3.
- If `STRICT_MODE == true` → proceed to **Step 1.6: Score + Gate** (pre-consolidation admission gate).

This is a runtime branch driven by config. Do not guess the value — read the flag from the config loaded in Step 0.

---

## Step 1.6: Score + Gate [SCRIPT] (strictMode=true only)

**Only execute this step when `STRICT_MODE == true`.** If `STRICT_MODE == false`, skip directly to Step 2.

### Score candidates:

```bash
python3 $SCRIPTS_DIR/score.py \
  --candidates $TMPDIR/reflections-candidates.json \
  --write-back
```

This enriches each candidate in place with an `importance` score, using the recency/reference-boost formula. Matched candidates (those with `lastReferenced` from the index) get accurate recency decay; new candidates default to perfect recency.

### Apply quality gates using actual due modes:

Use `MODE_CSV` derived after Step 0. Do NOT hardcode `rem,deep,core`.

Use `--write-back` so the gate decision is committed to the candidates file (deterministic Step 2 handoff):

```bash
python3 $SCRIPTS_DIR/gate.py \
  --candidates $TMPDIR/reflections-candidates.json \
  --config $CONFIG_PATH \
  --modes $MODE_CSV \
  --write-back \
  --emit-deferred $TMPDIR/reflections-deferred-new.json
```

This single invocation performs two deterministic handoffs:

**1. Candidates mutation (`--write-back`):** every candidate in `$TMPDIR/reflections-candidates.json` gets the following fields:
- `gate_status: "qualified" | "deferred"` — authoritative promotion decision
- `gate_promoted_by: string | null` — mode that qualified it (e.g. `"rem"`), or `null` if deferred
- `gate_bypass: "PERMANENT" | "FAST_PATH" | null` — bypass type (only for qualified entries that skipped the regular AND gate)
- `gate_fail_reasons: object | null` — per-mode failure reasons (only for deferred entries)

**2. Deferred-append payload (`--emit-deferred`):** gate.py writes the deferred candidate array to `$TMPDIR/reflections-deferred-new.json` in the exact schema expected by `deferred.py --append`. No LLM payload construction required.

The JSON output on stdout still contains:
- `qualified` / `deferred` arrays — for reporting/telemetry
- `breakdown` — count per mode
- `write_back` — summary of the candidates mutation
- `emit_deferred` — `{emit_deferred_path, deferred_count}`

After Step 1.6, the candidates file carries `gate_status` on every entry. This is **not the final handoff to Step 2** when durability is enabled — Step 1.8 runs next and produces the authoritative `route` field that Step 2 actually filters on. See Step 1.8 and Step 2 for the route-aware dispatch.

Under the v1.3.0 route-aware contract, Step 2 eligibility is **not** "qualified only". The final `route` set (promote / merge / compress / defer / reject) is written in Step 1.8 and determines dispatch:
- Rescue-promoted deferreds (gate_status=deferred + route=promote) DO reach Step 2.
- `merge` and `compress` routes DO reach Step 2 and trigger `index.py --reinforce` / `--compress-trend` respectively.
- Only `defer` (already persisted to the store in Step 1.8) and `reject` skip Step 2.

If durability is **disabled** (strict-without-durability, v1.1.6 behavior), the gate_status handoff is the final handoff: Step 2 filters `gate_status == "qualified"` AND `deferred_status != "persisted"`.

### Persist deferred candidates [SCRIPT]

Append the emitted file to the persistent store. No payload construction happens at the LLM level — the file written by gate.py is the payload:

```bash
python3 $SCRIPTS_DIR/deferred.py --append $TMPDIR/reflections-deferred-new.json
```

`deferred.py --append` auto-fills `candidate_hash`, `fingerprint`, and the timestamp pair on write. `fingerprint` is rewording-stable; `candidate_hash` is the v1.1.2-compat exact-string hash; both are written alongside `existingId` (if present) so `--is-deferred` can match on any identity layer in future cycles.

**In strict-without-durability mode**, only gate-qualified candidates proceed to Step 2; gate-deferred candidates are recorded in `runtime/reflections-deferred.jsonl` and will be respected by Step 2.7's log-marking decision. **In strict-with-durability mode (v1.3.0)**, Step 1.8 next produces the authoritative `route` field — see Step 1.8.

---

## Step 1.7: Durability Annotation [LLM] (strictMode=true AND durability.enabled=true)

**Only execute this step when `STRICT_MODE == true` AND `config.durability.enabled == true`.** If either is false, skip directly to Step 2.

**Purpose:** add a *semantic* admission layer on top of the structural gate. Structural scoring (Steps 1.3/1.6) answers "is this reinforced?"; durability answers "is this actually meaningful long-horizon memory, or just reinforced noise?". This prevents operational heartbeats / status pings / repeated symptom reports from polluting RTMEMORY while allowing rare one-off high-consequence items (a real boundary, a commitment, an architectural conclusion) to promote even when they are structurally underweight.

### Semantic-review scope

Annotate every candidate in the **semantic-review set**:

1. All candidates with `gate_status == "qualified"`, **OR**
2. Candidates with `gate_status == "deferred"` that belong to the **rescue subset** — any one of:
   - `gate_bypass` is set (`"PERMANENT"` or `"FAST_PATH"`) — structural bypass was attempted
   - `marker` is in `{"HIGH", "PERMANENT", "PIN"}`
   - the candidate is clearly a high-meaning class (decision, lesson, obligation, relationship, identity, architecture) even if structural scoring underweighted it

The rescue subset exists because structural scoring (`importance × reference × unique`) cannot see semantic consequence. A single statement establishing a boundary or commitment may never reach `minRecallCount ≥ 2` — yet it is exactly the kind of durable memory durability must allow to promote.

**Always skip:** candidates with `deferred_status == "persisted"` — already suppressed by the persisted store; respect that decision.

### Output file schema

Write annotations as a JSON array to `$TMPDIR/reflections-durability.json`. One record per in-scope candidate:

```json
{
  "candidate_id": "<matches gate.py get_entry_id: prefer `id`, else `summary`, else `title`, else `name`>",
  "memory_type": "decision | lesson | preference | procedure | obligation | relationship | identity | architecture | observation | status | trend",
  "durability_class": "durable | semi-durable | volatile | noise",
  "changed_future_decision": true | false,
  "changed_behavior_or_policy": true | false,
  "created_stable_preference": true | false,
  "created_obligation_or_boundary": true | false,
  "relationship_or_identity_shift": true | false,
  "cross_day_relevance": true | false,
  "rare_high_consequence": true | false,
  "actionable_procedure": true | false,
  "pattern_only": true | false,
  "pure_status": true | false,
  "telemetry_noise": true | false,
  "duplicate_of_existing": "mem_042 | null",
  "merge_key": "short-stable-slug | null",
  "trend_key": "short-stable-slug | null",
  "explanation": "short free-text rationale (stored for telemetry/report only; router does not read this)"
}
```

**Field rules:**
- `candidate_id` — must join cleanly against the candidate. Use the same resolution order gate.py uses: `id` if present, else `summary`, else `title`, else `name`.
- `memory_type` — pick exactly one from the list above. Use `"observation"` for cross-day pattern material that doesn't fit a durable category; use `"status"` or `"trend"` for repeated operational noise.
- Boolean flags — all must be explicitly `true` or `false` (no nulls). Missing/uncertain → default to `false`.
- `duplicate_of_existing` — the existing index ID (e.g. `"mem_042"`) if this candidate is semantically the same as an already-promoted memory; `null` otherwise. The LLM is responsible for this semantic match — the router trusts the annotation.
- `merge_key` / `trend_key` — stable slugs (e.g. `"dental-clinic-pricing-2026Q2"`, `"server-restart-frequency"`). **v1.3.0 activates routing on these**: `duplicate_of_existing` triggers the `merge` route; `trend_key` on weak ops material triggers the `compress` route.

### Hybrid discipline reminder

The LLM does semantic judgment **only**. All routing decisions (promote / merge / compress / defer / reject, destination choice, net-score banding, trend-promotion thresholds) happen deterministically in Step 1.8.

---

## Step 1.8: Durability Routing [SCRIPT] (strictMode=true AND durability.enabled=true)

**Only execute this step when `STRICT_MODE == true` AND `config.durability.enabled == true`.**

```bash
python3 $SCRIPTS_DIR/durability.py \
  --candidates $TMPDIR/reflections-candidates.json \
  --annotations $TMPDIR/reflections-durability.json \
  --config $CONFIG_PATH \
  --index runtime/reflections-metadata.json \
  --write-back \
  --emit-defer-subset $TMPDIR/reflections-durability-deferred.json
```

This single invocation:

**1. Mutates the candidates file** (`--write-back`) — writes these fields onto every in-scope candidate (v1.3.0 full route set):
- `route: "promote" | "merge" | "compress" | "defer" | "reject"` — authoritative routing decision
- `destination: "RTMEMORY" | "PROCEDURES" | "EPISODE" | "TREND" | "NONE"` — target surface for Step 2
- `durabilityScore: int` — computed `net` value (structural + meaning + futureConsequence − noise)
- `noisePenalty: int` — the penalty component in isolation
- `promotionReason: string` — hard-trigger name, `"net=N>=threshold"`, `"merge-into:<id>"`, `"reinforce-trend:<id>"`, `"new-trend:<key>"`, etc.
- `memoryType`, `durabilityClass`, `mergeKey`, `trendKey`, `duplicateOfExisting`, `supportCount` — echoed from annotation plus context
- `mergedInto` (v1.3.0): target entry id when `route == "merge"`; existing trend id when `route == "compress"` reinforces
- `promotedFromTrend` (v1.3.0): existing trend node id when a hard-triggered candidate promotes from an accumulated trend (both `trendPromoteSupportCount` and `trendPromoteUniqueDayCount` met on the existing trend)
- `compressionReason` (v1.3.0): `"reinforce-trend:<id>"` or `"new-trend:<key>"` when `route == "compress"`
- `durabilityComponents: {structuralEvidence, meaningWeight, futureConsequence, noisePenalty}` — for telemetry/audit

**2. Emits defer subset** (`--emit-defer-subset`) — writes defer-routed candidates to a separate file in the exact schema `deferred.py --append` expects, so the existing persistence path handles them with zero new code.

### Persist durability-deferred candidates [SCRIPT]

Append the defer subset to the persistent store:

```bash
python3 $SCRIPTS_DIR/deferred.py --append $TMPDIR/reflections-durability-deferred.json
```

Candidates that durability routes to `defer` (unresolved duplicates, borderline net scores) are recorded alongside gate-deferred candidates — future cycles will suppress re-extraction via the annotate step. (Resolved duplicates now route to `merge`, and cross-day observations with `trendKey` route to `compress` — both terminal in Step 2 with no need for the deferred store.)

### Deterministic precedence (for reference — actually enforced by the script)

1. **Hard-suppress triggers** → `reject` (telemetry_noise / pure_status-no-consequence / pattern_only-same-day)
2. **Hard-promote triggers** → `promote` (explicit decision-with-consequence, stable preference, obligation/boundary, relationship/identity shift, validated actionable procedure with structural evidence ≥ 2, architecture + rare_high_consequence) — **duplicates still allowed here** because a hard-triggered item may legitimately be distinct from an existing similar entry. **Trend-to-durable promotion**: if the candidate's `trendKey` matches an existing trend node AND that trend node meets both `trendPromoteSupportCount` and `trendPromoteUniqueDayCount` thresholds, the router additionally sets `promotedFromTrend: <trend_id>` so Step 2 can link the new durable node to its trend origin.
3. **Merge** (v1.3.0) → `route = "merge"` (`duplicate_of_existing` is non-null AND resolves in the index AND no hard-promote fired). Step 2 calls `index.py --reinforce <mergedInto>` instead of creating a new node. The `mergeKey` is persisted in the target's `mergeKeys` list.
4. **Defer (unresolved duplicate)** → `route = "defer"` (`duplicate_of_existing` is non-null BUT doesn't resolve in the index — stale reference). Re-evaluated next cycle.
5. **Compress** (v1.3.0) → `route = "compress"` (`trendKey` set AND `memory_type in {observation, status, trend}` AND no hard-promote fired AND `actionable_procedure != true`). Step 2 calls `index.py --compress-trend <trendKey>` which upserts a trend node. If the trendKey already exists, the trend node is reinforced; otherwise a new trend node is created.
6. **Net-score banding** — `promote` if net ≥ `netPromoteThreshold`; `defer` if net ≥ `netDeferThreshold`; else `reject`.

### Profile-driven thresholds

| Profile | `netPromoteThreshold` | `netDeferThreshold` | `trendPromoteSupportCount` | `trendPromoteUniqueDayCount` |
|---------|----------------------|---------------------|---------------------------|-----------------------------|
| business-employee | 6 | 3 | 5 | 3 |
| personal-assistant (only active if operator enabled `strictMode`) | 5 | 2 | 4 | 2 |

Values come from the `durability` block in `$CONFIG_PATH`. If the block is missing or `durability.enabled` is false, the script leaves candidates untouched (Step 2 filter falls back to Step 1.6-only semantics). **This is why durability is strict-mode-only by default** — personal-assistant parity flow never reaches Step 1.5 branch in the first place.

---

## Step 2: Consolidate [LLM + SCRIPT]

Process daily logs **one at a time**. For each daily log, work through its extracted candidates, then mark the log as consolidated before moving to the next log. This isolates the commit boundary per-log.

### Strict + durability mode — route-driven consolidation (v1.3.0)

When `STRICT_MODE == true` AND `config.durability.enabled == true`, each candidate carries a deterministic `route` field written by Step 1.8. Dispatch per route — no LLM guessing:

| `route` | `destination` | Action |
|---------|--------------|--------|
| `promote` | `RTMEMORY` \| `PROCEDURES` \| `EPISODE` | **New durable node.** Append to the destination file (`RTMEMORY.md` / `PROCEDURES.md` / `episodes/<name>.md`); call `index.py --add` with the full durability field payload. |
| `merge` | `NONE` (action target is `mergedInto`) | **Reinforce existing durable node.** Do NOT create a new surface entry. Call `index.py --reinforce <mergedInto> --from $TMPDIR/merge.json` with the candidate's source/mergeKey/mergeReason/refined summary. |
| `compress` | `TREND` | **Upsert trend node.** Call `index.py --compress-trend <trendKey> --from $TMPDIR/trend.json`. If an existing trend entry matches `trendKey`, it is reinforced (bumps `trendSupportCount`, `trendLastUpdated`, adds source); otherwise a new trend entry is created with `memoryType: "trend"`. Also append/update the trend section in `TRENDS.md` so there is a human-readable surface. |
| `defer` | `NONE` | **Already persisted** by `deferred.py --append` at end of Step 1.8. Nothing to do in Step 2. |
| `reject` | `NONE` | **Discarded.** Nothing written anywhere. |

**Prerequisite conditions** (the `route` field is already set correctly by Step 1.8, but Step 2 verifies before dispatching):

1. `deferred_status != "persisted"` — not already suppressed by the deferred store. Candidates failing this check are skipped (they were already handled).
2. `gate_status == "qualified"` **OR** `route == "promote"` with `gate_status == "deferred"` (rescue-promoted by durability), **OR** `route in {"merge", "compress"}`. All three sub-cases are legitimate paths through Steps 1.6 and 1.8.
3. If a candidate somehow arrives with `route` absent and durability was enabled, log a warning in the reflection report and skip it — durability.py produced an incomplete write.

### Strict mode without durability (`durability.enabled == false`)

Same as v1.1.6: promotion-eligibility is `deferred_status != "persisted"` AND `gate_status == "qualified"`. No `route` field is present. All eligible candidates promote to destination determined by the legacy semantic routing below.

### Parity mode (`strictMode == false`)

None of the gate/durability fields are present. All extracted candidates proceed to consolidation via the legacy semantic routing below — upstream Auto-Dream Lite behavior. Parity flow does not run durability by design; personal-assistant's sparse-but-meaningful topology naturally produces low-noise input.

### Legacy / fallback semantic routing (parity mode, or strict-without-durability)

- **New** → append to `RTMEMORY.md` in the right section
- **Updated** → update in place
- **Duplicate** → skip (semantic dedup — compare meaning, not text)
- **Procedures/preferences** → append to `PROCEDURES.md`
- **Multi-event project narrative** → append to `episodes/<project-name>.md`

Semantic dedup still applies on the LLM side even in non-durability modes — a candidate that semantically matches an existing RTMEMORY entry should update the existing entry rather than creating a duplicate. This is separate from durability's machine-deterministic merge route.

### Route-specific SCRIPT dispatch

Each route dispatches to a different `index.py` mode. All write actions are deterministic — the LLM assembles the payload, the script does the write.

**Route = `promote` → new durable node:**

```bash
python3 $SCRIPTS_DIR/index.py --index runtime/reflections-metadata.json --next-id
```

Use the returned ID. Write to the destination surface (RTMEMORY.md / PROCEDURES.md / episodes), then:

```bash
python3 $SCRIPTS_DIR/index.py --index runtime/reflections-metadata.json --add $TMPDIR/entry.json
```

The `$TMPDIR/entry.json` payload carries the full durability field set. If `promotedFromTrend` is non-null (trend-to-durable promotion), include it so the new durable node links to its trend origin:

```json
{
  "id": "mem_045",
  "summary": "...",
  "source": "memory/2026-04-18.md",
  "referenceCount": 1,
  "memoryType": "decision",
  "durabilityClass": "durable",
  "route": "promote",
  "destination": "RTMEMORY",
  "durabilityScore": 8,
  "noisePenalty": 0,
  "promotionReason": "hard-trigger:decision-with-consequence",
  "mergeKey": null,
  "trendKey": null,
  "promotedFromTrend": null,
  "supportCount": 1
}
```

**Route = `merge` → reinforce existing node (v1.3.0):**

Do NOT call `--add` and do NOT write a new surface entry. Construct `$TMPDIR/merge.json` with the reinforcement payload, then:

```bash
python3 $SCRIPTS_DIR/index.py --index runtime/reflections-metadata.json \
  --reinforce <mergedInto> --from $TMPDIR/merge.json
```

`$TMPDIR/merge.json` shape:

```json
{
  "source": "memory/2026-04-18.md",
  "mergeKey": "dental-clinic-pricing-2026Q2",
  "mergeReason": "merge-into:mem_012",
  "summary": "optional: refined summary text that replaces the existing entry's summary"
}
```

The script bumps `referenceCount`, updates `lastReferenced`, appends the source to `sessionSources` / `uniqueDaySources`, appends to the target's `mergeKeys` list, and appends a timestamped audit record to `reinforcedBy[]`.

**Route = `compress` → upsert trend node (v1.3.0):**

Do NOT call `--add` for a new RTMEMORY/PROCEDURES entry. Construct `$TMPDIR/trend.json`, then:

```bash
python3 $SCRIPTS_DIR/index.py --index runtime/reflections-metadata.json \
  --compress-trend <trendKey> --from $TMPDIR/trend.json
```

`$TMPDIR/trend.json` shape:

```json
{
  "source": "memory/2026-04-18.md",
  "trendKey": "dev-server-noon-restart",
  "summary": "Dev server restarts around noon each day — no clear trigger",
  "compressionReason": "reinforce-trend:mem_099",
  "tags": ["operations", "restart"]
}
```

If a trend entry matching `trendKey` exists, the script reinforces it (bumps `trendSupportCount`, `trendLastUpdated`, adds to `trendSources`, increments `sourceCount`). If no trend entry matches, a new trend entry is created with `memoryType: "trend"`.

**After any trend upsert**, also update the human-readable `TRENDS.md` surface:
- Find or create the section headed `### <trendKey>`
- Update *First observed*, *Last reinforced*, *Support*, *Pattern*, *Related entries*, *Node ID* lines
- Keep the file append-only for promoted-trend entries (if a trend promotes to RTMEMORY via a hard-trigger on a subsequent cycle, move it under a "Promoted Trends" subsection)

**Route = `defer` or `reject`:**

No Step 2 action. `defer` was already persisted by `deferred.py --append` at the end of Step 1.8. `reject` is discarded.

### Update session tracking [SCRIPT]

For existing entries that were re-referenced:

```bash
python3 $SCRIPTS_DIR/index.py --index runtime/reflections-metadata.json --update-session mem_042 --source memory/2026-04-05.md
```

### Write changes [LLM]

Update `_Last updated:` date in RTMEMORY.md. Write updated PROCEDURES.md if needed.

### Step 2.7: Mark processed files (mode-aware) [LLM]

The rule for marking daily logs with `<!-- consolidated -->` depends on `STRICT_MODE`:

**If `STRICT_MODE == false` (default parity flow):**

Immediately after a daily log's extractable entries have been successfully consolidated into the owned surfaces (RTMEMORY.md, PROCEDURES.md, episodes/*.md) and recorded in the index, append `<!-- consolidated -->` to the end of that daily log file. Per-log commit boundary — do not defer to end of cycle.

This isolates the commit boundary and prevents duplicate reprocessing if later steps (report, telemetry, notify) fail. If a log fails mid-consolidation, do not mark it; the next cron fire will retry that specific log.

**If `STRICT_MODE == true` (v1.3.0 rule — covers the full route set):**

Mark a daily log `<!-- consolidated -->` when **every** extractable item from that log has reached a terminal handled state. In v1.3.0, there are five terminal states — all five count as handled:

| Terminal state | How the candidate got there | Counts as handled? |
|---------------|-----------------------------|-------------------|
| `route == "promote"` | Written this cycle to RTMEMORY / PROCEDURES / EPISODE via `index.py --add` | ✅ |
| `route == "merge"` | Reinforced an existing durable node this cycle via `index.py --reinforce` | ✅ |
| `route == "compress"` | Upserted a trend node this cycle via `index.py --compress-trend` | ✅ |
| `route == "reject"` | Discarded by hard-suppress trigger or net-score floor | ✅ (deliberate discard is a valid terminal state) |
| `route == "defer"` AND persisted in the deferred store | Either durability appended it to the store in Step 1.8, or it was already in the store from an earlier cycle (`deferred_status == "persisted"`) | ✅ |

Only an item that is **fresh + deferred but NOT appended to the store** is unhandled. That case shouldn't occur under normal operation (durability.py always emits the defer-subset, and `deferred.py --append` always runs in Step 1.8), but if it does, leave the log unmarked so the next cron fire retries.

**How to check in practice:** every candidate in `$TMPDIR/reflections-candidates.json` carries a `route` field written by Step 1.8 plus a `deferred_status` from Step 1.3. A log is markable when, for every candidate extracted from that log:

```
route in {"promote", "merge", "compress", "reject"}
  OR (route == "defer" AND the candidate hash/fingerprint appears in the store)
```

As a safety backstop for the defer branch, re-verify via:

```bash
python3 $SCRIPTS_DIR/deferred.py --is-deferred <fingerprint-or-existingId-or-candidate_hash>
# Exit 0 → identity exists in the store
# Exit 1 → identity not in the store
```

`--is-deferred` matches against **any** of the three identity layers (existingId / fingerprint / candidate_hash) — pass the strongest identity you have.

This closes the strict+durability loop: logs reach stable processed-state as soon as every extracted candidate is accounted for by one of the five routes. Reject is a terminal state, not a non-event — the router made a deliberate decision. Rewording-stable identity ensures a lightly-reworded summary is recognized as already-persisted on subsequent cycles.

If durability is disabled (`config.durability.enabled == false`), only promote/defer routes exist (inherited from v1.1.6 behavior); fall back to the v1.1.6 rule — mark when every candidate is either promoted this cycle or persisted in the store.

Then move to the next unconsolidated daily log and repeat Step 2.

---

## Step 2.5: Snapshot AFTER [SCRIPT]

```bash
python3 $SCRIPTS_DIR/snapshot.py --memory-file RTMEMORY.md --save-as after
python3 $SCRIPTS_DIR/snapshot.py --delta $TMPDIR/reflections-snapshot-before.json $TMPDIR/reflections-snapshot-after.json
```

Read the delta output for the notification.

---

## Step 2.8: Stale Thread Detection [SCRIPT]

```bash
python3 $SCRIPTS_DIR/stale.py --memory-file RTMEMORY.md --index runtime/reflections-metadata.json --threshold 14 --top 3
```

Read `stale` array for the notification.

---

## Step 3: Health + Evaluation [SCRIPT]

### Compute health score:

```bash
python3 $SCRIPTS_DIR/health.py --index runtime/reflections-metadata.json --memory-file RTMEMORY.md
```

Read: `health_score`, `metrics`, `suggestions`, `reachability_detail`.

### Check archival candidates:

```bash
python3 $SCRIPTS_DIR/score.py --index runtime/reflections-metadata.json --check-archival
```

For each `archival_candidates` entry, archive via:

```bash
python3 $SCRIPTS_DIR/index.py --index runtime/reflections-metadata.json --archive mem_015 --summary "Old API endpoint"
```

Also remove the full entry from RTMEMORY.md and append the one-line summary to `memory/.reflections-archive.md`.

### Update index stats:

Write the health and gate results to a temp file, then:

```bash
python3 $SCRIPTS_DIR/index.py --index runtime/reflections-metadata.json --update-stats $TMPDIR/reflections-stats.json
```

---

## Step 3.5: Insights [LLM]

Review the health output, recent changes, and cross-layer patterns. Generate 1–2 non-obvious insights that scripts can't detect (semantic patterns, gap detection, trend interpretation).

**Mode-aware inputs:**

- If `STRICT_MODE == true` → also review **gate results from Step 1.6** (qualified/deferred breakdown, fail_reasons for deferred entries, and any patterns in what's repeatedly getting deferred).
- If `STRICT_MODE == false` → also review **archival/evaluation results from Step 3** (archival candidates from the forgetting curve, health-metric shifts, and patterns in what's aging out).

Do not claim "gate results" unconditionally — that is only meaningful in strict-mode. In parity mode, there is no gate.

---

## Step 3.7: Update Config [SCRIPT]

Use `MODE_CSV` derived after Step 0. Do NOT hardcode `core,rem,deep`.

```bash
python3 $SCRIPTS_DIR/dispatch.py --config $CONFIG_PATH --update-lastrun $MODE_CSV
```

This records `lastRun` timestamps only for modes that actually fired this cycle — critical for correct dispatch on subsequent cron fires.

---

## Step 3.8: Refresh Dashboard

This step is part of the upstream parity flow and is **not optional when the dashboard file exists**.

- If `memory/dashboard.html` exists, regenerate it from `$SKILL_ROOT/references/dashboard-template.html` using the latest `runtime/reflections-metadata.json` data, current health scores from Step 3, recent cycle changes, and the latest entries from `memory/.reflections-log.md`.
- If `memory/dashboard.html` does **not** exist, skip this step silently. (Dashboards are only regenerated, never auto-created here — the operator opts in by creating the initial file.)

This keeps the operator-facing dashboard in sync with the latest cycle's state. A stale dashboard after a recurring run suggests the system isn't working even when it is.

---

## Step 4: Report + Notify [LLM]

### 4.1 Always append to human-readable log

Append the run report to `memory/.reflections-log.md`. This is unconditional.

### 4.2 Always write telemetry

Write one structured event to the unified memory telemetry log via `append_memory_log.py`. This is unconditional — never skip telemetry regardless of reporting state.

**Mode-aware details payload:**

- If `STRICT_MODE == false` (parity flow):
  ```
  {"logs_scanned": N, "entries_extracted": N, "entries_consolidated": N, "logs_marked_consolidated": N}
  ```
- If `STRICT_MODE == true` AND `durability.enabled == false` (strict flow without durability):
  ```
  {"logs_scanned": N, "entries_extracted": N, "entries_qualified": N, "entries_deferred": N, "entries_promoted": N, "logs_marked_consolidated": N}
  ```
  where `entries_qualified` = gate.py qualified_count, `entries_deferred` = gate.py deferred_count, `entries_promoted` = qualified entries minus those already suppressed via `deferred_status == "persisted"`.
- If `STRICT_MODE == true` AND `durability.enabled == true` (strict flow with durability, v1.3.0+):
  ```
  {"logs_scanned": N, "entries_extracted": N, "entries_qualified": N, "entries_deferred": N,
   "entries_durable_promoted": N, "entries_durable_merged": N, "entries_durable_compressed": N,
   "entries_durable_deferred": N, "entries_durable_rejected": N, "logs_marked_consolidated": N}
  ```
  where `entries_qualified`/`entries_deferred` are gate.py outputs, and the five `entries_durable_*` counters are durability.py's route-partitioned buckets. `entries_durable_promoted` is new durable nodes. `entries_durable_merged` reinforced existing nodes. `entries_durable_compressed` updated trend nodes.

```bash
python3 $SCRIPTS_DIR/append_memory_log.py \
  --telemetry-dir $TELEMETRY_ROOT \
  --status ok \
  --event run_completed \
  --profile <profile from config> \
  --mode scheduled \
  --agent-id <agent id or "main"> \
  --details-json '<JSON string matching the mode-aware shape above>'
```

### 4.3 Check notify gate

Read the shared runtime state to determine whether chat notification should be sent:

```
MEMORY_STATE = $WORKSPACE_ROOT/runtime/memory-state.json
```

Read `reflections.reporting.sendReport` from the file.

**Rules:**
- If `memory-state.json` is missing → default `sendReport` to `false`
- If `memory-state.json` is unreadable or malformed → default `sendReport` to `false`
- If `reflections.reporting.sendReport` field is absent → default `sendReport` to `false`
- If `sendReport` is `false` → skip chat notification, end run normally
- If `sendReport` is `true` → proceed with notification (Step 4.4)

**Never fail the run** solely because the reporting state is absent or malformed.

### 4.4 Send notification (only if sendReport is true)

Check for milestones:
- REFLECTION_COUNT+1 == 1 → "🎉 First reflection complete!"
- REFLECTION_COUNT+1 == 7 → "🏅 One week streak!"
- REFLECTION_COUNT+1 == 30 → "🏆 One month streak!"
- TOTAL_AFTER crosses 100/200/500 → "📊 Memory milestone!"

### Is today Sunday? → Add weekly summary

Trigger conditions (either one qualifies):
- The current run is at the **18:30 schedule on a Sunday** (weekday match + local-time hour:minute check)
- Or `REFLECTION_COUNT+1` is a multiple of 7 (fallback — catches missed Sunday runs)

When triggered, prepend a weekly summary section to the notification:

```
📊 Weekly Report ({date_range})

🧠 This week: +{weekly_new} new · {weekly_updated} updated · {weekly_archived} archived
   {TOTAL_BEFORE_WEEK} → {TOTAL_AFTER} entries ({percent}% growth)

🌟 Biggest memories this week:
   1. {most significant new entry}
   2. {second}
   3. {third}
```

Compute the weekly stats by comparing against the reflections-metadata stats snapshot from 7 days ago (or the oldest available snapshot within the last 7 days). Rank "biggest memories" by importance score among entries added or updated in the last 7 days.

If no weekly snapshot is available yet (fresh install), skip the weekly block — do not emit placeholders.

Notification format:

```
💭 Reflection #{N} complete ({modes_fired} cycle)

📥 Consolidated: {E} entries from {L} logs
   new: {new} · updated: {updated} · archived: {archived}
📈 Total: {BEFORE} → {AFTER} entries ({pct}% growth)
🧠 Health: {score}/100 — {rating}

✨ Highlights:
   • {change_1}
   • {change_2}

💡 Insight: {top insight}

⏳ Stale: {stale items if any}

{milestone if any}
💬 Let me know if anything was missed
```

This reply is your ONLY output. Concise and high-value.
---

## Safety Rules

- Never delete daily log originals
- Never remove ⚠️ PERMANENT entries
- ⚠️ PERMANENT entries are immune to archival (forgetting curve)
- Backup: RTMEMORY.md changes >30% → save RTMEMORY.md.bak first
- Backup: reflections.json → reflections.json.bak (handled by dispatch.py)
- Backup: reflections-metadata.json → reflections-metadata.json.bak (handled by index.py)
- Only mark a daily log `<!-- consolidated -->` after its extracted entries have been successfully consolidated — never mark prematurely

---

## Cleanup

After the reflection cycle, remove temp files:

```bash
rm -f $TMPDIR/reflections-candidates.json $TMPDIR/reflections-snapshot-*.json $TMPDIR/reflections-stats.json $TMPDIR/entry.json

