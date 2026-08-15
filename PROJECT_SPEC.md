# Operations Allocation Tool — Project Specification

## 1. Project Overview

The Operations Allocation Tool is an offline-first Windows desktop application designed to replace repetitive manual Excel-based allocation, distribution, consolidation, quality analysis, and reporting workflows.

The application will initially be developed and validated using the MX Product Type (PT) workflow, but the underlying architecture must remain generic and configurable so that the same application can support other Operations programs in the future.

The final application will be distributed as a Windows executable (`.exe`) that can be installed and used without requiring internet connectivity.

---

# 2. Primary Objectives

The application must provide a single workflow for:

1. Importing and validating operational Excel/CSV files.
2. Dynamically selecting a percentage or number of items using controlled randomization.
3. Allocating selected items to associates based on configurable targets/capacity.
4. Splitting allocated work into associate-specific Excel files.
5. Creating dynamic Outlook email drafts for distribution.
6. Importing completed associate files.
7. Reconciling and consolidating completed files.
8. Importing QC results.
9. Calculating configurable QC metrics.
10. Importing or generating error reports.
11. Identifying trends, patterns, outliers, and operational insights.
12. Maintaining complete audit history for every allocation run.
13. Exporting operational reports and consolidated Excel files.

---

# 3. Core Design Principle

The application must be GENERIC and PROGRAM-CONFIGURABLE.

MX PT is the first implementation and reference workflow.

The application must NOT hard-code MX PT-specific columns, QC rules, error categories, or allocation rules into the core engine.

Instead, program-specific behavior must be controlled through configuration.

Example:

Program:
MX PT

Input fields:
Product ID
Product Name English
Short Description English
Long Description English
PT
PT Feedback
Correct PT
PT Key
Comments

Response fields:
Partner Feedback
Correct PT
PT Key
Comments

QC rule:
Pass / Audited × 100

A future program may have completely different fields and rules.

---

# 4. Application Modules

The application must contain the following major modules:

## 4.1 Dashboard

Provide an overview of:

- Current allocation run
- Input item count
- Sampled item count
- Allocated item count
- Associate count
- Consolidation status
- QC score
- Error count
- Completion status
- Recent runs

---

## 4.2 Program / Template Management

Users must be able to configure different operational programs.

Configuration should support:

- Program ID and name
- Primary identifier, normalization, and case-sensitivity rules
- Input and response column mappings
- Requiredness, data types, field ownership, and output ordering
- Validation rules
- Allocation rules
- Deterministic tie-breaking rules
- Sampling rules
- QC rules (restricted declarative model)
- Error configuration
- Output configuration
- Filename behavior
- Email template configuration

Program configuration must use a versioned, machine-validatable schema. It must be validated before it can be used to create a Run Configuration Snapshot.

When a Run is created, it begins in **Draft/Setup**. The user configures the Program, source file, sampling percentage or count, random-seed choice, associate roster, targets, maximum capacities, due date, and other program-configured settings. The active program configuration and final setup values are copied into an immutable Run Configuration Snapshot only when the user confirms the Run setup.

After the snapshot is frozen, configuration used by the Run must not be silently changed.

See `ARCHITECTURE.md` for Run-centric design and service boundaries.

The first program will be:

MX PT

---

# 5. Input Data

## V1 Supported Formats

The application must accept the following operational data formats in v1:

- `.xlsx`
- `.csv`

`.xls` support is deferred beyond v1.

## V1 Performance Target

The application should support input files of approximately **100,000 rows** per file in v1.

The original source file must never be modified. The authoritative processed source must be an imported local artifact associated with the Run, rather than a mutable external file path. Relevant parser and import settings must be recorded with that artifact.

---

# 6. MX PT Initial Input Structure

The first implementation should support the following fields.

## Required / Expected Fields

- Product ID
- Product Name English
- Short Description English
- Long Description English
- PT
- PT Feedback
- Correct PT
- PT Key
- Comments

The allocation process will also generate:

- Allocated To

These fields must be configurable through column mapping rather than permanently hard-coded.

The configuration must distinguish source fields, generated/system fields, and associate-editable response fields. For MX PT, Product ID, Product Name, Short Description, Long Description, and PT are source evidence. Partner Feedback, Correct PT, PT Key, and Comments are associate response fields. If a source file contains columns with response-style names, its original values must be preserved separately from returned associate values.

---

# 7. Product ID

Product ID is the primary unique identifier for an item in the MX PT workflow.

The application must:

- Validate that Product ID exists.
- Detect blank Product IDs.
- Detect duplicate Product IDs.
- Use Product ID for reconciliation.
- Never use Excel row number as the permanent item identifier.

## Product ID Normalization

Product IDs must be treated as strings internally.

Normalization rules:

- Trim leading and trailing whitespace.
- Preserve leading zeros.
- Do not silently alter identifier values.
- Do not convert scientific notation into another value.
- Preserve both the original Product ID and the normalized Product ID.
- MX PT comparisons are case-sensitive unless explicitly configured otherwise.

All allocation, consolidation, QC, and error matching must use the normalized Product ID unless audit inspection requires the original value.

If normalization creates a duplicate Product ID, the system must create a duplicate-ID exception.

---

# 8. Data Validation

Before allocation, the application must validate the uploaded dataset.

Validation should identify:

- Missing required columns
- Missing Product IDs
- Duplicate Product IDs
- Empty datasets
- Invalid values
- Unsupported file formats
- Unexpected data structures

The user must be shown a validation summary before proceeding.

Example:

Total Rows:
56,432

Valid Rows:
56,420

Duplicate IDs:
12

Missing IDs:
0

## Validation Severity

Validation results must use the following severity levels:

| Severity | Behavior |
|----------|----------|
| **Critical** | Blocks processing until resolved |
| **Warning** | Requires user acknowledgement where appropriate; does not block by itself |
| **Information** | Informational only; does not block processing |

Critical failures block processing.

Warnings require user acknowledgement where appropriate.

Information messages do not block processing.

## Duplicate Product IDs

Duplicate Product IDs are a **Critical** validation issue.

Duplicate Product IDs require **manual resolution** before sampling may proceed. In v1, the system must not automatically keep the first or last record and must not silently merge duplicates. Affected records are excluded from the eligible population until resolved.

The user should not be allowed to proceed if critical validation failures exist unless the user explicitly resolves or excludes the affected records.

For every duplicate-ID resolution or exclusion, record original and normalized identifier values, resolution action, user, timestamp, and reason.

## Validation and Sampling Sequence

Sampling must occur only after validation.

Processing sequence:

```text
Input
→ Validation
→ User-approved exclusions / resolution
→ Freeze eligible population
→ Random sampling
```

The eligible population used for sampling must be recorded for auditability and reproducibility.

---

# 9. Randomizer

The randomizer must allow the user to dynamically specify the sampling requirement.

Supported options should include:

- Percentage-based sampling
- Fixed-number sampling

Example:

Total valid items:
56,432

Sampling percentage:
3%

Expected sample:
1,693

The randomizer must:

- Operate only on the frozen eligible population for the Run.
- Select unique items.
- Use normalized Product ID as the unique identifier.
- Never modify the original dataset.
- Record the sampling method.
- Record the requested percentage or requested count.
- Record the calculated sample count before rounding (for percentage sampling).
- Record the actual sample count after rounding.
- Record the eligible population count.
- Record eligible population membership.
- Record canonical ordering and fingerprint of the eligible population.
- Record the random seed.
- Record RNG algorithm and version.
- Record sampling algorithm and version.
- Record timestamp.
- Associate the sample with a Run ID.

## Percentage Sampling Rounding

Percentage sampling must use explicit **HALF-UP** rounding to the nearest whole item. Python's default `round()` must not be used where it would produce a different result.

Example:

56,432 × 3% = 1,692.96 → 1,693

1,692.5 → 1,693

1,692.4 → 1,692

The system must store:

- Requested percentage
- Calculated sample count before rounding
- Actual sample count

---

# 10. Random Seed

Randomization must support a reproducible random seed.

The user may choose:

- Automatic seed
- User-defined seed

The seed must be stored with the allocation run.

If the same source dataset, eligible population, sampling configuration, and random seed are used, the randomizer should produce the same selection.

This is required for auditability and reproducibility.

---

# 11. Allocation

After random sampling, the selected items must be allocated to associates.

Allocation must support configurable allocation strategies.

Initial strategy:

Target / Capacity-based allocation.

The system must support associates with different workload capacities.

Example:

Associate A:
Target = 50

Associate B:
Target = 50

Associate C:
Target = 100

Associate D:
Target = 100

The system must not assume equal allocation across associates.

## Insufficient Capacity

If total maximum capacity is less than the sample count:

- Allocation finalization must be blocked.
- The user must see the shortage clearly.
- The system must not silently discard items.
- The system must not silently redistribute items.
- The user can resolve the issue by changing associates, targets, capacity, or sampling configuration.

## Excess Capacity

If total maximum capacity is greater than the sample count:

- Allocate only the sampled items.
- Do not automatically increase sampling.
- Show unused capacity in the allocation preview.

## Target and Maximum Capacity

- **Target** is the normal allocation level for an associate.
- **Maximum Capacity** is the upper bound for that associate in the Run.
- Allocation above target but below maximum capacity requires **explicit user confirmation** before finalization.
- When sampled items exceed total target capacity but total maximum capacity is sufficient, overflow must be distributed deterministically using the configured overflow strategy. The v1 strategy is proportional distribution based on remaining capacity, with Associate ID tie-breaking.
- The system must not silently redistribute work.

## Inactive Associates

Inactive associates are **automatically excluded** from allocation. They remain in the global master roster for historical reference.

---

# 12. Associate Configuration

Associate master data is **global** across the application.

Minimum master fields:

- Associate ID
- Associate Name
- Email
- Team / Program
- Experience Level
- Target
- Maximum Capacity
- Active / Inactive status

Target, maximum capacity, experience/configuration, and other run-specific associate settings are copied into the **Run Configuration Snapshot** when the user confirms Run setup and the snapshot is frozen.

Run processing must use the snapshot copy, not mutable master data alone.

The system must support new associates with lower targets and experienced associates with higher targets.

---

# 13. Allocation Preview

Before final allocation, the application must provide a preview.

The preview should display:

- Total input items
- Valid items
- Eligible population count
- Sampling percentage
- Sample count
- Number of associates
- Target allocation per associate
- Total planned allocation
- Remaining items
- Capacity shortage (if total maximum capacity is less than sample count)
- Unused capacity (if total maximum capacity exceeds sample count)
- Capacity issues
- Allocation above target requiring confirmation
- Allocation exceptions

The user must explicitly confirm the allocation before final output is generated.

Allocation above target but below maximum capacity requires a separate explicit user confirmation.

Allocation finalization must be blocked when total maximum associate capacity is less than the sample count.

---

# 14. Run

Every allocation execution must generate a unique Run ID.

## Run ID Format

Run IDs must follow this format:

```text
{PROGRAM}-{YYYYMMDD}-{SEQUENCE}
```

Example:

```text
MX-PT-20260815-001
```

Rules:

- `{PROGRAM}` identifies the operational program.
- `{YYYYMMDD}` is the Run creation date.
- `{SEQUENCE}` is a daily sequence number starting at `001`.
- The sequence resets daily per program.
- Run IDs are unique and **never reused**.

The **Run** is the central domain concept in the application. Every Run begins in a Draft/Setup state.

A Run connects:

- Source input
- Run Configuration Snapshot
- Eligible population
- Sampling
- Allocation
- Distribution
- Returned files
- Consolidation
- QC
- Errors
- Insights
- Audit
- Artifacts

The Run ID must be associated with all of the above.

## Run Configuration Snapshot

When the user confirms Run setup, the system must freeze an immutable Run Configuration Snapshot containing:

- Program configuration version
- Column mappings
- Sampling configuration
- Random seed
- Associate targets
- Associate capacities
- Associate experience/configuration and active/inactive status
- Due date
- QC rules
- Error rules
- Email template configuration

Historical Runs must continue to reference their original configuration even if the current program configuration changes.

All Run processing must use the Run Configuration Snapshot, not mutable program settings.

## Run State Machine

The system must define and enforce these states and valid transitions:

```text
DRAFT → SNAPSHOT_FROZEN → VALIDATED → ELIGIBLE_POPULATION_FROZEN
→ SAMPLED → ALLOCATED → DISTRIBUTED → RETURNED → CONSOLIDATED
→ QC_COMPLETED → COMPLETED

DRAFT → CANCELLED | ABANDONED
Any non-terminal state → FAILED
```

Transitions must be auditable and invalid transitions must be prevented.

## Execution Manifest and Immutable Evidence

Each Run must have an execution manifest containing:

- Run ID
- Configuration snapshot hash
- Source artifact hash
- Eligible population hash
- Sampling algorithm and version
- RNG algorithm and version
- Random seed
- Allocation strategy and version
- Output artifact hashes

The execution manifest supports reproducibility and auditability. Imported canonical source, eligible population, sampling result, allocation result, returned raw files, reconciliation records, artifact records, and the execution manifest are immutable Run evidence. Corrections must be represented through versioned resolution records or events rather than silently mutating historical evidence.

---

# 15. Associate File Splitting

After allocation, the application must generate separate Excel files for each associate.

Each file must contain only the items assigned to that associate.

Associate files must expose identity at three levels:

### A. Filename

The v1 filename convention is:

```text
{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx
```

Example:

```text
MX-PT_A001_Kumar_MX-PT-20260815-001.xlsx
```

Associate ID is the authoritative machine identifier. Associate Name is display-only and must be sanitized for filenames.

### B. Metadata Sheet

Each associate file must include a metadata sheet containing:

- Run ID
- Program
- Associate ID
- Associate Name
- Generation timestamp

### C. Data Columns

The data sheet must contain:

- Run ID
- Allocated To

Consolidation must cross-check filename, metadata sheet, and data-column identity against the Run Configuration Snapshot and allocation records.

The original master allocation dataset must remain unchanged.

---

# 16. Associate Work File

For the MX PT program, the minimum associate-facing fields include:

- Product ID
- Product Name
- Short Description
- Long Description
- PT
- Partner Feedback
- Correct PT
- PT Key
- Comments
- Allocated To

The application must allow program-specific response fields to be configured.

---

# 17. Associate Response Fields

When associates complete the assigned work, they may provide or update fields such as:

- Partner Feedback
- Correct PT
- PT Key
- Comments

The exact response fields must be configurable by program and stored separately from source evidence.

The consolidation engine must not assume that every program uses the same response fields.

---

# 18. Outlook Draft Generation

The application must be able to generate Outlook email drafts based on the allocation.

The email content must be dynamic.

## V1 Due Date

In v1, the due date is **entered by the user**.

## Email Template Tokens

Email templates must support the following placeholders:

- `{{associate_name}}`
- `{{program_name}}`
- `{{run_id}}`
- `{{item_count}}`
- `{{due_date}}`

The draft may also contain instructions and attachments.

The application must support:

1. Consolidated team email draft.
2. Individual associate email drafts.

The application must **NEVER** automatically send emails.

Outlook creates drafts only. The user must review and send the draft manually.

Outlook integration is Windows-specific and should be isolated from the core business logic via the Outlook Platform Adapter. V1 supports Classic desktop Outlook through COM on Windows. If Outlook is unavailable, core allocation workflow must continue and provide a manual email fallback.

---

# 19. Consolidation

The application must support importing completed associate files.

Users should be able to select multiple returned files at once.

The consolidation engine must:

1. Identify the Run ID from filename, metadata sheet, and data columns.
2. Identify the associate from filename, metadata sheet, and data columns.
3. Cross-check Run ID, Program, Associate ID, Associate Name, and Allocated To across all identity levels.
4. Match records using normalized Product ID.
5. Compare returned records against the original allocation.
6. Detect missing items.
7. Detect duplicate items.
8. Detect unexpected items.
9. Detect incorrect associate assignments.
10. Detect identity mismatches across filename, metadata, and data columns.
11. Detect incomplete returned files.
12. Detect invalid Run ID references.
13. Generate a consolidated master dataset.

Consolidation must maintain three conceptual layers:

1. Raw imported returned rows.
2. Reconciled valid rows.
3. Quarantined or resolved rows used by final export.

The system must never silently choose between conflicting returned responses. Conflicting values require manual resolution.

---

# 20. Consolidation Reconciliation

Example:

Allocated:
1,693

Returned:
1,512

Missing:
181

Duplicates:
2

Unexpected:
4

The application must display reconciliation results before final consolidation.

The user must be able to inspect exceptions.

## Critical Exceptions and Final Export

Open **critical** exceptions block final consolidated export **by default**.

Critical exceptions include missing allocated items, duplicate items, wrong-associate items, unexpected items, invalid Run IDs, and conflicting response data.

The user may **explicitly override** and finalize with open exceptions.

Overrides require user, timestamp, reason, and exception/reconciliation version, and must be audited.

## Wrong-Associate Rows

Rows detected as assigned to the wrong associate must be **quarantined** for manual resolution.

They must not be silently merged into the consolidated output.

---

# 21. Consolidated Output

The final consolidated file must preserve:

- Original item information
- Allocation information
- Associate response information
- Run ID
- Associate information
- Relevant metadata

The consolidated file should be exportable as Excel.

---

# 22. QC Module

The application must support importing QC reports.

QC rules must be configurable by program and must use a restricted declarative configuration model.

The application must NOT use `eval()`, `exec()`, arbitrary Python expressions, or unrestricted user-entered formulas for QC calculation.

The initial supported rule type is:

- `ratio_percentage`

Configurable fields:

- `numerator`
- `denominator`
- `zero_denominator_behavior`

For the initial MX PT workflow, the intended calculation is:

Pass Count / Audited Count × 100

If Audited Count = 0, the QC result is **N/A**.

For MX PT, Error Rate is Fail Count / Audited Count × 100. If Audited Count = 0, Error Rate is **N/A**.

Example:

Audited:
10

Pass:
8

Fail:
2

QC Score:
80%

QC calculations must use the QC rules stored in the Run Configuration Snapshot for that Run.

For MX PT v1, when the denominator (Audited Count) is zero, the QC result is **N/A**.

---

# 23. QC Metrics

QC must support metrics at three levels:

- **Item-level**
- **Associate-level**
- **Run-level**

The application should calculate at minimum:

- Items audited
- Pass count
- Fail count
- QC score (or N/A when Audited Count = 0)
- Error rate

The application should support:

- Overall QC score
- Associate-level QC score
- Run-level QC score
- Program-level QC score
- Historical QC trend

---

# 24. Error Reporting

Error reporting must support both **imported** and **generated** errors.

Error reporting must be configurable by program.

Error categories and types must NOT be hard-coded.

Do not hard-code error taxonomies from other Operations programs.

Each program may define its own:

- Error categories
- Error types
- Error fields
- Error severity
- Error classification rules

MX PT may have one error structure while another program may use a completely different structure.

Error rules are frozen in the Run Configuration Snapshot for each Run.

Error processing for a Run must use the error rules stored in that Run's Configuration Snapshot.

---

# 25. Insights Engine

The application must generate insights from:

- Allocation data
- Consolidated data
- QC data
- Error data
- Historical runs

Initial deterministic insights should include:

- QC trend
- Change from previous run
- Top error categories
- Error frequency
- Associate-level performance
- Category-level patterns where available
- Outliers
- Completion rate
- Allocation utilization
- Missing / duplicate trends

Insights should be calculated using deterministic data-processing rules.

AI-generated narrative summaries may be introduced as a later enhancement.

---

# 26. Historical Comparison

The system must maintain historical run information.

Historical comparison must use the **previous completed Run for the same Program**.

If no previous completed Run exists, historical comparison is **N/A**.

A Run is **COMPLETED** only when consolidation is finalized, critical exceptions are resolved or explicitly overridden, and QC processing is completed.

Users should be able to compare:

- Current QC vs previous completed run
- Current error rate vs previous completed run
- Associate performance over time
- Program performance over time
- Allocation completion over time

Percentage-point changes should be clearly distinguished from percentage changes.

Example:

Previous QC:
94.2%

Current QC:
91.7%

Change:
-2.5 percentage points

---

# 27. Audit

Every major operation must generate an audit record.

Audit information should include:

- Run ID
- Program
- OS username
- Application display name
- Timestamp
- Source file
- Input count
- Valid count
- Eligible population count
- Exclusion summary
- Sampling method
- Sampling percentage or requested count
- Calculated sample count before rounding
- Actual sample count
- Random seed
- RNG algorithm/version
- Sampling algorithm/version
- Eligible population membership/fingerprint
- Associate count
- Allocation count
- Capacity shortage indicators
- Unused capacity summary
- Consolidation count
- QC count
- Error count
- Consolidation override reason (when applicable)
- Consolidation override user, timestamp, and exception/reconciliation version (when applicable)
- Run Configuration Snapshot reference
- Output files
- Processing status

The audit history must allow the user to understand how a run was processed.

---

# 28. Offline Requirement

The application must be offline-first.

Core functionality must work without internet connectivity.

The application must not require:

- Cloud database
- External API
- Web server
- Internet connection

Local storage should use SQLite.

Excel files should be processed locally.

AI functionality, if introduced later, should support a local/offline model where practical.

---

# 29. Windows Application

The final application must be distributed as a Windows executable.

Target:

AllocationTool.exe

The application should eventually be packaged using PyInstaller or an equivalent packaging mechanism.

## Application Data Storage

Packaged application data must use a **user-writable Windows local application data directory**.

Do **not** store mutable production data inside the EXE installation directory.

Mutable data includes:

- SQLite database
- Run output artifacts
- Logs
- Application settings

The development environment may be macOS, but Windows testing is mandatory before production release.

Windows-specific functionality must remain behind platform interfaces. Core business logic must remain platform-independent.

---

# 30. Technology Direction

Initial technology stack:

- Python
- Pandas
- openpyxl
- XlsxWriter
- PySide6
- SQLite
- pytest
- pywin32 for Windows Outlook integration
- PyInstaller for Windows packaging

The application should use a modular, Run-centric architecture.

See `ARCHITECTURE.md` for:

- Program Configuration Service
- Run Orchestration Service
- Run State Machine
- Run Configuration Snapshot
- Associate Master
- Canonical Item Model
- Eligible Population
- Allocation Strategy
- Reconciliation Pipeline
- QC Rule Evaluator
- Error Rule Configuration
- File Artifact Manager
- Outlook Platform Adapter
- Audit Service
- Reporting Service

UI logic must be separated from business logic.

---

# 31. Future Enhancements

Potential future capabilities include:

- Additional Operations programs
- Advanced allocation strategies
- More configurable QC calculations
- Advanced error analytics
- Historical dashboards
- Local AI-generated management summaries
- Local LLM integration
- Additional email providers
- Configuration import/export
- Role-based access
- Application update mechanism
- Windows installer
