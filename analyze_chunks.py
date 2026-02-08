import sqlite3
import os
import statistics

db = os.path.expanduser("~/.claude/memory-access/memory.db")
conn = sqlite3.connect(db)

# Find the KB ID
kb = conn.execute("SELECT id FROM knowledge_bases WHERE name='unity-test'").fetchone()
if not kb:
    print("ERROR: knowledge base 'unity-test' not found")
    exit(1)

kb_id = kb[0]
print(f"Knowledge base 'unity-test' ID: {kb_id}\n")

# Get all chunks
rows = conn.execute(
    "SELECT frame, confidence, normalized_text FROM kb_chunks WHERE kb_id=? ORDER BY frame, confidence DESC",
    (kb_id,)
).fetchall()

print(f"Total chunks: {len(rows)}\n")
print("="*80)
print("ALL CHUNKS (ordered by frame, then confidence)")
print("="*80)

# Print all
for i, (frame, conf, text) in enumerate(rows, 1):
    truncated = text[:120] + "..." if len(text) > 120 else text
    print(f"{i:2d}. [{conf:.2f}] ({frame:12s}) {truncated}")

# Frame distribution
print("\n" + "="*80)
print("FRAME DISTRIBUTION")
print("="*80)
frame_counts = {}
for frame, conf, text in rows:
    frame_counts[frame] = frame_counts.get(frame, 0) + 1
for frame, count in sorted(frame_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {frame:12s}: {count:2d} ({count/len(rows)*100:.1f}%)")

# Confidence distribution
print("\n" + "="*80)
print("CONFIDENCE DISTRIBUTION")
print("="*80)
confs = [c for _, c, _ in rows]
print(f"  min   = {min(confs):.2f}")
print(f"  max   = {max(confs):.2f}")
print(f"  mean  = {statistics.mean(confs):.2f}")
print(f"  median= {statistics.median(confs):.2f}")

low = sum(1 for c in confs if c < 0.5)
mid = sum(1 for c in confs if 0.5 <= c < 0.7)
high = sum(1 for c in confs if c >= 0.7)
print(f"\nConfidence ranges:")
print(f"  < 0.5  : {low:2d} ({low/len(rows)*100:.1f}%)")
print(f"  0.5-0.7: {mid:2d} ({mid/len(rows)*100:.1f}%)")
print(f"  >= 0.7 : {high:2d} ({high/len(rows)*100:.1f}%)")

conn.close()
