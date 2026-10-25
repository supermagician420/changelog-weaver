#!/usr/bin/env python3
"""Turn JSONL commit metadata into a deterministic Keep-a-Changelog section."""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


class CommitError(ValueError):
    """A commit record or changelog file is invalid."""


@dataclass(frozen=True)
class Commit:
    hash: str
    subject: str
    body: str
    type: str
    scope: Optional[str]
    description: str
    breaking: bool
    ticket: Optional[str]


_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<description>.+)$"
)
_TICKET_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_TYPE_SECTION = {
    "feat": "Added",
    "feature": "Added",
    "fix": "Fixed",
    "bugfix": "Fixed",
    "perf": "Changed",
    "refactor": "Changed",
    "security": "Security",
    "revert": "Reverted",
    "docs": "Maintenance",
    "doc": "Maintenance",
    "test": "Maintenance",
    "tests": "Maintenance",
    "chore": "Maintenance",
    "ci": "Maintenance",
    "build": "Maintenance",
    "style": "Maintenance",
}
_SECTION_ORDER = (
    "Breaking Changes",
    "Added",
    "Changed",
    "Fixed",
    "Security",
    "Reverted",
    "Maintenance",
    "Other",
)


def _section_for(commit: Commit) -> str:
    if commit.breaking:
        return "Breaking Changes"
    return _TYPE_SECTION.get(commit.type, "Other")


def parse_commit(raw: object, where: str) -> Commit:
    if not isinstance(raw, dict):
        raise CommitError("%s: each commit must be a JSON object" % where)
    commit_hash = raw.get("hash")
    subject = raw.get("subject")
    body = raw.get("body", "")
    if not isinstance(commit_hash, str) or not commit_hash.strip():
        raise CommitError("%s: hash must be a non-empty string" % where)
    if not isinstance(subject, str) or not subject.strip():
        raise CommitError("%s: subject must be a non-empty string" % where)
    if body is None:
        body = ""
    if not isinstance(body, str):
        raise CommitError("%s: body must be a string" % where)

    subject = subject.strip()
    match = _CONVENTIONAL_RE.match(subject)
    if match:
        commit_type = match.group("type").lower()
        scope = match.group("scope")
        breaking = bool(match.group("breaking"))
        description = match.group("description").strip()
    else:
        commit_type = "other"
        scope = None
        breaking = False
        description = subject
    if "BREAKING CHANGE:" in body or "BREAKING-CHANGE:" in body:
        breaking = True
    ticket_match = _TICKET_RE.search(subject)
    ticket = ticket_match.group(0) if ticket_match else None
    return Commit(
        hash=commit_hash.strip(),
        subject=subject,
        body=body,
        type=commit_type,
        scope=scope.strip() if scope else None,
        description=description,
        breaking=breaking,
        ticket=ticket,
    )


def load_commits(path: str) -> List[Commit]:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CommitError("cannot read commits: %s" % exc) from exc

    commits: List[Commit] = []
    seen = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CommitError("line %d: invalid JSON: %s" % (line_number, exc.msg)) from exc
        commit = parse_commit(raw, "line %d" % line_number)
        if commit.hash in seen:
            raise CommitError("line %d: duplicate commit hash %s" % (line_number, commit.hash))
        seen.add(commit.hash)
        commits.append(commit)
    if not commits:
        raise CommitError("no commits found")
    return commits


def _link(commit: Commit, repo_url: Optional[str]) -> str:
    short = commit.hash[:7]
    if repo_url:
        return "[%s](%s/commit/%s)" % (short, repo_url.rstrip("/"), commit.hash)
    return "`%s`" % short


def render_section(commits: Sequence[Commit], version: str, release_date: str, repo_url: Optional[str] = None) -> str:
    grouped: Dict[str, List[Commit]] = {section: [] for section in _SECTION_ORDER}
    for commit in commits:
        grouped[_section_for(commit)].append(commit)

    lines = ["## [%s] - %s" % (version, release_date), ""]
    wrote_section = False
    for section in _SECTION_ORDER:
        items = grouped[section]
        if not items:
            continue
        wrote_section = True
        lines.extend(["### %s" % section, ""])
        for commit in sorted(items, key=lambda item: ((item.scope or ""), item.description.lower(), item.hash)):
            prefix = "- "
            if commit.scope:
                prefix += "**%s:** " % commit.scope
            suffix = " (%s)" % _link(commit, repo_url)
            ticket = " (%s)" % commit.ticket if commit.ticket and commit.ticket not in commit.description else ""
            lines.append(prefix + commit.description + ticket + suffix)
        lines.append("")
    if not wrote_section:
        lines.extend(["No notable changes.", ""])
    return "\n".join(lines).rstrip() + "\n"


def update_changelog(existing: Optional[str], section: str) -> str:
    if not existing or not existing.strip():
        return "# Changelog\n\nAll notable changes to this project are documented here.\n\n" + section
    lines = existing.rstrip().splitlines()
    insert_at = len(lines)
    for index, line in enumerate(lines):
        if line.startswith("## "):
            insert_at = index
            break
    head = lines[:insert_at]
    tail = lines[insert_at:]
    while head and not head[-1].strip():
        head.pop()
    new_lines = head + ["", section.rstrip(), ""] + tail
    return "\n".join(new_lines).rstrip() + "\n"


def _valid_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc
    return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a changelog section from JSONL commits")
    parser.add_argument("--commits", required=True, help="JSONL file, or - for stdin")
    parser.add_argument("--version", default="Unreleased")
    parser.add_argument("--date", type=_valid_date, default=date.today().isoformat())
    parser.add_argument("--repo-url", help="e.g. https://github.com/you/project")
    parser.add_argument("--output", help="prepend/merge into this changelog file; otherwise print")
    args = parser.parse_args(argv)

    try:
        commits = load_commits(args.commits)
        section = render_section(commits, args.version, args.date, args.repo_url)
        if args.output:
            output = Path(args.output)
            existing = output.read_text(encoding="utf-8") if output.exists() else None
            output.write_text(update_changelog(existing, section), encoding="utf-8")
    except (CommitError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.output:
        print("wrote %s" % args.output)
    else:
        print(section, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
