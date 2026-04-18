# Reflections Profile: Business Employee

**Agent type:** Bounded worker, supervisor/owner DM, small GC team workflows
**Memory emphasis:** Decisions, procedures, project state, team context, accountability

---

## When to use this profile

Use this profile for:

- Supervisor / owner DM agents
- Small group-chat team agents
- Bounded operational workflow agents
- Lower tolerance for casual preference promotion

These agents operate in a more structured topology: work conversations, team GCs, project channels. Promotion should be stricter for casual preferences and more focused on decisions, procedures, and accountability.

---

## Interaction topology

- Bounded — supervisor DM + small work GCs
- Decisions and procedures matter more than personal preferences
- Cross-session reinforcement is expected for important items
- Casual preferences should not promote as easily as in personal agents

---

## Default preset

```json
{
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
  "modes": {
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
  }
}
```

**Dispatch semantics** — two separate mechanisms, do not conflate:

- **Host scheduling** (when the cron fires the prompt): top-level `dispatchCadence`. That is the only scheduling control. The host cron invokes the recurring prompt at those slots.
- **Mode-due check** (which modes the prompt runs): `dispatch.py` uses **hardcoded elapsed-interval** gating — rem=6h, deep=12h, core=24h — compared against each mode's `lastRun` timestamp. Per-mode `modes.*.cadence` fields are **not** consumed by any script and have been removed from the sample preset above.

---

## Dispatch cadence

`dispatchCadence: "30 5,12,18,22 * * *"` — fires 4×/day at 05:30, 12:30, 18:30, 22:30 (local time per `timezone` field).

Business-employee cadence aligns with typical work rhythm (before shift, midday, end of shift, evening wrap). Intentionally different from personal-assistant's cadence to avoid installations on the same host contending for the same wake slots.

## Durability filter

`durability.enabled: true` — business-employee ships the second-stage durability filter as a default. The structural gate (Step 1.6) catches reinforcement but can't tell genuine long-horizon memory from structurally-reinforced shallow entries (heartbeats, status pings, repeated symptom reports). Durability adds a semantic layer after the gate that routes each candidate into one of five lanes:

- **Promotes** one-off but high-consequence items (decisions with downstream consequence, obligations/boundaries, relationship or identity shifts, architecture conclusions) even when they are structurally underweight — via the rescue path in Step 1.7
- **Merges** (v1.3.0) duplicate candidates (`duplicate_of_existing` resolves in the index, no hard-trigger) into the existing durable node instead of creating a duplicate. `index.py --reinforce` bumps `referenceCount`, `lastReferenced`, and appends to `mergeKeys` / `reinforcedBy[]`.
- **Compresses** (v1.3.0) repeated weak ops material with a stable `trendKey` (observation/status/trend memory types without actionable procedure) into a single trend node at `memory/TRENDS.md`. `index.py --compress-trend` upserts the trend entry (`memoryType: "trend"`) and bumps `trendSupportCount` / `trendLastUpdated`.
- **Rejects** telemetry-noise, pure-status, and same-day pattern-only content regardless of reinforcement.
- **Defers** unresolved duplicates (`duplicate_of_existing` refers to an entry no longer in the index) or borderline net scores — recorded in the deferred store for re-evaluation.

**Trend promotion**: a trend node that accumulates enough support (`trendPromoteSupportCount: 5` across `trendPromoteUniqueDayCount: 3` distinct days) becomes eligible to promote into RTMEMORY as a durable conclusion — but only when a fresh candidate cycle adds a hard-promote trigger (e.g., the operator explicitly ties the trend to a decision or lesson). The original trend node stays in place as historical context; the new RTMEMORY node carries `promotedFromTrend` linking back.

Thresholds (`netPromoteThreshold: 6`, `netDeferThreshold: 3`, `trendPromoteSupportCount: 5`, `trendPromoteUniqueDayCount: 3`) are stricter than personal-assistant because the work stream is higher-volume and noisier — the filter must be more discerning about what earns a durable node.

## Why these thresholds

- **Higher fastPathMinScore** — business agents should not fast-path casual observations. Only clearly high-signal entries should bypass regular gates.
- **Narrower fast-path markers** — no PREFERENCE or ROUTINE by default. Business agents care about HIGH, PIN, and PROCEDURE. Preferences and routines are less central to work memory.
- **Higher rem minRecallCount** — requires 3 recalls for rem promotion. Work items that matter get referenced across multiple interactions.
- **uniqueMode: day_or_session** — same as personal, but the narrower marker set and higher thresholds compensate for the topology difference.

---

## Fast-path markers

| Marker | Meaning |
|--------|---------|
| `HIGH` | High-importance entry (doubles base weight in scoring) |
| `PIN` | User-pinned — should promote quickly |
| `PROCEDURE` | Learned workflow or operational pattern |

Business agents do not include PREFERENCE or ROUTINE as fast-path markers by default. These can be added manually to `reflections.json` if the operator wants them.
