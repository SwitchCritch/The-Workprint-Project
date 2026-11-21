#!/usr/bin/env python3
"""Export a consistent local SQLite backup as SQL for review / future D1 import.

Run this on a PRIVATE computer against a COPY of the Railway DB.
Never commit the exported SQL, which includes member email addresses and hashes.
Does not connect to Railway or Cloudflare.
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Existing workprints.db backup")
    parser.add_argument("output", type=Path, help="Destination .sql outside GitHub")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Database backup not found.")
    if args.output.exists():
        parser.error("Output already exists; refusing to overwrite.")
    if args.output.resolve() == args.database.resolve():
        parser.error("Input and output must differ.")
    if args.output.suffix.lower() != ".sql":
        parser.error("Output filename must end in .sql")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{args.database.resolve()}?mode=ro", uri=True)
    try:
        # SQLite backup API captures a consistent snapshot without writing to source.
        memory = sqlite3.connect(":memory:")
        try:
            source.backup(memory)
            # D1 import needs independent review of triggers, pragmas,
            # transactions and SQLite feature compatibility before execution.
            with args.output.open("x", encoding="utf-8") as target:
                target.write("-- PRIVATE EXPORT: member data included. DO NOT COMMIT.\n")
                for statement in memory.iterdump():
                    target.write(statement + "\n")
        finally:
            memory.close()
    finally:
        source.close()
    print(f"Created PRIVATE SQL export: {args.output} (not uploaded).")
    print("Review/convert before D1 import. This is not an automatic migration.")


if __name__ == "__main__":
    main()
