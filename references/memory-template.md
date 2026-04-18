# Memory Templates (v1.4.0)

Reflections preserves the same reflection/scoring role as Auto-Dream, uses memory-core-safe long-term surfaces, and applies profile-driven admission before durable promotion.

Templates for initializing the v1.3.0 cognitive memory architecture with multi-mode consolidation. **Config schema bumped `"1.2.0"` → `"1.3.0"` in package v1.3.0** to reflect the full durability route set — `merge`, `compress`, and the `TREND` destination — plus the trend-promotion thresholds (`trendPromoteSupportCount`, `trendPromoteUniqueDayCount`). Parsers accept `"1.0.0"` through `"1.3.0"`; writers should emit `"1.3.0"`. Runtime metadata schema (`reflections-metadata.json`) remains at `"1.0.0"` — the new per-entry trend fields flow through `index.py`'s pass-through without a schema version bump.

---

## reflections.json

Location: resolved via `$CONFIG_PATH` (default: `~/.openclaw/reflections/reflections.json`)

Two profile presets are available. Select one during setup (see `INSTALL.md`).

### Personal-assistant preset (default for personal/family/home-automation agents)

```json
{
  "version": "1.3.0",
  "profile": "personal-assistant",
  "strictMode": false,
  "scanWindowDays": 7,
  "dispatchCadence": "30 4,10,16,22 * * *",
  "durability": {
    "enabled": false,
    "netPromoteThreshold": 5,
    "netDeferThreshold": 2,
    "trendPromoteSupportCount": 4,
    "trendPromoteUniqueDayCount": 2
  },
  "activeModes": ["core", "rem", "deep"],
  "notificationLevel": "summary",
  "instanceName": "default",
  "timezone": "UTC",
  "modes": {
    "off": { "enabled": false },
    "core": {
      "enabled": true,
      "minScore": 0.72,
      "minRecallCount": 2,
      "minUnique": 1,
      "uniqueMode": "day_or_session",
      "fastPathMinScore": 0.90,
      "fastPathMinRecallCount": 2,
      "fastPathMarkers": ["HIGH", "PIN", "PREFERENCE", "ROUTINE"]
    },
    "rem": {
      "enabled": true,
      "minScore": 0.85,
      "minRecallCount": 2,
      "minUnique": 2,
      "uniqueMode": "day_or_session",
      "fastPathMinScore": 0.88,
      "fastPathMinRecallCount": 2,
      "fastPathMarkers": ["HIGH", "PIN", "PREFERENCE", "ROUTINE", "PROCEDURE"]
    },
    "deep": {
      "enabled": true,
      "minScore": 0.80,
      "minRecallCount": 2,
      "minUnique": 2,
      "uniqueMode": "day_or_session",
      "fastPathMinScore": 0.86,
      "fastPathMinRecallCount": 2,
      "fastPathMarkers": ["HIGH", "PIN", "PREFERENCE", "ROUTINE"]
    }
  },
  "lastRun": {
    "core": null,
    "rem": null,
    "deep": null
  }
}
```

### Business-employee preset (for supervisor DM / team GC / bounded workflow agents)

```json
{
  "version": "1.3.0",
  "profile": "business-employee",
  "strictMode": true,
  "scanWindowDays": 3,
  "dispatchCadence": "30 5,12,18,22 * * *",
  "durability": {
    "enabled": true,
    "netPromoteThreshold": 6,
    "netDeferThreshold": 3,
    "trendPromoteSupportCount": 5,
    "trendPromoteUniqueDayCount": 3
  },
  "activeModes": ["core", "rem", "deep"],
  "notificationLevel": "summary",
  "instanceName": "default",
  "timezone": "UTC",
  "modes": {
    "off": { "enabled": false },
    "core": {
      "enabled": true,
      "minScore": 0.72,
      "minRecallCount": 2,
      "minUnique": 1,
      "uniqueMode": "day_or_session",
      "fastPathMinScore": 0.92,
      "fastPathMinRecallCount": 2,
      "fastPathMarkers": ["HIGH", "PIN"]
    },
    "rem": {
      "enabled": true,
      "minScore": 0.85,
      "minRecallCount": 3,
      "minUnique": 2,
      "uniqueMode": "day_or_session",
      "fastPathMinScore": 0.90,
      "fastPathMinRecallCount": 2,
      "fastPathMarkers": ["HIGH", "PIN", "PROCEDURE"]
    },
    "deep": {
      "enabled": true,
      "minScore": 0.80,
      "minRecallCount": 2,
      "minUnique": 2,
      "uniqueMode": "day_or_session",
      "fastPathMinScore": 0.88,
      "fastPathMinRecallCount": 2,
      "fastPathMarkers": ["HIGH", "PIN", "PROCEDURE"]
    }
  },
  "lastRun": {
    "core": null,
    "rem": null,
    "deep": null
  }
}
```

### reflections.json field reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `version` | string | `"1.3.0"` | Config schema version. `"1.0.0"` (package v1.0.0–v1.1.5): only `profile`, `modes`, `activeModes`, `lastRun`. `"1.1.0"` (package v1.1.6): adds optional top-level `strictMode`, `scanWindowDays`, `dispatchCadence`. `"1.2.0"` (package v1.2.0): adds optional top-level `durability` block with `enabled` / `netPromoteThreshold` / `netDeferThreshold`. `"1.3.0"` (package v1.3.0+): adds `durability.trendPromoteSupportCount` and `durability.trendPromoteUniqueDayCount` for the full merge/compress/trend route set. Parsers must accept all four; writers should emit `"1.3.0"`. |
| `profile` | string | — | Selected setup profile (`"personal-assistant"` or `"business-employee"`) |
| `strictMode` | boolean | `false` (personal-assistant), `true` (business-employee) | When `true`, recurring flow inserts a pre-consolidation gate **and** deterministic deferred-suppression: candidates are scored, cross-referenced against the persistent deferred store (by `existingId` / `fingerprint` / `candidate_hash`), gated, and only fresh-qualified entries promote. Failed candidates are recorded to `runtime/reflections-deferred.jsonl` and skipped on future cycles. When `false`, matches upstream Auto-Dream Lite parity (all extracted candidates promote; archival happens post-consolidation). **Strictness is profile-opt-in, not global.** |
| `scanWindowDays` | integer | `7` (personal-assistant), `3` (business-employee) | How many days of daily logs the recurring prompt scans for unconsolidated work. **Profile-driven by noise tolerance**, not role title: business agents are higher-volume/noisier → tight 3-day window prevents drowning in re-extraction. Personal-assistant agents have sparse-but-meaningful exchanges → wider 7-day window preserves continuity. First-run ignores this and scans full history regardless. |
| `dispatchCadence` | string | `"30 4,10,16,22 * * *"` (personal-assistant), `"30 5,12,18,22 * * *"` (business-employee) | Cron expression for the single host-level cron job that fires the recurring prompt. **Profile-driven**: cadences are intentionally offset so two profiles co-hosted on one machine don't fire at the same minute. Read by `INSTALL.md` Step 6 when creating the cron job; timezone is still sourced from the top-level `timezone` field. Operators can override for bespoke schedules. |
| `durability` | object | `{enabled: false, netPromoteThreshold: 5, netDeferThreshold: 2}` (personal-assistant); `{enabled: true, netPromoteThreshold: 6, netDeferThreshold: 3}` (business-employee) | Top-level durability filter configuration. **Added in schema `"1.2.0"`.** Durability runs as Steps 1.7 (LLM annotation) + 1.8 (SCRIPT routing) between structural gate and durable write. Activates only when `strictMode == true` AND `durability.enabled == true`. Parity mode never runs durability by design. |
| `durability.enabled` | boolean | `false` (personal-assistant), `true` (business-employee) | Master toggle for the durability filter. If `false`, Steps 1.7/1.8 are skipped and strict-mode behaves as v1.1.6 (gate-only). If `true` without `strictMode == true`, still skipped (durability requires strict mode). |
| `durability.netPromoteThreshold` | integer | `5` (personal-assistant), `6` (business-employee) | Minimum `net = structuralEvidence + meaningWeight + futureConsequence − noisePenalty` for a candidate to route to `promote` via net-score banding. Hard-promote triggers bypass this threshold. |
| `durability.netDeferThreshold` | integer | `2` (personal-assistant), `3` (business-employee) | Minimum `net` for a candidate to route to `defer` (below this → `reject`). Hard-suppress triggers bypass this and force `reject` regardless of net. |
| `durability.trendPromoteSupportCount` | integer | `4` (personal-assistant), `5` (business-employee) | **v1.3.0.** An existing trend node becomes eligible to promote into RTMEMORY as a durable conclusion only when its `trendSupportCount` meets or exceeds this value AND `trendPromoteUniqueDayCount` is also met AND a fresh candidate cycle adds a hard-promote trigger. Accumulation alone does not promote. |
| `durability.trendPromoteUniqueDayCount` | integer | `2` (personal-assistant), `3` (business-employee) | **v1.3.0.** Minimum distinct days the trend must have been reinforced across to be promotion-eligible. Paired with `trendPromoteSupportCount`. |
| `activeModes` | string[] | `["core","rem","deep"]` | Modes enabled for cron dispatch |
| `notificationLevel` | string | `"summary"` | `"silent"`, `"summary"`, or `"full"` |
| `instanceName` | string | `"default"` | Human-readable instance identifier |
| `timezone` | string | `"UTC"` | IANA timezone for cron scheduling |
| `modes` | object | — | Per-mode gate thresholds |
| `modes.{name}.enabled` | boolean | — | Whether this mode is active |
| `modes.{name}.minScore` | number | — | Minimum importance score to qualify |
| `modes.{name}.minRecallCount` | number | — | Minimum referenceCount to qualify |
| `modes.{name}.minUnique` | number | — | Minimum uniqueness count to qualify |
| `modes.{name}.uniqueMode` | string | `"day_or_session"` | How minUnique is evaluated: `"day_or_session"`, `"day"`, `"session"`, `"channel"`, `"max"` |
| `modes.{name}.fastPathMinScore` | number | — | Minimum importance for fast-path bypass |
| `modes.{name}.fastPathMinRecallCount` | number | — | Minimum recall count for fast-path bypass |
| `modes.{name}.fastPathMarkers` | string[] | — | Markers that trigger fast-path evaluation |
| `lastRun` | object | — | ISO timestamps of last completed run per mode |

### Dispatch Semantics

Two separate scheduling mechanisms — do not conflate:

| Layer | Controlled by | Scope |
|-------|---------------|-------|
| **Host scheduling** (cron fires the prompt) | top-level `dispatchCadence` (cron expr) + top-level `timezone` | When the recurring prompt runs at all |
| **Mode-due check** (which modes the prompt processes) | hardcoded `MODE_INTERVALS` in `scripts/dispatch.py` (rem=6h, deep=12h, core=24h), compared against each mode's `lastRun` timestamp | Which modes run inside a given fire |

Per-mode `modes.*.cadence` fields are **not consumed** by any script and have been removed from the sample presets above. If a legacy config still contains them, they are silently ignored by `dispatch.py` (no warning, no effect). The historically-intended "cadence" for each mode is the hardcoded interval documented in `dispatch.py`; the config-level cadence never drove it.

If the operator wants different mode intervals, that requires a `dispatch.py` code change. This is deliberate — uniform intervals across installs simplify observability and cross-install comparison.

---

## RTMEMORY.md

```markdown
# RTMEMORY.md — Long-Horizon Reflective Memory

_Last updated: YYYY-MM-DD_

> Managed by the Reflections consolidator.
> Canonical durable profile facts belong to MEMORY.md and bootstrap/profile files.
> This file stores reflective continuity, major decisions, long-horizon patterns, and project history.

---

## Scope Notes
- Agent identity is canonical in IDENTITY.md / SOUL.md
- User durable profile is canonical in USER.md and/or MEMORY.md
- Avoid duplicating static profile sheets here unless they matter to continuity, decisions, or history

## Active Initiatives
<!-- Major projects, architecture tracks, current state -->

## Business Context and Metrics
<!-- Revenue, unit economics, operational metrics, business state -->

## People and Relationships
<!-- Relationship-relevant history, working patterns, role shifts, trust-relevant context -->

## Strategy and Priorities
<!-- Long-horizon goals, direction shifts, strategic reasoning -->

## Key Decisions and Rationale
<!-- Important decisions with dates and why they were made -->

## Lessons and Patterns
<!-- Reusable lessons, recurring failures, successful patterns -->

## Episodes and Timelines
<!-- Cross-links to episodes/*.md and major historical turns -->

## Environment Notes
<!-- Only long-lived environment facts with repeated operational relevance -->

## Open Threads
<!-- Pending unresolved items that matter across sessions -->
```

---

## PROCEDURES.md

```markdown
# Procedures — How I Do Things

_Last updated: YYYY-MM-DD_

---

## Communication Preferences
<!-- Language, tone, format preferences the user has expressed -->

## Tool Workflows
<!-- Learned sequences for tools and integrations -->

## Format Preferences
<!-- How the user likes output structured -->

## Shortcuts and Patterns
<!-- Recurring patterns, aliases, quick references -->
```

---

## episodes/ structure

Each episode is a standalone markdown file tracking a project or significant event:

```markdown
# Episode: [Project/Event Name]

_Period: YYYY-MM-DD ~ YYYY-MM-DD_
_Status: active | completed | paused_
_Related: mem_xxx, mem_yyy_

---

## Timeline
<!-- Chronological entries, each with a date -->
- **YYYY-MM-DD** — What happened

## Key Decisions
<!-- Major choices made during this episode -->
- **YYYY-MM-DD** — Decision and rationale

## Lessons
<!-- What was learned from this episode -->
- Insight or takeaway
```

Naming convention: `episodes/<kebab-case-name>.md`

---

## TRENDS.md (v1.3.0+)

Single canonical file surfacing trend nodes that accumulate repeated weak ops material. Mirrors `RTMEMORY.md`'s structure (human-readable sections rendered from `runtime/reflections-metadata.json` entries where `memoryType == "trend"`).

**Distinction from other surfaces:**
- **RTMEMORY.md** = durable reflective conclusions, lessons, decisions, identity/relationship shifts
- **PROCEDURES.md** = repeatable know-how, validated workflows
- **episodes/** = bounded historical incidents/narratives
- **TRENDS.md** = repeated reality/pattern without stable method (recurring gateway instability, repeated weak blocker pattern, recurring support issue pattern)
- **memory/.reflections-archive.md** = low-importance compressed archive

Trend entries land here via `durability.py` routing `compress` and `index.py --compress-trend` upserting. A trend entry later becomes eligible to promote into RTMEMORY as a durable conclusion only when its `trendSupportCount` + `uniqueDayCount` pass the profile's thresholds AND a fresh candidate cycle adds a hard-promote trigger.

```markdown
# Memory Trends — Recurring Patterns

_Managed by the Reflections consolidator (memoryType=trend, route=compress)._
_Last updated: YYYY-MM-DD_

---

## Active Trends

### <trendKey>
- **First observed:** YYYY-MM-DD
- **Last reinforced:** YYYY-MM-DD
- **Support:** N observations across M days, S sources
- **Pattern:** one-line summary (echoes the index entry's `summary`)
- **Related entries:** mem_xxx, mem_yyy
- **Node ID:** mem_nnn

---

## Promoted Trends
<!-- Trend nodes that became durable conclusions via a hard-promote trigger on a subsequent cycle -->
- `mem_nnn` ("<trendKey>") → promoted to RTMEMORY as `mem_mmm` on YYYY-MM-DD
```

Naming rule: one `### <trendKey>` section per active trend. Promoted trends move to the "Promoted Trends" list but the original trend node stays in the index as historical context.

---

## runtime/reflections-metadata.json (v1.0.0 Schema)

```json
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
```

**Note:** Configuration fields (`notificationLevel`, `instanceName`, `timezone`, mode settings) have moved to `reflections.json` (resolved via `$CONFIG_PATH`). The `runtime/reflections-metadata.json` now contains only runtime entry metadata and stats.

### stats fields

| Field | Type | Description |
|-------|------|-------------|
| `totalEntries` | number | Count of all non-archived entries |
| `avgImportance` | number | Mean importance score across all entries |
| `lastPruned` | string \| null | ISO timestamp of last archival operation |
| `healthScore` | number | Latest health score (0–100) |
| `healthMetrics` | object | Per-metric scores for the latest consolidation |
| `insights` | string[] | Latest consolidation insights (plain text, 1–3 items) |
| `healthHistory` | array | Chronological health snapshots (capped at 90) |
| `gateStats` | object | Quality gate results from the most recent cycle |

### Entry schema (v1.0.0)

Each object in `entries` follows this structure:

```json
{
  "id": "mem_001",
  "summary": "One-line summary of the memory entry",
  "source": "memory/2026-04-01.md",
  "target": "RTMEMORY.md#active-initiatives",
  "created": "2026-04-01",
  "lastReferenced": "2026-04-05",
  "referenceCount": 7,
  "uniqueSessionCount": 4,
  "sessionSources": [
    "memory/2026-04-01.md",
    "memory/2026-04-02.md",
    "memory/2026-04-04.md",
    "memory/2026-04-05.md"
  ],
  "uniqueDayCount": 4,
  "uniqueDaySources": [
    "2026-04-01",
    "2026-04-02",
    "2026-04-04",
    "2026-04-05"
  ],
  "promotedBy": "rem",
  "importance": 0.82,
  "tags": ["project", "architecture"],
  "related": ["mem_002", "mem_005"],
  "archived": false,

  "memoryType": "decision",
  "durabilityClass": "durable",
  "route": "promote",
  "destination": "RTMEMORY",
  "durabilityScore": 8,
  "noisePenalty": 0,
  "promotionReason": "hard-trigger:decision-with-consequence",
  "mergeKey": null,
  "trendKey": null,
  "supportCount": 3
}
```

Field reference:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique ID: `mem_NNN` (zero-padded to 3+ digits) |
| `summary` | string | One-line plain-text summary |
| `source` | string | File path where the raw info was found |
| `target` | string | File path + section where it was consolidated |
| `created` | string | ISO date when entry was first created |
| `lastReferenced` | string | ISO date when entry was last read/updated |
| `referenceCount` | number | Total times this entry has been referenced |
| `uniqueSessionCount` | number | Distinct sessions that referenced this entry |
| `sessionSources` | string[] | Last 30 session filenames that referenced this entry |
| `uniqueDayCount` | number | Distinct days that referenced this entry (derived from source path dates) |
| `uniqueDaySources` | string[] | Last 30 day strings (YYYY-MM-DD) that referenced this entry |
| `promotedBy` | string | Which consolidation mode promoted this entry (`"core"`, `"rem"`, `"deep"`, `"first-reflection"`, `"manual"`) |
| `importance` | number | Computed score, 0.0–1.0 |
| `tags` | string[] | Categorization tags |
| `related` | string[] | IDs of related entries (undirected graph edges) |
| `archived` | boolean | True if moved to archive.md |

### Durability fields (added in package v1.2.0, optional)

These nine fields are written by `durability.py` (Step 1.8) for entries promoted through the durability filter. They are absent on entries promoted under parity mode or strict-without-durability, and absent on pre-v1.2.0 entries.

| Field | Type | Description |
|-------|------|-------------|
| `memoryType` | string | Semantic class assigned by Step 1.7: `"decision"`, `"lesson"`, `"preference"`, `"procedure"`, `"obligation"`, `"relationship"`, `"identity"`, `"architecture"`, `"observation"`, `"status"`, or `"trend"` |
| `durabilityClass` | string | LLM assessment: `"durable"`, `"semi-durable"`, `"volatile"`, or `"noise"` |
| `route` | string | Routing verdict from `durability.py`: `"promote"` (only this value appears on index entries), `"defer"`, or `"reject"` (the last two never reach the index — they are filtered out in Step 2 or persisted in the deferred store) |
| `destination` | string | Target surface for the write: `"RTMEMORY"`, `"PROCEDURES"`, `"EPISODE"`, `"TREND"` (v1.3.0+), or `"NONE"` |
| `durabilityScore` | integer | Computed `net` score: `structuralEvidence + meaningWeight + futureConsequence − noisePenalty` |
| `noisePenalty` | integer | The noise penalty component in isolation (0–4) |
| `promotionReason` | string | Why this entry was routed: hard-trigger name (e.g. `"hard-trigger:created_obligation_or_boundary"`), net-threshold match (e.g. `"net=7>=6"`), `"merge-into:<id>"`, `"reinforce-trend:<id>"`, or `"new-trend:<key>"` |
| `mergeKey` | string \| null | Stable slug for merge reconciliation (e.g. `"dental-clinic-pricing-2026Q2"`); `null` if no merge grouping |
| `trendKey` | string \| null | Stable slug for TREND compression (e.g. `"server-restart-frequency"`); `null` if no trend grouping |
| `supportCount` | integer | `referenceCount` snapshot at routing time (useful for observing how durable an entry was when it first promoted) |

### Merge and trend fields (added in package v1.3.0)

These fields appear on entries that participate in merge or compress flows. They are additive — pre-v1.3.0 entries do not carry them.

**On merged-into (target) entries** (existing durable nodes that have been reinforced):
| Field | Type | Description |
|-------|------|-------------|
| `mergeKeys` | string[] | Accumulated list of `mergeKey` slugs from each reinforcing candidate (deduplicated) |
| `reinforcedBy` | object[] | Last 50 reinforcement events. Each event: `{source, mergeKey, mergeReason, timestamp}` |

**On trend entries** (`memoryType == "trend"`):
| Field | Type | Description |
|-------|------|-------------|
| `trendKey` | string | Stable slug identifying this trend. Unique across active trend nodes. |
| `trendFirstObserved` | string | ISO date of first observation |
| `trendLastUpdated` | string | ISO date of last reinforcement |
| `trendSupportCount` | integer | Total reinforcing observations (may differ from `referenceCount` — `trendSupportCount` only increments via `--compress-trend`) |
| `trendSources` | string[] | Up to 200 source daily logs that reinforced this trend |
| `sourceCount` | integer | `len(trendSources)` — cached for quick threshold checks |
| `compressionReason` | string | `"new-trend:<key>"` or `"reinforce-trend:<id>"` as set on creation/last update |

**On any entry that was trend-promoted to RTMEMORY**:
| Field | Type | Description |
|-------|------|-------------|
| `promotedFromTrend` | string \| null | Entry ID of the originating trend node. The original trend node stays in place as historical context. |
| `mergedInto` | string \| null | When the candidate route was `merge`, the target entry ID. Written on the *candidate record* during processing; normally not persisted on durable nodes (those are modified via `--reinforce`, not created). |

### v3.0 → v3.1 Migration

Existing v3.0 entries need these additions when migrating to reflections-metadata.json:
1. Add `uniqueSessionCount` — set equal to `referenceCount` as initial estimate
2. Add `sessionSources` — set to `[entry.source]` as seed
3. Add `uniqueDayCount` — set to `uniqueSessionCount` as initial estimate (or derive from `sessionSources` dates)
4. Add `uniqueDaySources` — derive YYYY-MM-DD from existing `sessionSources` paths
5. Add `promotedBy` — set to `"core"` for all existing entries
6. Move `config` block from old index to `reflections.json` (resolved via `$CONFIG_PATH`)
7. Add `gateStats` to stats block

---

## memory/.reflections-archive.md

```markdown
# Memory Archive

_Compressed entries that fell below importance threshold._

---

<!-- Format: [id] (created → archived) One-line summary -->
```

---

## memory/.reflections-log.md

Starts as an empty file. Consolidation reports are appended after each cycle in the format defined in `runtime/reflections-prompt.md`.

---

## Directory structure summary

```
<config-root>/                           # Resolved via $CONFIG_PATH (default: ~/.openclaw/reflections/)
├── reflections.json                     # Consolidation mode configuration
└── reflections.json.bak                 # Pre-change backup

<workspace>/
├── RTMEMORY.md                          # Reflective memory (Reflections consolidator)
├── PROCEDURES.md                        # Procedural memory
├── episodes/                            # Bounded project/event narratives (append-only)
│   ├── project-alpha.md
│   └── product-launch.md
├── runtime/
│   ├── reflections-metadata.json        # Entry metadata + stats (v1.0.0)
│   └── reflections-metadata.json.bak    # Pre-consolidation backup
└── memory/
    ├── YYYY-MM-DD.md                    # Daily logs (raw, append-only)
    ├── TRENDS.md                        # Trend nodes (compress route)
    ├── .reflections-archive.md          # Compressed old entries
    ├── .reflections-log.md              # Consolidation cycle reports (append-only)
    └── export-YYYY-MM-DD.json           # Cross-instance export/import bundles
```
