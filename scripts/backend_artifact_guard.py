#!/usr/bin/env python3
"""Compare Flyway migrations in backend artifacts before production deployment."""

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path


MIGRATION_PREFIX = "BOOT-INF/classes/db/migration/"


def migration_manifest(jar_path: Path) -> dict[str, str]:
    with zipfile.ZipFile(jar_path) as jar:
        return {
            name.removeprefix(MIGRATION_PREFIX): hashlib.sha256(jar.read(name)).hexdigest()
            for name in sorted(jar.namelist())
            if name.startswith(MIGRATION_PREFIX) and name.endswith(".sql")
        }


def load_manifest(args: argparse.Namespace) -> dict[str, str]:
    if args.current_jar:
        return migration_manifest(Path(args.current_jar))
    return json.loads(Path(args.current_manifest).read_text())


def compare(args: argparse.Namespace) -> int:
    current = load_manifest(args)
    candidate = migration_manifest(Path(args.candidate_jar))
    changed = sorted(name for name in current.keys() & candidate.keys() if current[name] != candidate[name])
    removed = sorted(current.keys() - candidate.keys())
    added = sorted(candidate.keys() - current.keys())

    problems: list[str] = []
    problems.extend(f"changed existing migration: {name}" for name in changed)
    problems.extend(f"removed existing migration: {name}" for name in removed)
    if added and not args.allow_new_migrations:
        problems.extend(f"unauthorized new migration: {name}" for name in added)

    if problems:
        print("backend artifact migration guard rejected candidate:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    suffix = f"; authorized new migrations: {', '.join(added)}" if added else ""
    print(f"migration guard passed ({len(candidate)} migrations{suffix})")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("manifest")
    manifest.add_argument("--jar", required=True)
    compare_parser = commands.add_parser("compare")
    current = compare_parser.add_mutually_exclusive_group(required=True)
    current.add_argument("--current-jar")
    current.add_argument("--current-manifest")
    compare_parser.add_argument("--candidate-jar", required=True)
    compare_parser.add_argument("--allow-new-migrations", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "manifest":
        print(json.dumps(migration_manifest(Path(args.jar)), indent=2, sort_keys=True))
        return 0
    return compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
