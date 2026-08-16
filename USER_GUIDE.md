# User Guide — Operations Allocation Tool

This guide walks through the app screen-by-screen, in the order you'd
actually use it. Everything here reflects exactly what the app does
today — no aspirational or planned features are described.

## What this tool does

It replaces manual Excel-based work for allocating a batch of items
(e.g. products needing a Quality Control review) across a team of
associates, and tracks that batch of work from start to finish:
**Import → Sample → Allocate → Distribute → Return → Consolidate → QC
→ Errors → Reports**, with a permanent audit trail of who did what and
when.

It runs entirely on your own machine — no internet connection needed,
no server. Your data lives in a local file (see "Where your data
lives" below).

## Two core concepts: Programs and Runs

- **A Program** is a reusable *template*: what columns your source
  files have, how QC scores are calculated, what counts as an error,
  what your emails say, etc. You set this up once per type of work
  (e.g. "MX-PT").
- **A Run** is one actual batch of work under a Program — e.g. "this
  week's MX-PT allocation." You create a new Run every time you need
  to process a new batch. A Run moves through a fixed sequence of
  states (see below); it never skips steps and never goes backwards.

## The Dashboard (the screen you land on)

Two tables:

- **Programs** — lists every Program you've created. Double-click a row
  to edit its configuration. Buttons: **+ New Program**, **Edit
  Configuration**, **Archive Selected Program**, **Restore Selected
  Program**.
- **Runs** — lists every Run across every Program, newest first, with
  its current state color-coded (gray = not started, amber = in
  progress, green = Completed, red = Cancelled/Failed). Double-click a
  row to open that Run. Buttons: **+ New Run**, **Archive Selected
  Run**, **Restore Selected Run**.

The **"Show archived Programs & Runs"** checkbox at the top toggles
whether archived items are visible. Archiving is *never* permanent
deletion — see "Archiving" below.

## Setting up a Program

Click **+ New Program**, give it a short ID (e.g. `MX-PT`, uppercase
letters/digits/hyphens only) and a name. It starts with no
configuration. Double-click it (or use **Edit Configuration**) to open
the configuration editor.

The configuration editor is a **JSON text editor**, not a set of
individual form fields — this is deliberate: the same validation rules
the rest of the app uses are applied directly to whatever you type, so
what you see is exactly what will be accepted, with no separate "form"
that could drift out of sync. It starts you off with a working starter
template you can edit, covering:

- `primary_identifier` — which column uniquely identifies each item
- `input_columns` / `response_columns` — your source file's column
  layout
- `sampling` — which sampling methods are allowed (`percentage`,
  `count`)
- `allocation` — the allocation strategy
- `qc` / `errors` — QC scoring rules and error classification rules
- `filename` — the pattern used to name each associate's work file
  (must include `{ASSOCIATE_ID}` or every associate gets the same
  filename and the second one fails)
- `email` — the Outlook draft templates (subject/body, with
  `{{placeholders}}` like `{{associate_name}}`, `{{item_count}}`,
  `{{due_date}}`)

Click **Validate** to check it before saving, and **Save New Version**
to commit it. Every save creates a **new version** — nothing is ever
edited in place, so a Run that already started stays tied to the exact
configuration it was frozen with, even if you change the Program's
configuration afterward.

## Creating and running a Run

Click **+ New Run**, pick the Program. This opens the Run Detail
screen. Every available action is grouped into six checklist sections;
buttons outside your current step are grayed out.

### 1. Setup
- **Freeze Setup…** — opens a dialog to enter the Sampling Method
  (`count` or `percentage`) and value, an optional Random Seed (leave
  blank and one is generated for you — this matters for reproducing
  exactly which items get picked), a Due Date (shown to associates in
  their email), and the associate roster (Associate ID, Name, Email,
  Target, Max Capacity — use **+ Add Associate**/**- Remove Selected**
  to edit rows). Confirming this **freezes** the Run's setup
  permanently — the configuration snapshot behind it can't be
  silently changed afterward.
- **Cancel Run** — only available before Setup is frozen.

### 2. Import & Sample
- **Import Source File & Validate…** — pick your `.xlsx` or `.csv`
  source file. You'll see a log line with total rows, valid rows,
  critical issues, and duplicate identifier groups found.
- **Freeze Eligible Population** — if duplicates were found, you must
  resolve each group first (a dialog lets you choose "Exclude all" or
  "Keep row N" per group, plus one shared reason for all of them).
  Freezing this locks in exactly which items are eligible.
- **Draw Sample** — randomly selects items using the seed from Setup.

### 3. Allocate & Distribute
- **Preview Allocation** — shows planned counts per associate without
  committing anything; safe to run repeatedly.
- **Finalize Allocation** — commits the real assignment of sampled
  items to associates.
- **Distribute Associate Files** — writes one Excel work file per
  associate to the artifacts folder for this Run.
- **Send Individual Emails (Outlook)** / **Send Consolidated Email
  (Outlook)** — drafts real Outlook emails per associate (individual)
  or one team summary (consolidated). **Requires desktop Outlook to be
  installed** — if it isn't, a plain-text draft is still saved to disk
  as a fallback and the Run is not blocked.

### 4. Consolidate & QC
- **Import Returned Files…** — pick the files associates send back.
  These must be the *actual work files Distribution generated*, not
  the original source file or anything else — the dialog tries to
  guess which associate a file belongs to from its filename, but you
  confirm it.
- **Finalize Consolidation** — reconciles what was returned against
  what was allocated. If there are open critical issues (missing
  items, duplicates, unexpected items, wrong-associate items, identity
  mismatches), it's **blocked** unless you explicitly override with a
  typed reason — there is no way to override silently.
- **Import QC Report…** — imports QC results and calculates the QC
  score per your Program's configured QC rules.

### 5. Errors & Reports
- **Generate Errors From Consolidation** — auto-builds error records
  from the Run's own reconciliation exceptions.
- **Import Error Report…** — imports externally-tracked errors.
- **Export Error Report…** — saves an Excel error report.
- **View Insights** — shows allocation utilization per associate,
  completion rate, error frequency/categories, associate QC
  performance, outliers, and a historical comparison against the
  **previous COMPLETED Run for the same Program** (shows "N/A" if
  there isn't one yet).
- **Export Run Summary Report…** — saves a multi-sheet Excel summary.

### 6. Finish
- **Mark Run Completed** — the final step.
- **View Audit Log** — every action taken on this Run, with timestamp,
  who did it (your Windows username), and the state change — permanent
  and cannot be edited or deleted, by anyone, including through this
  app.

## Archiving (not permanent deletion)

Use **Archive Selected Program/Run** to hide something from the
Dashboard without losing any data — nothing is erased, and it's fully
recoverable via **Restore Selected**. You must type the exact
Program/Run ID to confirm before it archives, to prevent accidental
clicks. Archiving a Program also archives all of its Runs (so they
don't linger, orphaned, on the Dashboard); restoring a Program does
**not** bring its Runs back automatically — restore those individually
if you want them visible again.

## Where your data lives

Everything is stored in one SQLite database file at:

```
%LOCALAPPDATA%\OperationsAllocationTool\operations_allocation.db
```

Generated files (associate work files, exports, etc.) are alongside it
in an `artifacts\` folder. See `SUPPORT_GUIDE.md` if you ever need to
inspect this directly.
