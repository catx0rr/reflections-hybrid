#!/usr/bin/env python3
"""
reflections: index — metadata CRUD engine

Manages runtime/reflections-metadata.json: add entries, update session tracking,
assign IDs, mark archived, update stats.

Usage:
    python3 index.py --index runtime/reflections-metadata.json --next-id
    python3 index.py --index runtime/reflections-metadata.json --add entry.json
    python3 index.py --index runtime/reflections-metadata.json --update-session mem_042 --source memory/2026-04-05.md
    python3 index.py --index runtime/reflections-metadata.json --reinforce mem_042 --from merge.json
    python3 index.py --index runtime/reflections-metadata.json --compress-trend trendkey --from trend.json
    python3 index.py --index runtime/reflections-metadata.json --archive mem_015 --summary "Old API endpoint"
    python3 index.py --index runtime/reflections-metadata.json --update-stats stats.json
    python3 index.py --index runtime/reflections-metadata.json --info
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_index(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {
            'version': '1.0.0',
            'lastDream': None,
            'entries': [],
            'stats': {
                'totalEntries': 0,
                'avgImportance': 0,
                'lastPruned': None,
                'healthScore': 0,
                'healthMetrics': {},
                'insights': [],
                'healthHistory': [],
                'gateStats': {},
            },
        }
    with open(p, 'r') as f:
        return json.loads(f.read())


def save_index(index: dict, path: str, backup: bool = True):
    p = Path(path)
    if backup and p.exists():
        shutil.copy2(p, str(p) + '.bak')
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w') as f:
        f.write(json.dumps(index, indent=2, ensure_ascii=False) + '\n')


def get_next_id(index: dict) -> str:
    """Get the next available mem_NNN ID."""
    max_num = 0
    for entry in index.get('entries', []):
        eid = entry.get('id', '')
        if eid.startswith('mem_'):
            try:
                num = int(eid.replace('mem_', ''))
                max_num = max(max_num, num)
            except ValueError:
                pass
    return f'mem_{max_num + 1:03d}'


def _extract_day_from_source(source: str) -> str:
    """Extract YYYY-MM-DD from a source path like memory/2026-04-10.md."""
    import re
    match = re.search(r'(\d{4}-\d{2}-\d{2})', source)
    return match.group(1) if match else ''


def add_entry(index: dict, entry: dict) -> dict:
    """Add a new entry to the index."""
    now = datetime.now(tz=timezone.utc).isoformat()

    if 'id' not in entry:
        entry['id'] = get_next_id(index)
    if 'created' not in entry:
        entry['created'] = now[:10]
    if 'lastReferenced' not in entry:
        entry['lastReferenced'] = now[:10]
    if 'referenceCount' not in entry:
        entry['referenceCount'] = 1
    if 'uniqueSessionCount' not in entry:
        entry['uniqueSessionCount'] = 1
    if 'sessionSources' not in entry:
        entry['sessionSources'] = [entry.get('source', '')]
    if 'uniqueDayCount' not in entry:
        # Derive day from source path if possible (e.g. memory/2026-04-10.md)
        source = entry.get('source', '')
        day = _extract_day_from_source(source)
        entry['uniqueDayCount'] = 1 if day else 0
        entry['uniqueDaySources'] = [day] if day else []
    if 'importance' not in entry:
        entry['importance'] = 0.5
    if 'tags' not in entry:
        entry['tags'] = []
    if 'related' not in entry:
        entry['related'] = []
    if 'archived' not in entry:
        entry['archived'] = False

    index['entries'].append(entry)
    return entry


def update_session(index: dict, entry_id: str, source_log: str) -> dict:
    """Update referenceCount, uniqueSessionCount, and uniqueDayCount for an entry."""
    for entry in index['entries']:
        if entry.get('id') != entry_id:
            continue

        entry['referenceCount'] = entry.get('referenceCount', 0) + 1
        entry['lastReferenced'] = datetime.now(tz=timezone.utc).isoformat()[:10]

        sources = entry.get('sessionSources', [])
        if source_log not in sources:
            entry['uniqueSessionCount'] = entry.get('uniqueSessionCount', 0) + 1
            sources.append(source_log)
            # Keep last 30 sources
            if len(sources) > 30:
                sources = sources[-30:]
            entry['sessionSources'] = sources

        # Track unique days
        day = _extract_day_from_source(source_log)
        if day:
            day_sources = entry.get('uniqueDaySources', [])
            if day not in day_sources:
                entry['uniqueDayCount'] = entry.get('uniqueDayCount', 0) + 1
                day_sources.append(day)
                if len(day_sources) > 30:
                    day_sources = day_sources[-30:]
                entry['uniqueDaySources'] = day_sources

        return {
            'ok': True,
            'id': entry_id,
            'referenceCount': entry['referenceCount'],
            'uniqueSessionCount': entry['uniqueSessionCount'],
            'uniqueDayCount': entry.get('uniqueDayCount', 0),
            'lastReferenced': entry['lastReferenced'],
        }

    return {'ok': False, 'error': f'Entry {entry_id} not found'}


def reinforce_entry(index: dict, entry_id: str, merge_payload: dict) -> dict:
    """
    v1.3.0 merge: reinforce an existing durable node with a new observation.

    Does NOT create a new entry. Updates the target entry in place:
      - bumps referenceCount
      - updates lastReferenced (ISO date)
      - adds source log to sessionSources + uniqueSessionCount if new
      - adds day to uniqueDaySources + uniqueDayCount if new
      - appends the reinforcing source's mergeKey to a `mergeKeys` list (dedup)
      - appends `reinforcedBy` audit trail with timestamp + mergeReason

    Payload shape (merge.json):
      {
        "source": "memory/2026-04-18.md",
        "mergeKey": "...",
        "mergeReason": "merge-into:mem_042",
        "summary": "optional: updated/refined summary text to replace existing"
      }
    """
    for entry in index['entries']:
        if entry.get('id') != entry_id:
            continue

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        source = merge_payload.get('source', '')

        # Delegate counter math to update_session so semantics stay consistent
        update_session(index, entry_id, source)

        # Track merge provenance
        merge_keys = entry.get('mergeKeys', [])
        mk = merge_payload.get('mergeKey')
        if mk and mk not in merge_keys:
            merge_keys.append(mk)
            entry['mergeKeys'] = merge_keys

        reinforced = entry.get('reinforcedBy', [])
        reinforced.append({
            'source': source,
            'mergeKey': mk,
            'mergeReason': merge_payload.get('mergeReason'),
            'timestamp': now_iso,
        })
        # Cap audit trail at last 50 events
        if len(reinforced) > 50:
            reinforced = reinforced[-50:]
        entry['reinforcedBy'] = reinforced

        # Optional summary refresh
        new_summary = merge_payload.get('summary')
        if new_summary:
            entry['summary'] = new_summary

        return {
            'ok': True,
            'id': entry_id,
            'action': 'reinforced',
            'referenceCount': entry.get('referenceCount'),
            'uniqueSessionCount': entry.get('uniqueSessionCount'),
            'uniqueDayCount': entry.get('uniqueDayCount'),
            'mergeKeysCount': len(entry.get('mergeKeys', [])),
        }

    return {'ok': False, 'error': f'Entry {entry_id} not found'}


def compress_trend(index: dict, trend_key: str, trend_payload: dict) -> dict:
    """
    v1.3.0 compress: upsert a trend node (memoryType=trend) and reinforce.

    Looks up an existing entry with `memoryType == "trend"` AND matching
    `trendKey`. If found, reinforces it (mirrors `reinforce_entry` semantics
    but tailored for trend nodes — also bumps trendSupportCount and
    trendLastUpdated). If not found, creates a new trend entry.

    Payload shape (trend.json):
      {
        "source": "memory/2026-04-18.md",
        "trendKey": "dev-server-noon-restart",
        "summary": "Dev server restarts around noon each day — no clear trigger",
        "target_section": "...",   # optional; TRENDS.md section
        "compressionReason": "reinforce-trend:mem_099" or "new-trend:<key>",
        "tags": ["operations", "restart"]
      }

    Returns {ok, id, action: "new"|"reinforced", trendSupportCount, ...}.
    """
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    source = trend_payload.get('source', '')

    # Find existing trend node
    target = None
    for entry in index.get('entries', []):
        if entry.get('archived'):
            continue
        if entry.get('memoryType') == 'trend' and entry.get('trendKey') == trend_key:
            target = entry
            break

    if target is not None:
        # Reinforce: bump structural counters, then bump trend-specific counters
        update_session(index, target['id'], source)
        target['trendSupportCount'] = int(target.get('trendSupportCount', 0)) + 1
        target['trendLastUpdated'] = now_iso[:10]
        # Track source list (distinct from sessionSources which may cap)
        tsources = target.get('trendSources', [])
        if source and source not in tsources:
            tsources.append(source)
            if len(tsources) > 200:
                tsources = tsources[-200:]
            target['trendSources'] = tsources
        target['sourceCount'] = len(target.get('trendSources', []))
        # Refresh summary if caller provided a better one
        new_summary = trend_payload.get('summary')
        if new_summary:
            target['summary'] = new_summary

        return {
            'ok': True,
            'id': target['id'],
            'action': 'reinforced',
            'trendKey': trend_key,
            'trendSupportCount': target['trendSupportCount'],
            'trendLastUpdated': target['trendLastUpdated'],
            'sourceCount': target.get('sourceCount', 0),
            'referenceCount': target.get('referenceCount'),
            'uniqueDayCount': target.get('uniqueDayCount'),
        }

    # Create new trend node
    new_id = get_next_id(index)
    new_entry = {
        'id': new_id,
        'summary': trend_payload.get('summary', ''),
        'source': source,
        'target': 'TRENDS.md',
        'memoryType': 'trend',
        'durabilityClass': 'semi-durable',
        'route': 'compress',
        'destination': 'TREND',
        'trendKey': trend_key,
        'trendFirstObserved': now_iso[:10],
        'trendLastUpdated': now_iso[:10],
        'trendSupportCount': 1,
        'trendSources': [source] if source else [],
        'sourceCount': 1 if source else 0,
        'compressionReason': trend_payload.get('compressionReason'),
        'tags': trend_payload.get('tags', []),
        'related': [],
        'archived': False,
    }
    # Let add_entry fill structural defaults (referenceCount, uniqueDayCount, etc.)
    add_entry(index, new_entry)

    return {
        'ok': True,
        'id': new_id,
        'action': 'new',
        'trendKey': trend_key,
        'trendSupportCount': 1,
        'trendLastUpdated': now_iso[:10],
        'sourceCount': new_entry.get('sourceCount', 0),
    }


def archive_entry(index: dict, entry_id: str, summary: str) -> dict:
    """Mark an entry as archived."""
    for entry in index['entries']:
        if entry.get('id') != entry_id:
            continue

        entry['archived'] = True
        entry['archived_at'] = datetime.now(tz=timezone.utc).isoformat()[:10]
        if summary:
            entry['summary'] = summary

        return {
            'ok': True,
            'id': entry_id,
            'archived': True,
            'archived_at': entry['archived_at'],
            'summary': entry.get('summary'),
        }

    return {'ok': False, 'error': f'Entry {entry_id} not found'}


def update_stats(index: dict, stats_data: dict) -> dict:
    """Update stats section with health/gate data."""
    now = datetime.now(tz=timezone.utc).isoformat()

    index['lastDream'] = now

    stats = index.get('stats', {})

    # Active entries
    active = [e for e in index['entries'] if not e.get('archived')]
    stats['totalEntries'] = len(active)

    if active:
        total_imp = sum(e.get('importance', 0) for e in active)
        stats['avgImportance'] = round(total_imp / len(active), 4)
    else:
        stats['avgImportance'] = 0

    # Merge provided stats
    for key in ['healthScore', 'healthMetrics', 'insights', 'gateStats']:
        if key in stats_data:
            stats[key] = stats_data[key]

    # Append health history
    if 'healthScore' in stats_data:
        history = stats.get('healthHistory', [])
        history.append({
            'date': now[:10],
            'score': stats_data['healthScore'],
        })
        # Cap at 90
        if len(history) > 90:
            history = history[-90:]
        stats['healthHistory'] = history

    index['stats'] = stats
    return stats


def get_info(index: dict) -> dict:
    """Get summary information about the index."""
    entries = index.get('entries', [])
    active = [e for e in entries if not e.get('archived')]
    archived = [e for e in entries if e.get('archived')]

    return {
        'ok': True,
        'version': index.get('version'),
        'lastDream': index.get('lastDream'),
        'total_entries': len(entries),
        'active': len(active),
        'archived': len(archived),
        'next_id': get_next_id(index),
        'stats': index.get('stats', {}),
    }


def main():
    parser = argparse.ArgumentParser(description='Reflections: Index Manager')
    parser.add_argument('--index', required=True, help='Path to reflections-metadata.json')
    parser.add_argument('--next-id', action='store_true', help='Print the next available mem_NNN')
    parser.add_argument('--add', metavar='ENTRY_JSON', help='Add entry from JSON file')
    parser.add_argument('--update-session', metavar='ENTRY_ID', help='Update session tracking')
    parser.add_argument('--source', help='Source log file (for --update-session)')
    parser.add_argument('--reinforce', metavar='ENTRY_ID',
                        help='(v1.3.0 merge) reinforce an existing entry from a JSON payload passed via --from')
    parser.add_argument('--compress-trend', metavar='TREND_KEY',
                        help='(v1.3.0 compress) upsert a trend node for this trendKey from a JSON payload passed via --from')
    parser.add_argument('--from', dest='from_path', metavar='PAYLOAD_JSON',
                        help='Payload JSON for --reinforce or --compress-trend')
    parser.add_argument('--archive', metavar='ENTRY_ID', help='Archive an entry')
    parser.add_argument('--summary', help='Archive summary text')
    parser.add_argument('--update-stats', metavar='STATS_JSON', help='Update stats from JSON file')
    parser.add_argument('--info', action='store_true', help='Show index summary')
    parser.add_argument('--no-backup', action='store_true', help='Skip backup before write')
    args = parser.parse_args()

    index = load_index(args.index)
    do_save = False

    if args.next_id:
        print(json.dumps({'ok': True, 'next_id': get_next_id(index)}, indent=2))
        return 0

    if args.info:
        print(json.dumps(get_info(index), indent=2))
        return 0

    if args.add:
        with open(args.add, 'r') as f:
            entry_data = json.loads(f.read())
        result = add_entry(index, entry_data)
        print(json.dumps({'ok': True, **result}, indent=2, ensure_ascii=False))
        do_save = True

    if args.update_session:
        if not args.source:
            parser.error('--source is required with --update-session')
        result = update_session(index, args.update_session, args.source)
        print(json.dumps(result, indent=2))
        do_save = True

    if args.reinforce:
        if not args.from_path:
            parser.error('--from PAYLOAD_JSON is required with --reinforce')
        with open(args.from_path, 'r', encoding='utf-8') as f:
            payload = json.loads(f.read())
        result = reinforce_entry(index, args.reinforce, payload)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        do_save = True

    if args.compress_trend:
        if not args.from_path:
            parser.error('--from PAYLOAD_JSON is required with --compress-trend')
        with open(args.from_path, 'r', encoding='utf-8') as f:
            payload = json.loads(f.read())
        result = compress_trend(index, args.compress_trend, payload)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        do_save = True

    if args.archive:
        result = archive_entry(index, args.archive, args.summary or '')
        print(json.dumps(result, indent=2))
        do_save = True

    if args.update_stats:
        with open(args.update_stats, 'r') as f:
            stats_data = json.loads(f.read())
        result = update_stats(index, stats_data)
        print(json.dumps({'ok': True, **result}, indent=2))
        do_save = True

    if do_save:
        save_index(index, args.index, backup=not args.no_backup)

    return 0


if __name__ == '__main__':
    sys.exit(main())
