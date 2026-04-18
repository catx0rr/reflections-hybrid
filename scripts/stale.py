#!/usr/bin/env python3
"""
reflections: stale — stale thread detection

Scans RTMEMORY.md Open Threads for items not referenced in N+ days.
Cross-references with reflections-metadata.json and daily logs for last-mention dates.

Usage:
    python3 stale.py --memory-file RTMEMORY.md --index runtime/reflections-metadata.json --threshold 14
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def extract_open_threads(memory_path: str) -> list:
    """Extract uncompleted items from Open Threads section."""
    if not Path(memory_path).exists():
        return []

    with open(memory_path, 'r') as f:
        content = f.read()

    threads = []
    in_section = False
    lines = content.split('\n')

    for i, line in enumerate(lines):
        if line.startswith('## ') and 'Open Threads' in line:
            in_section = True
            continue
        elif line.startswith('## ') and in_section:
            break

        if not in_section:
            continue

        # Match uncompleted checkbox items
        match = re.match(r'^- \[\s*\]\s*(.+)', line.strip())
        if match:
            text = match.group(1).strip()

            # Extract mem_ID if present
            mem_match = re.search(r'<!--\s*(mem_\d+)\s*-->', text)
            mem_id = mem_match.group(1) if mem_match else None
            clean_text = re.sub(r'<!--.*?-->', '', text).strip()

            # Extract inline date if present (e.g., "2026-03-28 —")
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
            inline_date = date_match.group(1) if date_match else None

            threads.append({
                'text': clean_text,
                'mem_id': mem_id,
                'inline_date': inline_date,
                'line_number': i + 1,
            })

    return threads


def find_last_mention(thread_text: str, log_dir: str, index_path: str) -> str:
    """Find the most recent date this thread was mentioned."""
    last_date = None

    # Check reflections-metadata.json for lastReferenced
    if Path(index_path).exists():
        with open(index_path, 'r') as f:
            try:
                index = json.loads(f.read())
                for entry in index.get('entries', []):
                    # Match by text similarity (keyword overlap)
                    thread_keywords = set(re.findall(r'[a-z]{3,}', thread_text.lower()))
                    entry_keywords = set(re.findall(r'[a-z]{3,}', entry.get('summary', '').lower()))
                    if len(thread_keywords & entry_keywords) >= 2:
                        ref_date = entry.get('lastReferenced', '')
                        if ref_date and (last_date is None or ref_date > last_date):
                            last_date = ref_date
            except json.JSONDecodeError:
                pass

    # Scan daily logs (newest first) for keyword mentions
    pattern = os.path.join(log_dir, '????-??-??.md')
    log_files = sorted(glob.glob(pattern), reverse=True)
    thread_keywords = set(re.findall(r'[a-z]{4,}', thread_text.lower()))

    for log_file in log_files[:30]:  # cap at 30 files
        basename = os.path.basename(log_file).replace('.md', '')
        try:
            with open(log_file, 'r') as f:
                content = f.read().lower()
            content_keywords = set(re.findall(r'[a-z]{4,}', content))
            if len(thread_keywords & content_keywords) >= 2:
                if last_date is None or basename > last_date:
                    last_date = basename
                break  # newest match is enough
        except (IOError, UnicodeDecodeError):
            continue

    return last_date


def detect_stale(memory_path: str, index_path: str, log_dir: str,
                 threshold_days: int = 14, top_n: int = 5) -> dict:
    """Detect stale Open Threads items."""
    now = datetime.now(tz=timezone.utc)
    threads = extract_open_threads(memory_path)

    stale = []
    active = []

    for thread in threads:
        # Try inline date first
        last_date_str = thread['inline_date']

        # If no inline date, search logs and index
        if not last_date_str:
            last_date_str = find_last_mention(thread['text'], log_dir, index_path)

        # Compute staleness
        if last_date_str:
            try:
                last_dt = datetime.strptime(last_date_str[:10], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                days_stale = (now - last_dt).days
            except ValueError:
                days_stale = None
        else:
            days_stale = None  # unknown

        thread_result = {
            'text': thread['text'],
            'mem_id': thread['mem_id'],
            'last_mentioned': last_date_str,
            'days_stale': days_stale,
            'line_number': thread['line_number'],
        }

        if days_stale is not None and days_stale > threshold_days:
            stale.append(thread_result)
        elif days_stale is None:
            # Unknown staleness — flag as potentially stale
            thread_result['days_stale'] = '?'
            stale.append(thread_result)
        else:
            active.append(thread_result)

    # Sort stale by days (most stale first), unknowns at end
    stale.sort(key=lambda x: x['days_stale'] if isinstance(x['days_stale'], int) else 9999, reverse=True)

    return {
        'ok': True,
        'threshold_days': threshold_days,
        'total_open_threads': len(threads),
        'stale_count': len(stale),
        'active_count': len(active),
        'stale': stale[:top_n],
        'active': active,
    }


def main():
    parser = argparse.ArgumentParser(description='Reflections: Stale Thread Detection')
    parser.add_argument('--memory-file', default='RTMEMORY.md', help='Path to RTMEMORY.md')
    parser.add_argument('--index', default='runtime/reflections-metadata.json', help='Path to reflections-metadata.json')
    parser.add_argument('--log-dir', default='memory', help='Directory containing daily logs')
    parser.add_argument('--threshold', type=int, default=14, help='Days to consider stale')
    parser.add_argument('--top', type=int, default=5, help='Max stale items to return')
    args = parser.parse_args()

    result = detect_stale(args.memory_file, args.index, args.log_dir,
                          args.threshold, args.top)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0


if __name__ == '__main__':
    sys.exit(main())
