#!/usr/bin/env python3
"""
reflections: durability — second-stage durability routing (strictMode only)

Runs after score.py + gate.py + deferred.py --annotate. Consumes:
  - candidates file mutated by gate.py --write-back (gate_status, gate_bypass, marker)
  - semantic annotations emitted by the LLM in Step 1.7
  - profile-tuned thresholds from the config's top-level `durability` block
  - read-only index (for duplicate_of_existing lookups and supportCount verification)

Writes back onto each candidate (v1.3.0 full route set):
  route              promote | defer | reject | merge | compress
  destination        RTMEMORY | PROCEDURES | EPISODE | TREND | NONE
  durabilityScore    net = structural + meaning + futureConsequence - noisePenalty
  noisePenalty       the penalty component in isolation
  promotionReason    short string: hard-trigger name, "net>=threshold", "merge-into:...", etc.
  memoryType         echoed from annotation
  durabilityClass    echoed from annotation
  mergeKey           echoed from annotation
  trendKey           echoed from annotation
  duplicateOfExisting  echoed (string|null)
  mergedInto         v1.3.0: target entry id when route=merge; existing trend id when route=compress
  promotedFromTrend  v1.3.0: existing trend node id when a hard-triggered candidate promotes
                     from an accumulated trend (trendPromoteSupportCount + trendPromoteUniqueDayCount
                     thresholds met on the existing trend)
  compressionReason  v1.3.0: "reinforce-trend:<id>" or "new-trend:<key>"
  supportCount       referenceCount at routing time

Deferred candidates emit a separate file in deferred.py --append schema so the
existing persistence path handles them with zero new append code.

Usage:
    python3 durability.py \\
      --candidates $TMPDIR/reflections-candidates.json \\
      --annotations $TMPDIR/reflections-durability.json \\
      --config $CONFIG_PATH \\
      --index runtime/reflections-metadata.json \\
      --write-back \\
      --emit-defer-subset $TMPDIR/reflections-durability-deferred.json

Non-goals:
- Does not write to RTMEMORY.md, PROCEDURES.md, or episodes directly.
  Step 2 reads the `route` field and performs the actual writes.
- Does not modify score.py / gate.py / deferred.py output fields.
- Does not run in parity mode (skipped by the runtime prompt when strictMode=false).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ────────────────────────── identity helpers ──────────────────────────

def get_entry_id(entry: dict) -> str:
    """Mirrors gate.py's resolution order — must match for candidate↔annotation join."""
    return str(
        entry.get('id')
        or entry.get('summary')
        or entry.get('title')
        or entry.get('name')
        or json.dumps(entry, sort_keys=True, ensure_ascii=False)
    )


def normalize_marker(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip().upper()
    return str(value).strip().upper()


# ────────────────────────── scoring components ──────────────────────────

def compute_structural_evidence(cand: dict) -> int:
    """
    0..4 band from gate.py outputs + raw reinforcement.
    PERMANENT/FAST_PATH bypass always maxes structural evidence at 4.
    """
    bypass = cand.get('gate_bypass')
    if bypass in ('PERMANENT', 'FAST_PATH'):
        return 4

    ref_count = int(cand.get('referenceCount', cand.get('ref_count', 0)) or 0)
    unique_day = int(cand.get('uniqueDayCount', cand.get('unique_day_count', 0)) or 0)

    score = 0
    if ref_count >= 1:
        score += 1
    if ref_count >= 3:
        score += 1
    if unique_day >= 2:
        score += 1
    if unique_day >= 4:
        score += 1

    return min(4, max(0, score))


def compute_meaning_weight(ann: dict) -> int:
    """0..4 band from the five LLM meaning flags."""
    flags = [
        ann.get('changed_future_decision'),
        ann.get('changed_behavior_or_policy'),
        ann.get('created_stable_preference'),
        ann.get('created_obligation_or_boundary'),
        ann.get('relationship_or_identity_shift'),
    ]
    return min(4, sum(1 for f in flags if f is True))


def compute_future_consequence(ann: dict) -> int:
    """0..4 band from the three consequence flags (at most 3 set → clamp to 4 safe)."""
    flags = [
        ann.get('cross_day_relevance'),
        ann.get('rare_high_consequence'),
        ann.get('actionable_procedure'),
    ]
    base = sum(1 for f in flags if f is True)
    # rare_high_consequence is the strongest signal → bump by 1 if set
    if ann.get('rare_high_consequence') is True:
        base += 1
    return min(4, base)


def compute_noise_penalty(ann: dict) -> int:
    """0..4 band from the three noise flags (telemetry_noise weighted heavier)."""
    score = 0
    if ann.get('pattern_only') is True:
        score += 1
    if ann.get('pure_status') is True:
        score += 1
    if ann.get('telemetry_noise') is True:
        score += 2
    return min(4, score)


# ────────────────────────── hard-trigger evaluation ──────────────────────────

def check_hard_promote(ann: dict, structural: int) -> Optional[str]:
    """
    Return the trigger name if any hard-promote rule fires, else None.
    Trigger names are used verbatim as promotionReason values.
    """
    mem_type = (ann.get('memory_type') or '').strip().lower()

    if mem_type in ('decision', 'lesson') and (
        ann.get('changed_future_decision') or ann.get('changed_behavior_or_policy')
    ):
        return f'hard-trigger:{mem_type}-with-consequence'

    if ann.get('created_stable_preference') is True:
        return 'hard-trigger:created_stable_preference'

    if ann.get('created_obligation_or_boundary') is True:
        return 'hard-trigger:created_obligation_or_boundary'

    if ann.get('relationship_or_identity_shift') is True:
        return 'hard-trigger:relationship_or_identity_shift'

    if ann.get('actionable_procedure') is True and structural >= 2:
        return 'hard-trigger:validated_actionable_procedure'

    if mem_type == 'architecture' and ann.get('rare_high_consequence') is True:
        return 'hard-trigger:architecture_rare_high_consequence'

    return None


def check_hard_suppress(ann: dict) -> Optional[str]:
    """Return a short reason if any hard-suppress rule fires, else None."""
    if ann.get('telemetry_noise') is True:
        return 'hard-suppress:telemetry_noise'

    if ann.get('pure_status') is True and ann.get('rare_high_consequence') is not True:
        return 'hard-suppress:pure_status_no_consequence'

    if ann.get('pattern_only') is True and ann.get('cross_day_relevance') is not True:
        return 'hard-suppress:pattern_only_same_day'

    return None


# ────────────────────────── destination mapping ──────────────────────────

def pick_destination(mem_type: str, route: str, hard_trigger: Optional[str]) -> str:
    """
    v1.3.0 destination rules. Only meaningful when route == 'promote' OR 'compress'.
    - promote → RTMEMORY / PROCEDURES / EPISODE depending on memory_type
    - compress → TREND (unconditionally for compress route)
    - merge → NONE (action is reinforcement of an existing entry, no new surface write)
    - defer / reject → NONE
    """
    if route == 'compress':
        return 'TREND'
    if route == 'merge':
        return 'NONE'
    if route != 'promote':
        return 'NONE'

    mt = (mem_type or '').strip().lower()

    if mt in ('decision', 'lesson', 'obligation', 'relationship', 'identity', 'architecture'):
        return 'RTMEMORY'
    if mt == 'preference':
        return 'RTMEMORY'
    if mt == 'procedure':
        return 'PROCEDURES'
    if mt == 'observation':
        # Only hard-triggered observations reach EPISODE in Phase 1
        return 'EPISODE' if hard_trigger else 'RTMEMORY'
    if mt in ('trend', 'status'):
        # A trend type that reaches 'promote' is a promoted-trend case:
        # an accumulated trend that now has durable meaning (hard-triggered)
        # should land in RTMEMORY as a distinct durable conclusion, with
        # a cross-reference to the original trend node (added by Step 2).
        return 'RTMEMORY'

    # Unknown memory_type: fallback
    return 'RTMEMORY'


# ────────────────────────── trend node lookup (v1.3.0) ──────────────────────────

def find_trend_node_by_key(index: dict, trend_key: str) -> Optional[dict]:
    """Look up an existing trend node by its trendKey."""
    if not trend_key:
        return None
    for e in index.get('entries', []):
        if e.get('archived'):
            continue
        if e.get('memoryType') == 'trend' and e.get('trendKey') == trend_key:
            return e
    return None


def find_entry_by_id(index: dict, entry_id: str) -> Optional[dict]:
    """Look up any entry by id (for duplicate_of_existing resolution)."""
    if not entry_id:
        return None
    for e in index.get('entries', []):
        if e.get('id') == entry_id:
            return e
    return None


def trend_meets_promotion_criteria(trend_node: dict, cfg: dict) -> bool:
    """
    A trend node becomes eligible to promote into RTMEMORY as a durable
    conclusion only when its accumulated support crosses both thresholds
    AND the current annotation adds a hard-promote trigger (checked separately
    in route_candidate).

    This function only checks the structural side (accumulation). The semantic
    hard-promote check is folded into the router.
    """
    support = int(trend_node.get('trendSupportCount', trend_node.get('referenceCount', 0)) or 0)
    unique_days = int(trend_node.get('uniqueDayCount', 0) or 0)
    promote_support = int(cfg.get('trendPromoteSupportCount', 5))
    promote_days = int(cfg.get('trendPromoteUniqueDayCount', 3))
    return support >= promote_support and unique_days >= promote_days


# ────────────────────────── config loading ──────────────────────────

DEFAULT_DURABILITY = {
    'enabled': True,
    'netPromoteThreshold': 6,
    'netDeferThreshold': 3,
    # v1.3.0 trend-promotion criteria: when should an accumulated trend
    # node promote to RTMEMORY as a durable conclusion? These thresholds
    # are checked on the *existing trend node* at compress time; if they
    # are met AND the candidate carries a fresh hard-promote trigger,
    # route promotes as a distinct RTMEMORY node linked to the trend.
    'trendPromoteSupportCount': 5,
    'trendPromoteUniqueDayCount': 3,
}


def load_durability_config(config_path: str) -> dict:
    """Merge profile durability block with safe defaults."""
    path = Path(config_path)
    if not path.exists():
        return dict(DEFAULT_DURABILITY)
    with open(path, 'r', encoding='utf-8') as f:
        cfg = json.loads(f.read())
    dur = cfg.get('durability', {}) or {}
    merged = dict(DEFAULT_DURABILITY)
    merged.update({k: v for k, v in dur.items() if v is not None})
    return merged


def load_index(index_path: str) -> dict:
    """Read-only index load; empty shell if missing."""
    path = Path(index_path)
    if not path.exists():
        return {'entries': []}
    with open(path, 'r', encoding='utf-8') as f:
        return json.loads(f.read())


def build_index_id_set(index: dict) -> set:
    """Set of all existing entry IDs (for duplicate_of_existing validation)."""
    return {e.get('id') for e in index.get('entries', []) if e.get('id')}


# ────────────────────────── routing core ──────────────────────────

def route_candidate(cand: dict, ann: dict, cfg: dict,
                    index: dict, index_ids: set) -> dict:
    """
    v1.3.0 deterministic routing — full route set {reject, defer, merge, compress, promote}.

    Precedence:
      1. hard-suppress triggers → reject
      2. hard-promote triggers →
           if candidate has a trendKey matching an existing trend node AND that
           trend node already meets promotion criteria (support + unique days),
           route = promote with destination=RTMEMORY and `promotedFromTrend` set
           (existing trend node is preserved as historical context).
           Otherwise: route = promote (duplicates still allowed here — a
           hard-triggered item legitimately distinct from a similar existing node).
      3. duplicate_of_existing → merge (was defer in v1.2.0)
           Reinforces the existing durable node. Only happens when no
           hard-promote trigger fired.
      4. trendKey set + weak ops material → compress (was defer in v1.2.0)
           Reinforces or creates a single trend node. Applies when:
           - memory_type in {observation, status, trend}, AND
           - no hard-promote trigger, AND
           - no actionable_procedure (that would route to PROCEDURES instead),
           - regardless of whether existing trend node exists (durability.py signals
             Step 2 via trendKey; Step 2 looks up or creates the trend entry).
      5. Net-score banding (promote ≥ netPromoteThreshold; defer ≥ netDeferThreshold; else reject)
    """
    structural = compute_structural_evidence(cand)
    meaning = compute_meaning_weight(ann)
    future = compute_future_consequence(ann)
    noise = compute_noise_penalty(ann)
    net = structural + meaning + future - noise

    mem_type = (ann.get('memory_type') or '').strip().lower()
    duplicate_of = ann.get('duplicate_of_existing')
    # Normalize "null" strings from JSON to real None
    if duplicate_of in ('null', '', None):
        duplicate_of = None
    trend_key = ann.get('trend_key')
    if trend_key in ('null', '', None):
        trend_key = None

    hard_suppress_reason = check_hard_suppress(ann)
    hard_trigger = check_hard_promote(ann, structural)

    promote_threshold = int(cfg.get('netPromoteThreshold', 6))
    defer_threshold = int(cfg.get('netDeferThreshold', 3))

    # Look up existing trend node if trendKey is set — used for two branches:
    #   (a) trend-to-durable promotion (step 2 below)
    #   (b) compress reinforcement target (step 4 below)
    existing_trend = find_trend_node_by_key(index, trend_key) if trend_key else None

    # v1.3.0 additional output fields beyond v1.2.0
    merged_into = None
    promoted_from_trend = None
    compression_reason = None

    # 1. Hard-suppress wins over everything
    if hard_suppress_reason:
        route = 'reject'
        reason = hard_suppress_reason
        destination = 'NONE'

    # 2. Hard-promote
    elif hard_trigger:
        route = 'promote'
        reason = hard_trigger
        destination = pick_destination(mem_type, route, hard_trigger)
        # Trend-to-durable promotion: if this candidate carries a trendKey AND
        # the existing trend node already accumulated durable-grade support,
        # this hard-triggered promotion is the "trend became a durable conclusion"
        # case. Link them so the RTMEMORY node references its trend origin.
        if existing_trend and trend_meets_promotion_criteria(existing_trend, cfg):
            promoted_from_trend = existing_trend.get('id')
            reason = f'{hard_trigger};promoted-from-trend:{promoted_from_trend}'

    # 3. Merge (duplicate of existing durable node, no hard-trigger)
    elif duplicate_of and duplicate_of in index_ids:
        route = 'merge'
        reason = f'merge-into:{duplicate_of}'
        destination = 'NONE'
        merged_into = duplicate_of

    # 3b. duplicate_of_existing set but not resolvable in index → defer (stale ref)
    elif duplicate_of and duplicate_of not in index_ids:
        route = 'defer'
        reason = f'duplicate-of-unknown:{duplicate_of}'
        destination = 'NONE'

    # 4. Compress (repeated weak ops material with a stable trendKey)
    elif (
        trend_key
        and mem_type in ('observation', 'status', 'trend')
        and ann.get('actionable_procedure') is not True
    ):
        route = 'compress'
        destination = 'TREND'
        if existing_trend:
            merged_into = existing_trend.get('id')
            compression_reason = f'reinforce-trend:{existing_trend.get("id")}'
            reason = compression_reason
        else:
            compression_reason = f'new-trend:{trend_key}'
            reason = compression_reason

    # 5. Net-score banding
    elif net >= promote_threshold:
        route = 'promote'
        reason = f'net={net}>={promote_threshold}'
        destination = pick_destination(mem_type, route, None)
    elif net >= defer_threshold:
        route = 'defer'
        reason = f'net={net}>={defer_threshold}'
        destination = 'NONE'
    else:
        route = 'reject'
        reason = f'net={net}<{defer_threshold}'
        destination = 'NONE'

    return {
        'route': route,
        'destination': destination,
        'durabilityScore': net,
        'noisePenalty': noise,
        'promotionReason': reason,
        'memoryType': ann.get('memory_type'),
        'durabilityClass': ann.get('durability_class'),
        'mergeKey': ann.get('merge_key'),
        'trendKey': trend_key,
        'duplicateOfExisting': duplicate_of,
        'mergedInto': merged_into,
        'promotedFromTrend': promoted_from_trend,
        'compressionReason': compression_reason,
        'supportCount': int(cand.get('referenceCount', cand.get('ref_count', 0)) or 0),
        'components': {
            'structuralEvidence': structural,
            'meaningWeight': meaning,
            'futureConsequence': future,
            'noisePenalty': noise,
        },
    }


# ────────────────────────── annotation / candidate join ──────────────────────────

def index_annotations(annotations: list) -> dict:
    """
    Build a lookup from candidate_id → annotation dict.
    Accepts both an explicit `candidate_id` field or falls back to an `id` field.
    """
    out = {}
    for a in annotations:
        if not isinstance(a, dict):
            continue
        key = a.get('candidate_id') or a.get('id')
        if key is not None:
            out[str(key)] = a
    return out


def is_rescue_eligible(cand: dict, ann: Optional[dict]) -> bool:
    """
    A structurally-deferred candidate enters durability review if:
      - gate_bypass is set (PERMANENT / FAST_PATH tried to bypass), OR
      - marker ∈ {HIGH, PERMANENT, PIN}, OR
      - the LLM produced an annotation at all with a high-meaning memory_type
    """
    if cand.get('gate_bypass') in ('PERMANENT', 'FAST_PATH'):
        return True
    marker = normalize_marker(cand.get('marker'))
    if marker in ('HIGH', 'PERMANENT', 'PIN'):
        return True
    if ann is not None:
        mt = (ann.get('memory_type') or '').strip().lower()
        if mt in ('decision', 'lesson', 'obligation', 'relationship', 'identity', 'architecture'):
            return True
    return False


# ────────────────────────── defer-subset emission ──────────────────────────

def emit_defer_subset(output_path: str, deferred_records: list,
                      modes_evaluated: list) -> dict:
    """
    Write defer-routed candidates to a file in the exact schema expected by
    deferred.py --append, so the existing persistence path handles them with
    zero new code. Mirrors gate.py:emit_deferred_file() shape.
    """
    records = []
    for r in deferred_records:
        cand = r['candidate']
        routing = r['routing']
        records.append({
            'summary': cand.get('summary', ''),
            'source': cand.get('source', ''),
            'target_section': cand.get('target_section', ''),
            'fail_reasons': {
                'durability': {
                    'route': routing.get('route'),
                    'reason': routing.get('promotionReason'),
                    'durabilityScore': routing.get('durabilityScore'),
                    'noisePenalty': routing.get('noisePenalty'),
                    'mergeKey': routing.get('mergeKey'),
                    'trendKey': routing.get('trendKey'),
                    'duplicateOfExisting': routing.get('duplicateOfExisting'),
                },
            },
            'modes_evaluated': list(modes_evaluated),
            'referenceCount': int(cand.get('referenceCount', cand.get('ref_count', 1)) or 1),
            'existingId': cand.get('existingId'),
        })

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(records, indent=2, ensure_ascii=False))

    return {
        'ok': True,
        'emit_defer_subset_path': str(out_path),
        'deferred_count': len(records),
    }


# ────────────────────────── top-level orchestration ──────────────────────────

def run_durability(candidates_path: str, annotations_path: str,
                   config_path: str, index_path: str,
                   write_back: bool = False,
                   emit_defer_path: Optional[str] = None) -> dict:
    cand_file = Path(candidates_path)
    if not cand_file.exists():
        return {'ok': False, 'error': f'Candidates file not found: {candidates_path}'}

    ann_file = Path(annotations_path)
    if not ann_file.exists():
        return {'ok': False, 'error': f'Annotations file not found: {annotations_path}'}

    with open(cand_file, 'r', encoding='utf-8') as f:
        candidates = json.loads(f.read())
    if not isinstance(candidates, list):
        return {'ok': False, 'error': 'Candidates file must be a JSON array'}

    with open(ann_file, 'r', encoding='utf-8') as f:
        annotations = json.loads(f.read())
    if not isinstance(annotations, list):
        return {'ok': False, 'error': 'Annotations file must be a JSON array'}

    cfg = load_durability_config(config_path)
    index = load_index(index_path)
    index_ids = build_index_id_set(index)
    ann_by_id = index_annotations(annotations)

    if not cfg.get('enabled', True):
        # Durability is disabled for this install. Leave candidates untouched.
        return {
            'ok': True,
            'durability_disabled': True,
            'note': 'durability.enabled is false in config; no routing applied',
            'total_candidates': len(candidates),
        }

    # Shape: tally buckets per route + skipped
    promoted: List[dict] = []
    deferred: List[dict] = []
    rejected: List[dict] = []
    merged: List[dict] = []      # v1.3.0
    compressed: List[dict] = []  # v1.3.0
    skipped: List[dict] = []   # not in semantic-review set (structurally-deferred, not rescued)

    for cand in candidates:
        cid = get_entry_id(cand)
        ann = ann_by_id.get(cid)

        # Skip candidates already filtered by upstream deferred store
        if cand.get('deferred_status') == 'persisted':
            skipped.append(cand)
            continue

        gate_status = cand.get('gate_status')

        # Scope: qualified OR rescue-eligible deferred
        if gate_status == 'qualified':
            pass  # always in review set
        elif gate_status == 'deferred':
            if not is_rescue_eligible(cand, ann):
                skipped.append(cand)
                continue
        else:
            # No gate_status (shouldn't happen in strict flow, but be defensive)
            skipped.append(cand)
            continue

        # Must have an annotation for in-review candidates
        if ann is None:
            # LLM didn't annotate this one despite being in-scope; skip safely
            skipped.append(cand)
            continue

        routing = route_candidate(cand, ann, cfg, index, index_ids)

        if write_back:
            cand.update({
                'route': routing['route'],
                'destination': routing['destination'],
                'durabilityScore': routing['durabilityScore'],
                'noisePenalty': routing['noisePenalty'],
                'promotionReason': routing['promotionReason'],
                'memoryType': routing['memoryType'],
                'durabilityClass': routing['durabilityClass'],
                'mergeKey': routing['mergeKey'],
                'trendKey': routing['trendKey'],
                'duplicateOfExisting': routing['duplicateOfExisting'],
                'mergedInto': routing['mergedInto'],
                'promotedFromTrend': routing['promotedFromTrend'],
                'compressionReason': routing['compressionReason'],
                'supportCount': routing['supportCount'],
                'durabilityComponents': routing['components'],
            })

        record = {'candidate': cand, 'routing': routing}
        if routing['route'] == 'promote':
            promoted.append(record)
        elif routing['route'] == 'defer':
            deferred.append(record)
        elif routing['route'] == 'reject':
            rejected.append(record)
        elif routing['route'] == 'merge':
            merged.append(record)
        elif routing['route'] == 'compress':
            compressed.append(record)

    if write_back:
        with open(cand_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(candidates, indent=2, ensure_ascii=False))

    result = {
        'ok': True,
        'config': {
            'netPromoteThreshold': cfg.get('netPromoteThreshold'),
            'netDeferThreshold': cfg.get('netDeferThreshold'),
            'trendPromoteSupportCount': cfg.get('trendPromoteSupportCount'),
            'trendPromoteUniqueDayCount': cfg.get('trendPromoteUniqueDayCount'),
        },
        'total_candidates': len(candidates),
        'in_review': (len(promoted) + len(deferred) + len(rejected)
                      + len(merged) + len(compressed)),
        'promoted_count': len(promoted),
        'deferred_count': len(deferred),
        'rejected_count': len(rejected),
        'merged_count': len(merged),        # v1.3.0
        'compressed_count': len(compressed), # v1.3.0
        'skipped_count': len(skipped),
        'write_back': write_back,
    }

    if emit_defer_path:
        modes_evaluated = []
        # pluck modes from first candidate that carries them (gate.py writes it implicitly via gate_fail_reasons)
        for c in candidates:
            if c.get('gate_fail_reasons'):
                modes_evaluated = list(c.get('gate_fail_reasons', {}).keys())
                if modes_evaluated:
                    break
        ed = emit_defer_subset(emit_defer_path, deferred, modes_evaluated)
        result['emit_defer_subset'] = ed

    return result


# ────────────────────────── CLI ──────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Reflections: Durability routing (second-stage admission, strictMode only)'
    )
    parser.add_argument('--candidates', required=True,
                        help='Path to candidates JSON (mutated in place with --write-back)')
    parser.add_argument('--annotations', required=True,
                        help='Path to LLM durability annotations JSON (array)')
    parser.add_argument('--config', required=True,
                        help='Path to reflections.json (for durability thresholds)')
    parser.add_argument('--index', required=True,
                        help='Path to runtime/reflections-metadata.json (read-only)')
    parser.add_argument('--write-back', action='store_true',
                        help='Mutate the candidates file in place, writing route/destination/durabilityScore/etc.')
    parser.add_argument('--emit-defer-subset', metavar='OUTPUT_JSON',
                        help='Write defer-routed candidates to this path in deferred.py --append schema')
    args = parser.parse_args()

    result = run_durability(
        args.candidates,
        args.annotations,
        args.config,
        args.index,
        write_back=args.write_back,
        emit_defer_path=args.emit_defer_subset,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('ok') else 2


if __name__ == '__main__':
    sys.exit(main())
