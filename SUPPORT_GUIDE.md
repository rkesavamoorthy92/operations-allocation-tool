# Support Guide — Operations Allocation Tool

For whoever is fielding bug reports and enhancement requests for this
tool. Everything below reflects the actual current codebase — nothing
here is aspirational.

## 1. Architecture, in one paragraph

Layered: `domain` (pure data models, exceptions, the Run state
machine) → `core` (pure calculation functions — validation, sampling,
allocation, QC, errors, insights, reporting — no I/O) → `services`
(orchestrates `core` + `persistence` + `infrastructure`, one class per
capability) → `persistence` (SQLite repositories) / `infrastructure`
(file I/O: Excel read/write, Outlook COM) → `ui` (PySide6 desktop
widgets, zero business logic — everything they do is delegate to
`ui.run_actions` / `ui.dashboard_actions`, thin facades over
`services`). Full depth: `ARCHITECTURE.md`. Functional spec each piece
implements: `PROJECT_SPEC.md`. Engineering conventions (no `eval()`,
append-only audit trail, restricted rule engines): `AGENTS.md`.

## 2. Where the data actually lives

```
%LOCALAPPDATA%\OperationsAllocationTool\operations_allocation.db     (SQLite database)
%LOCALAPPDATA%\OperationsAllocationTool\artifacts\                   (generated files: source imports, allocation exports, distributed associate files, etc.)
```

Override: the `OPERATIONS_ALLOCATION_DATA_DIR` environment variable
redirects both, e.g. for a shared network location (see
`packaging/PACKAGING.md`). Check it first if someone's data "isn't
there" — `echo %OPERATIONS_ALLOCATION_DATA_DIR%`.

**Close the app before opening the `.db` file directly** — SQLite locks
it while running. Use [DB Browser for SQLite](https://sqlitebrowser.org/)
or the `sqlite3` CLI.

### Tables that reject direct SQL DELETE/UPDATE, by design

`run_configuration_snapshots`, `audit_logs`, `eligible_populations`,
`sampling_results`, `allocation_results`, `artifacts` all have SQLite
`BEFORE UPDATE`/`BEFORE DELETE` triggers that raise
`RAISE(ABORT, ...)` unconditionally. This is intentional — it's the
compliance/audit-trail guarantee the whole app is built around,
enforced at the database layer so no code path (including a raw SQL
tool) can quietly violate it. There is currently **no supported
hard-delete path** for a Run or Program — use **Archive** (see
`USER_GUIDE.md`) for anything reversible. If a genuine hard-delete
feature becomes necessary, it needs to be built deliberately (would
require dropping/recreating those triggers for that one operation) —
don't attempt it by hand against a live database.

### Schema version

`schema_metadata` table tracks a single integer version, checked
strictly at startup (`Database.initialize_schema()` in
`persistence/database.py`) — a mismatch raises `PersistenceError:
"Unsupported local database schema version."` New columns are added
via an idempotent `_migrate_pre_existing_tables()` ALTER TABLE step so
existing databases upgrade automatically; this only handles **adding
nullable columns**, not renames/removals/type changes.

## 3. There is no log file

Important and easy to assume otherwise: **this app does not write any
log file anywhere.** The only diagnostic trails are:

1. **The error dialog itself** — every user-facing error is a
   `QMessageBox` showing the exception's message text directly (see
   `RunDetailView._run_guarded` in `ui/run_detail_view.py`). **Ask the
   reporter for a screenshot or the exact copied text** — this is
   usually enough to identify which `OperationsAllocationError`
   subclass fired (see catalog below).
2. **The Activity Log panel** inside Run Detail — plain text, one line
   per successful action, but it's **session-only** (a `QPlainTextEdit`
   held in memory) and is lost the moment that Run Detail view closes
   or the app exits. If a reporter is still looking at it, get them to
   copy it before doing anything else.
3. **The persisted Audit Log** (View Audit Log button, or query
   `audit_logs` directly) — timestamp, action, previous/new state, OS
   username, and a metadata JSON blob, per Run. **Important
   limitation:** audit records are written *after* an action succeeds,
   so a failed/errored attempt leaves **no audit trail at all** — only
   completed actions show up here. If someone says "I clicked X and it
   failed," the audit log won't show that attempt.

Given this, **always ask for the exact error dialog text/screenshot
first** — it's often the only record that will ever exist of what went
wrong.

## 4. Exception catalog (`domain/exceptions.py`)

Every error the app can raise is a subclass of
`OperationsAllocationError`. Docstrings below are verbatim from source
— use them to map an error message to what actually happened:

| Exception | Meaning |
|---|---|
| `InvalidConfigurationError` | A program or setup configuration is structurally invalid |
| `InvalidStateTransitionError` | A Run transition is not permitted (moving out of sequence) |
| `DuplicateRunIdError` | A Run ID conflicts with an existing immutable Run |
| `InvalidAssociateConfigurationError` | An associate master or snapshot value is invalid |
| `SnapshotCreationError` | A frozen snapshot could not be created |
| `ManifestIntegrityError` | An execution manifest does not match its snapshot |
| `InvalidRunStateError` | Persistence received a state outside the approved state set |
| `PersistenceError` | Local (SQLite) persistence could not complete safely |
| `IdentifierNormalizationError` | A primary identifier value could not be normalized |
| `ValidationBlockedError` | Structural Critical validation issues prevent processing |
| `InvalidResolutionError` | A duplicate-identifier resolution record is malformed |
| `UnresolvedDuplicatesError` | Eligible population frozen with unresolved duplicate IDs |
| `SamplingConfigurationError` | Sampling configuration or inputs are invalid |
| `InsufficientCapacityError` | Total active-associate max capacity is below the sample count |
| `AboveTargetConfirmationRequiredError` | Finalizing allocation above target without explicit confirmation |
| `ArtifactAlreadyExistsError` | Writing an artifact would silently overwrite an existing file |
| `InvalidArtifactFilenameError` | An artifact filename is unsafe (e.g. path traversal) |
| `ArtifactSourceNotFoundError` | An imported artifact's source file cannot be found |
| `InvalidQcRuleError` | A QC rule configuration is structurally invalid/unsupported |
| `UnsupportedFileFormatError` | Input file format not supported (e.g. old `.xls`) |
| `ColumnMappingError` | A required source column cannot be found in an imported file |
| `AssignedItemNotFoundError` | An allocated identifier has no matching canonical source row |
| `OutlookUnavailableError` | Outlook/COM automation cannot be reached — non-fatal, plain-text draft still saved |
| `AssociateFileNotDistributedError` | Individual email requested for an associate not yet distributed to |
| `EmailTemplateError` | Email template references an unsupported placeholder / missing token value |
| `ConsolidationBlockedByExceptionsError` | Finalizing Consolidation with open critical exceptions and no override |
| `InvalidOverrideError` | A Consolidation override is missing required accountability fields |
| `InvalidQcResultError` | Imported QC row has an unrecognized outcome or unknown identifier |
| `InvalidErrorRuleError` | An error classification rule is structurally invalid |
| `InvalidErrorRecordError` | An imported error report row is missing its required identifier |
| `InvalidReturnedFileError` | A file picked in "Import Returned Files" isn't an actual Distribution work file |

## 5. Reproducing and verifying a fix

```powershell
cd operations-allocation-tool
uv run --frozen pytest -q                     # full suite (343 tests as of this writing)
uv run --frozen pytest tests/unit/test_X.py   # one file
```

`--frozen` is required until `uv.lock` is refreshed (see README) —
plain `uv run` will hang trying to re-resolve it over the network.

UI tests construct real PySide6 widgets against a real (temp-directory)
`AppContext` with `QT_QPA_PLATFORM=offscreen` — no visible window
needed, works over SSH/RDP/CI.

**Before declaring something fixed, prefer reproducing it as a new
test** (there's precedent throughout `tests/unit/` — see
`test_schema_migration.py` or the "Regression:" comments in
`test_ui_smoke.py` for the pattern) rather than only manually clicking
through it once. It stays fixed.

## 6. Rebuilding the packaged `.exe` after a fix

```powershell
cd operations-allocation-tool\packaging
rmdir /s /q build dist
..\.venv\Scripts\pyinstaller.exe operations_allocation.spec --noconfirm
```

Output: `packaging\dist\OperationsAllocationTool\` (ship the whole
folder). If the build fails with `PermissionError` on the dist folder,
the previous build's `.exe` is still running somewhere — close it
first (`taskkill /IM OperationsAllocationTool.exe /F`). Full detail:
`packaging/PACKAGING.md`.

## 7. Bug report checklist (what to collect from a reporter)

- [ ] Program ID and Run ID involved
- [ ] Exact error dialog text or a screenshot (see section 3 — this
      may be the *only* record that will ever exist)
- [ ] What action they clicked and what Run state it was in
- [ ] Whether it's reproducible, and with what input file if relevant
- [ ] Whether they're running the packaged `.exe` or from source (and
      which build/commit, if known)

*(Where these reports actually get filed/tracked is up to your team's
process — this repo doesn't include or assume any specific ticketing
system.)*

## 8. Enhancement request checklist

- [ ] Which Program(s) it affects, or whether it's general
- [ ] The workflow gap in plain terms — what can't be done today
- [ ] Whether it's a config-level change (many things — new fields, QC
      rules, error rules, email wording — need **zero code changes**,
      just Program Configuration edits, see `USER_GUIDE.md`) or a real
      code change
- [ ] Urgency/deadline if any

## 9. Known, already-fixed issues worth recognizing

If a report matches one of these, it's already fixed — check the
reporter is on a current build (rebuilt after the fix's commit):

- **Blank Random Seed field silently produced a Run with no seed at
  all**, failing later with `SamplingConfigurationError` on "Draw
  Sample" — fixed; a blank field now generates a real seed.
- **No Due Date field existed at all**, so every Run failed at "Send
  Emails" with `EmailTemplateError` — fixed; Setup now always collects
  and submits a due date.
- **Starter Program Configuration template shipped with empty email
  templates**, guaranteed to fail the moment Send Emails was clicked —
  fixed; the starter template now ships complete, working templates.
- **Starter filename pattern didn't include `{ASSOCIATE_ID}`**, so the
  second associate's file collided with the first
  (`ArtifactAlreadyExistsError`) — fixed.
- **A trailing space in `OPERATIONS_ALLOCATION_DATA_DIR`** (easy to
  introduce via Windows' environment variable editor) caused
  `sqlite3.OperationalError: unable to open database file` — fixed;
  the value is stripped automatically now.
- **Disabled accent/danger-styled buttons visually looked enabled**
  (solid blue/red) due to a CSS-style specificity ordering issue —
  fixed.
- **`&` in a couple of button/group labels was silently eaten** by
  Qt's keyboard-mnemonic parsing (e.g. "Import & Sample" rendered as
  "Import _Sample") — fixed; escaped as `&&` everywhere, with a test
  guarding against recurrence.
