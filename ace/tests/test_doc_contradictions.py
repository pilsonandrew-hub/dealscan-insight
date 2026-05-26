from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ace.ace import build_parser, main
from ace.doc_contradictions import (
    TABLE_HEADER,
    BadgeRef,
    ContradictionRow,
    _GhCiRun,
    check_ci_badges,
    check_tag_claims,
    collect_cli_command_paths,
    exit_code_for_rows,
    extract_command_references,
    run_contradiction_checks,
    run_contradictions_command,
)


class FakeTagLister:
    def __init__(self, tags: list[str]) -> None:
        self._tags = tags

    def list_tags(self) -> list[str]:
        return list(self._tags)


class FakeCiProbe:
    def __init__(self, *, conclusion: str = "success", available: bool = True) -> None:
        self.conclusion = conclusion
        self.available = available

    def latest_run(self, *, workflow_file: str, branch: str) -> _GhCiRun | None:
        if not self.available:
            return None
        return _GhCiRun(conclusion=self.conclusion, status="completed")


class DocContradictionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.allowed_commands = collect_cli_command_paths(build_parser())

    def test_operational_commands_resolve_against_cli(self) -> None:
        readme = """# ACE

Intro prose with no commands.

## Current operational commands

- `ace stale`
- `ace loose-ends`
- `ace digest`

## What ACE is not currently claiming

- `ace audit verify`
"""
        status = """# ACE Status

Current mission: `ace stale`, `ace loose-ends`, and `ace digest`

## Current operational commands

- `ace stale`
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            readme_path = root / "ace" / "README.md"
            status_path = root / "ace" / "STATUS.md"
            readme_path.parent.mkdir(parents=True)
            readme_path.write_text(readme, encoding="utf-8")
            status_path.write_text(status, encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ace-ci.yml").write_text("name: ACE CI\n", encoding="utf-8")

            rows = run_contradiction_checks(
                repo_root=root,
                readme_path=readme_path,
                status_path=status_path,
                parser=build_parser(),
                tag_lister=FakeTagLister([]),
                ci_probe=FakeCiProbe(),
                skip_ci=True,
            )
        self.assertEqual(rows, [])

    def test_readme_phantom_command_in_operational_section(self) -> None:
        readme = """## Current operational commands

- `ace ship-it`
"""
        refs = extract_command_references(readme, rel_path="ace/README.md")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0][2], "ship-it")
        self.assertNotIn("ship-it", self.allowed_commands)

    def test_negated_line_skips_command_extraction(self) -> None:
        readme = """## Current operational commands

ACE is not claiming `ace audit verify` as operational.
"""
        refs = extract_command_references(readme, rel_path="ace/README.md")
        self.assertEqual(refs, [])

    def test_digest_not_optional_line_is_not_skipped(self) -> None:
        readme = """## Current operational commands

`ace digest` is not optional for weekly operator visibility.
"""
        refs = extract_command_references(readme, rel_path="ace/README.md")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0][2], "digest")

    def test_skipped_section_commands_ignored(self) -> None:
        readme = """## What ACE is not currently claiming

- `ace attestation sync`
"""
        refs = extract_command_references(readme, rel_path="ace/README.md")
        self.assertEqual(refs, [])

    def test_fenced_code_block_commands_ignored(self) -> None:
        readme = """## Current operational commands

```
`ace phantom`
```
"""
        refs = extract_command_references(readme, rel_path="ace/README.md")
        self.assertEqual(refs, [])

    def test_blockquote_commands_ignored(self) -> None:
        readme = """## Current operational commands

> `ace phantom`
"""
        refs = extract_command_references(readme, rel_path="ace/README.md")
        self.assertEqual(refs, [])

    def test_positive_tag_missing_is_critical(self) -> None:
        rows = check_tag_claims(
            "Release is tagged `ace-2.0` on master.",
            rel_path="ace/STATUS.md",
            tags=[],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].severity, "critical")
        self.assertEqual(rows[0].detail, "positive_tag_missing")

    def test_negative_tag_present_is_critical(self) -> None:
        rows = check_tag_claims(
            "ACE 1.0 is not tagged `ace-1.0`.",
            rel_path="ace/STATUS.md",
            tags=["ace-1.0"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].severity, "critical")
        self.assertEqual(rows[0].detail, "negative_tag_present")

    def test_literal_tag_name_without_case_normalization(self) -> None:
        rows = check_tag_claims(
            "Tagged `ace-2.0` today.",
            rel_path="ace/STATUS.md",
            tags=["ACE-2.0"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].severity, "critical")
        self.assertEqual(rows[0].detail, "positive_tag_missing")

    def test_ambiguous_tag_claim_is_error(self) -> None:
        rows = check_tag_claims(
            "ACE 1.0 is tagged for release.",
            rel_path="ace/STATUS.md",
            tags=[],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].severity, "error")
        self.assertEqual(rows[0].detail, "ambiguous_tag_claim")

    def test_ci_badge_success_with_failed_run_is_critical(self) -> None:
        badge = BadgeRef(
            source="ace/README.md:1",
            line_number=1,
            label="passing",
            url="https://github.com/o/r/actions/workflows/ace-ci.yml/badge.svg?branch=master",
            claims_success=True,
            claims_failure=False,
            workflow_file=".github/workflows/ace-ci.yml",
            branch="master",
        )
        rows = check_ci_badges([badge], probe=FakeCiProbe(conclusion="failure"), skip_ci=False)
        self.assertEqual(rows[0].severity, "critical")

    def test_ci_badge_failure_with_success_run_is_warn(self) -> None:
        badge = BadgeRef(
            source="ace/README.md:1",
            line_number=1,
            label="failing",
            url="https://github.com/o/r/actions/workflows/ace-ci.yml/badge.svg",
            claims_success=False,
            claims_failure=True,
            workflow_file=".github/workflows/ace-ci.yml",
            branch="master",
        )
        rows = check_ci_badges([badge], probe=FakeCiProbe(conclusion="success"), skip_ci=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].severity, "warn")

    def test_ci_probe_unavailable_is_warn_not_error(self) -> None:
        badge = BadgeRef(
            source="ace/README.md:1",
            line_number=1,
            label="passing",
            url="https://github.com/o/r/actions/workflows/ace-ci.yml/badge.svg",
            claims_success=True,
            claims_failure=False,
            workflow_file=".github/workflows/ace-ci.yml",
            branch="master",
        )
        rows = check_ci_badges([badge], probe=FakeCiProbe(available=False), skip_ci=False)
        self.assertEqual(rows[0].severity, "warn")
        self.assertEqual(exit_code_for_rows(rows), 0)

    def test_no_badges_produces_no_ci_rows(self) -> None:
        rows = check_ci_badges([], probe=FakeCiProbe(), skip_ci=False)
        self.assertEqual(rows, [])

    def test_rows_sort_critical_before_error(self) -> None:
        rows = [
            ContradictionRow("error", "b", "s", "c", "o", "d"),
            ContradictionRow("critical", "a", "s", "c", "o", "d"),
        ]
        rows.sort(key=lambda row: ({"critical": 0, "error": 1}[row.severity], row.check))
        self.assertEqual(rows[0].severity, "critical")

    def test_cli_empty_findings_prints_header_only_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            readme_path = root / "ace" / "README.md"
            status_path = root / "ace" / "STATUS.md"
            readme_path.parent.mkdir(parents=True)
            readme_path.write_text(
                """## Current operational commands\n\n- `ace stale`\n""",
                encoding="utf-8",
            )
            status_path.write_text(
                """## Current operational commands\n\n- `ace stale`\n""",
                encoding="utf-8",
            )
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ace-ci.yml").write_text("name: ACE CI\n", encoding="utf-8")

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = run_contradictions_command(
                    repo_root=root,
                    readme_path=readme_path,
                    status_path=status_path,
                    parser=build_parser(),
                    tag_lister=FakeTagLister([]),
                    skip_ci=True,
                )
            output = buffer.getvalue().rstrip("\n").splitlines()
            self.assertEqual(code, 0)
            self.assertEqual(len(output), 1)
            self.assertEqual(output[0], TABLE_HEADER)

    def test_main_contradictions_integration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            readme_path = root / "ace" / "README.md"
            status_path = root / "ace" / "STATUS.md"
            readme_path.parent.mkdir(parents=True)
            readme_path.write_text("## Current operational commands\n\n- `ace stale`\n", encoding="utf-8")
            status_path.write_text("## Current operational commands\n\n- `ace stale`\n", encoding="utf-8")
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ace-ci.yml").write_text("name: ACE CI\n", encoding="utf-8")

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    [
                        "--db",
                        str(root / "ace.db"),
                        "contradictions",
                        "--repo-root",
                        str(root),
                        "--skip-ci",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertIn(TABLE_HEADER, buffer.getvalue())

    def test_contradictions_parser_registered(self) -> None:
        parser = build_parser()
        commands = collect_cli_command_paths(parser)
        self.assertIn("contradictions", commands)


if __name__ == "__main__":
    unittest.main()
