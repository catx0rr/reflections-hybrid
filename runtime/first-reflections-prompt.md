# First Reflection — Initial Memory Scan

This is the one-time initial memory scan. Execute every step in the current session.
Read USER.md first to determine user's language. All output in that language.

## Path Resolution

Resolve these roots before any execution. Do not hardcode paths.

```
SKILL_ROOT     = absolute path of the parent of runtime/ (this file's parent dir)
SCRIPTS_DIR    = $SKILL_ROOT/scripts
WORKSPACE_ROOT = current working directory
CONFIG_PATH    = resolve by precedence:
                 1. REFLECTIONS_CONFIG env var
                 2. ~/.openclaw/reflections/reflections.json fallback
TELEMETRY_ROOT = resolve by precedence:
                 1. REFLECTIONS_TELEMETRY_ROOT env var
                 2. MEMORY_TELEMETRY_ROOT env var
                 3. ~/.openclaw/telemetry fallback
```

**GATE BYPASS:** First Reflection bypasses all quality gates. Every extracted entry is consolidated regardless of thresholds.

**Config:** Read `$CONFIG_PATH`. Set `promotedBy: "first-reflection"` on all entries created during this run.

## Execution Guardrails

- **Execute this workflow directly.** Do not delegate any step to a sub-agent.
- Do not offload consolidation, file writes, telemetry, or reporting to a sub-agent.
- This job must run in the current session context only.
- Every phase below is executed by the current agent.
- Do not narrate phases in chat.
- Do not send progress updates in chat.
- Do not explain tool usage in chat.
- Internal execution details go only to telemetry and log files.
- Chat emits only: the final Phase 4 report (or Phase 5 Fresh Instance Report), a blocker message, or nothing.

## Phase 1: Snapshot BEFORE

Count and record these numbers BEFORE making any changes:

```
MEMORY_LINES = wc -l RTMEMORY.md (0 if missing)
MEMORY_SECTIONS = grep -c "^## " RTMEMORY.md (0 if missing)
DECISIONS = grep -c "^- " on the "Key Decisions and Rationale" section (0 if missing)
LESSONS = grep -c "^- " on the "Lessons and Patterns" section (0 if missing)
PROCEDURES = wc -l PROCEDURES.md (0 if missing)
OPEN_THREADS = grep -c "^- \[" on the "Open Threads" section (0 if missing)
DAILY_LOGS = ls memory/????-??-??.md | wc -l
UNCONSOLIDATED = count files WITHOUT <!-- consolidated -->
EPISODES = ls episodes/*.md 2>/dev/null | wc -l
```

Save all these values — you will need them for the before/after comparison.

If DAILY_LOGS == 0 AND MEMORY_LINES < 10:
  → This is a FRESH instance. Skip to Phase 5 (Fresh Instance Report).

## Phase 2: Collect

Read ALL unconsolidated daily logs (not just last 3 days — this is the first run).
Extract:
- Decisions (choices made, direction changes)
- Operational context updates (data changes, metrics, technical details)
- Project progress (milestones, blockers, completions)
- Lessons (failures, wins, things that worked)
- Todos (unfinished items, pending follow-ups)
- Reusable workflows (stable operating patterns, tool usage, communication patterns)

Skip small talk. Skip content already in RTMEMORY.md that hasn't changed.

## Phase 3: Consolidate

Read RTMEMORY.md. Compare with extracted content:

- **New** → append to appropriate RTMEMORY.md section
- **Updated** → update in place (e.g., newer metrics)
- **Duplicate** → skip
- **Procedures/workflows** → append to PROCEDURES.md

Semantic dedup (compare meaning, not exact text).
Update `_Last updated:` date in RTMEMORY.md.
Mark each processed daily log with `<!-- consolidated -->` at end of file.

## Phase 4: Snapshot AFTER + Report

Count the same metrics again:

```
MEMORY_LINES_AFTER = wc -l RTMEMORY.md
MEMORY_SECTIONS_AFTER = ...
DECISIONS_AFTER = ...
LESSONS_AFTER = ...
PROCEDURES_AFTER = ...
OPEN_THREADS_AFTER = ...
```

Calculate: NEW_ENTRIES = total new items added, UPDATED_ENTRIES = total items updated.

Find STALE items: entries in Open Threads or other sections not referenced in last 30 days.

Write reflection report to memory/.reflections-log.md.

Then compose and reply with the First Reflection Report (this is your final reply, cron delivery will push it):

```
Reflections — First Memory Scan Complete!

📦 Your memory assets:
   • {DAILY_LOGS} daily logs ({earliest_date} ~ {latest_date}, spanning {days} days)
   • {MEMORY_LINES} lines of long-term memory (RTMEMORY.md)
   • {PROCEDURES} lines of workflow procedures
   • {EPISODES} project narratives

🔍 Scan results:
   • Extracted {NEW_ENTRIES} new entries from {UNCONSOLIDATED} logs
   • Updated {UPDATED_ENTRIES} existing entries
   • Found {STALE_COUNT} items stale for 30+ days

📊 Before → After:
   ┌─────────────────┬────────┬────────┐
   │                 │ Before │ After  │
   ├─────────────────┼────────┼────────┤
   │ Long-term memory│ {B}    │ {A}    │
   │ Key decisions   │ {B}    │ {A}    │
   │ Lessons learned │ {B}    │ {A}    │
   │ Procedures      │ {B}    │ {A}    │
   │ Open threads    │ {B}    │ {A}    │
   └─────────────────┴────────┴────────┘

🔮 Insights:
   1. {insight_1}
   2. {insight_2}
   3. {insight_3}

⏰ Scheduled auto-reflection is now set up.
   You'll receive reports on the configured schedule.

💬 Let me know if anything was missed.
```

Then add a personalized reflection based on what you actually found in the logs:

```
💭 After reading through {days} days of your history:
   {2-3 sentence personalized summary — mention specific projects by name,
   growth numbers, patterns you observed. End with one sentence about what
   Reflections will do going forward. Reference real content from the logs.}
```

Translate the entire report to the user's language (from USER.md) before sending.

## Phase 5: Fresh Instance Report

If this is a brand new instance with no daily logs and minimal RTMEMORY.md:

```
💭 Reflections Initialized!

✅ Memory architecture is ready:
   • 📝 Long-term memory (RTMEMORY.md)
   • 🔄 Workflow procedures (PROCEDURES.md)
   • 📁 Project narratives (episodes/)
   • 📊 Reflection reports (memory/.reflections-log.md)
   • 📦 Archive (memory/.reflections-archive.md)

🌱 Starting from zero — and that's fine.
   From now on, every conversation is remembered.
   On the configured schedule, I'll consolidate your daily logs
   into structured long-term memory.

⏰ Auto-reflection scheduled on the configured cadence.
   Your first real report will come after a few runs.

💬 Just chat naturally — I'll handle the rest.
```

Translate to user's language before sending.

## Telemetry [SCRIPT]

After the first reflection completes (success or error), append one structured event:

First-reflection bypasses all quality gates by design — every extracted candidate is consolidated. Use `entries_consolidated` (not `entries_qualified`) in the telemetry payload; there is no gate to qualify against.

```bash
python3 $SCRIPTS_DIR/append_memory_log.py \
  --telemetry-dir $TELEMETRY_ROOT \
  --status ok \
  --event run_completed \
  --profile <selected profile> \
  --mode first-reflection \
  --details-json '{"logs_scanned": <N>, "entries_extracted": <N>, "entries_consolidated": <N>}'
```

## Safety Rules
- Never delete daily log originals — only mark <!-- consolidated -->
- Never remove ⚠️ PERMANENT entries
- Backup: if RTMEMORY.md changes >30%, save RTMEMORY.md.bak first
