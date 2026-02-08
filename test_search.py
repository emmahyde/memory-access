import asyncio
import os
import sys
sys.path.insert(0, "src")

async def main():
    from memory_access.server import create_app
    app = await create_app()

    queries = [
        "how to orbit camera in scene view",
        "audio system components and features",
        "lighting setup for realistic rendering",
        "keyboard shortcuts for navigation",
        "baked vs realtime lighting tradeoffs",
    ]

    for q in queries:
        print(f"\n{'='*80}")
        print(f"Query: {q}")
        print(f"{'='*80}")
        result = await app.search_knowledge_base(q, kb_name="unity-test", limit=3)
        print(result)

asyncio.run(main())
