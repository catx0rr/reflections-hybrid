# Reflections — Recurring Runtime Prompt

Read USER.md to determine user's language. All output in that language.

## Path Resolution

```
SKILL_ROOT     = absolute path of the parent of runtime/ (this file's parent dir)
SCRIPTS_DIR    = $SKILL_ROOT/scripts
WORKSPACE_ROOT = current working directory
CONFIG_PATH    = REFLECTIONS_CONFIG env var, else ~/.openclaw/reflections/reflections.json
TELEMETRY_ROOT = REFLECTIONS_TELEMETRY_ROOT, else MEMORY_TELEMETRY_ROOT, else ~/.openclaw/telemetry
TMPDIR         = system temp directory
```

## Canonical Surfaces

| Surface | Path |
|---------|------|
| Reflective memory | `RTMEMORY.md` |
| Procedures | `PROCEDURES.md` |
| Episodes | `episodes/*.md` |
| Trends | `memory/TRENDS.md` |
| Index | `runtime/reflections-metadata.json` |
| Log | `memory/.reflections-log.md` |
| Archive | `memory/.reflections-archive.md` |
| Daily input | `memory/YYYY-MM-DD.md` |

## Execution Guardrails

- Execute every step in the current agent. Do not delegate to a sub-agent.
- Do not narrate steps, progress, or tool usage in chat.
- Internal details go only to telemetry and log files.
- Chat emits exactly one of: the final Step 4.4 summary, a blocker message, or nothing (when `sendReport == false`).
- Scripts are the source of deterministic logic. The LLM supplies semantic judgment only.

---

## Step 0: Mode Dispatch [SCRIPT]

Always run dispatch first, then scan. Decide skip/continue from both outputs.

```bash
python3 $SCRIPTS_DIR/dispatch.py --config $CONFIG_PATH
```

From the output:
- `due_modes` → list of modes to run
- `notification_level` → summary/full/silent

**Derive runtime variables from config + Step 0:**
- `MODE_CSV` = comma-join `due_modes`. Never hardcode.
- `STRICT_MODE` = config `strictMode` (false if absent)
- `DURABILITY_ON` = `STRICT_MODE && config.durability.enabled == true`
- `SCAN_DAYS` = config `scanWindowDays` (7 if absent)

## Step 0-A: Scan for Work [SCRIPT]

```bash
python3 $SCRIPTS_DIR/scan.py --log-dir memory --days $SCAN_DAYS
```

From the output:
- `has_work` → true if unconsolidated logs exist

**Decision table:**

| `due_modes` non-empty | `has_work` | Next |
|-----------------------|-----------|------|
| no | — | Step 0-B (skip) |
| yes | no | Step 0-B (skip) |
| yes | yes | Step 0.5 (continue) |

Continue only when modes are due AND work exists. Otherwise skip.

## Step 0-B: Skip With Recall [SCRIPT + LLM]

Skipped runs are valid outcomes.

```bash
python3 $SCRIPTS_DIR/append_memory_log.py \
  --telemetry-dir $TELEMETRY_ROOT \
  --status skipped --event run_skipped \
  --profile <profile> --mode scheduled

python3 $SCRIPTS_DIR/stale.py --memory-file RTMEMORY.md \
  --index runtime/reflections-metadata.json --threshold 14 --top 1 \
  > $TMPDIR/reflections-stale.json

python3 $SCRIPTS_DIR/report.py \
  --index runtime/reflections-metadata.json \
  --config $CONFIG_PATH \
  --kind skip > $TMPDIR/reflections-report-skip.json
```

Read `$WORKSPACE_ROOT/runtime/memory-state.json`. If `reflections.reporting.sendReport != true` → emit nothing, END.

Otherwise emit the skip message using **only** values from the two JSON outputs:
- `reflections-stale.json` → memory-recall line
- `reflections-report-skip.json` → `total_after`, `health_score`, `streak`, `next_due`, `active_modes`

Do not invent any field. Do not read from `memory-state.json` or config directly for these values. If a field is null, omit its line.

```
💭 No modes due — skipped reflection
✨ From your memory:
   {N} days ago ({date}), {stale result one-liner}.
📈 Memory: {total_after} entries · Health {health_score}/100 · Streak: {streak}
⚙️ Active modes: {active_modes} · Next due: {next_due.mode} in {next_due.in}
```

END.

---

## Step 0.5: Snapshot BEFORE [SCRIPT]

```bash
python3 $SCRIPTS_DIR/snapshot.py --memory-file RTMEMORY.md --save-as before
```

Output at `$TMPDIR/reflections-snapshot-before.json`.

---

## Step 1: Collect [LLM]

Read unconsolidated daily logs from Step 0-A. Extract decisions, operational context, progress, lessons, todos. Skip small talk and unchanged content.

Write `$TMPDIR/reflections-candidates.json`:

```json
[
  {
    "id": "c1",
    "summary": "One-line summary",
    "source": "memory/YYYY-MM-DD.md",
    "category": "decision",
    "referenceCount": 1,
    "uniqueSessionCount": 1,
    "uniqueDayCount": 1,
    "marker": null,
    "target_section": "Key Decisions and Rationale",
    "existingId": "mem_042",
    "lastReferenced": "YYYY-MM-DDTHH:MM:SS+HH:MM",
    "created": "YYYY-MM-DD",
    "tags": ["decision"]
  }
]
```

**Required every candidate:** `id`, `summary`, `source`, `category`, `referenceCount`, `uniqueSessionCount`, `uniqueDayCount`, `marker`, `target_section`.
**Required when matched to an index entry:** `existingId`, `lastReferenced`, `created`. Without `lastReferenced`, score.py treats the entry as perfectly recent — skewing the gate.
**Optional:** `tags`.

---

## Step 1.2: Load deferred state [SCRIPT] (STRICT_MODE only)

```bash
python3 $SCRIPTS_DIR/deferred.py --all > $TMPDIR/reflections-deferred-current.json
```

## Step 1.3: Annotate deferred [SCRIPT] (STRICT_MODE only)

```bash
python3 $SCRIPTS_DIR/deferred.py --annotate $TMPDIR/reflections-candidates.json --write-back
```

Writes `fingerprint`, `candidate_hash`, `deferred_status ∈ {persisted, fresh}`, `deferred_matched_by` onto each candidate.

## Step 1.5: Branch

- `STRICT_MODE == false` → skip to Step 2 (parity flow).
- `STRICT_MODE == true` → proceed to Step 1.6.

## Step 1.6: Score + Gate [SCRIPT] (STRICT_MODE only)

```bash
python3 $SCRIPTS_DIR/score.py --candidates $TMPDIR/reflections-candidates.json --write-back

python3 $SCRIPTS_DIR/gate.py \
  --candidates $TMPDIR/reflections-candidates.json \
  --config $CONFIG_PATH \
  --modes $MODE_CSV \
  --write-back \
  --emit-deferred $TMPDIR/reflections-deferred-new.json

python3 $SCRIPTS_DIR/deferred.py --append $TMPDIR/reflections-deferred-new.json
```

After this:
- Each candidate carries `gate_status ∈ {qualified, deferred}`, `gate_promoted_by`, `gate_bypass`, `gate_fail_reasons`.
- `$TMPDIR/reflections-deferred-new.json` has been persisted to the deferred store.

If `DURABILITY_ON == false` → skip to Step 2.

## Step 1.7: Durability Annotation [LLM] (DURABILITY_ON only)

Scope: candidates where `deferred_status != "persisted"` AND (`gate_status == "qualified"` OR rescue-eligible).

**Rescue-eligible** = `gate_status == "deferred"` AND any of:
- `gate_bypass` is set (PERMANENT / FAST_PATH)
- `marker ∈ {HIGH, PERMANENT, PIN}`
- semantic class is high-meaning (decision, lesson, obligation, relationship, identity, architecture)

Write `$TMPDIR/reflections-durability.json`:

```json
[
  {
    "candidate_id": "c1",
    "memory_type": "decision | lesson | preference | procedure | obligation | relationship | identity | architecture | observation | status | trend",
    "durability_class": "durable | semi-durable | volatile | noise",
    "changed_future_decision": true,
    "changed_behavior_or_policy": true,
    "created_stable_preference": false,
    "created_obligation_or_boundary": false,
    "relationship_or_identity_shift": false,
    "cross_day_relevance": true,
    "rare_high_consequence": false,
    "actionable_procedure": false,
    "pattern_only": false,
    "pure_status": false,
    "telemetry_noise": false,
    "duplicate_of_existing": "mem_042 or null",
    "merge_key": "stable-slug or null",
    "trend_key": "stable-slug or null",
    "explanation": "short rationale (telemetry only)"
  }
]
```

All booleans must be explicit `true`/`false`.

## Step 1.8: Durability Routing [SCRIPT] (DURABILITY_ON only)

```bash
python3 $SCRIPTS_DIR/durability.py \
  --candidates $TMPDIR/reflections-candidates.json \
  --annotations $TMPDIR/reflections-durability.json \
  --config $CONFIG_PATH \
  --index runtime/reflections-metadata.json \
  --write-back \
  --emit-defer-subset $TMPDIR/reflections-durability-deferred.json

python3 $SCRIPTS_DIR/deferred.py --append $TMPDIR/reflections-durability-deferred.json
```

After this, each in-scope candidate carries:
- `route ∈ {promote, merge, compress, defer, reject}`
- `destination ∈ {RTMEMORY, PROCEDURES, EPISODE, TREND, NONE}`
- `durabilityScore`, `noisePenalty`, `promotionReason`
- `memoryType`, `durabilityClass`, `mergeKey`, `trendKey`, `duplicateOfExisting`
- `mergedInto` (merge target id, or trend id when compressing into existing trend)
- `promotedFromTrend` (when hard-trigger promotes an accumulated trend to durable)
- `compressionReason`, `supportCount`, `durabilityComponents`

---

## Step 2: Consolidate [LLM + SCRIPT]

Process daily logs one at a time. Dispatch per-route.

**When `DURABILITY_ON == true`** — route-driven:

| `route` | Action |
|---------|--------|
| `promote` | Append to destination file (`RTMEMORY.md` / `PROCEDURES.md` / `episodes/<name>.md`), then `index.py --add $TMPDIR/entry.json`. |
| `merge` | `index.py --reinforce <mergedInto> --from $TMPDIR/merge.json`. No new surface entry. |
| `compress` | `index.py --compress-trend <trendKey> --from $TMPDIR/trend.json`. Also upsert the `### <trendKey>` section in `memory/TRENDS.md`. |
| `defer` | No action. Already persisted by Step 1.6/1.8. |
| `reject` | No action. Discarded. |

**When `DURABILITY_ON == false`, `STRICT_MODE == true`:**
- Promotion-eligible = `deferred_status != "persisted"` AND `gate_status == "qualified"`.
- Dispatch eligible candidates via semantic LLM routing: reflective content → `RTMEMORY.md`, procedures/preferences → `PROCEDURES.md`, multi-event narratives → `episodes/<name>.md`.

**When `STRICT_MODE == false` (parity flow):**
- Every extracted candidate consolidates via semantic LLM routing (same surface split as above).

### Payloads for index.py

**`$TMPDIR/entry.json`** (for `--add`):

```json
{
  "id": "mem_045",
  "summary": "...",
  "source": "memory/YYYY-MM-DD.md",
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

Durability fields are only required in strict+durability mode. Parity and strict-without-durability modes may omit them — `index.py --add` tolerates absence.

**`$TMPDIR/merge.json`** (for `--reinforce`):

```json
{
  "source": "memory/YYYY-MM-DD.md",
  "mergeKey": "stable-slug",
  "mergeReason": "merge-into:mem_042",
  "summary": "optional refined summary"
}
```

**`$TMPDIR/trend.json`** (for `--compress-trend`):

```json
{
  "source": "memory/YYYY-MM-DD.md",
  "trendKey": "stable-slug",
  "summary": "Trend one-liner",
  "compressionReason": "reinforce-trend:mem_099 or new-trend:<key>",
  "tags": []
}
```

### Step 2.5: Snapshot AFTER [SCRIPT]

```bash
python3 $SCRIPTS_DIR/snapshot.py --memory-file RTMEMORY.md --save-as after
python3 $SCRIPTS_DIR/snapshot.py --delta $TMPDIR/reflections-snapshot-before.json $TMPDIR/reflections-snapshot-after.json
```

### Step 2.7: Mark processed logs [LLM]

Mark a daily log `<!-- consolidated -->` when every candidate extracted from that log has reached a terminal handled state:

- `route ∈ {promote, merge, compress, reject}` (strict+durability), OR
- `route == "defer"` AND the candidate's identity is in the deferred store, OR
- promoted this cycle (strict-without-durability and parity), OR
- recorded in the deferred store (strict-without-durability).

Otherwise leave unmarked — next cycle retries only unhandled candidates.

Backstop check:

```bash
python3 $SCRIPTS_DIR/deferred.py --is-deferred <existingId|fingerprint|candidate_hash>
# exit 0 = present in store
```

### Step 2.8: Stale Thread Detection [SCRIPT]

```bash
python3 $SCRIPTS_DIR/stale.py --memory-file RTMEMORY.md \
  --index runtime/reflections-metadata.json --threshold 14 --top 3
```

---

## Step 3: Evaluate + Archival [SCRIPT]

```bash
python3 $SCRIPTS_DIR/health.py --index runtime/reflections-metadata.json --memory-file RTMEMORY.md
python3 $SCRIPTS_DIR/score.py --index runtime/reflections-metadata.json --check-archival
```

For each archival candidate:

```bash
python3 $SCRIPTS_DIR/index.py --index runtime/reflections-metadata.json --archive <id> --summary "<one-line>"
```

Append one line per archived entry to `memory/.reflections-archive.md`.

---

## Step 3.5: Insights [LLM]

Generate 1–2 non-obvious insights from the health output and this cycle's route counts. Append to the reflection report.

---

## Step 3.6: Persist index stats [SCRIPT]

Write this cycle's `healthScore`, `healthMetrics`, `insights`, and route counters back into `runtime/reflections-metadata.json`. This updates `lastDream`, appends to `healthHistory`, and makes the weekly helper (Step 4.4) see a fresh snapshot next cycle.

Compose `$TMPDIR/stats.json` from the health.py output + Step 3.5 insights + cycle route counters:

```json
{
  "healthScore": <health_score from health.py>,
  "healthMetrics": <metrics object from health.py>,
  "insights": ["<insight 1>", "<insight 2>"],
  "gateStats": {
    "lastCycleQualified": <gate.py qualified_count or 0>,
    "lastCycleDeferred": <gate.py deferred_count or 0>,
    "lastCycleBreakdown": { "rem": 0, "deep": 0, "core": 0 },
    "lastCycleDurable": {
      "promoted": <durability promoted_count or 0>,
      "merged": <durability merged_count or 0>,
      "compressed": <durability compressed_count or 0>,
      "deferred": <durability deferred_count or 0>,
      "rejected": <durability rejected_count or 0>
    }
  }
}
```

In parity / strict-without-durability mode, omit `lastCycleDurable` (or set all counters to 0). The `gateStats` block tolerates missing keys.

```bash
python3 $SCRIPTS_DIR/index.py --index runtime/reflections-metadata.json --update-stats $TMPDIR/stats.json
```

---

## Step 4: Report + Notify

### 4.1 Append to log [LLM]

Append the cycle report to `memory/.reflections-log.md`.

### 4.2 Write telemetry [SCRIPT]

Mode-aware details payload:

- `STRICT_MODE == false`:
  ```
  {"logs_scanned": N, "entries_extracted": N, "entries_consolidated": N, "logs_marked_consolidated": N}
  ```
- `STRICT_MODE == true` AND `DURABILITY_ON == false`:
  ```
  {"logs_scanned": N, "entries_extracted": N, "entries_qualified": N, "entries_deferred": N, "entries_promoted": N, "logs_marked_consolidated": N}
  ```
- `DURABILITY_ON == true`:
  ```
  {"logs_scanned": N, "entries_extracted": N, "entries_qualified": N, "entries_deferred": N,
   "entries_durable_promoted": N, "entries_durable_merged": N, "entries_durable_compressed": N,
   "entries_durable_deferred": N, "entries_durable_rejected": N, "logs_marked_consolidated": N}
  ```

```bash
python3 $SCRIPTS_DIR/append_memory_log.py \
  --telemetry-dir $TELEMETRY_ROOT \
  --status ok --event run_completed \
  --profile <profile> --mode scheduled \
  --agent-id <agent id or main> \
  --details-json '<payload>'
```

### 4.3 Check notify gate

Read `$WORKSPACE_ROOT/runtime/memory-state.json`. If `reflections.reporting.sendReport != true` → END (no chat output).

### 4.4 Send notification (only if sendReport is true)

Compute all notification fields deterministically before composing the message. The prompt formats; scripts compute.

**Weekly trigger check** (Sunday 18:30 local time OR `reflection_count % 7 == 0`) — set `WEEKLY_FLAG` accordingly.

```bash
python3 $SCRIPTS_DIR/report.py \
  --index runtime/reflections-metadata.json \
  --config $CONFIG_PATH \
  --kind cycle \
  --before $TMPDIR/reflections-snapshot-before.json \
  --after $TMPDIR/reflections-snapshot-after.json \
  --modes-fired $MODE_CSV \
  --logs-count <N> \
  --new <N> --updated <N> --archived <N> \
  [--gate-qualified <N> --gate-deferred <N>] \
  [--durable-promoted <N> --durable-merged <N> --durable-compressed <N> --durable-deferred <N> --durable-rejected <N>] \
  [--weekly]   # add this flag only when WEEKLY_FLAG is set
  > $TMPDIR/reflections-report-cycle.json
```

`--logs-count` is the number of daily logs processed this cycle (from the `unconsolidated` list in Step 0-A's scan.py output). Optional counter flags: pass `--gate-*` in strict mode; pass `--durable-*` in strict+durability mode. Omit them in parity mode. The `--weekly` flag triggers the weekly block computation.

Emit the notification using **only** fields from `$TMPDIR/reflections-report-cycle.json`. The prompt never invents numbers.

**Weekly block** (prepend if `report.weekly.weekly_snapshot_available == true`):

```
📊 Weekly Report ({weekly.date_range})

🧠 This week: +{weekly.weekly_new} new · {weekly.weekly_updated} updated · {weekly.weekly_archived} archived
   {weekly.total_before_week} → {weekly.total_after} entries ({weekly.percent_growth} growth)

🌟 Biggest memories this week:
   1. {weekly.biggest_memories[0].summary}
   2. {weekly.biggest_memories[1].summary}
   3. {weekly.biggest_memories[2].summary}
```

If fewer than 3 biggest-memories are returned, render only the entries present. If `weekly_snapshot_available == false`, omit the block entirely.

**Main notification format:**

```
💭 Reflection #{reflection_count} complete ({modes_fired} cycle)

📥 Consolidated: {entries_delta} entries from {logs_count} logs
   new: {new} · updated: {updated} · archived: {archived}
📈 Total: {total_before} → {total_after} entries ({percent_growth} growth)
🧠 Health: {health_score}/100 — {rating}

✨ Highlights:
   • {LLM-composed change bullet, from this cycle's promoted entries}
   • {LLM-composed change bullet}

💡 Insight: {top insight from Step 3.5}

⏳ Stale: {one stale result if any, from Step 2.8 output}

{milestones[0] if any}
{milestones[1] if any}
💬 {LLM-composed Let the user know if there are something missed}
```

**Field provenance — all numeric/state fields come from `reflections-report-cycle.json`:**

| Template placeholder | JSON path |
|----------------------|-----------|
| `{reflection_count}` | `.reflection_count` |
| `{modes_fired}` | `.modes_fired` |
| `{entries_delta}` | `.entries_delta` |
| `{logs_count}` | `.logs_count` |
| `{new}` / `{updated}` / `{archived}` | `.new` / `.updated` / `.archived` |
| `{total_before}` / `{total_after}` / `{percent_growth}` | `.total_before` / `.total_after` / `.percent_growth` |
| `{health_score}` / `{rating}` | `.health_score` / `.rating` |
| `{milestones[...]}` | `.milestones[]` |

**LLM-authored fields** (semantic summarization only):
- `✨ Highlights` — composed from this cycle's promoted entries (read the mutated `reflections-candidates.json` where `route == "promote"`; distill into short bullets)
- `💡 Insight` — the top line from Step 3.5's LLM-generated insights
- `⏳ Stale` — one stale result from Step 2.8's `stale.py` output
- `💬 closing line` — a short, warm closing that invites the operator to flag anything missed. Vary the wording each cycle (e.g. "Let me know if anything was missed." / "Flag anything that didn't land." / "Tell me if I missed a beat."). Do not hardcode the same sentence every time; do not include any numeric/state field here.

Do not invent any numeric field. If a report field is `null`, omit the line or token.

This reply is your ONLY output. Concise. No narration. No meta-commentary about which fields were populated.

---

## Step 5: Update lastRun [SCRIPT]

```bash
python3 $SCRIPTS_DIR/dispatch.py --config $CONFIG_PATH --update-lastrun $MODE_CSV
```

---

## Blocker Handling

If any required script fails, config is missing, or the workspace is unwritable:

1. Write a `run_failed` telemetry event with `--status error --error "<message>"`.
2. Emit a single blocker message to chat if `sendReport == true`.
3. Do NOT mark any daily log. Do NOT partial-commit the index. END.

## Safety Rules

- Never delete daily logs — only mark `<!-- consolidated -->`.
- Never remove ⚠️ PERMANENT entries during archival.
- Back up `RTMEMORY.md` to `RTMEMORY.md.bak` before any write that changes it by >30%.
- Back up `runtime/reflections-metadata.json` to `.bak` before mutation.

For design rationale and longer explanations, see `references/reflections-prompt-v1.4-full.md`.
