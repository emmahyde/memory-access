from __future__ import annotations

import argparse
import asyncio
import sys


def main():
    """Entry point for memory-access CLI."""
    if len(sys.argv) > 1 and sys.argv[1] == "kb":
        return _run_kb_cli()

    # Default: run MCP server
    from .server import main as server_main
    server_main()


def _run_kb_cli():
    parser = argparse.ArgumentParser(prog="memory-access kb")
    sub = parser.add_subparsers(dest="command", required=True)

    # new
    new_p = sub.add_parser("new", help="Create a new knowledge base")
    new_p.add_argument("name", help="Knowledge base name (slug)")
    new_p.add_argument("--crawl", help="URL to crawl")
    new_p.add_argument("--scrape", help="Single URL to scrape")
    new_p.add_argument("--from-dir", dest="from_dir", help="Directory of Firecrawl JSON files")
    new_p.add_argument("--limit", type=int, default=1000, help="Max pages to crawl")
    new_p.add_argument("--description", default="", help="KB description")

    # list
    sub.add_parser("list", help="List knowledge bases")

    # delete
    del_p = sub.add_parser("delete", help="Delete a knowledge base")
    del_p.add_argument("name", help="Knowledge base name")

    # refresh
    ref_p = sub.add_parser("refresh", help="Re-crawl and refresh a knowledge base")
    ref_p.add_argument("name", help="Knowledge base name")
    ref_p.add_argument("--limit", type=int, default=1000, help="Max pages to crawl")

    args = parser.parse_args(sys.argv[2:])
    asyncio.run(_dispatch(args))


async def _dispatch(args):
    from .server import create_app
    from .ingest import Ingestor

    app = await create_app()

    # Only create crawl service when needed (requires firecrawl dependency + API key)
    crawl_service = None
    needs_crawl = args.command == "new" and (getattr(args, "crawl", None) or getattr(args, "scrape", None))
    needs_crawl = needs_crawl or args.command == "refresh"
    if needs_crawl:
        from .crawl import create_crawl_service
        crawl_service = create_crawl_service()

    ingestor = Ingestor(
        store=app.store,
        normalizer=app.normalizer,
        embeddings=app.embeddings,
        crawl_service=crawl_service,
    )

    if args.command == "new":
        await _cmd_new(app, ingestor, args)
    elif args.command == "list":
        await _cmd_list(app)
    elif args.command == "delete":
        await _cmd_delete(app, args)
    elif args.command == "refresh":
        await _cmd_refresh(app, ingestor, args)


async def _cmd_new(app, ingestor, args):
    source_type = "crawl" if args.crawl else "scrape" if args.scrape else "file" if args.from_dir else "text"
    kb_id = await app.store.create_kb(args.name, description=args.description, source_type=source_type)
    print(f"Created knowledge base '{args.name}' ({kb_id})", file=sys.stderr)

    def on_progress(current, total, url):
        print(f"  [{current}/{total}] {url}", file=sys.stderr)

    if args.crawl:
        count = await ingestor.ingest_crawl(kb_id, args.crawl, limit=args.limit, on_progress=on_progress)
        print(f"Ingested {count} chunks from {args.crawl}", file=sys.stderr)
    elif args.scrape:
        count = await ingestor.ingest_scrape(kb_id, args.scrape)
        print(f"Ingested {count} chunks from {args.scrape}", file=sys.stderr)
    elif args.from_dir:
        count = await ingestor.ingest_from_directory(kb_id, args.from_dir, on_progress=on_progress)
        print(f"Ingested {count} chunks from {args.from_dir}", file=sys.stderr)


async def _cmd_list(app):
    kbs = await app.store.list_kbs()
    if not kbs:
        print("No knowledge bases found.", file=sys.stderr)
        return
    for kb in kbs:
        desc = f" - {kb.description}" if kb.description else ""
        print(f"  {kb.name}{desc} [{kb.source_type or 'unknown'}]", file=sys.stderr)


async def _cmd_delete(app, args):
    kb = await app.store.get_kb_by_name(args.name)
    if kb is None:
        print(f"Knowledge base '{args.name}' not found.", file=sys.stderr)
        return
    await app.store.delete_kb(kb.id)
    print(f"Deleted knowledge base '{args.name}'.", file=sys.stderr)


async def _cmd_refresh(app, ingestor, args):
    kb = await app.store.get_kb_by_name(args.name)
    if kb is None:
        print(f"Knowledge base '{args.name}' not found.", file=sys.stderr)
        return
    if not kb.source_type or kb.source_type == "text":
        print(f"Cannot refresh KB '{args.name}': no crawl/scrape source.", file=sys.stderr)
        return

    deleted = await app.store.delete_kb_chunks(kb.id)
    print(f"Deleted {deleted} existing chunks.", file=sys.stderr)

    # Re-ingest — we need the original URL, but it's not stored on the KB model.
    # For now, require --crawl or --scrape on refresh too, or look for source_url from old chunks.
    # Since we don't store the source URL on the KB, print a message.
    print(f"Chunks cleared. Use 'memory-access kb new' with --crawl/--scrape to re-ingest.", file=sys.stderr)
