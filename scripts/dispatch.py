#!/usr/bin/env python3
"""
reflections: dispatch — mode dispatch engine

Reads reflections.json, compares lastRun timestamps against current time,
returns which reflection modes are due. Also handles lastRun updates after a cycle.

Usage:
    python3 dispatch.py --config ~/.openclaw/reflections/reflections.json
    python3 dispatch.py --config ~/.openclaw/reflections/reflections.json --update-lastrun core,rem
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Mode cadence intervals in hours
MODE_INTERVALS = {
    'rem': 6,
    'deep': 12,
    'core': 24,
}


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        print(json.dumps({'ok': False, 'error': f'Config not found: {config_path}'}))
        sys.exit(2)
    with open(path, 'r') as f:
        return json.loads(f.read())


def get_due_modes(conf: dict) -> dict:
    now = datetime.now(tz=timezone.utc)
    active = conf.get('activeModes', [])
    modes = conf.get('modes', {})
    last_run = conf.get('lastRun', {})

    due = []
    not_due = []

    for mode_name in ['rem', 'deep', 'core']:  # strictest first
        if mode_name not in active:
            continue
        mode_conf = modes.get(mode_name, {})
        if not mode_conf.get('enabled', False):
            continue

        interval_hours = MODE_INTERVALS.get(mode_name, 24)
        last = last_run.get(mode_name)

        if last is None:
            elapsed_hours = float('inf')
            elapsed_str = 'never run'
        else:
            last_dt = datetime.fromisoformat(last.replace('Z', '+00:00'))
            elapsed = now - last_dt
            elapsed_hours = elapsed.total_seconds() / 3600
            elapsed_str = f'{elapsed_hours:.1f}h ago'

        if elapsed_hours >= interval_hours:
            due.append({
                'mode': mode_name,
                'interval_hours': interval_hours,
                'elapsed': elapsed_str,
                'gate': {
                    'minScore': mode_conf.get('minScore'),
                    'minRecallCount': mode_conf.get('minRecallCount'),
                    'minUnique': mode_conf.get('minUnique'),
                },
            })
        else:
            remaining = interval_hours - elapsed_hours
            not_due.append({
                'mode': mode_name,
                'next_due_in': f'{remaining:.1f}h',
            })

    return {
        'ok': True,
        'timestamp': now.isoformat(),
        'due_modes': due,
        'not_due': not_due,
        'active_modes': active,
        'notification_level': conf.get('notificationLevel', 'summary'),
    }


def update_lastrun(config_path: str, modes_to_update: list):
    conf = load_config(config_path)
    now = datetime.now(tz=timezone.utc).isoformat()

    # Backup
    backup = Path(config_path + '.bak')
    shutil.copy2(config_path, backup)

    if 'lastRun' not in conf:
        conf['lastRun'] = {}

    for mode in modes_to_update:
        conf['lastRun'][mode] = now

    with open(config_path, 'w') as f:
        f.write(json.dumps(conf, indent=2, ensure_ascii=False) + '\n')

    return {
        'ok': True,
        'action': 'lastRun_updated',
        'modes': modes_to_update,
        'timestamp': now,
        'backup': str(backup),
    }


def main():
    parser = argparse.ArgumentParser(description='Reflections: Mode Dispatch')
    parser.add_argument('--config', required=True, help='Path to reflections.json')
    parser.add_argument('--update-lastrun', metavar='MODES',
                        help='Comma-separated modes to update lastRun for (e.g., core,rem)')
    args = parser.parse_args()

    if args.update_lastrun:
        modes = [m.strip() for m in args.update_lastrun.split(',')]
        result = update_lastrun(args.config, modes)
        print(json.dumps(result, indent=2))
        return 0

    conf = load_config(args.config)
    result = get_due_modes(conf)
    print(json.dumps(result, indent=2))

    # Exit 0 for all valid states (idle or active).
    # Idle is signaled by due_modes: [] in the JSON output.
    # Exit non-zero only for real errors (missing config, malformed JSON, etc.).
    return 0


if __name__ == '__main__':
    sys.exit(main())
