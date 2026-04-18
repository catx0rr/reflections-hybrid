#!/usr/bin/env python3
"""
reflections: score — importance scoring engine

Computes importance scores for memory entries using the exact formula:
  importance = clamp((base_weight × recency × ref_boost) / 8.0, 0.0, 1.0)

Also checks archival eligibility (forgetting curve).

Usage:
    python3 score.py --index runtime/reflections-metadata.json                     # Score committed entries (archival input)
    python3 score.py --index runtime/reflections-metadata.json --check-archival    # Flag archival candidates
    python3 score.py --single --ref-count 7 --unique 4 --days 30                   # Score one entry
    python3 score.py --single --ref-count 7 --unique 4 --days 30 --marker HIGH
    python3 score.py --candidates /tmp/reflections-candidates.json --write-back    # Pre-consolidation scoring (strict flow)

Modes:
    --index       Score entries already committed to the metadata file. Always runs in every
                  flow (parity + strict); the output drives the archival/forgetting curve.
    --candidates  Score pre-consolidation candidate entries in-place. Used by the strict-mode
                  flow only. business-employee default path invokes this before gate.py.
                  personal-assistant parity flow skips this step (no pre-consolidation gate).
    --single      Score one hypothetical entry from CLI parameters (diagnostic / demonstration).

Profile-driven invocation:
    strictMode is profile-driven (personal-assistant defaults false, business-employee
    defaults true). The recurring prompt's Step 1.6 invokes --candidates only when
    STRICT_MODE == true. Parity flow reads scores from --index at archival time.
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ARCHIVAL_DAYS_THRESHOLD = 90
ARCHIVAL_IMPORTANCE_THRESHOLD = 0.3


def compute_importance(ref_count: int, days_since_ref: int,
                       marker: str = None) -> dict:
    """Compute importance score for a single entry."""
    # Permanent always 1.0
    if marker == 'PERMANENT':
        return {
            'importance': 1.0,
            'base_weight': 'N/A',
            'recency_factor': 'N/A',
            'reference_boost': 'N/A',
            'raw': 'N/A',
            'marker': 'PERMANENT',
            'note': 'PERMANENT marker — always 1.0',
        }

    # Base weight
    base_weight = 2.0 if marker == 'HIGH' else 1.0

    # Recency factor
    recency = max(0.1, 1.0 - (days_since_ref / 180))

    # Reference boost
    ref_boost = max(1.0, math.log2(ref_count + 1))

    # Raw and normalized
    raw = base_weight * recency * ref_boost
    importance = min(1.0, max(0.0, raw / 8.0))

    return {
        'importance': round(importance, 4),
        'base_weight': base_weight,
        'recency_factor': round(recency, 4),
        'reference_boost': round(ref_boost, 4),
        'raw': round(raw, 4),
        'marker': marker,
    }


def detect_marker(entry: dict) -> str:
    """Detect marker from entry summary or tags."""
    summary = entry.get('summary', '')
    tags = entry.get('tags', [])

    if '⚠️ PERMANENT' in summary or 'PERMANENT' in summary:
        return 'PERMANENT'
    if '🔥 HIGH' in summary or 'HIGH' in tags:
        return 'HIGH'
    if '📌 PIN' in summary or 'PIN' in tags:
        return 'PIN'
    return None


def check_archival(entry: dict, importance: float, days_since_ref: int) -> dict:
    """Check if entry is eligible for archival."""
    marker = detect_marker(entry)

    eligible = (
        days_since_ref > ARCHIVAL_DAYS_THRESHOLD
        and importance < ARCHIVAL_IMPORTANCE_THRESHOLD
        and marker not in ('PERMANENT', 'PIN')
        and not entry.get('archived', False)
    )

    reasons = []
    if days_since_ref <= ARCHIVAL_DAYS_THRESHOLD:
        reasons.append(f'referenced {days_since_ref} days ago (need >{ARCHIVAL_DAYS_THRESHOLD})')
    if importance >= ARCHIVAL_IMPORTANCE_THRESHOLD:
        reasons.append(f'importance {importance:.3f} (need <{ARCHIVAL_IMPORTANCE_THRESHOLD})')
    if marker in ('PERMANENT', 'PIN'):
        reasons.append(f'{marker} marker — immune')
    if entry.get('archived'):
        reasons.append('already archived')

    return {
        'eligible': eligible,
        'days_since_ref': days_since_ref,
        'importance': importance,
        'marker': marker,
        'reasons': reasons if not eligible else ['all archival conditions met'],
    }


def score_index(index_path: str, check_archival_flag: bool = False) -> dict:
    """Score all entries in a reflections-metadata.json file."""
    path = Path(index_path)
    if not path.exists():
        return {'ok': False, 'error': f'Index not found: {index_path}'}

    with open(path, 'r') as f:
        index = json.loads(f.read())

    entries = index.get('entries', [])
    now = datetime.now(tz=timezone.utc)

    scored = []
    archival_candidates = []
    total_importance = 0.0
    active_count = 0

    for entry in entries:
        if entry.get('archived'):
            continue

        active_count += 1

        # Compute days since last referenced
        last_ref = entry.get('lastReferenced', entry.get('created', ''))
        if last_ref:
            try:
                ref_dt = datetime.fromisoformat(last_ref.replace('Z', '+00:00'))
                if ref_dt.tzinfo is None:
                    ref_dt = ref_dt.replace(tzinfo=timezone.utc)
                days = (now - ref_dt).days
            except ValueError:
                days = 0
        else:
            days = 0

        ref_count = entry.get('referenceCount', 1)
        marker = detect_marker(entry)

        score_result = compute_importance(ref_count, days, marker)
        importance = score_result['importance']
        total_importance += importance

        scored_entry = {
            'id': entry.get('id'),
            'summary': entry.get('summary', ''),
            'importance': importance,
            'days_since_ref': days,
            'ref_count': ref_count,
            'unique_sessions': entry.get('uniqueSessionCount', 1),
            'uniqueDayCount': entry.get('uniqueDayCount', 0),
            'marker': marker,
        }

        if check_archival_flag:
            archival = check_archival(entry, importance, days)
            scored_entry['archival'] = archival
            if archival['eligible']:
                archival_candidates.append(scored_entry)

        scored.append(scored_entry)

    # Sort by importance descending
    scored.sort(key=lambda x: x['importance'], reverse=True)

    result = {
        'ok': True,
        'index_path': index_path,
        'active_entries': active_count,
        'avg_importance': round(total_importance / active_count, 4) if active_count > 0 else 0,
        'scored': scored,
    }

    if check_archival_flag:
        result['archival_candidates'] = archival_candidates
        result['archival_count'] = len(archival_candidates)

    return result


def score_candidates(candidates_path: str, write_back: bool = False) -> dict:
    """
    Score entries in a candidates JSON file (strict-mode flow).

    Invoked by the recurring prompt's Step 1.6 when `strictMode == true`.
    business-employee default path calls this; personal-assistant parity
    flow skips it (parity consolidates first, then scores the index for
    archival at Step 3).

    Reads an array of candidate dicts, computes importance for each using
    the same formula as score_index, writes the `importance` field in-place,
    preserves all other fields. Recency fallback order: lastReferenced →
    created → 0 days. Optionally writes the enriched array back to the
    source file for downstream gate.py consumption.
    """
    path = Path(candidates_path)
    if not path.exists():
        return {'ok': False, 'error': f'Candidates file not found: {candidates_path}'}

    try:
        with open(path, 'r') as f:
            candidates = json.loads(f.read())
    except json.JSONDecodeError as e:
        return {'ok': False, 'error': f'Malformed candidates JSON: {e}'}

    if not isinstance(candidates, list):
        return {'ok': False, 'error': 'Candidates file must contain a JSON array'}

    now = datetime.now(tz=timezone.utc)
    enriched_count = 0

    for cand in candidates:
        # Recency fallback order: lastReferenced → created → 0 (truly new)
        # Matched-index entries always have lastReferenced. Brand-new
        # candidates with only `created` (e.g. extracted this cycle) should
        # decay from their created date, not be treated as perfectly fresh.
        days = None
        for field in ('lastReferenced', 'created'):
            raw = cand.get(field, '')
            if not raw:
                continue
            try:
                ref_dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
                if ref_dt.tzinfo is None:
                    ref_dt = ref_dt.replace(tzinfo=timezone.utc)
                days = (now - ref_dt).days
                break
            except ValueError:
                continue
        if days is None:
            days = 0

        ref_count = cand.get('referenceCount', 1)
        marker = cand.get('marker') or detect_marker(cand)

        score_result = compute_importance(ref_count, days, marker)
        cand['importance'] = score_result['importance']
        enriched_count += 1

    if write_back:
        with open(path, 'w') as f:
            f.write(json.dumps(candidates, indent=2, ensure_ascii=False))

    return {
        'ok': True,
        'candidates_path': candidates_path,
        'enriched_count': enriched_count,
        'write_back': write_back,
        'candidates': candidates,
    }


def main():
    parser = argparse.ArgumentParser(description='Reflections: Importance Scoring')
    parser.add_argument('--index', help='Path to reflections-metadata.json — score all entries')
    parser.add_argument('--check-archival', action='store_true',
                        help='Also check archival eligibility')
    parser.add_argument('--single', action='store_true',
                        help='Score a single entry from parameters')
    parser.add_argument('--ref-count', type=int, default=1, help='Reference count')
    parser.add_argument('--unique', type=int, default=1, help='Unique session count')
    parser.add_argument('--days', type=int, default=0, help='Days since last reference')
    parser.add_argument('--marker', choices=['HIGH', 'PERMANENT', 'PIN'],
                        help='Entry marker')
    parser.add_argument('--candidates',
                        help='Path to candidates JSON file — score in-place. Invoked by the strict-mode flow (business-employee default); skipped by the parity flow (personal-assistant default).')
    parser.add_argument('--write-back', action='store_true',
                        help='(with --candidates) Write enriched JSON back to the same file. The recurring prompt uses this to commit importance scores before gate.py applies quality gates.')
    args = parser.parse_args()

    if args.single:
        result = compute_importance(args.ref_count, args.days, args.marker)
        result['unique_sessions'] = args.unique
        print(json.dumps({'ok': True, **result}, indent=2))
        return 0

    if args.candidates:
        result = score_candidates(args.candidates, args.write_back)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get('ok') else 2

    if args.index:
        result = score_index(args.index, args.check_archival)
        print(json.dumps(result, indent=2))
        return 0

    parser.error('One of --index, --candidates, or --single is required')


if __name__ == '__main__':
    sys.exit(main())
