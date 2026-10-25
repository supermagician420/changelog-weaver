import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from changelog_weaver import (
    CommitError,
    load_commits,
    parse_commit,
    render_section,
    update_changelog,
    main,
)


class ParseTests(unittest.TestCase):
    def test_conventional_commit(self) -> None:
        commit = parse_commit({"hash": "abcdef1", "subject": "feat(api): add export endpoint", "body": ""}, "line 1")
        self.assertEqual(commit.type, "feat")
        self.assertEqual(commit.scope, "api")
        self.assertEqual(commit.description, "add export endpoint")
        self.assertFalse(commit.breaking)

    def test_breaking_change(self) -> None:
        commit = parse_commit({"hash": "abcdef2", "subject": "feat!: remove v1 endpoint"}, "line 1")
        self.assertTrue(commit.breaking)
        self.assertEqual(commit.type, "feat")

    def test_breaking_change_in_body(self) -> None:
        commit = parse_commit(
            {"hash": "abcdef3", "subject": "refactor: split module", "body": "BREAKING CHANGE: move config"},
            "line 1",
        )
        self.assertTrue(commit.breaking)

    def test_non_conventional_commit(self) -> None:
        commit = parse_commit({"hash": "abcdef4", "subject": "Update README wording"}, "line 1")
        self.assertEqual(commit.type, "other")
        self.assertEqual(commit.description, "Update README wording")

    def test_ticket_extraction(self) -> None:
        commit = parse_commit({"hash": "abcdef5", "subject": "fix(auth): handle timeout [ABC-123]"}, "line 1")
        self.assertEqual(commit.ticket, "ABC-123")

    def test_invalid_commit(self) -> None:
        with self.assertRaises(CommitError):
            parse_commit({"hash": "", "subject": "x"}, "line 1")


class LoadTests(unittest.TestCase):
    def test_load_jsonl_and_deduplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "commits.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"hash": "a1", "subject": "feat: one"}),
                        json.dumps({"hash": "b2", "subject": "fix: two"}),
                    ]
                ),
                encoding="utf-8",
            )
            commits = load_commits(str(path))
        self.assertEqual([commit.hash for commit in commits], ["a1", "b2"])

    def test_duplicate_hash_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "commits.jsonl"
            row = json.dumps({"hash": "a1", "subject": "feat: one"}) + "\n"
            path.write_text(row + row, encoding="utf-8")
            with self.assertRaises(CommitError) as ctx:
                load_commits(str(path))
        self.assertIn("duplicate", str(ctx.exception))

    def test_invalid_json_reports_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "commits.jsonl"
            path.write_text("not-json\n", encoding="utf-8")
            with self.assertRaises(CommitError) as ctx:
                load_commits(str(path))
        self.assertIn("line 1", str(ctx.exception))


class RenderTests(unittest.TestCase):
    def test_section_groups_and_links(self) -> None:
        commits = [
            parse_commit({"hash": "a" * 40, "subject": "feat(api): add export"}, "x"),
            parse_commit({"hash": "b" * 40, "subject": "fix: handle timeout"}, "x"),
            parse_commit({"hash": "c" * 40, "subject": "chore: bump deps"}, "x"),
        ]
        rendered = render_section(commits, "1.2.0", "2026-10-25", "https://github.com/me/demo")
        self.assertIn("## [1.2.0] - 2026-10-25", rendered)
        self.assertIn("### Added", rendered)
        self.assertIn("### Fixed", rendered)
        self.assertIn("### Maintenance", rendered)
        self.assertIn("**api:** add export", rendered)
        self.assertIn("https://github.com/me/demo/commit/" + "a" * 40, rendered)

    def test_breaking_section_has_priority(self) -> None:
        commit = parse_commit({"hash": "a", "subject": "feat!: remove old API"}, "x")
        rendered = render_section([commit], "2.0.0", "2026-10-25")
        self.assertIn("### Breaking Changes", rendered)
        self.assertNotIn("### Added", rendered)

    def test_update_existing_inserts_before_old_version(self) -> None:
        existing = "# Changelog\n\nIntro.\n\n## [1.0.0] - 2026-01-01\n\n### Added\n\n- old\n"
        section = render_section([parse_commit({"hash": "a", "subject": "feat: new"}, "x")], "1.1.0", "2026-10-25")
        updated = update_changelog(existing, section)
        self.assertLess(updated.index("## [1.1.0]"), updated.index("## [1.0.0]"))
        self.assertIn("- old", updated)

    def test_create_new_changelog(self) -> None:
        section = render_section([parse_commit({"hash": "a", "subject": "fix: bug"}, "x")], "0.1.0", "2026-10-25")
        updated = update_changelog(None, section)
        self.assertTrue(updated.startswith("# Changelog"))
        self.assertIn("## [0.1.0]", updated)


class CliTests(unittest.TestCase):
    def test_cli_writes_changelog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            commits = Path(tmp) / "commits.jsonl"
            output = Path(tmp) / "CHANGELOG.md"
            commits.write_text(json.dumps({"hash": "abcdef123456", "subject": "feat: add export"}) + "\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["--commits", str(commits), "--version", "1.0.0", "--date", "2026-10-25", "--output", str(output)])
            text = output.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("wrote", buf.getvalue())
        self.assertIn("## [1.0.0] - 2026-10-25", text)

    def test_cli_missing_file(self) -> None:
        self.assertEqual(main(["--commits", "does-not-exist.jsonl"]), 2)


if __name__ == "__main__":
    unittest.main()
