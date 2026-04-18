# Reflections Profile: Personal Assistant

**Agent type:** Owner-centric personal assistant, family assistant, butler, concierge, home-automation agent
**Memory emphasis:** Routines, preferences, household state, device state, services, family context

---

## When to use this profile

Use this profile for:

- Personal assistants (owner DM topology)
- Family assistants
- Butler / concierge agents
- Home-automation assistants

These agents share a common topology: narrow interaction surface (one owner or a small family), where repeated truths recur inside the same DM or channel family. Routines, preferences, devices, services, and household state are normal consolidation targets.

---

## Interaction topology

- Narrow — one owner or small family
- Repeated truths across the same few people / channels
- Day-based reinforcement is natural (same preference expressed on different days)
- Single-conversation repetition should not inflate recall

---

## Default preset

```json
{
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
  "modes": {
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
  }
}
```

**Dispatch semantics** — two separate mechanisms, do not conflate:

- **Host scheduling** (when the cron fires the prompt): top-level `dispatchCadence`. That is the only scheduling control. The host cron invokes the recurring prompt at those slots.
- **Mode-due check** (which modes the prompt runs): `dispatch.py` uses **hardcoded elapsed-interval** gating — rem=6h, deep=12h, core=24h — compared against each mode's `lastRun` timestamp. Per-mode `modes.*.cadence` fields are **not** consumed by any script and have been removed from the sample preset above.

---

## Dispatch cadence

`dispatchCadence: "30 4,10,16,22 * * *"` — fires 4×/day at 04:30, 10:30, 16:30, 22:30 (local time per `timezone` field).

Personal-assistant cadence aligns with typical household rhythm (early morning, late morning, late afternoon, late evening). Intentionally different from business-employee's cadence to avoid installations on the same host contending for the same wake slots.

## Durability filter

`durability.enabled: false` — personal-assistant defaults to parity mode (`strictMode: false`), which doesn't run the structural gate, so the durability filter has nothing to filter. The block carries softer thresholds (`netPromoteThreshold: 5`, `netDeferThreshold: 2`) that only activate if an operator explicitly enables `strictMode: true` on a personal-assistant install. The softer values reflect the narrower topology — the personal-assistant stream has sparse, meaningful exchanges where most content deserves durable promotion.

## Why these thresholds

- **Lower minRecallCount** — owner-centric agents hear the same truths from fewer sources. Requiring 3+ recalls penalizes narrow topology unfairly.
- **uniqueMode: day_or_session** — prefers `uniqueDayCount` when available, falls back to `uniqueSessionCount`. Day-based reinforcement is more meaningful than session count for personal agents.
- **Broader fast-path markers** — PREFERENCE and ROUTINE are first-class for personal/home agents. A stated preference or routine should promote faster than a generic fact.
- **Lower minScore for core** — personal agents accumulate low-drama but durable truths (household rules, device configs). These matter even at lower salience.

---

## Fast-path markers

| Marker | Meaning |
|--------|---------|
| `HIGH` | High-importance entry (doubles base weight in scoring) |
| `PIN` | User-pinned — should promote quickly |
| `PREFERENCE` | Stated owner/family preference |
| `ROUTINE` | Recurring pattern (morning routine, meal preference, etc.) |
| `PROCEDURE` | Learned workflow or tool pattern |

Fast-path markers provide a softer bypass than PERMANENT. An entry with a matching marker and sufficient score/recall can skip the regular AND gate.
