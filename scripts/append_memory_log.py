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
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


# ──────────────────────── token_usage resolution (v1.5.0) ────────────────────────
#
# "Scripts own math" rule: the runtime prompt never computes ceil(chars/4). It
# passes either exact token counts from host metadata, or char counts, or neither.
# This helper resolves the three-way ladder deterministically. Shared in spirit
# with scripts/report.py; keep both in sync.
#
# Ladder:
#   1. --token-source exact AND (--token-total OR --token-prompt) present → exact
#   2. --prompt-chars OR --completion-chars present → approximate (ceil(n/4))
#   3. otherwise → unavailable (nulls)

def resolve_token_usage(args) -> dict:
    """Resolve token_usage per v1.5.0 ladder. Never fabricates 'exact'."""
    src = getattr(args, 'token_source', None) or 'unavailable'
    pt = getattr(args, 'token_prompt', None)
    ct = getattr(args, 'token_completion', None)
    tt = getattr(args, 'token_total', None)
    pc = getattr(args, 'prompt_chars', None)
    cc = getattr(args, 'completion_chars', None)

    if src == 'exact' and (tt is not None or pt is not None or ct is not None):
        # Verbatim pass-through of host-provided metadata
        return {
            'prompt_tokens': pt,
            'completion_tokens': ct,
            'total_tokens': tt,
            'source': 'exact',
        }

    if pc is not None or cc is not None:
        # Compute approximation inside the script — runtime never does this
        est_pt = math.ceil(pc / 4) if pc is not None else None
        est_ct = math.ceil(cc / 4) if cc is not None else None
        est_tt = ((est_pt or 0) + (est_ct or 0)) if (est_pt is not None or est_ct is not None) else None
        return {
            'prompt_tokens': est_pt,
            'completion_tokens': est_ct,
            'total_tokens': est_tt,
            'source': 'approximate',
        }

    # Neither exact nor char counts — unavailable. Envelope always carries the block.
    return {
        'prompt_tokens': None,
        'completion_tokens': None,
        'total_tokens': None,
        'source': 'unavailable',
    }


def _add_token_args(parser) -> None:
    """Register the 6 token CLI args. Shared signature with report.py."""
    parser.add_argument('--token-prompt', type=int, default=None,
                        help='Exact prompt tokens from host metadata')
    parser.add_argument('--token-completion', type=int, default=None,
                        help='Exact completion tokens from host metadata')
    parser.add_argument('--token-total', type=int, default=None,
                        help='Exact total tokens from host metadata')
    parser.add_argument('--token-source', choices=['exact', 'approximate', 'unavailable'],
                        default='unavailable',
                        help='Source of token_usage values (default: unavailable)')
    parser.add_argument('--prompt-chars', type=int, default=None,
                        help='Char count of prompt input (fallback for approximation)')
    parser.add_argument('--completion-chars', type=int, default=None,
                        help='Char count of model output (fallback for approximation)')


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

    # v1.5.0: token-usage CLI args (shared with report.py)
    _add_token_args(parser)

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
        # v1.5.0: token_usage envelope — always present (nulls when unavailable)
        'token_usage': resolve_token_usage(args),
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
