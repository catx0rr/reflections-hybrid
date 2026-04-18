#!/usr/bin/env python3
"""
reflections: deferred — persisted deferred-candidate store (strict-mode only)

Owns read/write for `runtime/reflections-deferred.jsonl`. Each line is one
deferred-candidate event: candidate_hash, summary, source, fail_reasons,
modes_evaluated, referenceCount, existingId, plus timestamp triple.

This is strict-mode only. When the default parity flow is active, this script
is not invoked. The file does not exist on fresh installs.

Usage:
    python3 deferred.py --append <json-file>             Append records from a JSON array
    python3 deferred.py --is-deferred <identity>         Exit 0 if identity in store (matches existingId/fingerprint/candidate_hash)
    python3 deferred.py --load-for-source <log-path>     Print records matching source (JSON array)
    python3 deferred.py --all                            Print all records (JSON array)
    python3 deferred.py --hash <source> <summary>        Print stable v1.1.2-compat candidate_hash
    python3 deferred.py --fingerprint <source> <summary> [--target-section S]
                                                         Print rewording-stable fingerprint
    python3 deferred.py --annotate <candidates.json> [--write-back]
                                                         Annotate candidates with deferred_status (deterministic suppression)
    python3 deferred.py --file <path>                    Override default store path

Default store path resolution:
    1. --file CLI flag
    2. ./runtime/reflections-deferred.jsonl (relative to current working directory)

Append semantics: atomic append per line. Concurrent cron fires are safe because
each record is a newline-terminated JSON object — the OS append guarantees no
interleaving at the line level.

Candidate identity (layered, strongest-first):
    1. existingId           — matched-index entries (most stable, survives any rewording)
    2. fingerprint          — sha256(source + "::" + target_section + "::" + normalized(summary))[:12]
                              where normalized = lowercase, whitespace-collapsed,
                              punctuation-stripped, stopword-filtered
    3. candidate_hash       — sha256(source + "::" + summary)[:12]  (v1.1.2 compat;
                              preserved on new records for rollback/audit only)

`--is-deferred` matches on existingId first, then fingerprint, then candidate_hash.
Light wording edits to the same semantic candidate from the same source produce
the same fingerprint and are treated as already deferred.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_STORE = 'runtime/reflections-deferred.jsonl'

# Short, conservative English stopword list. Intentionally small — we want
# to neutralize trivial filler ("the", "a", "to") without stripping semantic
# content. Not a full NLP tokenizer — a deterministic fingerprint function.
_STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'of', 'to', 'in', 'on', 'at',
    'for', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'that', 'this', 'these', 'those', 'it', 'its',
}

_PUNCT_RE = re.compile(r'[^\w\s]')
_WS_RE = re.compile(r'\s+')


def normalize_text(text: str) -> str:
    """
    Deterministic token-bag normalizer for fingerprint stability.

    Steps (in order):
    1. Lowercase
    2. Strip punctuation (Unicode-aware \\w keeps letters/digits/underscore)
    3. Collapse whitespace
    4. Drop a small set of English stopwords
    5. Sort remaining tokens (order-independent — light rewording survives)
    6. Deduplicate adjacent repeats
    7. Re-join with single spaces

    This is a token-bag fingerprint: same content words in any order produce
    the same hash. Scoping to (source + target_section) naturally bounds the
    risk of two genuinely-distinct candidates sharing a token bag — at the
    daily-log level the collision surface is tiny. A false-positive collision
    just means one deferred record absorbs a near-duplicate, which is exactly
    what we want for light-rewording suppression.
    """
    if not text:
        return ''
    s = text.lower()
    s = _PUNCT_RE.sub(' ', s)
    s = _WS_RE.sub(' ', s).strip()
    tokens = [t for t in s.split(' ') if t and t not in _STOPWORDS]
    tokens.sort()
    deduped = []
    for tok in tokens:
        if not deduped or deduped[-1] != tok:
            deduped.append(tok)
    return ' '.join(deduped)


def _timestamp_pair() -> dict:
    """Generate timestamp pair (matches append_memory_log.py convention)."""
    now_local = datetime.now().astimezone()
    now_utc = now_local.astimezone(timezone.utc)
    return {
        'timestamp': now_local.isoformat(),
        'timestamp_utc': now_utc.isoformat().replace('+00:00', 'Z'),
    }


def compute_candidate_hash(source: str, summary: str) -> str:
    """
    v1.1.2-compat exact-string hash. Kept on new records for rollback/audit.

    Use compute_fingerprint() for the rewording-stable identity.
    """
    key = f'{source}::{summary}'
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]


def compute_fingerprint(source: str, summary: str, target_section: str = '') -> str:
    """
    Rewording-stable 12-char identity.

    hash = sha256(source + "::" + normalized(target_section) + "::" + normalized(summary))[:12]

    Stability properties:
    - Same source + same target_section + semantically-same summary → same hash
      (survives case, punctuation, extra whitespace, a small stopword set)
    - Different source or different target_section → different hash
    - Heavy rewording (new content words, reordering material facts) → different hash
      (intentional — fingerprint is for near-duplicate suppression, not semantic clustering)
    """
    key = f'{source}::{normalize_text(target_section)}::{normalize_text(summary)}'
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]


def append_records(store_path: str, records: list) -> dict:
    """Append a list of candidate records to the store (one JSON line per record)."""
    path = Path(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    ts = _timestamp_pair()
    appended = 0

    with open(path, 'a', encoding='utf-8') as f:
        for rec in records:
            if not isinstance(rec, dict):
                continue
            # Fill required fields if missing
            summary = rec.get('summary', '')
            source = rec.get('source', '')
            target_section = rec.get('target_section', '')
            if not rec.get('candidate_hash'):
                rec['candidate_hash'] = compute_candidate_hash(source, summary)
            if not rec.get('fingerprint'):
                rec['fingerprint'] = compute_fingerprint(source, summary, target_section)
            rec.setdefault('timestamp', ts['timestamp'])
            rec.setdefault('timestamp_utc', ts['timestamp_utc'])
            rec.setdefault('fail_reasons', [])
            rec.setdefault('modes_evaluated', [])
            rec.setdefault('referenceCount', 1)
            rec.setdefault('existingId', None)
            rec.setdefault('target_section', target_section)

            line = json.dumps(rec, ensure_ascii=False, separators=(',', ':'))
            f.write(line + '\n')
            appended += 1

    return {
        'ok': True,
        'store_path': str(path),
        'appended': appended,
    }


def load_all(store_path: str) -> list:
    """Load every record from the store. Returns empty list if file missing."""
    path = Path(store_path)
    if not path.exists():
        return []

    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip malformed lines; append-only store shouldn't normally have them
                continue
    return records


def is_deferred(store_path: str, identity: str) -> bool:
    """
    Check if any record in the store matches the given identity.

    Matches against existingId, fingerprint, or legacy candidate_hash — the
    caller doesn't need to know which identity layer applies.
    """
    records = load_all(store_path)
    for r in records:
        if r.get('existingId') and r['existingId'] == identity:
            return True
        if r.get('fingerprint') == identity:
            return True
        if r.get('candidate_hash') == identity:
            return True
    return False


def lookup_identity(store_path: str, source: str, summary: str,
                    target_section: str = '', existing_id: str = None) -> dict:
    """
    Resolve a candidate's best-available deferred identity and report whether it's in the store.

    Layering (strongest identity first):
    1. existingId match (matched-index entries)
    2. fingerprint match (rewording-stable, same source+section+normalized summary)
    3. candidate_hash match (exact string, v1.1.2 compat)

    Returns {persisted: bool, matched_by: str|None, fingerprint, candidate_hash, existingId}.
    """
    fp = compute_fingerprint(source, summary, target_section)
    ch = compute_candidate_hash(source, summary)
    records = load_all(store_path)

    matched_by = None
    if existing_id:
        for r in records:
            if r.get('existingId') and r['existingId'] == existing_id:
                matched_by = 'existingId'
                break

    if matched_by is None:
        for r in records:
            if r.get('fingerprint') == fp:
                matched_by = 'fingerprint'
                break

    if matched_by is None:
        for r in records:
            if r.get('candidate_hash') == ch:
                matched_by = 'candidate_hash'
                break

    return {
        'persisted': matched_by is not None,
        'matched_by': matched_by,
        'fingerprint': fp,
        'candidate_hash': ch,
        'existingId': existing_id,
    }


def annotate_candidates(store_path: str, candidates_path: str,
                        write_back: bool = False) -> dict:
    """
    Deterministic suppression helper.

    Read a candidates JSON array, compute each candidate's identity layers,
    cross-reference the deferred store, and annotate each record with:
      - fingerprint
      - candidate_hash
      - deferred_status: "persisted" | "fresh"
      - deferred_matched_by: "existingId" | "fingerprint" | "candidate_hash" | null

    This removes prompt-follow dependency for suppression: downstream steps
    (gate.py or the Step 2 promotion decision) can filter by deferred_status
    without consulting the LLM.
    """
    path = Path(candidates_path)
    if not path.exists():
        return {'ok': False, 'error': f'Candidates file not found: {candidates_path}'}

    try:
        with open(path, 'r', encoding='utf-8') as f:
            candidates = json.loads(f.read())
    except json.JSONDecodeError as e:
        return {'ok': False, 'error': f'Malformed candidates JSON: {e}'}

    if not isinstance(candidates, list):
        return {'ok': False, 'error': 'Candidates file must contain a JSON array'}

    records = load_all(store_path)
    fp_set = {r.get('fingerprint') for r in records if r.get('fingerprint')}
    hash_set = {r.get('candidate_hash') for r in records if r.get('candidate_hash')}
    id_set = {r.get('existingId') for r in records if r.get('existingId')}

    persisted_count = 0
    fresh_count = 0

    for cand in candidates:
        source = cand.get('source', '')
        summary = cand.get('summary', '')
        target_section = cand.get('target_section', '')
        existing_id = cand.get('existingId')

        fp = compute_fingerprint(source, summary, target_section)
        ch = compute_candidate_hash(source, summary)
        cand['fingerprint'] = fp
        cand['candidate_hash'] = ch

        matched_by = None
        if existing_id and existing_id in id_set:
            matched_by = 'existingId'
        elif fp in fp_set:
            matched_by = 'fingerprint'
        elif ch in hash_set:
            matched_by = 'candidate_hash'

        cand['deferred_matched_by'] = matched_by
        cand['deferred_status'] = 'persisted' if matched_by else 'fresh'
        if matched_by:
            persisted_count += 1
        else:
            fresh_count += 1

    if write_back:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(candidates, indent=2, ensure_ascii=False))

    return {
        'ok': True,
        'store_path': store_path,
        'candidates_path': candidates_path,
        'total': len(candidates),
        'persisted': persisted_count,
        'fresh': fresh_count,
        'write_back': write_back,
    }


def load_for_source(store_path: str, source: str) -> list:
    """Return all records whose `source` field matches the given log path."""
    records = load_all(store_path)
    return [r for r in records if r.get('source') == source]


def main():
    parser = argparse.ArgumentParser(
        description='Reflections: Deferred-candidate store (strict-mode only)'
    )
    parser.add_argument(
        '--file',
        help=f'Override default store path (default: {DEFAULT_STORE})'
    )

    parser.add_argument(
        '--target-section',
        default='',
        help='(with --fingerprint) target section for fingerprint scoping'
    )
    parser.add_argument(
        '--write-back',
        action='store_true',
        help='(with --annotate) write annotated candidates back to source file'
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--append', metavar='JSON_FILE',
        help='Append records from a JSON array file'
    )
    group.add_argument(
        '--is-deferred', metavar='IDENTITY',
        help='Exit 0 if identity (existingId/fingerprint/candidate_hash) in store, 1 otherwise'
    )
    group.add_argument(
        '--load-for-source', metavar='SOURCE_LOG',
        help='Print all records matching source daily log (JSON array)'
    )
    group.add_argument(
        '--all', action='store_true',
        help='Print all records (JSON array)'
    )
    group.add_argument(
        '--hash', nargs=2, metavar=('SOURCE', 'SUMMARY'),
        help='Compute v1.1.2-compat candidate hash for source + summary'
    )
    group.add_argument(
        '--fingerprint', nargs=2, metavar=('SOURCE', 'SUMMARY'),
        help='Compute rewording-stable fingerprint for source + summary (+ optional --target-section)'
    )
    group.add_argument(
        '--annotate', metavar='CANDIDATES_JSON',
        help='Annotate candidates JSON with deferred_status (deterministic suppression)'
    )

    args = parser.parse_args()

    store_path = args.file or DEFAULT_STORE

    if args.append:
        try:
            with open(args.append, 'r', encoding='utf-8') as f:
                records = json.loads(f.read())
        except FileNotFoundError:
            print(json.dumps({'ok': False, 'error': f'Input file not found: {args.append}'}))
            return 2
        except json.JSONDecodeError as e:
            print(json.dumps({'ok': False, 'error': f'Malformed input JSON: {e}'}))
            return 2

        if not isinstance(records, list):
            print(json.dumps({'ok': False, 'error': 'Input must be a JSON array'}))
            return 2

        result = append_records(store_path, records)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.is_deferred:
        if is_deferred(store_path, args.is_deferred):
            return 0
        return 1

    if args.load_for_source:
        records = load_for_source(store_path, args.load_for_source)
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return 0

    if args.all:
        records = load_all(store_path)
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return 0

    if args.hash:
        source, summary = args.hash
        h = compute_candidate_hash(source, summary)
        print(json.dumps({'ok': True, 'candidate_hash': h}, indent=2))
        return 0

    if args.fingerprint:
        source, summary = args.fingerprint
        fp = compute_fingerprint(source, summary, args.target_section)
        print(json.dumps({
            'ok': True,
            'fingerprint': fp,
            'source': source,
            'target_section': args.target_section,
        }, indent=2, ensure_ascii=False))
        return 0

    if args.annotate:
        result = annotate_candidates(store_path, args.annotate, args.write_back)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get('ok') else 2

    return 0


if __name__ == '__main__':
    sys.exit(main())
