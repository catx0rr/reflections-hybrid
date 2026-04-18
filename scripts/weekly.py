#!/usr/bin/env python3
"""
reflections: weekly — compute deterministic weekly-report stats

Consumes runtime/reflections-metadata.json and produces the weekly-summary
numbers that Step 4.4 of the runtime prompt needs. Keeps all weekly math
out of the prompt.

Outputs a single JSON object:
  {
    "ok": true,
    "window_days": 7,
    "date_range": "YYYY-MM-DD to YYYY-MM-DD",
    "weekly_snapshot_available": true|false,
    "total_after": int,
    "total_before_week": int,
    "percent_growth": "+N.N%",
    "weekly_new": int,
    "weekly_updated": int,
    "weekly_archived": int,
    "biggest_memories": [
      {"id": "mem_NNN", "summary": "...", "importance": 0.xx}
    ]
  }

If no healthHistory snapshot ≥ 7 days old exists, weekly_snapshot_available
is false and total_before_week is null. The prompt skips the weekly block
in that case.

Usage:
    python3 weekly.py --index runtime/reflections-metadata.json
    python3 weekly.py --index runtime/reflections-metadata.json --days 7 --top 3
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _parse_iso_date(value: str) -> datetime:
    """Parse ISO date/datetime; return tz-aware UTC datetime or None."""
    if not value:
        return None
    try:
        s = value.replace('Z', '+00:00') if value.endswith('Z') else value
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def compute_weekly(index_path: str, days: int = 7, top: int = 3) -> dict:
    path = Path(index_path)
    if not path.exists():
        return {'ok': False, 'error': f'Index not found: {index_path}'}

    with open(path, 'r', encoding='utf-8') as f:
        index = json.loads(f.read())

    entries = index.get('entries', [])
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=days)

    active = [e for e in entries if not e.get('archived')]
    total_after = len(active)

    # weekly_new: active entries created within window
    # weekly_updated: active entries lastReferenced within window AND created before window
    #   (an entry created this week is counted as "new", not "updated")
    weekly_new_entries = []
    weekly_updated_entries = []
    for e in active:
        created = _parse_iso_date(e.get('created', ''))
        last_ref = _parse_iso_date(e.get('lastReferenced', ''))
        is_new = created is not None and created >= cutoff
        is_touched = last_ref is not None and last_ref >= cutoff

        if is_new:
            weekly_new_entries.append(e)
        elif is_touched:
            weekly_updated_entries.append(e)

    # weekly_archived: archived entries whose archived_at is within window
    # Entries archived before archived_at was tracked (legacy) are counted only
    # if they have no archived_at AND any timestamp field places them in window —
    # otherwise they don't count this cycle.
    weekly_archived = 0
    for e in entries:
        if not e.get('archived'):
            continue
        archived_at = _parse_iso_date(e.get('archived_at', ''))
        if archived_at is not None and archived_at >= cutoff:
            weekly_archived += 1

    # total_before_week: from healthHistory snapshot closest to (now - days).
    # healthHistory[i] = {"date": "YYYY-MM-DD", "score": int}. It does not store
    # totalEntries directly, so we derive: total_before_week = total_after
    # - weekly_new + weekly_archived (conservation of entries over the window,
    # assuming no unarchived entries moved in/out for other reasons). If
    # healthHistory has no entry ≥ days old, mark snapshot unavailable so the
    # prompt skips the weekly block.
    history = index.get('stats', {}).get('healthHistory', [])
    snapshot_available = False
    for snap in history:
        snap_date = _parse_iso_date(snap.get('date', ''))
        if snap_date is not None and snap_date <= cutoff:
            snapshot_available = True
            break

    if snapshot_available:
        total_before_week = total_after - len(weekly_new_entries) + weekly_archived
        delta = total_after - total_before_week
        if total_before_week > 0:
            pct = (delta / total_before_week) * 100
            percent_growth = f'{"+" if pct >= 0 else ""}{pct:.1f}%'
        else:
            percent_growth = '+∞%' if delta > 0 else '0.0%'
    else:
        total_before_week = None
        percent_growth = None

    # biggest_memories: top N by importance from the weekly_new ∪ weekly_updated set
    weekly_touched = weekly_new_entries + weekly_updated_entries
    weekly_touched.sort(key=lambda e: e.get('importance', 0) or 0, reverse=True)
    biggest = [
        {
            'id': e.get('id'),
            'summary': e.get('summary', '')[:120],
            'importance': e.get('importance', 0),
        }
        for e in weekly_touched[:top]
    ]

    return {
        'ok': True,
        'window_days': days,
        'date_range': f'{cutoff.date().isoformat()} to {now.date().isoformat()}',
        'weekly_snapshot_available': snapshot_available,
        'total_after': total_after,
        'total_before_week': total_before_week,
        'percent_growth': percent_growth,
        'weekly_new': len(weekly_new_entries),
        'weekly_updated': len(weekly_updated_entries),
        'weekly_archived': weekly_archived,
        'biggest_memories': biggest,
    }


def main():
    parser = argparse.ArgumentParser(description='Reflections: Weekly report stats')
    parser.add_argument('--index', default='runtime/reflections-metadata.json',
                        help='Path to reflections-metadata.json')
    parser.add_argument('--days', type=int, default=7,
                        help='Window size in days (default: 7)')
    parser.add_argument('--top', type=int, default=3,
                        help='How many biggest-memories to return (default: 3)')
    args = parser.parse_args()

    result = compute_weekly(args.index, days=args.days, top=args.top)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('ok') else 2


if __name__ == '__main__':
    sys.exit(main())
