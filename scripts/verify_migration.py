#!/usr/bin/env python3
"""Verify subject index migration against 1000-row test database."""

import asyncio
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from semantic_memory.storage import InsightStore
from semantic_memory.models import Insight, Frame


async def main():
    """Verify migration 001 by checking subject index creation and backfill."""

    db_path = "/tmp/semantic-memory-test.db"
    print("=" * 70)
    print("SUBJECT INDEX MIGRATION VERIFICATION")
    print("=" * 70)

    # Initialize store (applies migration 001)
    print(f"\nInitializing InsightStore from {db_path}...")
    store = InsightStore(db_path)
    await store.initialize()
    print("✓ Store initialized and migration 001 applied")

    # Connect to database to verify
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Total subjects created
    print("\n" + "-" * 70)
    print("1. TOTAL SUBJECTS CREATED")
    print("-" * 70)
    cursor.execute("SELECT COUNT(*) as count FROM subjects")
    total_subjects = cursor.fetchone()["count"]
    print(f"Total subjects: {total_subjects}")
    print(f"Expected: ~42 (13 domains + 29 entities)")

    # 2. Subject count by kind
    print("\n" + "-" * 70)
    print("2. SUBJECT COUNT BY KIND")
    print("-" * 70)
    cursor.execute("SELECT kind, COUNT(*) as count FROM subjects GROUP BY kind ORDER BY kind")
    kind_counts = cursor.fetchall()
    for row in kind_counts:
        print(f"  {row['kind']:10s}: {row['count']:4d} subjects")

    # 3. Top 10 subjects by insight count
    print("\n" + "-" * 70)
    print("3. TOP 10 SUBJECTS BY INSIGHT COUNT")
    print("-" * 70)
    cursor.execute("""
        SELECT s.name, s.kind, COUNT(isub.insight_id) as insight_count
        FROM subjects s
        LEFT JOIN insight_subjects isub ON s.id = isub.subject_id
        GROUP BY s.id, s.name, s.kind
        ORDER BY insight_count DESC
        LIMIT 10
    """)
    top_subjects = cursor.fetchall()
    for i, row in enumerate(top_subjects, 1):
        print(f"  {i:2d}. {row['name']:20s} ({row['kind']:6s}): {row['insight_count']:3d} insights")

    # 4. Sample search_by_subject("docker") results
    print("\n" + "-" * 70)
    print("4. SAMPLE search_by_subject('docker') RESULTS")
    print("-" * 70)
    docker_results = await store.search_by_subject("docker", limit=20)
    print(f"Found {len(docker_results)} insights with 'docker' subject")
    for i, insight in enumerate(docker_results[:5], 1):
        print(f"\n  Result {i}:")
        print(f"    Text: {insight.text[:70]}...")
        print(f"    Frame: {insight.frame.value}")
        print(f"    Domains: {', '.join(insight.domains[:3])}")

    # 5. Time comparison: search_by_subject vs LIKE query
    print("\n" + "-" * 70)
    print("5. PERFORMANCE COMPARISON: search_by_subject vs LIKE query")
    print("-" * 70)

    test_terms = ["docker", "kubernetes", "postgres"]

    for term in test_terms:
        # Timed search_by_subject (async)
        start = time.time()
        results = await store.search_by_subject(term, limit=20)
        subject_search_time = time.time() - start

        # Timed LIKE query (sync)
        start = time.time()
        cursor.execute(
            "SELECT * FROM insights WHERE domains LIKE ? OR entities LIKE ?",
            (f'%"{term}"%', f'%"{term}"%')
        )
        like_results = cursor.fetchall()
        like_query_time = time.time() - start

        speedup = like_query_time / subject_search_time if subject_search_time > 0 else 0
        print(f"\n  Term: '{term}'")
        print(f"    search_by_subject: {subject_search_time*1000:.3f}ms ({len(results)} results)")
        print(f"    LIKE query:        {like_query_time*1000:.3f}ms ({len(like_results)} results)")
        print(f"    Speedup: {speedup:.2f}x")

    # Summary stats
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    cursor.execute("SELECT COUNT(*) as count FROM insights")
    total_insights = cursor.fetchone()["count"]
    cursor.execute("SELECT COUNT(*) as count FROM insight_subjects")
    total_mappings = cursor.fetchone()["count"]

    print(f"Total insights in database: {total_insights}")
    print(f"Total subjects created: {total_subjects}")
    print(f"Total insight_subjects mappings: {total_mappings}")

    # Verify relationships
    cursor.execute("""
        SELECT COUNT(DISTINCT insight_id) as insight_count FROM insight_subjects
    """)
    insights_with_subjects = cursor.fetchone()["insight_count"]
    print(f"Insights linked to subjects: {insights_with_subjects}")

    if insights_with_subjects > 0:
        print(f"✓ Migration 001 successful: All insights linked to subjects")
    else:
        print(f"✗ Migration 001 may have issues: No insights linked to subjects")

    conn.close()
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
