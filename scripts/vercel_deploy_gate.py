#!/usr/bin/env python3
"""Decide whether a change set should create a Vercel deployment.

The gate is intentionally conservative: known backend/proof/report-only paths
skip Vercel, while unknown or frontend-impacting paths deploy.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
from pathlib import PurePosixPath


DEPLOY_EXACT_PATHS = {
    ".env.example",
    ".env.production.example",
    ".npmrc",
    ".vercelignore",
    "bun.lockb",
    "components.json",
    "index.html",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "postcss.config.cjs",
    "postcss.config.js",
    "postcss.config.mjs",
    "postcss.config.ts",
    "tailwind.config.cjs",
    "tailwind.config.js",
    "tailwind.config.mjs",
    "tailwind.config.ts",
    "vercel.json",
    "yarn.lock",
}

DEPLOY_PREFIXES = (
    "api/",
    "app/",
    "functions/",
    "pages/",
    "public/",
    "server/",
    "src/",
)

DEPLOY_PATTERNS = (
    "eslint.config.*",
    "tsconfig*.json",
    "vite.config.*",
)

SKIP_EXACT_PATHS = {
    "pytest.ini",
    "requirements-dev.txt",
    "requirements.txt",
}

SKIP_PREFIXES = (
    ".github/workflows/",
    "apify/",
    "backend/",
    "data/",
    "docs/",
    "reports/",
    "scripts/",
    "supabase/",
    "tests/",
)


def _clean_path(path: str) -> str:
    cleaned = str(PurePosixPath(path.strip().replace("\\", "/")))
    if cleaned == ".":
        return ""
    return cleaned.removeprefix("./")


def _is_deploy_path(path: str) -> bool:
    if path in DEPLOY_EXACT_PATHS:
        return True
    if path.startswith(DEPLOY_PREFIXES):
        return True
    if path.startswith("scripts/vercel") or path == "scripts/vercel_deploy_gate.py":
        return True
    if fnmatch.fnmatch(path, ".github/workflows/vercel*.yml"):
        return True
    if fnmatch.fnmatch(path, ".github/workflows/vercel*.yaml"):
        return True
    return any(fnmatch.fnmatch(path, pattern) for pattern in DEPLOY_PATTERNS)


def _is_known_skip_path(path: str) -> bool:
    if path in SKIP_EXACT_PATHS:
        return True
    return path.startswith(SKIP_PREFIXES)


def should_deploy_for_paths(paths: list[str]) -> bool:
    cleaned_paths = [_clean_path(path) for path in paths if _clean_path(path)]
    if not cleaned_paths:
        return True

    for path in cleaned_paths:
        if _is_deploy_path(path):
            return True
        if not _is_known_skip_path(path):
            return True

    return False


def _changed_paths(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="*", help="Explicit changed file list.")
    parser.add_argument("--base", help="Base git ref for changed-file detection.")
    parser.add_argument("--head", help="Head git ref for changed-file detection.")
    parser.add_argument("--github-output", help="Optional GITHUB_OUTPUT path.")
    parser.add_argument(
        "--ignore-command-exit",
        action="store_true",
        help="Use Vercel ignoreCommand exit semantics: 0 skips, 1 deploys.",
    )
    args = parser.parse_args()

    try:
        paths = (
            args.files
            if args.files is not None
            else _changed_paths(args.base or "origin/main", args.head or "HEAD")
        )
        deploy = should_deploy_for_paths(paths)
    except Exception as exc:
        paths = []
        deploy = True
        print(f"Vercel deploy gate failed open: {exc}")

    deploy_value = "true" if deploy else "false"
    print(f"Vercel deploy decision: {deploy_value}")
    if paths:
        print("Changed paths:")
        for path in paths:
            print(f"- {_clean_path(path)}")

    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as output_file:
            output_file.write(f"deploy={deploy_value}\n")

    if args.ignore_command_exit:
        return 1 if deploy else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
