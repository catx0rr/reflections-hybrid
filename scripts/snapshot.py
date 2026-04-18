#!/usr/bin/env python3
"""
reflections: snapshot — count memory state metrics

Takes a snapshot of RTMEMORY.md metrics for before/after comparison.
Can compute deltas between two snapshots.

Usage:
    python3 snapshot.py --memory-file RTMEMORY.md --save-as before
    python3 snapshot.py --memory-file RTMEMORY.md --save-as after
    python3 snapshot.py --delta before.json after.json
"""

import argparse
import glob
import json
import os
import re
import sys
import tempfile
from pathlib import Path


def count_section_items(content: str, section_header: str) -> int:
    """Count bullet items in a specific section."""
    lines = content.split('\n')
    in_section = False
    count = 0

    for line in lines:
        if line.startswith('## ') and section_header.lower() in line.lower():
            in_section = True
            continue
        elif line.startswith('## ') and in_section:
            break

        if in_section and re.match(r'^- ', line.strip()):
            count += 1

    return count


def take_snapshot(memory_file: str, procedures_file: str = None,
                  episodes_dir: str = None, consolidation_log_file: str = None,
                  index_file: str = None) -> dict:
    """Take a full snapshot of memory state."""

    snapshot = {
        'memory_lines': 0,
        'memory_sections': 0,
        'total_entries': 0,
        'decisions': 0,
        'lessons': 0,
        'open_threads': 0,
        'open_threads_completed': 0,
        'initiatives': 0,
        'relationships': 0,
        'procedures_lines': 0,
        'procedures_entries': 0,
        'episodes_count': 0,
        'consolidation_count': 0,
    }

    # RTMEMORY.md
    if os.path.exists(memory_file):
        with open(memory_file, 'r') as f:
            content = f.read()

        lines = content.strip().split('\n')
        snapshot['memory_lines'] = len(lines)
        snapshot['memory_sections'] = sum(1 for l in lines if l.startswith('## '))
        snapshot['total_entries'] = sum(1 for l in lines if re.match(r'^- ', l.strip()))

        snapshot['decisions'] = count_section_items(content, 'Key Decisions and Rationale')
        snapshot['lessons'] = count_section_items(content, 'Lessons and Patterns')
        snapshot['initiatives'] = count_section_items(content, 'Active Initiatives')
        snapshot['relationships'] = count_section_items(content, 'People and Relationships')

        # Open threads — count completed vs open
        in_threads = False
        for line in lines:
            if '## ' in line and 'Open Threads' in line:
                in_threads = True
                continue
            elif line.startswith('## ') and in_threads:
                break
            if in_threads:
                if re.match(r'^- \[x\]', line.strip(), re.IGNORECASE):
                    snapshot['open_threads_completed'] += 1
                elif re.match(r'^- \[', line.strip()):
                    snapshot['open_threads'] += 1

    # procedures.md
    proc_path = procedures_file or 'PROCEDURES.md'
    if os.path.exists(proc_path):
        with open(proc_path, 'r') as f:
            proc_content = f.read()
        proc_lines = proc_content.strip().split('\n')
        snapshot['procedures_lines'] = len(proc_lines)
        snapshot['procedures_entries'] = sum(1 for l in proc_lines if re.match(r'^- ', l.strip()))

    # episodes — canonical: ROOT_WORKSPACE/episodes/
    ep_dir = episodes_dir or 'episodes'
    if os.path.exists(ep_dir):
        snapshot['episodes_count'] = len(glob.glob(os.path.join(ep_dir, '*.md')))

    # consolidation count
    log_path = consolidation_log_file or 'memory/.reflections-log.md'
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            log_content = f.read()
        snapshot['consolidation_count'] = len(re.findall(r'^## .+Consolidation', log_content, re.MULTILINE))

    # index entry count
    idx_path = index_file or 'runtime/reflections-metadata.json'
    if os.path.exists(idx_path):
        try:
            with open(idx_path, 'r') as f:
                idx = json.loads(f.read())
            entries = idx.get('entries', [])
            snapshot['index_entries'] = len(entries)
            snapshot['index_archived'] = sum(1 for e in entries if e.get('archived'))
            snapshot['index_active'] = snapshot['index_entries'] - snapshot['index_archived']
        except (json.JSONDecodeError, KeyError):
            pass

    return snapshot


def compute_delta(before: dict, after: dict) -> dict:
    """Compute differences between two snapshots."""
    delta = {}
    for key in after:
        if key in before:
            b = before[key]
            a = after[key]
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                diff = a - b
                pct = ((a - b) / b * 100) if b > 0 else (100.0 if a > 0 else 0.0)
                delta[key] = {
                    'before': b,
                    'after': a,
                    'diff': diff,
                    'pct_change': round(pct, 1),
                }
    return delta


def main():
    parser = argparse.ArgumentParser(description='Reflections: Memory Snapshot')
    parser.add_argument('--memory-file', default='RTMEMORY.md', help='Path to RTMEMORY.md')
    parser.add_argument('--procedures-file', help='Path to procedures.md')
    parser.add_argument('--episodes-dir', help='Path to episodes directory')
    parser.add_argument('--consolidation-log', help='Path to .reflections-log.md')
    parser.add_argument('--index-file', help='Path to reflections-metadata.json')
    parser.add_argument('--save-as', metavar='LABEL',
                        help='Save snapshot to a temp file: {tmpdir}/reflections-snapshot-{LABEL}.json')
    parser.add_argument('--delta', nargs=2, metavar=('BEFORE', 'AFTER'),
                        help='Compute delta between two saved snapshots')
    args = parser.parse_args()

    if args.delta:
        before_path, after_path = args.delta
        with open(before_path, 'r') as f:
            before = json.loads(f.read())
        with open(after_path, 'r') as f:
            after = json.loads(f.read())
        delta = compute_delta(before, after)
        print(json.dumps({'ok': True, **delta}, indent=2))
        return 0

    snapshot = take_snapshot(
        args.memory_file,
        args.procedures_file,
        args.episodes_dir,
        args.consolidation_log,
        args.index_file,
    )

    if args.save_as:
        save_path = os.path.join(tempfile.gettempdir(), f'reflections-snapshot-{args.save_as}.json')
        with open(save_path, 'w') as f:
            f.write(json.dumps(snapshot, indent=2))
        snapshot['_saved_to'] = save_path

    print(json.dumps({'ok': True, **snapshot}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
