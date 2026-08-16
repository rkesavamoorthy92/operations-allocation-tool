# Operations Allocation Tool

An offline-first Windows desktop application for allocating Product
Type (PT) classification/QC work across a team of associates, tracking
it through Distribution -> Return -> Consolidation -> QC -> Error
Reporting, with a full audit trail at every step.

Built with Python, PySide6, and SQLite. No server, no internet
connection required to run -- everything lives in a local database on
the machine it runs on (see `packaging/PACKAGING.md` for how that scales
to a shared/team setup later).

**Using the app?** See `USER_GUIDE.md`. **Supporting/troubleshooting
it?** See `SUPPORT_GUIDE.md`.

## Running from source

```powershell
uv sync
uv run python -m operations_allocation.ui.app
```

Application data (Programs, Runs, artifacts) lives in
`%LOCALAPPDATA%\OperationsAllocationTool` by default -- see
`packaging/PACKAGING.md` for how to override that.

## Running the tests

```powershell
uv run --frozen pytest -q
```

**Note:** `uv.lock` is currently stale relative to `pyproject.toml`
(pyinstaller was added for packaging -- see below -- but `uv lock`
could not complete on this network: it kept timing out trying to
resolve wheels for platforms other than Windows). Until someone runs
`uv lock` successfully to refresh it, use `--frozen` (or `--no-sync`) on
every `uv run` command, otherwise it will hang trying to re-resolve the
lockfile. `pytest` and all runtime dependencies are unaffected -- only
the dev-only `pyinstaller` entry is missing from the lock, which was
already separately installed into `.venv` via `uv pip install`.

UI tests run against the real PySide6 widgets with `QT_QPA_PLATFORM=offscreen`
(no visible window needed) -- set that environment variable first if
running on a machine without a display.

## Building a standalone .exe

See `packaging/PACKAGING.md`.

## Project structure

See `ARCHITECTURE.md` for the full layer breakdown (core / services /
persistence / infrastructure / ui) and `PROJECT_SPEC.md` for the
functional specification each piece implements. `AGENTS.md` documents
the engineering conventions (no `eval()`, restricted rule engines,
append-only audit trail, etc.) that every module in this codebase
follows.

## Adding a new Program

No code changes or rebuild required -- every Program's field layout,
sampling/allocation rules, QC rules, error classification rules, and
email templates are authored entirely through the app's "New Program" +
"Edit Configuration" UI and stored as versioned JSON in the local
database. See `packaging/PACKAGING.md` for why this remains true even
once the app is packaged as a standalone .exe.
