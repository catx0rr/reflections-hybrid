#!/usr/bin/env python3
"""
reflections: append_memory_log — structured telemetry writer

Appends one structured JSONL event to the unified memory telemetry log.
Owns JSON serialization, timestamp generation, daily sharding, and
error-safe append behavior.

Output target:
    TELEMETRY_ROOT/memory-log-YYYY-MM-DD.jsonl

Telemetry root resolution order:
    1. --telemetry-dir CLI flag
    2. REFLECTIONS_TELEMETRY_ROOT env var
    3. MEMORY_TELEMETRY_ROOT env var
    4. ~/.openclaw/telemetry fallback

Usage:
    python3 append_memory_log.py \\
      --status ok \\
      --event run_completed \\
      --profile personal-assistant \\
      --mode scheduled \\
      --details-json '{"logs_scanned": 7, "entries_qualified": 3}'

    python3 append_memory_log.py \\
      --status error \\
      --event run_failed \\
      --error "Config file missing"
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _timestamp_pair() -> dict:
    """Generate the timestamp pair: local-aware and UTC."""
    now_local = datetime.now().astimezone()
    now_utc = now_local.astimezone(timezone.utc)

    return {
        'timestamp': now_local.isoformat(),
        'timestamp_utc': now_utc.isoformat().replace('+00:00', 'Z'),
    }


def _generate_run_id(ts: str) -> str:
    """Generate a short deterministic run ID from the timestamp."""
    ts_clean = ts.replace(':', '-').replace('+', '-').replace('.', '-')[:19]
    suffix = hashlib.sha256(ts.encode()).hexdigest()[:6]
    return f'refl-{ts_clean}-{suffix}'


def resolve_telemetry_root(cli_dir: str = None) -> str:
    """Resolve telemetry root by precedence ladder."""
    if cli_dir:
        return cli_dir

    for env_var in ('REFLECTIONS_TELEMETRY_ROOT', 'MEMORY_TELEMETRY_ROOT'):
        val = os.environ.get(env_var)
        if val:
            return val

    return os.path.expanduser('~/.openclaw/telemetry')


def append_event(telemetry_root: str, event: dict) -> str:
    """Append a single JSON event to the daily-sharded JSONL file."""
    root = Path(telemetry_root)
    root.mkdir(parents=True, exist_ok=True)

    today = datetime.now().astimezone().strftime('%Y-%m-%d')
    target = root / f'memory-log-{today}.jsonl'

    line = json.dumps(event, ensure_ascii=False, separators=(',', ':'))

    with open(target, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

    return str(target)


def main():
    parser = argparse.ArgumentParser(
        description='Reflections: Unified Memory Telemetry Writer'
    )
    parser.add_argument(
        '--telemetry-dir',
        help='Explicit telemetry root directory (overrides env vars)'
    )
    parser.add_argument(
        '--status', required=True,
        choices=['ok', 'error', 'skipped'],
        help='Run outcome status'
    )
    parser.add_argument(
        '--event', default='run_completed',
        help='Event type (default: run_completed)'
    )
    parser.add_argument(
        '--agent-id', default='main',
        help='Agent identifier (default: main)'
    )
    parser.add_argument(
        '--profile', default='unknown',
        help='Active profile name'
    )
    parser.add_argument(
        '--mode', default='scheduled',
        help='Run mode: scheduled, manual, first-reflection'
    )
    parser.add_argument(
        '--details-json',
        help='JSON string with run details (logs_scanned, entries_qualified, etc.)'
    )
    parser.add_argument(
        '--error',
        help='Error message (used when --status error)'
    )

    args = parser.parse_args()

    # Resolve telemetry root
    telemetry_root = resolve_telemetry_root(args.telemetry_dir)

    # Build event
    ts = _timestamp_pair()
    run_id = _generate_run_id(ts['timestamp'])

    record = {
        'timestamp': ts['timestamp'],
        'timestamp_utc': ts['timestamp_utc'],
        'domain': 'memory',
        'component': 'reflections.consolidator',
        'event': args.event,
        'run_id': run_id,
        'status': args.status,
        'agent': args.agent_id,
        'profile': args.profile,
        'mode': args.mode,
    }

    # Parse details
    if args.details_json:
        try:
            record['details'] = json.loads(args.details_json)
        except json.JSONDecodeError as e:
            record['details'] = {'_parse_error': str(e), '_raw': args.details_json}

    # Error field
    if args.error:
        record['error'] = args.error

    # Append
    try:
        target_file = append_event(telemetry_root, record)
        record['_target_file'] = target_file
    except OSError as e:
        record['_write_error'] = str(e)
        record['_target_file'] = None

    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
