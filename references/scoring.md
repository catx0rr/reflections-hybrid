# Scoring, Quality Gates & Forgetting — Memory Evaluation Algorithms (v1.4.0)

## Importance Score

Every memory entry receives an importance score on each consolidation cycle.

### Formula

```
importance = clamp(base_weight × recency_factor × reference_boost, 0.0, 1.0)
```

### Components

#### base_weight

Default weight determined by user markers:

| Marker | base_weight | Notes |
|--------|-------------|-------|
| (none) | 1.0 | Default |
| `🔥 HIGH` | 2.0 | Doubles importance |
| `📌 PIN` | 1.0 | Normal weight but exempt from archival |
| `⚠️ PERMANENT` | — | Always 1.0 final score, skip formula. Also bypasses quality gates. |

#### recency_factor

How recently the entry was referenced or updated:

```
days_elapsed = today - lastReferenced
recency_factor = max(0.1, 1.0 - (days_elapsed / 180))
```

Characteristics:
- Referenced today: `1.0`
- Referenced 30 days ago: `0.83`
- Referenced 90 days ago: `0.5`
- Referenced 180+ days ago: `0.1` (floor)

#### reference_boost

How many other entries or sessions have referenced this entry:

```
reference_boost = max(1.0, log2(referenceCount + 1))
```

Examples:
- `referenceCount = 0` → `max(1.0, log2(1)) = 1.0`
- `referenceCount = 1` → `max(1.0, log2(2)) = 1.0`
- `referenceCount = 7` → `log2(8) = 3.0`
- `referenceCount = 15` → `log2(16) = 4.0`

### Full pseudocode

```python
def compute_importance(entry, today):
    # Permanent entries always score 1.0
    if "⚠️ PERMANENT" in entry.markers:
        return 1.0

    # Base weight from markers
    base = 2.0 if "🔥 HIGH" in entry.markers else 1.0

    # Recency decay
    days = (today - entry.lastReferenced).days
    recency = max(0.1, 1.0 - (days / 180))

    # Reference boost (logarithmic, floored at 1.0)
    ref_boost = max(1.0, log2(entry.referenceCount + 1))

    # Combine and normalize
    # Max realistic: 2.0 * 1.0 * 4.0 = 8.0
    raw = base * recency * ref_boost
    normalized = raw / 8.0
    return min(1.0, max(0.0, normalized))
```

---

## Quality Gates (strictMode is profile-driven)

> **strictMode is profile-driven; personal-assistant defaults `false`, business-employee defaults `true`.**
>
> - **Parity flow** (`strictMode: false`, personal-assistant default): all extracted candidates consolidate. Scoring is applied post-consolidation to drive the forgetting curve (archival).
> - **Strict flow** (`strictMode: true`, business-employee default): candidates are scored + gated **before** consolidation. The structural gate (`scripts/gate.py --write-back`) produces `gate_status: "qualified" | "deferred"` on each candidate. What happens next depends on whether the durability filter is active:
>   - **Strict-without-durability** (`durability.enabled: false`): `gate_status` is the **final handoff**. Only `gate_status == "qualified"` candidates proceed to Step 2; deferred candidates are recorded to `runtime/reflections-deferred.jsonl` for deterministic suppression on future cycles.
>   - **Strict-with-durability** (`durability.enabled: true`, v1.3.0+): `gate_status` is an **intermediate signal**. Step 1.8 (`scripts/durability.py --write-back`) then assigns the authoritative `route` field — one of `promote`, `merge`, `compress`, `defer`, `reject`. Step 2 dispatches per-route, not per gate_status alone. Rescue-promoted gate-deferred candidates (those with hard-promote semantic triggers) do reach Step 2 via `route == "promote"`; merge / compress routes reinforce existing durable nodes or upsert trend nodes; only `reject` is discarded and `defer` is already persisted.
>
> The strict branch is a first-class runtime step in `runtime/reflections-prompt.md` (Steps 1.3, 1.6, and — when durability is enabled — 1.7 and 1.8), not an optional appendix. Step 2 consolidation dispatches deterministically on the fields written by these steps (`gate_status` / `deferred_status` / `route`), never on prose interpretation.

Quality gates (in strict mode) determine a candidate's structural standing. Whether that translates to "promote" one-to-one depends on the active flow: in strict-without-durability mode it does; in strict-with-durability mode, gate_status feeds into a further route decision. Each consolidation mode defines three thresholds that an entry must **all** pass to qualify.

### Gate Parameters

| Parameter | Field in reflections-metadata.json | What it measures |
|-----------|-------------------|------------------|
| `minScore` | `importance` | Computed importance score (0.0–1.0) |
| `minRecallCount` | `referenceCount` | Total times this entry has been referenced |
| `minUnique` | depends on `uniqueMode` | Uniqueness count — evaluated according to `uniqueMode` config |

#### uniqueMode

Controls how `minUnique` is resolved:

| uniqueMode | Field used | Behavior |
|------------|-----------|----------|
| `day_or_session` (default) | `uniqueDayCount` if > 0, else `uniqueSessionCount` | Prefer day-based reinforcement, fall back to session count |
| `day` | `uniqueDayCount` | Day count only |
| `session` | `uniqueSessionCount` | Session count only (legacy behavior) |
| `channel` | `uniqueChannelCount` | Channel count only |
| `max` | highest of day/session/channel | Use the maximum available signal |

### Mode Thresholds

Defined in `$CONFIG_PATH` (reflections.json). Thresholds vary by profile.

**Personal-assistant defaults:**

| Mode | minScore | minRecallCount | minUnique |
|------|----------|----------------|-----------|
| `core` | 0.72 | 2 | 1 |
| `rem` | 0.85 | 2 | 2 |
| `deep` | 0.80 | 2 | 2 |

**Business-employee defaults:**

| Mode | minScore | minRecallCount | minUnique |
|------|----------|----------------|-----------|
| `core` | 0.72 | 2 | 1 |
| `rem` | 0.85 | 3 | 2 |
| `deep` | 0.80 | 2 | 2 |

See `profiles/` for full presets including fast-path thresholds and markers.

### Gate Evaluation Order

Gates are evaluated **strictest mode first** (rem → deep → core). Once an entry is qualified by any mode, it is not re-evaluated by subsequent modes.

```python
def apply_gates(candidates, due_modes, conf):
    qualified = []
    deferred = []

    # Sort modes by strictness (highest minScore first)
    mode_order = sorted(due_modes, key=lambda m: conf.modes[m].minScore, reverse=True)

    for mode in mode_order:
        gate = conf.modes[mode]
        for entry in candidates:
            if entry in qualified:
                continue  # already promoted by stricter mode

            # Hard bypass: PERMANENT always passes
            if "⚠️ PERMANENT" in entry.markers:
                qualified.append((entry, mode))
                continue

            # Soft bypass: fast-path
            if passes_fast_path(entry, gate):
                qualified.append((entry, mode))
                continue

            # Resolve effective uniqueness via uniqueMode
            effective_unique = get_effective_unique(entry, gate.uniqueMode)

            # Regular AND gate
            if (entry.importance >= gate.minScore
                and entry.referenceCount >= gate.minRecallCount
                and effective_unique >= gate.minUnique):
                qualified.append((entry, mode))

    deferred = [e for e in candidates if e not in [q[0] for q in qualified]]
    return qualified, deferred


def passes_fast_path(entry, gate):
    """Softer bypass for high-salience entries."""
    marker = entry.marker
    # Score + recall fast-path
    if (gate.fastPathMinScore is not None
        and entry.importance >= gate.fastPathMinScore
        and entry.referenceCount >= gate.fastPathMinRecallCount):
        return True
    # Marker fast-path
    if marker and marker in gate.fastPathMarkers:
        return True
    return False


def get_effective_unique(entry, unique_mode):
    """Resolve uniqueness count based on configured mode."""
    if unique_mode == "day_or_session":
        return entry.uniqueDayCount if entry.uniqueDayCount > 0 else entry.uniqueSessionCount
    elif unique_mode == "day":
        return entry.uniqueDayCount
    elif unique_mode == "session":
        return entry.uniqueSessionCount
    elif unique_mode == "channel":
        return entry.uniqueChannelCount
    elif unique_mode == "max":
        return max(entry.uniqueDayCount, entry.uniqueSessionCount, entry.uniqueChannelCount)
    return entry.uniqueSessionCount  # fallback
```

### Gate Bypass Rules

| Condition | Bypass? | Rationale |
|-----------|---------|-----------|
| `⚠️ PERMANENT` marker | Yes (hard) | User-protected entries always consolidate |
| Fast-path (marker match or score+recall) | Yes (soft) | High-salience entries that meet `fastPathMinScore`/`fastPathMinRecallCount` or have a marker in `fastPathMarkers` |
| `🔥 HIGH` marker | No (unless in `fastPathMarkers`) | HIGH doubles base_weight but must pass gates unless fast-path configured |
| `📌 PIN` marker | No (unless in `fastPathMarkers`) | PIN prevents archival but does not bypass intake gates unless fast-path configured |
| First Reflection (post-install) | Yes | Bootstrap run consolidates everything to seed memory |
| Manual trigger ("Reflect now" (alias: "Dream now")) | Configurable | Can run with or without gates per user preference |

---

## Durability Filter (v1.2.0+, strictMode AND durability.enabled)

> **Activation:** runs as Steps 1.7 (LLM annotation) + 1.8 (SCRIPT routing) **after** the structural gate and **before** durable write. Only active when `strictMode == true` AND `durability.enabled == true`. Parity mode never runs durability by design.
>
> **Purpose:** structural scoring answers "is this reinforced?". The durability filter answers the harder question: "is this actually meaningful long-horizon memory, or just reinforced noise?". A heartbeat repeated across sessions may pass the structural gate; durability rejects it. A single statement establishing a boundary may never pass the gate; durability can **rescue-promote** it.

### Scoring model (deterministic, 0–4 bands)

Each component is clamped to the integer range `0..4`:

```
structuralEvidence  derived from referenceCount, uniqueDayCount, gate_bypass
                    (PERMANENT/FAST_PATH bypass forces 4)

meaningWeight       count of LLM-set meaning flags (cap at 4):
                    changed_future_decision, changed_behavior_or_policy,
                    created_stable_preference, created_obligation_or_boundary,
                    relationship_or_identity_shift

futureConsequence   derived from LLM flags (rare_high_consequence weighted heavier):
                    cross_day_relevance, rare_high_consequence (×2), actionable_procedure

noisePenalty        derived from LLM noise flags (telemetry_noise weighted heavier):
                    pattern_only, pure_status, telemetry_noise (×2)

net = structuralEvidence + meaningWeight + futureConsequence − noisePenalty
```

### Hard-promote triggers (force `route = "promote"` regardless of net)

Any one of these short-circuits the net-score banding:

- `memory_type in {"decision", "lesson"}` AND (`changed_future_decision` OR `changed_behavior_or_policy`)
- `created_stable_preference` is true
- `created_obligation_or_boundary` is true
- `relationship_or_identity_shift` is true
- `actionable_procedure` is true AND `structuralEvidence >= 2` (validated repeatable — not one-shot)
- `memory_type == "architecture"` AND `rare_high_consequence` is true

### Hard-suppress triggers (force `route = "reject"` regardless of net)

- `telemetry_noise` is true
- `pure_status` is true AND `rare_high_consequence` is not true
- `pattern_only` is true AND `cross_day_relevance` is not true (single-day repetition)

### Routing rules (v1.3.0 full route set)

Applied in this deterministic order:

1. **Hard-suppress** → `reject`
2. **Hard-promote** → `promote`. Duplicates allowed here (hard-trigger justifies a distinct node). If the candidate's `trendKey` matches an existing trend node AND that trend meets both `trendPromoteSupportCount` and `trendPromoteUniqueDayCount` thresholds, additionally set `promotedFromTrend` so the new RTMEMORY node links to its trend origin.
3. **Merge** — `duplicate_of_existing` is non-null AND resolves in the index AND no hard-trigger → `route = "merge"`. Step 2 calls `index.py --reinforce <mergedInto>`; no new durable node is created. `mergeKey` is appended to the target's `mergeKeys` list.
4. **Defer (unresolved duplicate)** — `duplicate_of_existing` is non-null but refers to an entry not in the index → `route = "defer"` (re-evaluated next cycle).
5. **Compress** — `trendKey` set AND `memory_type in {observation, status, trend}` AND no hard-trigger AND `actionable_procedure != true` → `route = "compress"`. Step 2 calls `index.py --compress-trend <trendKey>` which upserts a trend node and updates `TRENDS.md`.
6. **Net-score banding** — `promote` if net ≥ `netPromoteThreshold`; `defer` if net ≥ `netDeferThreshold`; else `reject`.

### Destination split (v1.3.0)

| Surface | Route that writes here | Purpose |
|---------|-----------------------|---------|
| `RTMEMORY.md` | `promote` | Durable reflective conclusions — decisions, lessons, identity/relationship shifts |
| `PROCEDURES.md` | `promote` (memory_type=procedure + validated actionable) | Repeatable know-how |
| `episodes/*.md` | `promote` (hard-triggered observations only) | Bounded historical incident narratives |
| `TRENDS.md` | `compress` | Repeated reality/pattern without stable method (recurring gateway instability, repeated symptom pattern) |
| — (reinforce existing) | `merge` | Duplicate of existing durable node — reinforcement, not a new surface entry |
| — (no write) | `defer`, `reject` | Held for re-evaluation or discarded |

**Rule for repeated ops material**:
- Repetition yields a validated actionable workflow → PROCEDURES
- Repetition reveals a durable condition/pattern but no stable method → TREND
- Repeated presence with no guidance and no durable pattern → reject or defer
- Repeated symptom chatter is never promoted as a new RTMEMORY node.

### Trend-to-durable promotion (v1.3.0)

A trend node (`memoryType == "trend"`) accumulates `trendSupportCount` via `index.py --compress-trend`. It becomes eligible to promote into RTMEMORY as a durable conclusion only when **all** of:

- `trendSupportCount >= trendPromoteSupportCount` (from profile)
- `uniqueDayCount >= trendPromoteUniqueDayCount` (from profile)
- A fresh candidate cycle annotates a matching `trend_key` with a hard-promote trigger (e.g., `changed_future_decision` or `rare_high_consequence`)

The first two conditions are structural (checked by `trend_meets_promotion_criteria()` in durability.py). The third is semantic (emitted by the LLM in Step 1.7). All three must be satisfied for promotion — accumulation alone does not promote. The original trend node stays in place as historical context; the new RTMEMORY node carries `promotedFromTrend = <trend_id>`.

### Profile thresholds

| Profile | `netPromoteThreshold` | `netDeferThreshold` | `trendPromoteSupportCount` | `trendPromoteUniqueDayCount` | Default |
|---------|----------------------|---------------------|---------------------------|------------------------------|---------|
| business-employee | 6 | 3 | 5 | 3 | `durability.enabled: true` |
| personal-assistant (only if operator opts into strictMode) | 5 | 2 | 4 | 2 | `durability.enabled: false` |

Values come from the top-level `durability` block in `reflections.json`. If the block is missing or `durability.enabled` is false, durability is skipped entirely.

### Rescue subset (Step 1.7 scope expansion)

Structural scoring underestimates rare one-off high-consequence items. Step 1.7 therefore annotates not only `gate_status == "qualified"` candidates but also a **rescue subset** of structurally-deferred candidates — any one of:

- `gate_bypass` is set (`"PERMANENT"` or `"FAST_PATH"`)
- `marker in {"HIGH", "PERMANENT", "PIN"}`
- candidate belongs to a high-meaning class (decision, lesson, obligation, relationship, identity, architecture)

This is the path a single commitment or architectural conclusion takes to reach `promote` despite failing structural `minRecallCount` / `minUnique`.

### Destination mapping (v1.3.0 — full shipped behavior)

Destination is only meaningful on routes `promote` or `compress`. Routes `merge`, `defer`, and `reject` use `destination = "NONE"` (merge reinforces an existing entry; defer/reject don't write).

| memory_type | destination | Route + condition |
|-------------|-------------|-------------------|
| decision, lesson, obligation, relationship, identity, architecture, preference | `RTMEMORY` | `promote` via hard-promote trigger OR net ≥ promote threshold |
| procedure | `PROCEDURES` | `promote` via `actionable_procedure` hard-trigger AND `structuralEvidence >= 2` |
| observation | `EPISODE` | `promote` — **only** when a hard-promote trigger fires alongside cross-day relevance. Generic cross-day observations (no hard-trigger, no actionable procedure) route to `compress` → TREND instead. |
| trend / status | `TREND` | `compress` — weak ops material with a stable `trendKey`. Upserted via `index.py --compress-trend`; surface at `TRENDS.md`. |
| duplicate-of-existing (any memory_type, no hard-trigger) | — | `merge` — reinforces target at `mergedInto` via `index.py --reinforce`. No new surface entry. |
| (any other / NONE) | `RTMEMORY` fallback | `promote` but memory_type doesn't match above |

### Fields written to the candidate and the index entry

Durability fields persist through `index.py --add` / `--reinforce` / `--compress-trend` onto the durable record:

| Field | Purpose |
|-------|---------|
| `memoryType` | Semantic class from Step 1.7 |
| `durabilityClass` | LLM assessment (durable / semi-durable / volatile / noise) |
| `route` | Routing verdict (full v1.3.0 set: `promote` / `merge` / `compress` / `defer` / `reject`; only `promote` and `compress` produce new/updated index entries directly; `merge` reinforces an existing entry) |
| `destination` | Target surface: `RTMEMORY` / `PROCEDURES` / `EPISODE` / `TREND` / `NONE` |
| `durabilityScore` | Computed net |
| `noisePenalty` | Penalty component in isolation |
| `promotionReason` | Hard-trigger name, `"net=N>=threshold"`, `"merge-into:<id>"`, `"reinforce-trend:<id>"`, or `"new-trend:<key>"` |
| `mergeKey` | Stable slug used by `merge` route; persisted in target's `mergeKeys[]` list |
| `trendKey` | Stable slug used by `compress` route; identifies the trend node |
| `mergedInto` | Target entry id for `merge`; existing trend id for `compress` (when reinforcing) |
| `promotedFromTrend` | Existing trend node id when a hard-triggered candidate trend-promotes to RTMEMORY |
| `compressionReason` | `"reinforce-trend:<id>"` or `"new-trend:<key>"` when route is `compress` |
| `supportCount` | `referenceCount` snapshot at routing time |

### Shipped status (v1.3.0)

- ✅ `merge` route: `index.py --reinforce <id>` bumps existing durable node's `referenceCount` / `sessionSources` / `lastReferenced` / `uniqueDayCount` and appends to `mergeKeys` / `reinforcedBy[]`. No new surface entry.
- ✅ `compress` route + `TREND` destination: `index.py --compress-trend <key>` upserts a trend node (`memoryType: "trend"`); the human-readable surface is `TRENDS.md` with one `### <trendKey>` section per active trend.
- ✅ Trend-to-durable promotion: when accumulated trend crosses support thresholds AND a fresh cycle adds a hard-promote trigger, the new RTMEMORY node carries `promotedFromTrend` back to the original trend node (which stays in place as historical context).
- ⏭ Trend decay (automatic expiration of old unreinforced trends) — future work; current cycle keeps trends indefinitely.

---

## Uniqueness Tracking — `uniqueSessionCount` and `uniqueDayCount`

### Purpose

`referenceCount` tracks total references but can be inflated by a single long conversation mentioning the same topic repeatedly. Uniqueness tracking ensures an entry has been referenced across **distinct sessions or days**, providing a cross-context relevance signal.

### Two uniqueness signals

| Field | What it tracks | How it increments |
|-------|---------------|-------------------|
| `uniqueSessionCount` | Distinct source log files that referenced this entry | New source log not in `sessionSources` |
| `uniqueDayCount` | Distinct calendar days that referenced this entry | New day (YYYY-MM-DD) not in `uniqueDaySources` |

The `uniqueMode` config determines which signal is used by the gate. Default is `day_or_session`: prefer `uniqueDayCount` when available, fall back to `uniqueSessionCount`.

### Definition

A "session" is identified by the daily log filename (`memory/YYYY-MM-DD.md`). Each daily log represents one session boundary.

A "day" is the YYYY-MM-DD date extracted from the source log path.

### Tracking Algorithm

```python
def update_tracking(entry, source_log_filename, index):
    """Called during the Collect phase for each extracted entry."""

    if entry.id not in index.entries:
        # New entry — initialize
        entry.referenceCount = 1
        entry.uniqueSessionCount = 1
        entry.sessionSources = [source_log_filename]
        day = extract_day(source_log_filename)  # e.g. "2026-04-10"
        entry.uniqueDayCount = 1 if day else 0
        entry.uniqueDaySources = [day] if day else []
        return

    existing = index.entries[entry.id]

    # Always increment referenceCount
    existing.referenceCount += 1

    # Only increment uniqueSessionCount if this is a new session
    if source_log_filename not in existing.sessionSources:
        existing.uniqueSessionCount += 1
        existing.sessionSources.append(source_log_filename)

    # Only increment uniqueDayCount if this is a new day
    day = extract_day(source_log_filename)
    if day and day not in existing.uniqueDaySources:
        existing.uniqueDayCount += 1
        existing.uniqueDaySources.append(day)

    existing.lastReferenced = today
```

### Index Entry Schema (v1.0.0)

The `sessionSources` and `uniqueDaySources` fields are stored in `reflections-metadata.json` but kept compact — only the last 30 entries are retained (older ones are trimmed from the front since the counts already captured the history).

```json
{
  "id": "mem_001",
  "summary": "One-line summary",
  "source": "memory/2026-04-01.md",
  "target": "RTMEMORY.md#projects",
  "created": "2026-04-01",
  "lastReferenced": "2026-04-05",
  "referenceCount": 7,
  "uniqueSessionCount": 4,
  "sessionSources": ["memory/2026-04-01.md", "memory/2026-04-02.md", "memory/2026-04-04.md", "memory/2026-04-05.md"],
  "uniqueDayCount": 4,
  "uniqueDaySources": ["2026-04-01", "2026-04-02", "2026-04-04", "2026-04-05"],
  "importance": 0.82,
  "tags": ["project", "architecture"],
  "related": ["mem_002", "mem_005"],
  "archived": false
}
```

### Edge Cases

| Case | Behavior |
|------|----------|
| Same entry mentioned 5 times in one daily log | `referenceCount += 5`, `uniqueSessionCount += 1` |
| Entry referenced in 3 different daily logs | `uniqueSessionCount = 3` (one per log) |
| Entry exists in index but never extracted before | Initialize `uniqueSessionCount = 1`, `sessionSources = [current_log]` |
| Manual "Reflect now" trigger (no daily log source) | Use `"manual-YYYY-MM-DD"` as synthetic session ID |

---

## Forgetting Curve

Entries that are no longer relevant should be gracefully archived, not deleted.

### Archival conditions

An entry is eligible for archival when **ALL** of these are true:

```
1. days_since_last_referenced > 90
2. importance < 0.3
3. NOT marked ⚠️ PERMANENT
4. NOT marked 📌 PIN
5. NOT in an episode file (episodes are append-only)
```

### Archival process

```
1. Compress entry to one-line summary
2. Append to memory/.reflections-archive.md:
   - [mem_NNN] (YYYY-MM-DD) One-line summary
3. Remove full entry from source file (RTMEMORY.md or PROCEDURES.md)
4. Set entry.archived = true in reflections-metadata.json
5. Keep the index entry (for relation tracking and reachability graph)
```

### Decay visualization

```
Importance
1.0 │ ████
    │ ████████
    │ ████████████
0.5 │ ████████████████
    │ ████████████████████
0.3 │─────────────────────────── archival threshold
    │ ████████████████████████████
0.1 │ ████████████████████████████████
0.0 └──────────────────────────────────→ Days
    0    30    60    90    120   150   180
```

---

## Health Score (v3.0 — Five Metrics)

The health score measures overall memory system quality on a 0–100 scale.

### Formula

```
health = (freshness×0.25 + coverage×0.25 + coherence×0.2 + efficiency×0.15 + reachability×0.15) × 100
```

### Metric 1: Freshness (weight: 0.25)

What proportion of entries have been recently referenced?

```
freshness = entries_referenced_in_last_30_days / total_entries
```

### Metric 2: Coverage (weight: 0.25)

Are all knowledge categories being actively maintained?

```
categories = [
    "Scope Notes", "Active Initiatives",
    "Business Context and Metrics",
    "People and Relationships",
    "Strategy and Priorities", "Key Decisions and Rationale",
    "Lessons and Patterns", "Episodes and Timelines",
    "Environment Notes", "Open Threads"
]
coverage = categories_with_updates_in_last_14_days / len(categories)
```

### Metric 3: Coherence (weight: 0.2)

How well-connected is the memory graph?

```
coherence = entries_with_at_least_one_relation / total_entries
```

### Metric 4: Size Efficiency (weight: 0.15)

Is RTMEMORY.md staying concise and well-pruned?

```
efficiency = max(0.0, 1.0 - (memory_md_line_count / 500))
```

### Metric 5: Reachability (weight: 0.15)

What fraction of the memory graph is mutually reachable via relation links?

#### Algorithm

```python
def compute_reachability(entries):
    if not entries:
        return 0.0

    adj = defaultdict(set)
    ids = {e["id"] for e in entries if not e.get("archived")}

    for entry in entries:
        if entry.get("archived"):
            continue
        for related_id in entry.get("related", []):
            if related_id in ids:
                adj[entry["id"]].add(related_id)
                adj[related_id].add(entry["id"])

    visited = set()
    components = []
    for node in ids:
        if node not in visited:
            component = set()
            queue = [node]
            while queue:
                current = queue.pop()
                if current in visited:
                    continue
                visited.add(current)
                component.add(current)
                queue.extend(adj[current] - visited)
            components.append(len(component))

    total = len(ids)
    if total == 0:
        return 0.0

    weighted_sum = sum(size * size for size in components)
    reachability = weighted_sum / (total * total)
    return min(1.0, reachability)
```

#### Interpretation

| Value | Meaning |
|-------|---------|
| `1.0` | All entries in one connected component — perfect graph |
| `0.7–0.9` | Most entries connected, a few isolated clusters |
| `0.4–0.6` | Significant fragmentation — many topics not linked |
| `0.1–0.3` | Heavily fragmented — knowledge silos |
| `0.0–0.1` | Almost no connections — a flat list, not a graph |

---

## Suggestion Triggers

Generate suggestions in the consolidation report when:

| Condition | Suggestion |
|-----------|------------|
| `freshness < 0.5` | "Many entries are stale — review for relevance or increase cross-referencing" |
| `coverage < 0.5` | "Several RTMEMORY.md sections haven't been updated — check for knowledge gaps" |
| `coherence < 0.3` | "Low entry connectivity — consider linking related memories manually" |
| `efficiency < 0.3` | "RTMEMORY.md is large (N lines) — review for pruning or archival opportunities" |
| `reachability < 0.4` | "Memory graph is fragmented (N isolated clusters) — add cross-references" |
| `DEFERRED_COUNT > 10` | "Many entries deferred — consider lowering gate thresholds or running in core mode" |
| `no entries pass rem gates for 3+ cycles` | "rem mode is too strict — no entries qualifying. Review minScore threshold" |
| `health declining 3+ cycles` | "Health trending down for N cycles — investigate which metric is deteriorating" |
