#!/usr/bin/env python3
"""
reflections: scan — find unconsolidated daily logs

Scans memory/ for YYYY-MM-DD.md files, checks for <!-- consolidated --> marker,
returns list of files needing processing.

Usage:
    python3 scan.py --log-dir memory --days 7
    python3 scan.py --log-dir memory --days 3 --verbose
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def scan_daily_logs(log_dir: str, days: int = 7, verbose: bool = False) -> dict:
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=days)

    pattern = os.path.join(log_dir, '????-??-??.md')
    all_files = sorted(glob.glob(pattern), reverse=True)

    unconsolidated = []
    consolidated = []
    skipped = []

    for filepath in all_files:
        basename = os.path.basename(filepath).replace('.md', '')
        try:
            file_date = datetime.strptime(basename, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            skipped.append({'file': filepath, 'reason': 'invalid date format'})
            continue

        if file_date < cutoff:
            if verbose:
                skipped.append({'file': filepath, 'reason': f'older than {days} days'})
            continue

        # Check for consolidated marker
        try:
            with open(filepath, 'r') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            skipped.append({'file': filepath, 'reason': 'unreadable'})
            continue

        is_consolidated = '<!-- consolidated -->' in content
        line_count = len(content.strip().split('\n'))
        size_bytes = len(content.encode('utf-8'))

        entry = {
            'file': filepath,
            'date': basename,
            'lines': line_count,
            'size_bytes': size_bytes,
            'age_days': (now - file_date).days,
        }

        if is_consolidated:
            consolidated.append(entry)
        else:
            unconsolidated.append(entry)

    return {
        'ok': True,
        'scan_time': now.isoformat(),
        'log_dir': log_dir,
        'days_scanned': days,
        'total_found': len(unconsolidated) + len(consolidated),
        'unconsolidated': unconsolidated,
        'unconsolidated_count': len(unconsolidated),
        'consolidated': consolidated if verbose else [],
        'consolidated_count': len(consolidated),
        'skipped': skipped if verbose else [],
        'has_work': len(unconsolidated) > 0,
    }


def main():
    parser = argparse.ArgumentParser(description='Reflections: Daily Log Scanner')
    parser.add_argument('--log-dir', default='memory', help='Directory containing daily logs')
    parser.add_argument('--days', type=int, default=7, help='Scan window in days')
    parser.add_argument('--verbose', action='store_true', help='Include consolidated and skipped files')
    args = parser.parse_args()

    result = scan_daily_logs(args.log_dir, args.days, args.verbose)
    print(json.dumps(result, indent=2))

    # Exit 0 for all valid states (idle or active).
    # Idle is signaled by has_work: false in the JSON output.
    # Exit non-zero only for real errors (missing dir, read failure, etc.).
    return 0


if __name__ == '__main__':
    sys.exit(main())
