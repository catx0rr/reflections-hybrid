#!/usr/bin/env python3
"""
reflections: report — deterministic reporting/state helper

Consolidates the numbers the runtime prompt needs for skip messages and cycle
notifications. Reads the index, config, and (optionally) snapshots + cycle
counters, and emits a single JSON blob. No prose, no invention.

Usage (skip-with-recall context — no cycle ran):
    python3 report.py --index runtime/reflections-metadata.json \\
                      --config $CONFIG_PATH \\
                      --kind skip

Usage (end-of-cycle notification):
    python3 report.py --index runtime/reflections-metadata.json \\
                      --config $CONFIG_PATH \\
                      --kind cycle \\
                      --before $TMPDIR/reflections-snapshot-before.json \\
                      --after $TMPDIR/reflections-snapshot-after.json \\
                      --modes-fired core,rem \\
                      --logs-count 3 \\
                      --new 2 --updated 1 --archived 0 \\
                      [--gate-qualified 6 --gate-deferred 8] \\
                      [--durable-promoted 2 --durable-merged 1 \\
                       --durable-compressed 1 --durable-deferred 1 --durable-rejected 1] \\
                      [--weekly]

Output shape (cycle, with --weekly when triggered):
    {
      "ok": true,
      "kind": "cycle",
      "reflection_count": 42,
      "streak": 7,
      "modes_fired": "core+rem",
      "active_modes": ["core", "rem", "deep"],
      "total_before": 142,
      "total_after": 145,
      "entries_delta": 3,
      "percent_growth": "+2.1%",
      "new": 2, "updated": 1, "archived": 0,
      "logs_count": 3,
      "health_score": 82, "rating": "excellent",
      "next_due": {"mode": "rem", "in": "2.5h"} | null,
      "gate": {"qualified": 6, "deferred": 8},
      "durable": {"promoted": 2, "merged": 1, "compressed": 1, "deferred": 1, "rejected": 1},
      "milestones": ["🏅 One week streak!"],
      "weekly": { ... from weekly.py when --weekly }
    }

For --kind skip, the same fields are present but cycle-specific ones
(modes_fired, new/updated/archived, total_before/delta/percent_growth,
gate, durable, weekly) are null or absent. `active_modes` is always
populated from config so Step 0-B can render the skip message
deterministically.

Fields are omitted (null) when the inputs needed to compute them aren't
supplied. The runtime prompt skips any empty section instead of inventing
placeholders.

Leans on: weekly.py (imported), dispatch.py (for next_due via config state).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

# Reuse weekly.py's logic
from weekly import compute_weekly  # type: ignore


# ────────────────────── index + config loading ──────────────────────

def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, 'r', encoding='utf-8') as f:
        return json.loads(f.read())


def _parse_iso(ts: str):
    if not ts:
        return None
    try:
        s = ts.replace('Z', '+00:00') if ts.endswith('Z') else ts
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


# ────────────────────── reflection count + streak ──────────────────────

def compute_reflection_count(index: dict) -> int:
    """Number of non-skip cycles completed — len(healthHistory)."""
    return len(index.get('stats', {}).get('healthHistory', []))


def compute_streak(index: dict) -> int:
    """
    Count of distinct consecutive calendar days with at least one cycle,
    counting backward from the most recent cycle. A gap of ≥2 days breaks
    the streak.

    Example: healthHistory has dates 2026-04-10, 2026-04-11, 2026-04-13
    → streak = 1 (2026-04-13 is alone; the gap to 2026-04-11 is 2 days).

    Example: dates 2026-04-10, 2026-04-11, 2026-04-12 → streak = 3.
    """
    history = index.get('stats', {}).get('healthHistory', [])
    if not history:
        return 0
    dates = sorted({snap.get('date') for snap in history if snap.get('date')}, reverse=True)
    if not dates:
        return 0
    streak = 1
    for i in range(len(dates) - 1):
        a = datetime.fromisoformat(dates[i])
        b = datetime.fromisoformat(dates[i + 1])
        if (a - b).days == 1:
            streak += 1
        else:
            break
    return streak


# ────────────────────── growth math ──────────────────────

def compute_growth(before: dict, after: dict, index: dict) -> dict:
    """Derive total_before/after, delta, percent_growth from snapshots + index."""
    if not before or not after:
        # No cycle context — just return current total
        total_after = len([e for e in index.get('entries', []) if not e.get('archived')])
        return {
            'total_before': None,
            'total_after': total_after,
            'entries_delta': None,
            'percent_growth': None,
        }

    total_before = int(before.get('index_entries', before.get('total_entries', 0)) or 0)
    total_after = int(after.get('index_entries', after.get('total_entries', 0)) or 0)
    if total_after == 0:
        # Fall back to live index count if snapshot didn't record it
        total_after = len([e for e in index.get('entries', []) if not e.get('archived')])
    delta = total_after - total_before
    if total_before > 0:
        pct = (delta / total_before) * 100
        percent_growth = f'{"+" if pct >= 0 else ""}{pct:.1f}%'
    else:
        percent_growth = '+∞%' if delta > 0 else '0.0%'
    return {
        'total_before': total_before,
        'total_after': total_after,
        'entries_delta': delta,
        'percent_growth': percent_growth,
    }


# ────────────────────── health score ──────────────────────

def last_health(index: dict) -> dict:
    """Return the most recent health snapshot (score + rating)."""
    stats = index.get('stats', {})
    score = stats.get('healthScore')
    history = stats.get('healthHistory', [])
    if score is None and history:
        score = history[-1].get('score')
    if score is None:
        return {'health_score': None, 'rating': None}
    score = int(score)
    if score >= 80:
        rating = 'excellent'
    elif score >= 60:
        rating = 'good'
    elif score >= 40:
        rating = 'fair'
    elif score >= 20:
        rating = 'poor'
    else:
        rating = 'critical'
    return {'health_score': score, 'rating': rating}


# ────────────────────── next due ──────────────────────

MODE_INTERVALS_H = {'rem': 6, 'deep': 12, 'core': 24}


def compute_next_due(config: dict) -> dict:
    """Look at config lastRun timestamps and return the soonest-due mode."""
    active = config.get('activeModes', [])
    modes = config.get('modes', {})
    last_run = config.get('lastRun', {})
    now = datetime.now(tz=timezone.utc)

    best = None  # (remaining_hours, mode_name)
    for mode_name in ('rem', 'deep', 'core'):
        if mode_name not in active:
            continue
        if not modes.get(mode_name, {}).get('enabled', False):
            continue
        interval = MODE_INTERVALS_H.get(mode_name, 24)
        last = last_run.get(mode_name)
        last_dt = _parse_iso(last) if last else None
        if last_dt is None:
            remaining = 0.0  # never run → due now
        else:
            elapsed = (now - last_dt).total_seconds() / 3600
            remaining = max(0.0, interval - elapsed)
        if best is None or remaining < best[0]:
            best = (remaining, mode_name)

    if best is None:
        return None
    remaining_h, mode_name = best
    if remaining_h <= 0:
        return {'mode': mode_name, 'in': 'now'}
    if remaining_h < 1:
        return {'mode': mode_name, 'in': f'{int(remaining_h * 60)}m'}
    return {'mode': mode_name, 'in': f'{remaining_h:.1f}h'}


# ────────────────────── milestones ──────────────────────

def compute_milestones(reflection_count: int, streak: int, total_after: int,
                       total_before) -> list:
    """Return any milestone banners to append to the notification."""
    out = []
    next_count = reflection_count  # reflection_count already reflects this cycle
    if next_count == 1:
        out.append('🎉 First reflection complete!')
    if next_count == 7 or streak == 7:
        out.append('🏅 One week streak!')
    if next_count == 30 or streak == 30:
        out.append('🏆 One month streak!')
    # Entries crossed a round milestone this cycle
    if total_before is not None and total_after is not None:
        for landmark in (100, 200, 500, 1000):
            if total_before < landmark <= total_after:
                out.append('📊 Memory milestone!')
                break
    return out


# ────────────────────── main composition ──────────────────────

def build_report(args) -> dict:
    index = _load_json(args.index)
    config = _load_json(args.config) if args.config else {}

    reflection_count = compute_reflection_count(index)
    streak = compute_streak(index)
    health = last_health(index)
    next_due = compute_next_due(config) if config else None

    # Growth (optional — only when snapshots given)
    before = _load_json(args.before) if args.before else {}
    after = _load_json(args.after) if args.after else {}
    growth = compute_growth(before, after, index)

    modes_fired = args.modes_fired.replace(',', '+') if args.modes_fired else None

    milestones = compute_milestones(
        reflection_count, streak,
        growth.get('total_after'),
        growth.get('total_before'),
    )

    # active_modes from config — pertains to both skip and cycle reports
    # so the prompt can always source this field from the report JSON.
    active_modes = list(config.get('activeModes', [])) if config else []

    payload = {
        'ok': True,
        'kind': args.kind,
        'reflection_count': reflection_count,
        'streak': streak,
        'modes_fired': modes_fired,
        'active_modes': active_modes,
        **growth,
        'new': args.new,
        'updated': args.updated,
        'archived': args.archived,
        'logs_count': args.logs_count,
        'health_score': health['health_score'],
        'rating': health['rating'],
        'next_due': next_due,
        'milestones': milestones,
    }

    # Gate + durability counters — only populate if caller supplied them
    gate = {}
    if args.gate_qualified is not None:
        gate['qualified'] = args.gate_qualified
    if args.gate_deferred is not None:
        gate['deferred'] = args.gate_deferred
    if gate:
        payload['gate'] = gate

    durable = {}
    for name in ('promoted', 'merged', 'compressed', 'deferred', 'rejected'):
        v = getattr(args, f'durable_{name}')
        if v is not None:
            durable[name] = v
    if durable:
        payload['durable'] = durable

    # Weekly block — compute only if flagged
    if args.weekly:
        weekly = compute_weekly(args.index, days=7, top=3)
        payload['weekly'] = weekly

    return payload


def main():
    parser = argparse.ArgumentParser(
        description='Reflections: deterministic reporting helper'
    )
    parser.add_argument('--index', default='runtime/reflections-metadata.json',
                        help='Path to reflections-metadata.json')
    parser.add_argument('--config', default='',
                        help='Path to reflections.json (for next-due)')
    parser.add_argument('--kind', choices=['skip', 'cycle'], default='cycle',
                        help='Report shape (skip uses a subset)')
    parser.add_argument('--before', default='',
                        help='Path to before-snapshot JSON')
    parser.add_argument('--after', default='',
                        help='Path to after-snapshot JSON')
    parser.add_argument('--modes-fired', default='',
                        help='Comma-separated modes that ran this cycle')
    parser.add_argument('--new', type=int, default=None)
    parser.add_argument('--updated', type=int, default=None)
    parser.add_argument('--archived', type=int, default=None)
    parser.add_argument('--logs-count', type=int, default=None,
                        help='Count of daily logs scanned/processed this cycle (from scan.py output)')
    parser.add_argument('--gate-qualified', type=int, default=None)
    parser.add_argument('--gate-deferred', type=int, default=None)
    parser.add_argument('--durable-promoted', type=int, default=None)
    parser.add_argument('--durable-merged', type=int, default=None)
    parser.add_argument('--durable-compressed', type=int, default=None)
    parser.add_argument('--durable-deferred', type=int, default=None)
    parser.add_argument('--durable-rejected', type=int, default=None)
    parser.add_argument('--weekly', action='store_true',
                        help='Include weekly summary block (triggers weekly.py)')

    args = parser.parse_args()
    result = build_report(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get('ok') else 2


if __name__ == '__main__':
    sys.exit(main())
