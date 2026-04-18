#!/usr/bin/env python3
"""
reflections: health — 5-metric health score engine

Computes the health score using exact formulas:
  health = (freshness*0.25 + coverage*0.25 + coherence*0.2 + efficiency*0.15 + reachability*0.15) * 100

Includes actual BFS-based reachability computation (not LLM estimation).

Usage:
    python3 health.py --index runtime/reflections-metadata.json --memory-file RTMEMORY.md
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

CATEGORIES = [
    'Scope Notes', 'Active Initiatives',
    'Business Context and Metrics',
    'People and Relationships',
    'Strategy and Priorities', 'Key Decisions and Rationale',
    'Lessons and Patterns', 'Episodes and Timelines',
    'Environment Notes', 'Open Threads',
]

MAX_EFFICIENT_LINES = 500


def compute_freshness(entries: list, days: int = 30) -> float:
    """Fraction of active entries referenced in last N days."""
    if not entries:
        return 0.0

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=days)
    active = [e for e in entries if not e.get('archived')]

    if not active:
        return 0.0

    recent = 0
    for entry in active:
        last_ref = entry.get('lastReferenced', '')
        if last_ref:
            try:
                ref_dt = datetime.fromisoformat(last_ref.replace('Z', '+00:00'))
                if ref_dt.tzinfo is None:
                    ref_dt = ref_dt.replace(tzinfo=timezone.utc)
                if ref_dt >= cutoff:
                    recent += 1
            except ValueError:
                pass

    return recent / len(active)


def compute_coverage(memory_content: str, days: int = 14) -> float:
    """Fraction of knowledge categories with recent updates."""
    if not memory_content:
        return 0.0

    # Check which sections have content (non-empty, non-comment)
    sections_with_content = 0
    lines = memory_content.split('\n')
    current_section = None
    section_has_content = False

    for line in lines:
        if line.startswith('## '):
            if current_section and section_has_content:
                sections_with_content += 1
            # Check if this section matches any category
            current_section = None
            for cat in CATEGORIES:
                if cat.lower() in line.lower():
                    current_section = cat
                    section_has_content = False
                    break
        elif current_section:
            stripped = line.strip()
            if stripped and not stripped.startswith('<!--') and not stripped.startswith('_'):
                section_has_content = True

    # Don't forget the last section
    if current_section and section_has_content:
        sections_with_content += 1

    return sections_with_content / len(CATEGORIES) if CATEGORIES else 0.0


def compute_coherence(entries: list) -> float:
    """Fraction of active entries with at least one relation."""
    active = [e for e in entries if not e.get('archived')]
    if not active:
        return 0.0

    with_relations = sum(1 for e in active if e.get('related') and len(e['related']) > 0)
    return with_relations / len(active)


def compute_efficiency(memory_line_count: int) -> float:
    """How concise RTMEMORY.md is. Inversely proportional to line count."""
    return max(0.0, 1.0 - (memory_line_count / MAX_EFFICIENT_LINES))


def compute_reachability(entries: list) -> dict:
    """
    Compute reachability using BFS over the relation graph.
    Returns the weighted-average component coverage.
    """
    active = [e for e in entries if not e.get('archived')]

    if not active:
        return {'score': 0.0, 'components': 0, 'largest_component': 0, 'isolated': 0}

    ids = {e['id'] for e in active if 'id' in e}

    # Build undirected adjacency list
    adj = defaultdict(set)
    for entry in active:
        eid = entry.get('id')
        if not eid:
            continue
        for related_id in entry.get('related', []):
            if related_id in ids:
                adj[eid].add(related_id)
                adj[related_id].add(eid)

    # BFS to find connected components
    visited = set()
    components = []

    for node in ids:
        if node in visited:
            continue
        component = set()
        queue = [node]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            for neighbor in adj[current]:
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(len(component))

    total = len(ids)
    if total == 0:
        return {'score': 0.0, 'components': 0, 'largest_component': 0, 'isolated': 0}

    # Weighted average: each node contributes component_size / total
    weighted_sum = sum(size * size for size in components)
    reachability = min(1.0, weighted_sum / (total * total))

    isolated = sum(1 for size in components if size == 1)

    return {
        'score': round(reachability, 4),
        'components': len(components),
        'largest_component': max(components) if components else 0,
        'isolated': isolated,
        'total_nodes': total,
    }


def compute_health(index_path: str, memory_path: str) -> dict:
    """Compute the full 5-metric health score."""

    # Load index
    entries = []
    if Path(index_path).exists():
        with open(index_path, 'r') as f:
            index = json.loads(f.read())
        entries = index.get('entries', [])

    # Load RTMEMORY.md
    memory_content = ''
    memory_lines = 0
    if Path(memory_path).exists():
        with open(memory_path, 'r') as f:
            memory_content = f.read()
        memory_lines = len(memory_content.strip().split('\n'))

    # Compute metrics
    freshness = compute_freshness(entries)
    coverage = compute_coverage(memory_content)
    coherence = compute_coherence(entries)
    efficiency = compute_efficiency(memory_lines)
    reachability_result = compute_reachability(entries)
    reachability = reachability_result['score']

    # Combined score
    health_raw = (
        freshness * 0.25
        + coverage * 0.25
        + coherence * 0.20
        + efficiency * 0.15
        + reachability * 0.15
    )
    health_score = round(health_raw * 100)

    # Rating
    if health_score >= 80:
        rating = 'excellent'
    elif health_score >= 60:
        rating = 'good'
    elif health_score >= 40:
        rating = 'fair'
    elif health_score >= 20:
        rating = 'poor'
    else:
        rating = 'critical'

    # Suggestions
    suggestions = []
    if freshness < 0.5:
        suggestions.append(f'Freshness at {freshness:.0%} — many entries are stale')
    if coverage < 0.5:
        suggestions.append(f'Coverage at {coverage:.0%} — some RTMEMORY.md sections are empty')
    if coherence < 0.3:
        suggestions.append(f'Coherence at {coherence:.0%} — most entries have no relation links')
    if efficiency < 0.3:
        suggestions.append(f'Efficiency at {efficiency:.0%} — RTMEMORY.md has {memory_lines} lines (review for pruning)')
    if reachability < 0.4:
        suggestions.append(
            f'Reachability at {reachability:.0%} — {reachability_result["components"]} '
            f'components, {reachability_result["isolated"]} isolated entries'
        )

    return {
        'ok': True,
        'health_score': health_score,
        'rating': rating,
        'metrics': {
            'freshness': round(freshness, 4),
            'coverage': round(coverage, 4),
            'coherence': round(coherence, 4),
            'efficiency': round(efficiency, 4),
            'reachability': round(reachability, 4),
        },
        'reachability_detail': reachability_result,
        'memory_lines': memory_lines,
        'active_entries': len([e for e in entries if not e.get('archived')]),
        'suggestions': suggestions,
    }


def main():
    parser = argparse.ArgumentParser(description='Reflections: Health Score Engine')
    parser.add_argument('--index', default='runtime/reflections-metadata.json', help='Path to reflections-metadata.json')
    parser.add_argument('--memory-file', default='RTMEMORY.md', help='Path to RTMEMORY.md')
    args = parser.parse_args()

    result = compute_health(args.index, args.memory_file)
    print(json.dumps(result, indent=2))

    return 0


if __name__ == '__main__':
    sys.exit(main())
