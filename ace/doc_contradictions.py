from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol, Sequence
from urllib.parse import parse_qs, urlparse

SKIP_SECTION_HEADINGS = frozenset(
    {
        "what ace is not",
        "what ace is not currently claiming",
        "non-goals",
        "explicit non-goals",
        "deferred",
    }
)

SKIP_SECTION_LABELS = ("deferred", "future", "historical", "non-goal")

OPERATIONAL_SECTION_MARKERS = (
    "current operational",
    "current mission",
    "activated and operational",
)

NEGATION_PHRASES = (
    "not claiming",
    "not currently claiming",
    "not authorized",
    "does not provide",
    "not active",
    "not tagged",
)

SEVERITY_RANK = {"critical": 0, "error": 1, "warn": 2, "info": 3}

COMMAND_PATTERN = re.compile(r"`ace\s+([^`]+)`")
TAG_LITERAL_PATTERN = re.compile(r"`([^\s`]+)`")
WORKFLOW_PATH = ".github/workflows/ace-ci.yml"

TABLE_HEADER = (
    f"{'severity':<10} {'check':<26} {'source':<30} {'claim':<30} "
    f"{'observed':<30} {'detail':<32}"
)


class CiRun(Protocol):
    conclusion: str
    status: str


class CiStatusProbe(Protocol):
    def latest_run(self, *, workflow_file: str, branch: str) -> CiRun | None: ...


class TagLister(Protocol):
    def list_tags(self) -> list[str]: ...


@dataclass(frozen=True)
class ContradictionRow:
    severity: str
    check: str
    source: str
    claim: str
    observed: str
    detail: str


@dataclass(frozen=True)
class BadgeRef:
    source: str
    line_number: int
    label: str
    url: str
    claims_success: bool
    claims_failure: bool
    workflow_file: str
    branch: str


def collect_cli_command_paths(parser: argparse.ArgumentParser) -> set[str]:
    paths: set[str] = set()

    def walk(subparser_action: argparse._SubParsersAction | None, prefix: tuple[str, ...]) -> None:
        if subparser_action is None:
            return
        for name, subparser in subparser_action.choices.items():
            command = (*prefix, name)
            paths.add(" ".join(command))
            for action in subparser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    walk(action, command)

    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            walk(action, ())
    return paths


def _normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _heading_level(line: str) -> int | None:
    stripped = line.strip()
    if not stripped.startswith("#"):
        return None
    hashes = len(stripped) - len(stripped.lstrip("#"))
    if hashes > 6:
        return None
    if not stripped[hashes:].strip():
        return None
    return hashes


def _heading_text(line: str) -> str:
    return re.sub(r"^#+\s*", "", line.strip())


def _section_is_skipped(heading: str) -> bool:
    normalized = _normalize_heading(heading)
    if normalized in SKIP_SECTION_HEADINGS:
        return True
    return any(label in normalized for label in SKIP_SECTION_LABELS)


def _section_is_operational(heading: str) -> bool:
    normalized = _normalize_heading(heading)
    if any(marker in normalized for marker in OPERATIONAL_SECTION_MARKERS):
        return True
    if normalized == "operational boundaries":
        return True
    if "activated" in normalized and "operational" in normalized:
        return True
    return False


def _line_has_tag_context(line: str) -> bool:
    return bool(re.search(r"\btags?\b|\btagged\b", line, flags=re.IGNORECASE))


def _line_has_negation_phrase(line: str) -> bool:
    lowered = line.lower()
    return any(phrase in lowered for phrase in NEGATION_PHRASES)


def _iter_extractable_lines(markdown: str) -> Iterable[tuple[int, str, str]]:
    lines = markdown.splitlines()
    current_heading = ""
    skipped_context = False
    operational_context = False
    before_first_h2 = True
    in_fence = False
    fence_marker = ""

    for index, line in enumerate(lines, start=1):
        level = _heading_level(line)
        if level == 2:
            before_first_h2 = False
            in_fence = False
            fence_marker = ""
            current_heading = _heading_text(line)
            skipped_context = _section_is_skipped(current_heading)
            operational_context = _section_is_operational(current_heading) and not skipped_context
            continue
        if level is not None:
            if level == 1:
                current_heading = _heading_text(line)
            continue

        stripped = line.strip()
        if stripped.startswith("```"):
            marker = stripped[3:].strip()
            if in_fence and (not fence_marker or stripped == "```" or marker == fence_marker):
                in_fence = False
                fence_marker = ""
            else:
                in_fence = True
                fence_marker = marker
            continue
        if in_fence:
            continue
        if stripped.startswith(">"):
            continue

        extract_here = (before_first_h2 and not skipped_context) or operational_context
        if not extract_here:
            continue

        source = f"line {index}"
        if current_heading:
            source = f"{current_heading}:{index}"
        yield index, source, line


def extract_command_references(markdown: str, *, rel_path: str) -> list[tuple[str, int, str]]:
    references: list[tuple[str, int, str]] = []
    for line_number, source, line in _iter_extractable_lines(markdown):
        if _line_has_negation_phrase(line):
            continue
        for match in COMMAND_PATTERN.finditer(line):
            command_tail = " ".join(match.group(1).strip().split())
            references.append((f"{rel_path}:{source}", line_number, command_tail))
    return references


def _badge_claims(url: str, label: str) -> tuple[bool, bool]:
    haystack = f"{label} {url}".lower()
    success_tokens = ("passing", "success", "ok")
    failure_tokens = ("failing", "failed", "failure", "error")
    claims_success = any(token in haystack for token in success_tokens)
    claims_failure = any(token in haystack for token in failure_tokens)
    return claims_success, claims_failure


def _workflow_from_badge_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if "ace-ci.yml" in path or "ace-ci" in path:
        return WORKFLOW_PATH
    match = re.search(r"workflows/([^/]+?)(?:\.yml)?/badge", path)
    if match:
        name = match.group(1)
        if not name.endswith(".yml"):
            return f".github/workflows/{name}.yml"
        return f".github/workflows/{name}"
    query = parse_qs(parsed.query)
    for key in ("workflow", "filename"):
        if key in query and query[key]:
            value = query[key][0]
            if value.endswith(".yml"):
                return f".github/workflows/{value}"
            return f".github/workflows/{value}.yml"
    return WORKFLOW_PATH


def _branch_from_badge_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "branch" in query and query["branch"]:
        return query["branch"][0]
    return "master"


def extract_badge_references(markdown: str, *, rel_path: str) -> list[BadgeRef]:
    badges: list[BadgeRef] = []
    image_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        for match in image_pattern.finditer(line):
            label = match.group(1)
            url = match.group(2).strip()
            lowered = url.lower()
            if "github" not in lowered and "shields.io" not in lowered and "workflow" not in lowered:
                continue
            claims_success, claims_failure = _badge_claims(url, label)
            if not claims_success and not claims_failure:
                continue
            badges.append(
                BadgeRef(
                    source=f"{rel_path}:{line_number}",
                    line_number=line_number,
                    label=label,
                    url=url,
                    claims_success=claims_success,
                    claims_failure=claims_failure,
                    workflow_file=_workflow_from_badge_url(url),
                    branch=_branch_from_badge_url(url),
                )
            )
    return badges


def _positive_tag_context(line: str) -> bool:
    lowered = line.lower()
    if _line_has_negation_phrase(line):
        return False
    if re.search(r"\btagged\b", lowered):
        return True
    positive_markers = ("tag `", "tag points", "tag exists", " tag ", "points at `")
    return any(marker in lowered for marker in positive_markers) or bool(
        re.search(r"\btag\s+`", line, flags=re.IGNORECASE)
    )


def _extract_tag_literals(line: str) -> list[str]:
    literals: list[str] = []
    for match in TAG_LITERAL_PATTERN.finditer(line):
        literals.append(match.group(1))
    for match in re.finditer(r"(?<![A-Za-z0-9_])(ace-[0-9A-Za-z._-]+)", line):
        token = match.group(1)
        if token not in literals:
            literals.append(token)
    return literals


def _tag_literals_on_line(line: str) -> list[str]:
    if not _line_has_tag_context(line):
        return []
    return _extract_tag_literals(line)


def check_tag_claims(status_markdown: str, *, rel_path: str, tags: Sequence[str]) -> list[ContradictionRow]:
    rows: list[ContradictionRow] = []
    tag_set = set(tags)

    for line_number, _source, line in _iter_extractable_lines(status_markdown):
        if not _line_has_tag_context(line):
            continue
        literals = _extract_tag_literals(line)
        negated = _line_has_negation_phrase(line)
        positive = _positive_tag_context(line)

        if not literals:
            if positive and not negated and re.search(r"\btag(?:ged)?\b", line, flags=re.IGNORECASE):
                rows.append(
                    ContradictionRow(
                        severity="error",
                        check="tag_claim_mismatch",
                        source=f"{rel_path}:{_source}"[:30],
                        claim=line.strip()[:30],
                        observed="git: no literal tag name",
                        detail="ambiguous_tag_claim",
                    )
                )
            continue

        for literal in literals:
            source = f"{rel_path}:{_source}"
            claim = literal[:30]
            if negated:
                if literal in tag_set:
                    rows.append(
                        ContradictionRow(
                            severity="critical",
                            check="tag_claim_mismatch",
                            source=source,
                            claim=claim,
                            observed=f"git tag present: {literal}"[:30],
                            detail="negative_tag_present",
                        )
                    )
                continue
            if positive:
                if literal not in tag_set:
                    rows.append(
                        ContradictionRow(
                            severity="critical",
                            check="tag_claim_mismatch",
                            source=source,
                            claim=claim,
                            observed="git: tag missing",
                            detail="positive_tag_missing",
                        )
                    )
                continue
            if re.search(r"\btag(?:ged)?\b", line, flags=re.IGNORECASE):
                rows.append(
                    ContradictionRow(
                        severity="error",
                        check="tag_claim_mismatch",
                        source=source,
                        claim=claim,
                        observed="git: unresolved tag claim",
                        detail="ambiguous_tag_claim",
                    )
                )
    return rows


def check_command_references(
    references: Iterable[tuple[str, int, str]],
    *,
    allowed_commands: set[str],
    check_name: str,
) -> list[ContradictionRow]:
    rows: list[ContradictionRow] = []
    for source, _line_number, command_tail in references:
        if command_tail not in allowed_commands:
            rows.append(
                ContradictionRow(
                    severity="error",
                    check=check_name,
                    source=source[:30],
                    claim=f"ace {command_tail}"[:30],
                    observed="CLI: command missing"[:30],
                    detail="command_not_in_help",
                )
            )
    return rows


def check_workflow_reference(repo_root: Path, *, rel_path: str, markdown: str) -> list[ContradictionRow]:
    if WORKFLOW_PATH not in markdown:
        return []
    workflow = repo_root / WORKFLOW_PATH
    if workflow.is_file():
        return []
    return [
        ContradictionRow(
            severity="error",
            check="workflow_reference_missing",
            source=rel_path[:30],
            claim=WORKFLOW_PATH[:30],
            observed="file missing",
            detail="workflow_path_missing",
        )
    ]


def check_ci_badges(
    badges: Sequence[BadgeRef],
    *,
    probe: CiStatusProbe | None,
    skip_ci: bool,
) -> list[ContradictionRow]:
    if skip_ci or not badges:
        return []
    rows: list[ContradictionRow] = []
    if probe is None:
        return [
            ContradictionRow(
                severity="warn",
                check="ci_badge_stale",
                source=badges[0].source[:30],
                claim="badge ci status",
                observed="probe unavailable",
                detail="ci_probe_unavailable",
            )
        ]

    for badge in badges:
        try:
            latest = probe.latest_run(workflow_file=badge.workflow_file, branch=badge.branch)
        except Exception:
            latest = None
        if latest is None:
            rows.append(
                ContradictionRow(
                    severity="warn",
                    check="ci_badge_stale",
                    source=badge.source[:30],
                    claim=badge.label[:30] or "workflow badge",
                    observed="probe unavailable",
                    detail="ci_probe_unavailable",
                )
            )
            continue

        conclusion = (getattr(latest, "conclusion", None) or "").lower()
        success = conclusion == "success"
        failed = conclusion in {"failure", "cancelled", "timed_out"}

        if badge.claims_success and failed:
            rows.append(
                ContradictionRow(
                    severity="critical",
                    check="ci_badge_stale",
                    source=badge.source[:30],
                    claim="badge claims success",
                    observed=f"latest run: {conclusion}"[:30],
                    detail="badge_success_run_failed",
                )
            )
        elif badge.claims_failure and success:
            rows.append(
                ContradictionRow(
                    severity="warn",
                    check="ci_badge_stale",
                    source=badge.source[:30],
                    claim="badge claims failure",
                    observed="latest run: success",
                    detail="badge_failure_run_succeeded",
                )
            )
    return rows


def run_contradiction_checks(
    *,
    repo_root: Path,
    readme_path: Path,
    status_path: Path,
    parser: argparse.ArgumentParser,
    tag_lister: TagLister | None = None,
    ci_probe: CiStatusProbe | None = None,
    skip_ci: bool = False,
) -> list[ContradictionRow]:
    if not readme_path.is_file():
        raise FileNotFoundError(f"readme not found: {readme_path}")
    if not status_path.is_file():
        raise FileNotFoundError(f"status not found: {status_path}")

    readme = readme_path.read_text(encoding="utf-8")
    status = status_path.read_text(encoding="utf-8")
    allowed_commands = collect_cli_command_paths(parser)

    rows: list[ContradictionRow] = []
    readme_rel = str(readme_path.relative_to(repo_root)) if readme_path.is_relative_to(repo_root) else str(readme_path)
    status_rel = str(status_path.relative_to(repo_root)) if status_path.is_relative_to(repo_root) else str(status_path)

    rows.extend(
        check_command_references(
            extract_command_references(readme, rel_path=readme_rel),
            allowed_commands=allowed_commands,
            check_name="readme_command_missing",
        )
    )
    rows.extend(
        check_command_references(
            extract_command_references(status, rel_path=status_rel),
            allowed_commands=allowed_commands,
            check_name="status_command_missing",
        )
    )

    lister = tag_lister or GitTagLister(repo_root)
    rows.extend(check_tag_claims(status, rel_path=status_rel, tags=lister.list_tags()))
    rows.extend(check_workflow_reference(repo_root, rel_path=readme_rel, markdown=readme))

    badges = extract_badge_references(readme, rel_path=readme_rel) + extract_badge_references(
        status, rel_path=status_rel
    )
    probe = None if skip_ci else (ci_probe or GhCiStatusProbe(repo_root))
    rows.extend(check_ci_badges(badges, probe=probe, skip_ci=skip_ci))

    rows.sort(key=lambda row: (SEVERITY_RANK.get(row.severity, 99), row.check, row.source, row.claim))
    return rows


def render_contradiction_table(rows: Sequence[ContradictionRow]) -> str:
    lines = [TABLE_HEADER]
    for row in rows:
        lines.append(
            f"{row.severity:<10} {row.check:<26} {row.source:<30} {row.claim:<30} "
            f"{row.observed:<30} {row.detail:<32}"
        )
    return "\n".join(lines)


def print_contradiction_rows(rows: Sequence[ContradictionRow]) -> None:
    print(TABLE_HEADER)
    for row in rows:
        print(
            f"{row.severity:<10} {row.check:<26} {row.source:<30} {row.claim:<30} "
            f"{row.observed:<30} {row.detail:<32}"
        )


def exit_code_for_rows(rows: Sequence[ContradictionRow]) -> int:
    for row in rows:
        if row.severity in {"critical", "error"}:
            return 1
    return 0


class GitTagLister:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def list_tags(self) -> list[str]:
        result = subprocess.run(
            ["git", "tag", "-l"],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line]


@dataclass
class _GhCiRun:
    conclusion: str
    status: str


class GhCiStatusProbe:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def latest_run(self, *, workflow_file: str, branch: str) -> CiRun | None:
        workflow_name = Path(workflow_file).name
        result = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                workflow_name,
                "--branch",
                branch,
                "--limit",
                "1",
                "--json",
                "conclusion,status",
            ],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        import json

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        if not payload:
            return None
        row = payload[0]
        return _GhCiRun(
            conclusion=str(row.get("conclusion") or ""),
            status=str(row.get("status") or ""),
        )


def default_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def run_contradictions_command(
    *,
    repo_root: Path | None = None,
    readme_path: Path | None = None,
    status_path: Path | None = None,
    parser: argparse.ArgumentParser | None = None,
    tag_lister: TagLister | None = None,
    ci_probe: CiStatusProbe | None = None,
    skip_ci: bool = False,
    parser_factory: Callable[[], argparse.ArgumentParser] | None = None,
) -> int:
    root = repo_root or default_repo_root()
    readme = readme_path or (root / "ace" / "README.md")
    status = status_path or (root / "ace" / "STATUS.md")
    if parser is None:
        factory = parser_factory
        if factory is None:
            from ace.ace import build_parser

            factory = build_parser
        parser = factory()

    try:
        rows = run_contradiction_checks(
            repo_root=root,
            readme_path=readme,
            status_path=status,
            parser=parser,
            tag_lister=tag_lister,
            ci_probe=ci_probe,
            skip_ci=skip_ci,
        )
    except FileNotFoundError as exc:
        print(f"error={exc}")
        return 1

    print_contradiction_rows(rows)
    return exit_code_for_rows(rows)
