# changelog-weaver

A zero-dependency CLI that turns structured commit metadata into a deterministic Keep-a-Changelog section.

It is for teams that already write conventional commits or maintain a ticket ID in the subject, and want release notes to be generated from data instead of memory.

## Quick start

Requires Python 3.8+, no third-party packages.

```bash
python changelog_weaver.py \
  --commits examples/commits.jsonl \
  --version 2.0.0 \
  --date 2026-10-25 \
  --repo-url https://github.com/example/demo
```

Output:

```text
## [2.0.0] - 2026-10-25

### Breaking Changes

- remove legacy /v1/export ([c3d4e5f](https://github.com/example/demo/commit/c3d4e5f...))

### Added

- **api:** add CSV export endpoint ([a1b2c3d](https://github.com/example/demo/commit/a1b2c3d...))

### Fixed

- handle empty upstream response ([b2c3d4e](https://github.com/example/demo/commit/b2c3d4e...))

### Maintenance

- bump dev dependencies ([d4e5f60](https://github.com/example/demo/commit/d4e5f60...))

### Other

- Update README wording ([e5f6071](https://github.com/example/demo/commit/e5f6071...))
```

Write or merge into an existing changelog:

```bash
python changelog_weaver.py \
  --commits examples/commits.jsonl \
  --version 2.0.0 \
  --date 2026-10-25 \
  --output CHANGELOG.md
```

If `CHANGELOG.md` already contains versions, the new section is inserted before the newest existing `## [...]` heading.

## Input format

One JSON object per line:

```json
{"hash": "a1b2c3d4...", "subject": "feat(api): add CSV export", "body": ""}
```

- `hash`: required, unique short or full hash;
- `subject`: required, one line;
- `body`: optional; `BREAKING CHANGE:` is detected.

Example subject forms:

```text
feat(api): add CSV export endpoint
fix: handle empty upstream response
feat!: remove legacy /v1/export
chore: bump dev dependencies
Update README wording
ABC-123 fix timeout
```

## Mapping

| Prefix | Section |
| --- | --- |
| `feat`, `feature` | Added |
| `fix`, `bugfix` | Fixed |
| `perf`, `refactor` | Changed |
| `security` | Security |
| `revert` | Reverted |
| `docs`, `test`, `chore`, `ci`, `build`, `style` | Maintenance |
| `!` or `BREAKING CHANGE:` | Breaking Changes |
| anything else | Other |

## Design choices

- **Input is data, not prose.** JSONL keeps hashes, scopes, and bodies unambiguous.
- **Deterministic output.** Same commits + same options = same Markdown.
- **Tickets stay visible.** An ID such as `ABC-123` is appended to the bullet if it is not already in the description.
- **Safe merge.** Existing changelog content is preserved; the new section is inserted before older versions.
- **No network.** The repo URL is only used to build commit links.

## Limitations

- It does not call GitHub or `git log`; you must export commits.
- Conventional commit parsing is intentionally shallow.
- A `BREAKING CHANGE:` body is detected but not expanded into a migration guide.
- Merge commits and reverts need sensible subjects upstream.
- Markdown is not escaped; commit subjects are trusted input.

## Tests

```bash
python -m unittest -v
```

15 tests cover conventional parsing, breaking changes, ticket extraction, JSONL validation, duplicate hashes, grouping, links, insertion into existing changelogs, and CLI writing.

## Files

```text
changelog-weaver/
├── changelog_weaver.py
├── test_changelog_weaver.py
├── examples/commits.jsonl
├── README.md
├── .gitignore
└── .github/workflows/tests.yml
```
