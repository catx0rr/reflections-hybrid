---
name: reflections
description: "Manual reflective memory consolidation for operator-triggered use. Use when: user asks for 'reflections', 'reflect', 'reflect now', 'dream', 'memory consolidation', 'consolidate memory', 'export memory'."
---

# Reflections — Manual Consolidation Skill

Reflections preserves the same reflection/scoring role as Auto-Dream, uses memory-core-safe long-term surfaces, and applies profile-driven admission before durable promotion.

Reflections consolidates daily logs into structured long-horizon memory surfaces. This skill covers operator-requested runs, checks, summaries, and targeted consolidation. Autonomous scheduling and setup are handled separately.

## When to Use

- Operator wants to run a reflection cycle now
- Operator wants a manual core/rem/deep pass
- Operator wants a status check or health summary
- Operator wants to see what changed in the last run
- Operator wants to inspect outputs or telemetry after a run
- Operator wants to adjust consolidation modes or thresholds

## Manual Triggers

| Command | Action |
|---------|--------|
| "Consolidate memory" / "Reflect now" | Run full consolidation cycle (all modes) |
| "Reflect core" / "Reflect rem" / "Reflect deep" | Run specific mode only |
| "Dream now" / "Dream core" / etc. | Backward-compatible aliases |
| "Export memory" | Export memory/export-YYYY-MM-DD.json |
| "Show reflection config" | Display current reflections.json |
| "Set consolidation mode to core only" | Update reflections.json (confirm with user first) |

## Preconditions

Before manual execution:

1. Confirm workspace context — resolve paths dynamically, do not assume fixed install paths
2. Verify `reflections.json` exists with a selected profile
3. Verify required memory files are initialized (RTMEMORY.md, runtime/reflections-metadata.json, PROCEDURES.md)
4. If files are missing, point the operator to `INSTALL.md` — do not invent outputs

## Outputs

A manual run produces:

- **RTMEMORY.md** — updated long-horizon reflective memory
- **PROCEDURES.md** — updated reusable workflows
- **episodes/*.md** — updated project narratives (if applicable)
- **runtime/reflections-metadata.json** — updated consolidation metadata and health stats
- **memory/.reflections-log.md** — appended human-readable consolidation report
- **Unified memory telemetry** — one structured event appended to `TELEMETRY_ROOT/memory-log-YYYY-MM-DD.jsonl`

## What the Agent Must Not Do

- Do not delete daily logs — only mark with `<!-- consolidated -->`
- Do not remove PERMANENT items
- Do not auto-install plugins or modify host config
- Do not write telemetry with raw shell echo — use `scripts/append_memory_log.py`
- Do not assume hardcoded paths — resolve SKILL_ROOT, WORKSPACE_ROOT, TELEMETRY_ROOT dynamically
- Do not skip telemetry even when notification is silent

## Language

All output uses the user's preferred language as recorded in USER.md.

## Boundaries

- This skill is for manual/operator-triggered use
- Scheduling and cron behavior are not owned by this file
- Setup and config internals are documented elsewhere
- Runtime orchestration details live in references and runtime files

## See Also

- `INSTALL.md` — installation, configuration, and first-run bootstrap
- `README.md` — package overview, ownership boundary, architecture
- `references/skill-reference.md` — full operational reference (modes, gates, config schema, scripts, cycle flow)
- `references/runtime-templates.md` — telemetry schema, log formats, path model
