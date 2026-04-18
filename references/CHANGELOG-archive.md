# Reflections — Historical Changelog (Archived)

> ## 🚫 ARCHIVED HISTORICAL REFERENCE — NOT CURRENT RUNTIME BEHAVIOR
>
> **This file is archived reference material only.** It documents the evolution of Reflections from v1.1.0 through v1.3.0, preserved for traceability of design decisions. **It is not a migration guide.** v1.4.0 is a clean baseline — no upgrade path from earlier versions is supported.
>
> For current runtime contracts see the live `runtime/` prompts and `references/*.md`. For the current substrate, see `README.md` "Baseline" section.

---

## Changes in v1.3.0

- **Full durability route set shipped**: `durability.py` now activates `merge` and `compress` as first-class routes alongside `promote` / `defer` / `reject`. What was stored-but-unused metadata in v1.2.0 (`mergeKey`, `trendKey`, `duplicate_of_existing`) is now acted upon deterministically.
- **Merge route**: when an annotated candidate carries `duplicate_of_existing` that resolves in the index AND no hard-promote trigger fires, the router sets `route = "merge"` and `mergedInto = <target_id>`. Step 2 calls `index.py --reinforce <target_id>` which bumps `referenceCount`, updates `lastReferenced`, appends to the target's `mergeKeys` list, and logs a timestamped entry to `reinforcedBy[]`. No new surface entry is created. Prevents duplicate pollution in RTMEMORY/PROCEDURES.
- **Compress route + TREND destination**: when a candidate has a stable `trendKey` AND `memory_type in {observation, status, trend}` AND no hard-promote AND `actionable_procedure != true`, the router sets `route = "compress"`. Step 2 calls `index.py --compress-trend <trendKey>` which upserts a trend entry (`memoryType: "trend"`) — reinforcing an existing trend via `trendSupportCount` / `trendLastUpdated` or creating a new one. Also maintains the human-readable surface at **`memory/TRENDS.md`** (one section per active `trendKey`).
- **Trend-to-durable promotion**: when a trend node crosses both `trendPromoteSupportCount` and `trendPromoteUniqueDayCount` thresholds AND a fresh candidate cycle annotates a matching `trend_key` with a hard-promote trigger, the router promotes as a new RTMEMORY node with `promotedFromTrend = <trend_id>` linking back. The original trend node stays as historical context. Trend accumulation alone does not promote — the semantic hard-trigger is required.
- **Clean destination split enforced**:
  - `RTMEMORY.md` = durable reflective conclusions, lessons, decisions, identity/relationship changes
  - `PROCEDURES.md` = repeated validated know-how (actionable workflows)
  - `memory/TRENDS.md` = repeated reality/pattern without stable method
  - `episodes/` = bounded historical incidents
  - Routing rules: repetition + actionable → PROCEDURES; repetition without stable method → TREND; repeated shallow chatter → reject. Repeated symptom presence is never promoted as a new RTMEMORY node.
- **New config fields (schema 1.2.0 → 1.3.0)**: `durability.trendPromoteSupportCount` (business=5, personal=4) and `durability.trendPromoteUniqueDayCount` (business=3, personal=2). Absent-field defaults match business thresholds.
- **New index fields**: trend entries carry `trendKey`, `trendFirstObserved`, `trendLastUpdated`, `trendSupportCount`, `trendSources[]`, `sourceCount`, `compressionReason`. Merged-into entries carry `mergeKeys[]` and `reinforcedBy[]` audit trail. Promoted-from-trend entries carry `promotedFromTrend`. Runtime metadata schema stays at `"1.0.0"` — all new fields are pass-through-tolerated.
- **New `index.py` CLI modes**: `--reinforce <entry_id> --from payload.json` (merge) and `--compress-trend <trend_key> --from payload.json` (compress). Both delegate counter math to the existing `update_session()` so semantics stay consistent.
- **Mode-aware telemetry extended**: strict+durability flow now emits `entries_durable_promoted` / `entries_durable_merged` / `entries_durable_compressed` / `entries_durable_deferred` / `entries_durable_rejected`. `writes.trends` counter added for trend upserts.
- **Scripts unchanged (no logic diff)**: `score.py`, `gate.py`, `deferred.py`, `dispatch.py`, `scan.py`, `health.py`, `snapshot.py`, `stale.py`, `append_memory_log.py`. Only `durability.py` and `index.py` were extended. No new scripts in v1.3.0 — the feature ships by extending existing deterministic helpers.
- **Parity flow unchanged by design**: personal-assistant continues to run the parity flow (Collect → Consolidate → Archive) without any gate, deferred, or durability stages. The substrate no longer treats repeated presence as durable memory **in strict+durability mode** — but parity flow's upstream-compatible behavior is preserved for installs that need it.
- **Substrate completion**: v1.3.0 is the "substrate no longer treats repeated presence as durable memory" milestone. It can now promote durable guidance, merge reinforcement into existing durable memory, compress repeated weak events into trend memory, separate procedures from trends, and preserve one-off high-consequence memories — without polluting RTMEMORY with repetitive weak material.

## Changes in v1.2.0

- **Durability filter — new second-stage admission layer.** Runs after the structural gate and before durable write, *only* when `strictMode == true` AND `durability.enabled == true`. Business-employee defaults to both true; personal-assistant keeps durability disabled in its parity flow. The filter is two steps:
  - **Step 1.7 (LLM)** — semantic annotation. For each qualified candidate (plus a narrow **rescue subset** of structurally-deferred candidates with `gate_bypass`, `HIGH`/`PERMANENT`/`PIN` markers, or high-meaning memory types), the LLM emits `$TMPDIR/reflections-durability.json` with `memory_type`, `durability_class`, nine semantic flags, `duplicate_of_existing`, `merge_key`, and `trend_key`. The LLM does semantic judgment *only* — no routing.
  - **Step 1.8 (SCRIPT)** — deterministic routing via new `scripts/durability.py`. Computes `net = structuralEvidence + meaningWeight + futureConsequence − noisePenalty`. Hard-promote triggers (decision/lesson with consequence, stable preference, obligation/boundary, relationship/identity shift, validated actionable procedure, architecture with rare high consequence) short-circuit to `promote`. Hard-suppress triggers (telemetry_noise, pure_status-no-consequence, pattern_only-same-day) short-circuit to `reject`. Duplicate candidates (`duplicate_of_existing` non-null without a hard-trigger) and generic cross-day observations (without hard-trigger or actionable procedure) were routed to `defer` in v1.2.0, pending the merge/compress infrastructure. (v1.3.0 reroutes these to `merge` and `compress` respectively.)
- **Rescue promotion path**: rare one-off high-consequence items (a single commitment, a boundary statement, an architectural conclusion) can now reach `promote` even when they fail the structural gate's `minRecallCount` — the rescue subset is explicitly annotated and the hard-trigger short-circuit bypasses net thresholds.
- **Duplicate protection (v1.2.0 transitional)**: `duplicate_of_existing` candidates route to `defer` in v1.2.0 with `mergeKey` stored — stops duplicate pollution before merge support exists. *(Superseded in v1.3.0: these candidates now route to `merge` and reinforce the existing durable node via `index.py --reinforce`.)*
- **Observation tightening (v1.2.0 transitional)**: generic cross-day observations no longer auto-route to EPISODE. They defer with `trendKey` stored. Only hard-triggered observations (e.g. `rare_high_consequence` + `changed_future_decision`) reach EPISODE. *(Superseded in v1.3.0: these candidates now route to `compress` and upsert a trend node at `memory/TRENDS.md` via `index.py --compress-trend`.)*
- **Extended candidate + index schema**: candidates carry `route`, `destination`, `durabilityScore`, `noisePenalty`, `promotionReason`, `memoryType`, `durabilityClass`, `mergeKey`, `trendKey`, `duplicateOfExisting`, `supportCount` after Step 1.8. The nine durability fields persist onto the durable index record via `index.py --add` (no script change — `index.py` already accepts arbitrary fields).
- **Mode-aware telemetry extended**: strict+durability flow emits `entries_durable_promoted` / `entries_durable_deferred` / `entries_durable_rejected` instead of `entries_promoted`. Strict-without-durability keeps the v1.1.6 shape. Parity keeps `entries_consolidated`.
- **Config schema bumped `"1.1.0"` → `"1.2.0"`**: new optional top-level `durability` block. Parsers accept `"1.0.0"`, `"1.1.0"`, and `"1.2.0"`. Runtime metadata schema (`reflections-metadata.json`) remains at `"1.0.0"` — the new per-entry durability fields flow through `index.py`'s pass-through without a schema version bump.
- **Scripts unchanged**: `score.py`, `gate.py`, `deferred.py`, `dispatch.py`, `scan.py`, `health.py`, `snapshot.py`, `index.py`, `stale.py`, `append_memory_log.py` have no code changes. Only `durability.py` is new.
- **Parity flow unchanged by design**: personal-assistant's sparse-but-meaningful topology doesn't need durability. The parity path (Collect → Consolidate → Archive) is preserved exactly as v1.1.6.
- **Follow-up shipped in v1.3.0**: `merge` route + `index.py --reinforce` (reinforce existing durable node), `compress` route + `TREND` destination + `memory/TRENDS.md` surface + `index.py --compress-trend`, trend-to-durable promotion via `promotedFromTrend`. v1.2.0 stored `mergeKey` / `trendKey` / `duplicate_of_existing` on records so v1.3.0 could act on them without migration.

## Changes in v1.1.6

- **Config schema bumped `"1.0.0"` → `"1.1.0"`**: reflects the profile-driven additions accumulated since v1.1.1 (`strictMode`, `scanWindowDays`, `dispatchCadence`). Parsers still accept `"1.0.0"`; writers should emit `"1.1.0"`. Runtime metadata schema (`reflections-metadata.json`) remains at `"1.0.0"` — unchanged.
- **skill-reference.md rewritten for profile-driven reality**: the Consolidation Cycle Flow now documents Steps 1.2 (load deferred), 1.3 (annotate), 1.5 (branch), 1.6 (score + gate) as first-class, with mode-aware promotion eligibility and mode-aware per-log marking rules. Previous text that said "proceed directly to Step 2" and "immediately after consolidation" is now split per-branch. Scan-window language uses profile-driven `SCAN_DAYS` (7 personal / 3 business) instead of a hardcoded "last 7 days".
- **Deterministic deferred-append handoff**: new `gate.py --emit-deferred <path>` writes the deferred candidate array to a file in the exact schema expected by `deferred.py --append`. The LLM no longer hand-constructs `$TMPDIR/reflections-deferred-new.json` — gate.py emits it. This closes the last prose seam on the strict-mode persistence path.
- **`references/consolidation-prompt.md` marked ARCHIVED**: top-level banner explicitly identifies it as v1.0.0 historical reference, not runtime authority. Readers are pointed to `runtime/reflections-prompt.md` for current contracts.
- All 10 scripts compile; end-to-end strict flow (annotate → score → gate --write-back --emit-deferred → deferred --append) verified with zero LLM payload construction.

## Changes in v1.1.5

- **Scan-window wording corrected**: runtime prompt no longer claims the absent-field fallback of `7` matches upstream Auto-Dream Lite. The truth: upstream Lite scans 3 days; this fork is profile-driven (personal=7, business=3); fallback `7` is a fork convention for legacy/misconfigured installs only.
- **Stale "optional strict-mode" bullets rewritten**: v1.1.0 changelog entries that called `score.py --candidates` and `gate.py` "optional/diagnostic/disabled by default" now carry historical-note framing — strict-mode is profile-driven (business=true default) since v1.1.2+, not optional.
- **`score.py` docstring + CLI help updated**: `--candidates` is now documented as the strict-mode runtime path used by the business-employee default. Removed misleading "optional/not default" phrasing.
- **`modes.*.cadence` removed from sample JSONs**: those fields were never consumed by any script. `dispatch.py` uses hardcoded intervals (rem=6h, deep=12h, core=24h). Sample presets in `profiles/` and `references/memory-template.md` no longer carry inert fields. Field reference table and skill-reference.md updated to reflect hardcoded-interval reality.
- **Dispatch semantics explicitly documented**: new "Dispatch Semantics" subsection in `references/memory-template.md` and README Configuration section clearly separate host scheduling (`dispatchCadence`) from mode-due elapsed gating (`MODE_INTERVALS`).
- **Canonical sentence updated**: "supports profile-driven admission" → "**applies** profile-driven admission" across all 5 user-facing docs. "Applies" better reflects that admission is an active, shipped behavior, not opt-in capability.
- JSON schema version unchanged (removing inert fields is non-breaking — legacy configs still parse).

## Changes in v1.1.4

- **Deterministic gate handoff**: `gate.py --write-back` now commits the gate decision to `reflections-candidates.json` as `gate_status: "qualified" | "deferred"`, `gate_promoted_by`, `gate_bypass`, and `gate_fail_reasons` fields on each candidate. Step 2 consolidation filters on `gate_status == "qualified"` AND `deferred_status != "persisted"` — no prompt-volitional decisions remain on the strict promotion path.
- **Mode-aware telemetry vocabulary**: `details` payload now reflects branch behavior. Parity flow emits `entries_consolidated` / `entries_extracted`. Strict flow emits `entries_qualified` / `entries_deferred` / `entries_promoted`. First-reflection continues to use `entries_consolidated`.
- **Profile-driven cron cadence**: new top-level `dispatchCadence` config field. Personal-assistant defaults to `"30 4,10,16,22 * * *"` (04:30/10:30/16:30/22:30); business-employee defaults to `"30 5,12,18,22 * * *"` (05:30/12:30/18:30/22:30). Cadences are intentionally offset so co-hosted profiles don't fire at the same minute. `INSTALL.md` Step 6 resolves cadence from the config.
- **scanWindowDays fallback unified**: recurring-prompt fallback now `7` (matches personal-assistant default). **Not upstream parity** — upstream Lite recurring scans the last 3 days; this fork diverges deliberately to accommodate profile-driven topologies. Stale v1.1.1 changelog line corrected to reference the v1.1.2 canonical defaults.
- **Strict-mode wording unified** in `references/skill-reference.md` and `references/scoring.md`: strict is profile-driven (personal=false, business=true), not an optional appendix or diagnostic path. Strict steps are first-class runtime steps.
- **Docs consistency audit**: INSTALL.md Step 6 no longer hardcodes a single cadence; all docs reference the profile-driven cadence and the mode-aware telemetry schema.
- JSON schema version unchanged (new `dispatchCadence` field is optional; absent-field fallback derives from `profile`).

## Changes in v1.1.3

- **Candidate recency fallback hardened**: `score.py --candidates` mode now falls back `lastReferenced → created → 0 days`. Previously, a candidate with only `created` (no `lastReferenced`) scored as perfectly fresh. Strict-mode gates now decay correctly for newly-extracted items aged on disk.
- **Deferred identity now rewording-stable**: each deferred record carries three identities — `existingId` (strongest, when matched), `fingerprint` (token-bag scoped to `source + target_section`, survives light rewording: case, punctuation, whitespace, stopwords, word order), and `candidate_hash` (v1.1.2-compat exact-string, kept for audit). `--is-deferred` matches on any identity layer.
- **Deterministic deferred-suppression**: new Step 1.3 runs `deferred.py --annotate --write-back` before the gate, writing `deferred_status: "persisted" | "fresh"` and `deferred_matched_by` onto every candidate. Step 2 skips `persisted` candidates. Suppression no longer depends on prompt-following.
- **Strict-fork scope clarified as profile-opt-in**: personal-assistant defaults to `strictMode: false` (upstream parity); business-employee defaults to `strictMode: true` (strict fork). Canonical sentence updated: "…uses memory-core-safe long-term surfaces, **and supports** profile-driven admission before durable promotion" — "supports" signals profile-opt-in, not global-strict.
- New `deferred.py` CLI modes: `--fingerprint`, `--annotate` (with `--write-back`). Extended `--is-deferred` to match existingId/fingerprint/candidate_hash.
- Deferred record schema adds `fingerprint` and `target_section` fields.
- JSON schema version unchanged (no migration — new fields are optional).

## Changes in v1.1.2

- **Persisted deferred state**: strict-mode now writes deferred candidates to `runtime/reflections-deferred.jsonl` with candidate hash, source, fail reasons, timestamps — closes the data-loss gap from v1.1.1
- **Strict-mode log marking now works end-to-end**: logs reach stable processed-state when every extractable item is either promoted or recorded in the deferred store
- **Mode-aware Step 3.5 insights**: gate results reviewed only when strictMode=true; archival results reviewed when strictMode=false
- **First-reflection telemetry**: `entries_qualified` → `entries_consolidated` (first-run bypasses gates by design)
- **Profile scanWindowDays reoriented around noise tolerance**: personal-assistant=7 (sparse, meaningful), business-employee=3 (noisy, higher-volume) — the v1.1.1 defaults were inverted
- **Docs unified** around: "Reflections preserves the same reflection/scoring role as Auto-Dream, uses memory-core-safe long-term surfaces, and applies profile-driven admission before durable promotion"
- New script: `scripts/deferred.py` for deferred-state CRUD (--append, --is-deferred, --load-for-source, --all, --hash)
- JSON schema version unchanged (no migration)

## Changes in v1.1.1

- `strictMode` is now a first-class config field with a real runtime branch in the recurring prompt (not just an appendix pointer)
- `scanWindowDays` is now profile-driven (replaces hardcoded 7-day window). Initial v1.1.1 defaults were inverted; **corrected in v1.1.2 to the noise-tolerance model** (personal-assistant=7, business-employee=3). Refer to the v1.1.2 changelog for the canonical defaults.
- Mode-aware log-marking: strict-mode now intentionally does NOT mark logs until persisted-deferred state is implemented — prevents data loss; parity mode still marks per-log immediately
- Candidate schema adds optional `existingId`, `lastReferenced`, `created`, `tags` for correct recency scoring of matched entries
- `MODE_CSV` derived from actual `due_modes`; no more hardcoded `rem,deep,core` in gate.py or update-lastrun calls
- First-run wording: removed "every morning" in favor of "configured schedule"
- Docs unified around: "profile-driven hybrid fork, same reflection/scoring role, memory-core-safe surfaces, configurable scored promotion"
- Profile presets now specify `strictMode` and `scanWindowDays` defaults
- JSON schema version unchanged (no migration required)

---
This repository is a fork of [MyClaw.ai - openclaw-auto-dream](https://github.com/LeoYeAI/openclaw-auto-dream)

---

## Changes in v1.1.0

- **Recurring flow restored to upstream Auto-Dream Lite parity**: `collect → consolidate → archive` (no pre-consolidation gate in default path)
- **Daily logs now marked `<!-- consolidated -->` immediately after per-log consolidation** (not at end of cycle) — prevents duplicate reprocessing if later steps fail
- **Dashboard refresh restored as active step** in the default recurring flow (regenerates from `references/dashboard-template.html` when `memory/dashboard.html` exists)
- **`score.py` now supports `--candidates` mode** used by the strict-mode flow (business-employee default; personal-assistant parity flow skips it). (Historical note: earlier v1.1.0 framing described this as "diagnostic/optional"; strictMode became profile-driven in v1.1.2+ — strict is now a shipped default for business-employee, not optional.)
- **`dispatch.py` and `scan.py` return exit 0 on valid idle states** — idle is not failure
- **`gate.py` retained for strict-mode flows**. (Historical note: earlier v1.1.0 framing described this as "disabled by default"; strictMode became a first-class runtime branch in v1.1.1 and profile-driven in v1.1.2+. `gate.py` runs by default when `strictMode: true` — personal-assistant defaults false, business-employee defaults true.)
- Package version bumped; **JSON schema version unchanged** (no migration required)

---
