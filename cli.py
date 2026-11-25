"""CLI for dataset processing and verification. Run python cli.py --help."""

import argparse
from pathlib import Path
import sys

from indexing.pipeline import inspect_dataset, run, verify
from indexing.masking import setup_models
from sql.database import connect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "setup-models", "init-db", "verify-db"):
        subs.add_parser(name)
    process = subs.add_parser("run")
    process.add_argument("--image", type=Path, action="append", help="Image under data/images (repeatable)")
    process.add_argument("--limit", type=int)
    process.add_argument("--mask", type=Path, help="Replacement binary PNG for a single image")
    process.add_argument("--preview", action="store_true")
    process.add_argument("--check-background", action="store_true")
    process.add_argument("--offline", action="store_true", help="Write vectors to the run log without MySQL")
    find = subs.add_parser("search", help="Rank gallery images for one or more query files")
    find.add_argument("--image", type=Path, required=True, action="append")
    find.add_argument("--evidence", action="store_true", help="Also export full precision results as JSON")
    find.add_argument("--species", action="append", help="Optional ground truth label for evaluation")
    find.add_argument("--exclude-id", type=int, action="append", default=[], help="Exclude a known source ID before fitting")
    evaluation = subs.add_parser("evaluate", help="Hold out query images per species before fitting the gallery")
    evaluation.add_argument("--seed", type=int, default=42)
    evaluation.add_argument("--per-species", type=int, default=1, help="Maximum queries per species (keep at least one gallery image)")
    args = parser.parse_args()
    if args.command == "inspect":
        inspect_dataset()
    elif args.command == "setup-models":
        setup_models()
    elif args.command == "init-db":
        with connect(initialize=True) as conn, conn.cursor() as cur:
            cur.execute("SELECT VERSION(), DATABASE()")
            print(*cur.fetchone())
    elif args.command == "verify-db":
        return verify()
    elif args.command == "search":
        from search.search_cli import search
        return search(args)
    elif args.command == "evaluate":
        if args.per_species < 1:
            parser.error("--per-species must be positive")
        from search.search_cli import evaluate
        return evaluate(args)
    else:
        if args.limit is not None and args.limit < 1:
            parser.error("--limit must be positive")
        return run(args)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.exit(f"{type(exc).__name__}: {exc}")
