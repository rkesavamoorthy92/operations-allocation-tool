# AGENTS.md

## Operations Allocation Tool — AI Development Instructions

This file defines the rules that AI coding agents must follow when working on this repository.

The agent must read and follow:

- PROJECT_SPEC.md
- ARCHITECTURE.md
- AGENTS.md

before modifying the project.

---

# 1. Core Objective

Build and maintain an offline-first Operations Allocation Tool for Windows.

The application will initially support the MX PT workflow but must remain generic and configurable so that other Operations programs can be added without rewriting the core engine.

---

# 2. Non-Negotiable Requirements

The following requirements must always be respected.

## Offline-first

The core application must work without internet access.

Do not introduce mandatory:

- Cloud APIs
- Cloud databases
- Remote services
- Web servers
- Internet dependencies

unless explicitly approved.

---

# 3. Program Agnostic Design

Never hard-code MX PT-specific business rules into the core engine.

MX PT is the first implementation and reference configuration.

Program-specific differences must be handled through configuration.

Examples of configurable elements:

- Input columns
- Output columns
- Response columns
- Sampling rules
- Allocation rules
- QC rules
- Error categories
- Error types
- Email templates

---

# 4. Business Rules

AI agents must not invent business rules.

If a requirement is ambiguous:

1. Identify the ambiguity.
2. Explain the possible interpretations.
3. Ask for clarification when necessary.
4. Do not silently choose a business rule that could affect operational results.

Technical implementation decisions may be made by the agent when they do not change business behavior.

---

# 5. Source Data Protection

Never modify original source files.

Never overwrite:

- Source Excel files
- Original associate files
- Original QC reports
- Original error reports

Always create new output files.

Never delete source data automatically.

---

# 6. Product / Item Identifier

Product ID is the primary identifier for the MX PT workflow.

Never use:

- Excel row number
- DataFrame row index
- File position

as the permanent identifier.

Use Product ID for:

- Allocation
- Consolidation
- Reconciliation
- QC matching
- Error matching

Product IDs must be treated as strings internally.

Normalization rules:

- Trim leading and trailing whitespace.
- Preserve leading zeros.
- Do not silently alter identifier values.
- Do not convert scientific notation into another value.
- Preserve both the original Product ID and the normalized Product ID.
- MX PT comparisons are case-sensitive unless explicitly configured otherwise.

If normalization creates a duplicate Product ID, create a duplicate-ID exception.

The architecture must allow future programs to define their own primary identifier.

---

# 7. Run ID and Run-Centric Design

Every allocation workflow must have a unique Run ID.

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

- Sequence resets daily per program.
- Run IDs are unique and **never reused**.

The **Run** is the central domain concept.

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

All related records must be traceable through the Run ID.

Every Run begins in a Draft/Setup state. The user configures Program, source file, sampling percentage or count, random seed or automatic seed, associate roster, targets, maximum capacities, due date, and other program-configured settings. Freeze the immutable Run Configuration Snapshot only after the user confirms setup.

The snapshot must contain:

- Program configuration version
- Column mappings
- Sampling configuration
- Random seed
- Associate targets
- Associate capacities
- Associate active/inactive status at snapshot freezing
- Associate experience/configuration and due date
- QC rules
- Error rules
- Email template configuration

Associate master data is global. Snapshot copies are authoritative for Run processing.

Historical Runs must continue to reference their original snapshot even if the current program configuration or associate master data changes.

After snapshot freezing, configuration used by the Run must not be silently changed.

---

# 8. Randomization

Random sampling must occur only after validation and user-approved exclusions/resolution.

Processing sequence:

```text
Input
→ Validation
→ User-approved exclusions / resolution
→ Freeze eligible population
→ Random sampling
```

The eligible population used for sampling must be recorded for auditability.

Random sampling must be reproducible when a seed is provided.

Always record:

- Eligible population count
- Eligible population membership
- Sampling method
- Sampling percentage or requested count
- Calculated sample count before rounding (for percentage sampling)
- Actual sample count
- Random seed
- RNG algorithm/version
- Sampling algorithm/version
- Canonical ordering/fingerprint of eligible population
- Run ID
- Timestamp

Percentage sampling must use explicit HALF-UP rounding to the nearest whole item. Do not use Python's default `round()` where it would produce a different result.

Example:

56,432 × 3% = 1,692.96 → 1,693

1,692.5 → 1,693

1,692.4 → 1,692

Never use uncontrolled randomness when the operation requires auditability.

Do not modify the source dataset during sampling.

Duplicate Product IDs require **manual resolution** before sampling may proceed. Do not automatically keep first or last records and do not silently merge. Exclude affected records from the eligible population until the user resolves them. Record original and normalized values, resolution action, user, timestamp, and reason.

---

# 8A. Data Validation

Validation must use these severity levels:

| Severity | Behavior |
|----------|----------|
| **Critical** | Blocks processing until resolved |
| **Warning** | Requires user acknowledgement where appropriate |
| **Information** | Does not block processing |

Critical failures block processing.

Duplicate Product IDs are Critical and require manual resolution before sampling.

---

# 9. Allocation

Allocation must support variable associate targets and capacities.

Do not assume equal distribution.

The allocation engine must detect:

- Insufficient capacity
- Unallocated items
- Duplicate allocations
- Invalid associates
- Inactive associates
- Unused capacity

Do not silently discard unallocated items.

Do not silently redistribute items when the redistribution rule has not been defined.

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

- **Target** is the normal allocation level.
- **Maximum Capacity** is the upper bound.
- Allocation above target but below maximum capacity requires **explicit user confirmation** before finalization.
- If sampled items exceed total target capacity but maximum capacity is sufficient, use the configured deterministic overflow strategy after explicit confirmation. V1 uses proportional distribution based on remaining capacity with Associate ID tie-breaking.

## Inactive Associates

Inactive associates are **automatically excluded** from allocation. They remain in the master roster for historical reference.

## Associate Master Data

Associate master data is **global**.

Target, capacity, experience/configuration, and run-specific associate settings are copied into the Run Configuration Snapshot when the user confirms Run setup.

Run processing must use the snapshot copy, not mutable master data alone.

---

# 10. Allocation Preview

Allocation must provide a preview before finalization.

The user must be able to see:

- Total items
- Eligible population count
- Sample count
- Associate count
- Target per associate
- Planned allocation
- Remaining items
- Capacity shortage
- Unused capacity
- Above-target allocation requiring confirmation
- Exceptions

Final allocation requires explicit confirmation.

Allocation above target but below maximum capacity requires a separate explicit confirmation.

Allocation finalization must be blocked when total maximum associate capacity is less than the sample count.

---

# 11. Consolidation

Returned associate files must be reconciled against the original allocation.

Associate files must expose identity at three levels:

1. **Filename** — `{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx`
2. **Metadata sheet** — Run ID, Program, Associate ID, Associate Name, Generation timestamp
3. **Data columns** — Run ID, Allocated To

Consolidation must cross-check all available identity information against the Run Configuration Snapshot and allocation records.

Associate ID is the authoritative machine identifier. Associate Name is display-only and must be sanitized for filenames.

The system must detect:

- Missing items
- Duplicate items
- Unexpected items
- Wrong associate
- Identity mismatches across filename, metadata, and data columns
- Incomplete files
- Invalid Run ID
- Conflicting response data

Wrong-associate rows must be **quarantined** for manual resolution.

Open **critical** exceptions block final consolidated export **by default**.

The user may **explicitly override** and finalize with open exceptions.

Overrides require user, timestamp, reason, and exception/reconciliation version, and must be audited.

Never assume a returned file is correct merely because it contains a valid Product ID.

Matching must use normalized Product ID values.

Maintain raw imported returned rows, reconciled valid rows, and quarantined/resolved rows used by final export as separate conceptual layers. Never silently choose between conflicting returned responses; require a versioned manual resolution record.

---

# 12. QC

QC calculations must be configurable by program.

QC rules must use a restricted declarative configuration model.

Do NOT use:

- `eval()`
- `exec()`
- Arbitrary Python expressions
- Unrestricted user-entered formulas

The initial supported rule type is:

- `ratio_percentage`

Configurable fields:

- `numerator`
- `denominator`
- `zero_denominator_behavior`

For MX PT, the initial intended calculation is:

Pass Count / Audited Count × 100

If Audited Count = 0, the QC result is **N/A**.

For MX PT, Error Rate is Fail Count / Audited Count × 100. If Audited Count = 0, Error Rate is N/A.

QC must support item-level, associate-level, and run-level metrics.

Do not hard-code this formula into the generic QC engine.

The engine must obtain the calculation rule from the Run Configuration Snapshot and evaluate it through the QC Rule Evaluator.

Never silently treat missing QC results as Pass.

---

# 13. Error Classification

Error reporting must support both **imported** and **generated** errors.

Error categories and types must be configurable by program.

Do not hard-code categories or taxonomies from other Operations programs.

Do not assume that MX PT uses the same error taxonomy as another program.

Error rules are frozen in the Run Configuration Snapshot for each Run.

Error processing for a Run must use the error rules stored in that Run's Configuration Snapshot.

---

# 14. Insights

Insights must be based on calculated and validated data.

The deterministic analytics engine is responsible for:

- Counts
- Percentages
- QC scores
- Error rates
- Trends
- Variances
- Comparisons
- Outliers

An AI/LLM must not be responsible for calculating operational metrics.

Historical comparison must use the **previous completed Run for the same Program**.

If no previous completed Run exists, historical comparison is **N/A**.

A Run is Completed only when consolidation is finalized, critical exceptions are resolved or explicitly overridden, and QC processing is completed.

If a future LLM is introduced, it should consume validated metrics and generate narrative summaries.

---

# 15. Auditability

Every important operation must be auditable.

Record:

- Run ID
- Program
- OS username
- Application display name
- Timestamp
- Input count
- Eligible population count
- Exclusion summary
- Sampling information (method, requested value, calculated count before rounding, actual sample count)
- Random seed
- RNG algorithm/version
- Sampling algorithm/version
- Eligible population membership/fingerprint
- Associate information
- Allocation count
- Capacity shortage indicators
- Unused capacity summary
- Consolidation status
- Consolidation override reason (when applicable)
- Consolidation override user, timestamp, and exception/reconciliation version (when applicable)
- QC results
- Error results
- Run Configuration Snapshot reference
- Output files
- Processing status

Do not remove audit information merely to simplify implementation.

---

# 16. Outlook

Outlook integration must create drafts only.

The application must NEVER automatically send emails.

In v1, due date is **entered by the user**.

Email templates must support these placeholders:

- `{{associate_name}}`
- `{{program_name}}`
- `{{run_id}}`
- `{{item_count}}`
- `{{due_date}}`

Email content must be dynamically generated from the current Run.

The Outlook implementation must remain isolated from the core business logic via the Outlook Platform Adapter.

V1 Outlook integration targets Classic desktop Outlook via COM on Windows. The application should remain usable if Outlook is unavailable and provide a manual email fallback.

---

# 17. UI Rules

Use PySide6 for the desktop UI.

The UI must not contain business logic.

Do not implement allocation algorithms directly inside UI event handlers.

Use application services.

Example:

Correct:

UI → AllocationService → AllocationEngine

Incorrect:

UI → allocation calculations → database

---

# 18. Separation of Concerns

Use clear separation between:

- UI
- Application services (including Program Configuration Service, Run Orchestration Service, Audit Service, and Reporting Service)
- Core business logic (including Allocation Strategy, Reconciliation Pipeline, and QC Rule Evaluator)
- Data access (including Associate Master)
- File processing (including File Artifact Manager)
- Reporting
- Outlook integration (via Outlook Platform Adapter)
- Error Rule Configuration

Follow `ARCHITECTURE.md` for Run State Machine, Run Configuration Snapshot, Canonical Item Model, Eligible Population, and service boundaries.

Avoid large monolithic files.

Avoid functions that perform unrelated responsibilities.

Prefer small, testable modules.

---

# 19. Python Standards

Use:

- Type hints where practical.
- Descriptive variable names.
- Small functions.
- Clear class responsibilities.
- Exceptions for exceptional conditions.
- Logging for important processing events.

Avoid:

- Global mutable state.
- Hard-coded file paths.
- Hard-coded user-specific paths.
- Hard-coded program-specific values.
- Unnecessary dependencies.

---

# 20. File Paths

Never hard-code paths such as:

/Users/kesavamoorthyr/...

or:

C:\Users\...

Use application-relative paths or configurable paths on development platforms.

On Windows, mutable production data must use a user-writable local application data directory.

Do **not** store mutable production data inside the EXE installation directory.

The application must work for different users.

---

# 21. Configuration

Configuration must be externalized where appropriate.

Do not embed program-specific configuration directly into Python source code.

Program configuration should be stored in:

- SQLite
- JSON
- Other explicitly approved configuration mechanisms

Program configuration must use a versioned, machine-validatable schema. It must cover Program ID, primary identifier, identifier normalization, case sensitivity, input and response columns, requiredness, data types, field ownership, output ordering, validation rules, allocation strategy, tie-breaking rules, QC mappings, error mappings, and filename behavior.

When Run setup is confirmed, freeze an immutable Run Configuration Snapshot containing:

- Program configuration version
- Column mappings
- Sampling configuration
- Random seed
- Associate targets
- Associate capacities
- QC rules
- Error rules
- Email template configuration

Historical Runs must continue to reference their original snapshot even if the current program configuration changes.

All Run processing must use the Run Configuration Snapshot, not mutable program settings.

## Immutable Evidence and Execution Manifest

The authoritative source is the imported local artifact associated with the Run, not a mutable external path. Record relevant parser/import settings.

Treat imported canonical source, eligible population, sampling result, allocation result, returned raw files, reconciliation records, artifact records, and execution manifest as immutable Run evidence. Corrections must use versioned resolution records/events rather than silently mutating history.

For every imported or generated artifact record SHA-256 hash, byte size, original filename, import/generation timestamp, Run ID, and artifact type. Never overwrite source artifacts. Generated outputs should use temporary-file plus atomic rename where practical.

Each Run must have an execution manifest containing Run ID, configuration snapshot hash, source artifact hash, eligible population hash, sampling algorithm/version, RNG algorithm/version, random seed, allocation strategy/version, and output artifact hashes.

## Run State Machine

Use and enforce these states:

```text
DRAFT → SNAPSHOT_FROZEN → VALIDATED → ELIGIBLE_POPULATION_FROZEN
→ SAMPLED → ALLOCATED → DISTRIBUTED → RETURNED → CONSOLIDATED
→ QC_COMPLETED → COMPLETED

DRAFT → CANCELLED | ABANDONED
Any non-terminal state → FAILED
```

Define and audit valid transitions. Prevent invalid transitions.

---

# 22. Testing Requirements

Every core engine must have unit tests.

At minimum:

- Validation
- Randomization
- Allocation
- Reconciliation
- QC
- Analytics

Tests must include normal and edge cases.

Examples:

- Empty input
- Duplicate IDs requiring manual resolution before sampling
- Missing IDs
- Validation severity (Critical/Warning/Information)
- Invalid percentages
- Zero capacity
- Insufficient capacity blocking finalization
- Excess capacity / unused capacity reporting
- Above-target allocation requiring confirmation
- Inactive associate exclusion
- Product ID normalization (whitespace, leading zeros, case sensitivity)
- Percentage sampling rounding
- Eligible population freeze before sampling
- Associate filename convention validation
- Duplicate returned records
- Missing returned records
- Invalid Run ID
- Associate file identity cross-check failures
- Wrong-associate row quarantine
- Consolidation override with audited reason
- Zero audited records (QC result N/A)
- Restricted QC rule evaluation (`ratio_percentage`)
- Historical comparison vs previous completed Run (and N/A when none)
- Run ID format and daily sequence uniqueness

---

# 23. Regression Protection

When fixing a bug:

1. Reproduce the bug.
2. Add a regression test.
3. Fix the implementation.
4. Run the regression test.
5. Run the complete test suite.

Do not remove or weaken a test simply because the current implementation fails it.

---

# 24. Dependency Management

Use `pyproject.toml` as the primary project configuration.

Do not install dependencies globally.

Use the project virtual environment during development.

Avoid adding a dependency when the standard library or an existing dependency can solve the problem adequately.

Before introducing a major dependency, explain why it is needed.

---

# 25. Database

Use SQLite for local persistence.

Database operations must be isolated from business logic.

Avoid direct SQL scattered throughout UI components.

Use a repository/data-access layer.

Do not store raw confidential operational data in logs.

---

# 26. Excel Processing

V1 supports `.xlsx` and `.csv` only. `.xls` is deferred.

V1 performance target: approximately **100,000 rows** per input file.

Use Pandas for data processing.

Use openpyxl and/or XlsxWriter for Excel-specific functionality.

Never assume:

- Column order
- Excel row number
- Sheet name
- Formatting
- Hidden columns

unless explicitly defined by the program configuration.

Column mapping must be used where possible.

---

# 27. Output Files

Generated output files must:

- Use meaningful names.
- Include Run ID where appropriate.
- Never overwrite source files.
- Be stored in the Run-specific output directory.

Example:

output/

    MX-PT-20260815-001/

        source/

        samples/

        allocation/

        associate_files/

        returned_files/

        consolidated/

        qc/

        errors/

        reports/

---

# 28. Logging

Use structured logging.

Include Run ID where available.

Logs should help diagnose:

- File processing failures
- Validation failures
- Allocation failures
- Consolidation failures
- QC processing failures
- Unexpected application errors

Do not log unnecessary product descriptions or sensitive operational content.

---

# 29. Error Handling

User-facing errors must be understandable.

Bad:

"KeyError: PT_COL_7"

Better:

"Required column 'PT' could not be found in the uploaded file."

Technical details should remain available in logs for debugging.

---

# 30. No Silent Data Loss

Never:

- Drop records silently.
- Ignore invalid records silently.
- Overwrite files silently.
- Skip errors silently.
- Reassign work silently.

If records are excluded, the application must show:

- Number excluded
- Reason
- Ability to inspect exceptions where practical

---

# 31. Agent Workflow

Before implementing a significant feature:

1. Read the specification.
2. Inspect the existing code.
3. Identify affected modules.
4. Explain the implementation approach.
5. Implement the smallest reasonable change.
6. Add tests.
7. Run tests.
8. Review the change for unintended side effects.

Do not rewrite unrelated modules.

---

# 32. Git Workflow

Make focused commits.

Preferred commit examples:

"Implement Excel validation"

"Add deterministic randomizer"

"Implement capacity-based allocation"

"Add consolidation reconciliation"

"Avoid giant commits containing unrelated features."

Do not rewrite Git history unless explicitly requested.

---

# 33. Scope Control

Do not introduce future features prematurely.

Examples:

Do not add:

- AI
- Cloud infrastructure
- Web application
- Authentication
- Multi-user server
- Automatic email sending

unless explicitly requested.

Build the reliable offline core first.

---

# 34. Definition of Done

A feature is not complete merely because the code runs.

A feature is complete when:

- Requirements are implemented.
- Code is modular.
- Unit tests exist.
- Tests pass.
- Edge cases are handled.
- Errors are understandable.
- Existing functionality remains intact.
- Documentation is updated where necessary.

---

# 35. Important Instruction

If a requirement conflicts with:

- PROJECT_SPEC.md
- ARCHITECTURE.md
- AGENTS.md

do not silently choose one.

Identify the conflict and request clarification.

The goal is to build a reliable Operations application, not merely to produce code quickly.

---

# 36. V1 Finalized Business Rules Summary

The following v1 business rules are non-negotiable. Do not implement alternatives without explicit approval.

## Allocation

1. Block final allocation if total available capacity is below sample count.
2. If capacity exceeds sample count, allocate only sampled items and show unused capacity.
3. Target is the normal allocation level.
4. Allocation above target but below maximum capacity requires explicit user confirmation.
5. Inactive associates are automatically excluded.
6. Associate master data is global; target, capacity, and run-specific settings are copied into the Run Snapshot.
7. Duplicate Product IDs require manual resolution before sampling.

## Sampling

8. Sample only from validated, user-approved eligible population.
9. Freeze and record eligible population for the Run.
10. Percentage sampling uses explicit HALF-UP rounding to nearest integer.
11. Store requested percentage, pre-round calculated count, and actual count.

## Product ID

12. Treat Product ID as string internally.
13. Trim leading/trailing whitespace.
14. Preserve leading zeros.
15. Preserve original and normalized Product ID.
16. Do not silently convert scientific notation.
17. MX PT matching is case-sensitive unless configured otherwise.
18. If normalization produces duplicates, create a duplicate-ID exception; do not auto-keep, merge, or sample affected records before manual resolution.

## Consolidation

19. Associate identity in filename, metadata sheet, and data columns.
20. Filename: `{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx`; Associate ID is authoritative and Associate Name is sanitized display text.
21. Metadata: Run ID, Program, Associate ID, Associate Name, Generation timestamp.
22. Data columns: Run ID, Allocated To.
23. Cross-check all available identity information.
24. Open critical exceptions block final consolidated export by default.
25. User may override with open exceptions only with user, timestamp, reason, and reconciliation version audited.
26. Wrong-associate rows are quarantined for manual resolution; conflicting response values also require manual resolution.

## QC

27. QC supports item-level, associate-level, and run-level metrics.
28. MX PT QC: Pass Count / Audited Count × 100; error rate: Fail Count / Audited Count × 100.
29. If Audited Count = 0, QC score and error rate are N/A.
30. QC rules use restricted declarative configuration.
31. No `eval()`, `exec()`, arbitrary Python expressions, or unrestricted formulas.

## Errors

32. Support imported and generated errors.
33. Error taxonomy is configurable by program.
34. Error rules are frozen in the Run Snapshot.

## Historical

35. Historical comparison uses previous completed Run for same Program; a Completed Run has finalized consolidation, resolved/overridden critical exceptions, and completed QC.
36. If none exists, historical comparison is N/A.

## Audit

37. Audit captures OS username and application display name.
38. Run ID format: `{PROGRAM}-{YYYYMMDD}-{SEQUENCE}`.
39. Sequence resets daily.
40. Run IDs are unique and never reused.

## Validation

41. Severity levels: Critical, Warning, Information.
42. Critical failures block processing.
43. Warnings require user acknowledgement where appropriate.
44. Information messages do not block processing.

## Input

45. V1 supports XLSX and CSV.
46. XLS is deferred.
47. V1 performance target: approximately 100,000 rows per input file.

## Outlook

48. V1 due date is entered by the user.
49. Email template tokens: `{{associate_name}}`, `{{program_name}}`, `{{run_id}}`, `{{item_count}}`, `{{due_date}}`.
50. Outlook creates drafts only; never automatically send messages.

## Windows

51. Packaged application data uses a user-writable Windows local application data directory.
52. Do not store mutable production data inside the EXE installation directory.

## Run Setup, Allocation, and Evidence

53. Snapshot freezing occurs only after user-confirmed Draft/Setup configuration.
54. Sampling records membership, canonical ordering/fingerprint, RNG algorithm/version, and sampling algorithm/version.
55. If sample count exceeds target but not maximum capacity, require confirmation and use v1 proportional remaining-capacity overflow with Associate ID tie-breaking.
56. Source, generated/system, and associate-response fields must remain distinct; source evidence must never be overwritten.
57. Immutable Run evidence and execution-manifest requirements in Section 21 are mandatory.
58. Enforce the Run State Machine in Section 21.
