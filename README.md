# Reflections v1.5.0

Reflections preserves the same reflection/scoring role as Auto-Dream, uses memory-core-safe long-term surfaces, and applies profile-driven admission before durable promotion.

## The Problem

AI agents forget. Session ends, context gone. Files pile up. Daily logs accumulate but remain unconsolidated and disconnected. The agent has data but can't reason about it across time.

Reflections runs periodic consolidation cycles that scan, extract, consolidate, and archive the agent's knowledge -- automatically and safely.

## What This Package Is

Reflections is a scheduled cron consolidator -- a host-side structured memory maintenance layer. It reads daily logs on a timer, consolidates extracted entries into its long-horizon surfaces, and archives low-importance entries via a forgetting curve.

It is not a plugin. It is not the active memory system. It does not intercept, modify, or compete with the host's native memory pipeline.

## What It Owns

- `RTMEMORY.md` -- reflective long-horizon continuity (consolidated from daily logs)
- `PROCEDURES.md` -- reusable workflows and stable operating patterns
- `episodes/*.md` -- bounded event/project narratives
- `runtime/reflections-metadata.json` -- consolidation metadata, routing/index state, health stats
- `reflections.json` -- its own configuration (resolved dynamically at runtime)
- `memory/.reflections-log.md` -- consolidation cycle reports
- `memory/.reflections-archive.md` -- compressed old entries

## Why It Exists

Daily logs accumulate but remain unconsolidated and disconnected. Reflections runs periodic consolidation cycles that scan, extract, consolidate, and archive knowledge automatically and safely -- producing structured long-horizon memory that complements the host's active memory system.

## Works With memory-core

Reflections is designed to run alongside OpenClaw's native memory-core dreaming system, not replace it.

**memory-core** handles active memory: recall during conversations, promotion of high-signal facts into `MEMORY.md`, and native dreaming cycles that maintain the agent's live durable memory surface. It owns what the agent knows right now.

**Reflections** handles long-horizon maintenance: it reads the same daily logs that memory-core reads, but writes to different surfaces (`RTMEMORY.md`, `PROCEDURES.md`, `episodes/`). It extracts decision rationale, project arcs, relationship history, and operational patterns that matter across weeks and months -- things that are too structural or slow-moving for memory-core's active promotion cycle.

Both systems coexist because they serve different time horizons:

| System | Time Horizon | What It Captures | Primary Surface |
|--------|-------------|-------------------|-----------------|
| memory-core | Active/recent | Durable facts, preferences, decisions | `MEMORY.md` |
| Reflections | Long-horizon | Rationale, patterns, arcs, procedures | `RTMEMORY.md` |

They share the same daily logs as input but never write to each other's surfaces. memory-core does not write to `RTMEMORY.md`. Reflections does not write to `MEMORY.md`. There is no conflict, no race condition, and no ownership overlap.

If memory-wiki is also installed, it provides a third layer: compiled provenance-rich wiki knowledge built from both active and reflective memory. Reflections does not interact with memory-wiki directly.

## Non-Goals

Reflections does **NOT**:
- Replace memory-core's active memory — `MEMORY.md` remains owned by memory-core
- Intercept or modify daily logs — they are read-only input
- Delete any entries — only archives old low-importance ones
- Own agent identity or user profile surfaces — those remain in `IDENTITY.md` / `USER.md`
- Run without mode dispatch checks — elapsed-time gating self-regulates

## Memory Layers

| Layer | Storage | What Goes Here |
|-------|---------|----------------|
| **Working** | LCM plugin (optional) | Real-time context compression and recall |
| **Episodic** | `episodes/*.md` | Bounded event/project narratives |
| **Long-horizon** | `RTMEMORY.md` | Reflective continuity, decisions, project arcs, strategic shifts |
| **Procedural** | `PROCEDURES.md` | Reusable workflows, routines, operating patterns |
| **Index** | `runtime/reflections-metadata.json` | Consolidation metadata, routing state, health stats |

## Features

- **Multi-mode consolidation** -- rem (6h), deep (12h), core (daily) dispatch cadence
- **Importance scoring** -- recency-weighted, reference-boosted entry scoring (used for archival)
- **Configurable scored admission (strictMode)** -- when enabled, minScore/minRecallCount/minUnique thresholds gate candidates before promotion; non-qualified items are recorded in a persistent deferred store (`runtime/reflections-deferred.jsonl`) and deterministically suppressed on future cycles. Default: `false` for personal-assistant (parity flow), `true` for business-employee (strict fork). Strictness is profile-opt-in, not global.
- **Durability filter (v1.3.0 full route set, strictMode AND durability.enabled)** -- second-stage semantic admission after the structural gate. Routes each candidate into one of five lanes: `promote` (new durable node), `merge` (reinforce existing node, no new surface entry), `compress` (upsert trend node in `TRENDS.md`), `defer` (re-evaluate next cycle), or `reject` (discard). Hard-promote triggers rescue rare one-off high-consequence items that structural scoring underweights; hard-suppress triggers reject telemetry noise regardless of reinforcement. Trend-to-durable promotion: an accumulated trend becomes eligible for RTMEMORY only when a fresh cycle adds a hard-promote trigger AND the trend meets support thresholds. Default on for business-employee; off for personal-assistant.
- **Fast-path markers** -- PERMANENT/HIGH/PIN recognized for archival immunity and strict-mode routing
- **Intelligent forgetting** -- old low-importance entries archived, never deleted
- **Knowledge graph** -- semantic relation linking with reachability metrics
- **Health monitoring** -- 5-metric health score (freshness, coverage, coherence, efficiency, reachability)
- **Push notifications** -- silent, summary, or full consolidation reports
- **Dashboard template** (optional, operator-driven) -- zero-dependency HTML template at `references/dashboard-template.html`. Rendering is not part of the automated cycle; operators can use it manually or via external tooling.
- **Cross-instance export/import** -- portable JSON bundles with conflict resolution
- **Token-usage visibility (v1.5.0)** -- every telemetry event carries a `token_usage` block (`prompt_tokens` / `completion_tokens` / `total_tokens` / `source ∈ {exact, approximate, unavailable}`). Scripts own the math: `append_memory_log.py` and `report.py` accept either exact token args (from host metadata) or `--prompt-chars` / `--completion-chars` (in which case the `ceil(chars/4)` approximation is computed internally and labeled `approximate`). The runtime prompt never computes token counts itself. `index.py --update-stats` appends to `stats.tokenHistory` only when source is `exact` or `approximate`; `weekly.py` rolls up in-window totals. Final notification emits a compact `🪙 Token Usage:` line (omits when unavailable). Visibility-only — does not affect scoring, gating, deferring, routing, or archival behavior.

## Manual Triggers

- "Reflect now" (alias: "Dream now") -- run all modes immediately
- "Reflect core" / "Reflect rem" / "Reflect deep" -- run a specific mode
- "Show reflection config" -- display current reflections.json
- "Set consolidation mode to core only" -- update active modes

## Safety

| Rule | Why |
|------|-----|
| Never delete daily logs | Immutable source of truth |
| Never remove `PERMANENT` entries | User protection is absolute |
| Episodes are append-only | Narrative history preserved forever |
| Auto-backup on >30% change | Prevents accidental corruption |
| Config + index backup every cycle | Always recoverable |
| Daily logs marked `<!-- consolidated -->` per-log | Immediately after each log's consolidation succeeds; unmarked logs retry next cycle |

## Configuration

Key config fields in `reflections.json` (see `references/memory-template.md` for full schema):

- `strictMode` (boolean): when `true`, recurring flow inserts a pre-consolidation gate and deterministic deferred-suppression. **Scope: profile-opt-in.** Personal-assistant defaults to `false` (parity flow — all extracted candidates consolidate). Business-employee defaults to `true` (strict flow — scored admission + persistent deferred store + durability filter). Operators can override per-install.
- `scanWindowDays` (integer): days of recent daily logs the recurring prompt scans. **Profile-driven by noise tolerance**: personal-assistant default `7` (sparse-but-meaningful exchanges); business-employee default `3` (higher-volume/noisier stream). First-run scans full history regardless.
- `dispatchCadence` (cron expr): when the host cron fires the recurring prompt. Personal-assistant default `"30 4,10,16,22 * * *"`, business-employee default `"30 5,12,18,22 * * *"`.
- `durability` (object): second-stage semantic filter. `durability.enabled` activates the filter (personal-assistant default `false`; business-employee default `true`). `durability.netPromoteThreshold` / `durability.netDeferThreshold` set the net-score bands (business: 6/3; personal: 5/2). `durability.trendPromoteSupportCount` / `durability.trendPromoteUniqueDayCount` set the trend-to-durable promotion thresholds (business: 5/3; personal: 4/2). Only runs when `strictMode == true`.
- Per-mode thresholds (`minScore`, `minRecallCount`, `minUnique`) — used by strict-mode gate when `strictMode: true`.

**Dispatch semantics** (two separate layers):
- **Host scheduling** uses top-level `dispatchCadence`. That is the only cron schedule.
- **Mode-due check** inside the prompt uses hardcoded intervals in `scripts/dispatch.py` — rem=6h, deep=12h, core=24h — compared against each mode's `lastRun` timestamp. Per-mode `modes.*.cadence` fields are not consumed by any script and have been removed from the sample presets in v1.1.5.

## Install

### Option 1: Quick Install (operator)

```bash
curl -fsSL https://raw.githubusercontent.com/catx0rr/reflections/main/install.sh | bash
```

Override defaults if needed:

```bash
CONFIG_ROOT="$HOME/.openclaw" \
WORKSPACE="$HOME/.openclaw/workspace" \
SKILLS_PATH="$HOME/.openclaw/workspace/skills" \
curl -fsSL https://raw.githubusercontent.com/catx0rr/reflections/main/install.sh | bash
```

### Option 2: Agent Setup

Tell your agent to read `INSTALL.md`:

> Install the reflections, read the `INSTALL.md` follow every step and provide summary of changes after the install.


## Reference Documentation

| Document | Audience | Content |
|----------|----------|---------|
| `INSTALL.md` | Agent | Setup, configuration, profile selection, cron wiring, first-run bootstrap |
| `SKILL.md` | Agent | Manual-use skill -- operator-triggered reflections |
| `references/skill-reference.md` | Agent/operator | Full architecture, consolidation flow, script inventory, orchestration |
| `references/runtime-templates.md` | Agent/operator | Runtime artifact schemas, telemetry log format, path model |
| `references/scoring.md` | Agent/operator | Importance scoring, forgetting curve, health algorithms, profile-driven strict-mode gates |

## CREDITS
> **Fork note:** This is a fork of [*myclaw.ai - openclaw-auto-dream*](https://github.com/LeoYeAI/openclaw-auto-dream)
> This version (Reflections) redirects the long-horizon layer from `MEMORY.md` to `RTMEMORY.md`.
> `MEMORY.md` remains owned by OpenClaw's native `memory-core` and dreaming system.
> Both systems read from the same daily logs but write to separate primary targets -- complementary but distinct roles.

## License

[MIT](LICENSE)
