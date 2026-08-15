# Operations Allocation Tool — Architecture

## 1. Architecture Principles

The application must follow these principles:

1. Offline-first.
2. Modular.
3. Program-configurable.
4. Testable.
5. Auditable.
6. Excel-compatible.
7. UI and business logic must be separated.
8. Business rules must not be duplicated across UI components.
9. Source files must never be modified.
10. Every major processing operation must be traceable to a Run ID.
11. **Run-centric design** — the Run is the central domain concept connecting all workflow stages.
12. **Immutable run configuration** — historical Runs must retain their original configuration even when program settings change.

---

# 2. Run-Centric Architecture

The **Run** is the central domain concept in the application.

A Run connects:

- Source input
- Run Configuration Snapshot
- Eligible population
- Sampling
- Allocation
- Distribution (associate files, Outlook drafts)
- Returned files
- Consolidation
- QC
- Errors
- Insights
- Audit events
- Artifacts

All processing, persistence, audit records, and output files for a workflow execution must be associated with exactly one Run ID.

Historical Runs must continue to reference their original Run Configuration Snapshot even if the current program configuration is edited later.

---

# 3. High-Level Architecture

The application uses a layered desktop architecture with explicit run orchestration and configuration services.

```text
┌──────────────────────────────────────────────────────────────┐
│                         PySide6 UI                           │
│                                                              │
│ Dashboard | Allocation | Consolidation | QC | Errors         │
│ Insights | Audit | Program Settings                          │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                   Application Services                       │
│                                                              │
│ Program Configuration Service                                │
│ Run Orchestration Service                                    │
│ Allocation Service                                           │
│ Consolidation Service                                        │
│ QC Service                                                   │
│ Error Service                                                │
│ Insights Service                                             │
│ Audit Service                                                │
│ Reporting Service                                            │
│ Outlook Service (via Outlook Platform Adapter)               │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                       Core Engine                            │
│                                                              │
│ Validation Engine                                            │
│ Randomizer                                                   │
│ Allocation Strategy (Target / Capacity)                      │
│ Reconciliation Pipeline                                      │
│ QC Rule Evaluator                                            │
│ Analytics Engine                                             │
└────────────────────────────┬─────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│   Data Access   │ │ File Processing │ │  Infrastructure     │
│                 │ │                 │ │                     │
│ SQLite          │ │ Pandas          │ │ File Artifact Mgr   │
│ Repositories    │ │ openpyxl        │ │ Outlook Platform    │
│ Run Snapshot    │ │ XlsxWriter      │ │ Adapter             │
│ Associate Master│ │                 │ │                     │
│ Audit Store     │ │                 │ │                     │
└────────┬────────┘ └────────┬────────┘ └──────────┬──────────┘
         │                   │                     │
         ▼                   ▼                     ▼
    SQLite DB           Excel / CSV         Run output tree
```

---

# 4. Application Services

## 4.1 Program Configuration Service

Manages operational program definitions and editable program settings.

Responsibilities:

- Create, read, update program configuration
- Manage program configuration versions
- Validate the versioned, machine-validatable configuration schema before use
- Validate primary identifier, normalization, case-sensitivity, input and response columns, requiredness, data types, field ownership, output ordering, validation rules, allocation strategy, tie-breaking rules, QC mappings, error mappings, filename behavior, and email templates
- Provide the active program configuration to Run Orchestration when a new Run is created

Program configuration is mutable. Runs must never read mutable program settings directly after creation; they must use the Run Configuration Snapshot.

## 4.2 Run Orchestration Service

Coordinates the end-to-end lifecycle of a Run.

Responsibilities:

- Create Runs and assign Run IDs using the format `{PROGRAM}-{YYYYMMDD}-{SEQUENCE}`
- Reset sequence daily per program; ensure Run IDs are unique and never reused
- Create the Run in `DRAFT` and coordinate user-confirmed Run setup
- Persist the immutable Run Configuration Snapshot only when the user confirms setup
- Copy global Associate Master data (targets, capacities, run-specific settings) into the snapshot
- Enforce the Run State Machine
- Coordinate validation, eligible population freeze, sampling, allocation preview/finalization, file generation, consolidation, QC, errors, insights, audit recording, and reporting
- Ensure each stage references the Run, its snapshot, and recorded artifacts

## 4.3 Run State Machine

Each Run progresses through explicit states. Transitions must be auditable.

Example states:

```text
DRAFT
→ SNAPSHOT_FROZEN
→ VALIDATED
→ EligiblePopulationFrozen
→ Sampled
→ ALLOCATED
→ DISTRIBUTED
→ RETURNED
→ CONSOLIDATED
→ QC_COMPLETED
→ COMPLETED

DRAFT → CANCELLED | ABANDONED
Any non-terminal state → FAILED
```

Valid transitions must be explicitly defined and audited; the system must prevent invalid transitions. `SNAPSHOT_FROZEN` may be entered only after user confirmation of Program, source file, sampling requirement, random-seed choice, associate roster, targets, maximum capacities, due date, and other program-configured settings. `COMPLETED` may be entered only after consolidation is finalized, critical exceptions are resolved or explicitly overridden, and QC processing is completed. Allocation finalization is prohibited when capacity is insufficient, and consolidated export is prohibited when critical exceptions are open unless explicitly overridden.

## 4.4 Associate Master

Global associate master data is stored separately from Run-specific snapshot copies.

Responsibilities:

- Maintain global associate records (Associate ID, Name, Email, Team/Program, Experience Level, Target, Maximum Capacity, Active/Inactive)
- Provide associate data to Run Orchestration when a Run is created
- Support inactive associates being automatically excluded from allocation

Run processing must use associate targets, capacities, and status copied into the Run Configuration Snapshot, not mutable master data alone.

## 4.5 Run Configuration Snapshot

When the user confirms Run setup, the system must freeze an immutable snapshot containing:

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

The snapshot is the authoritative configuration for all processing of that Run.

Implementation requirements:

- Stored with the Run record
- Never modified after setup confirmation and snapshot freezing
- Used by validation, sampling, allocation, file generation, consolidation, QC, error processing, and audit replay
- Referenced by historical Runs even after program settings or associate master data change

## 4.6 File Artifact Manager

Manages Run-specific output directories and artifact metadata.

Responsibilities:

- Create and maintain the Run output directory tree
- Register imported and generated files (canonical source, samples, allocation, associate files, returned files, consolidated output, QC, errors, reports)
- Record SHA-256 hash, byte size, original filename, import/generation timestamp, Run ID, and artifact type for every artifact
- Use temporary-file plus atomic rename for generated outputs where practical
- Associate each artifact with Run ID, artifact type, and creation timestamp
- Support audit and UI navigation without relying on ad hoc filesystem scanning

Example layout:

```text
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
```

On Windows, mutable artifact storage must use a user-writable local application data directory, not the EXE installation directory.

## 4.7 Outlook Platform Adapter

Isolates platform-specific behavior from core business logic.

Responsibilities:

- Abstract Outlook draft creation behind an interface
- Provide a Windows implementation using `pywin32`
- Provide a no-op or stub implementation on non-Windows development platforms
- Keep the core application usable when Outlook is unavailable
- Support Classic desktop Outlook via COM on Windows in v1 and provide a manual-email fallback when it is unavailable

Outlook integration must remain outside the core engines and must never send email automatically.

Email templates support these v1 placeholders:

- `{{associate_name}}`
- `{{program_name}}`
- `{{run_id}}`
- `{{item_count}}`
- `{{due_date}}`

In v1, due date is entered by the user.

## 4.8 QC Rule Evaluator

Evaluates program-configured QC rules using a restricted declarative model.

Requirements:

- Must NOT use `eval()`, `exec()`, arbitrary Python expressions, or unrestricted user-entered formulas
- Must validate rule configuration at load/save time
- Must support only approved rule types

Initial supported QC rule type:

- `ratio_percentage`

Configurable fields:

- `numerator`
- `denominator`
- `zero_denominator_behavior`

For MX PT v1:

- Intended calculation: Pass Count / Audited Count × 100
- If Audited Count = 0, QC result is **N/A**

QC must support item-level, associate-level, and run-level metrics.

Rules are evaluated from the Run Configuration Snapshot through the QC Service.

## 4.9 Error Rule Configuration

Manages program-configurable error taxonomy and error rules.

Requirements:

- Error categories and types are configurable by program
- Do not hard-code error taxonomies from other Operations programs
- Support both imported and generated errors
- Error rules are frozen in the Run Configuration Snapshot for each Run
- Any future error classification evaluation must use the same restricted declarative approach as QC rules

## 4.10 Audit Service

Records immutable audit events for significant Run operations.

Responsibilities:

- Capture OS username and application display name
- Record Run ID, program, timestamps, counts, configuration references, and processing status
- Record consolidation overrides with user, timestamp, reason, and exception/reconciliation version
- Support audit replay and historical traceability

Audit events must not be removed to simplify implementation.

## 4.11 Reporting Service

Generates operational reports and exports from validated Run data.

Responsibilities:

- Produce Run-level and program-level reports
- Export consolidated Excel outputs and operational summaries
- Use Reporting Service outputs for insights where appropriate

## 4.12 Other Application Services

The following services orchestrate core engines against a Run and its snapshot:

- **Allocation Service** — validation coordination, eligible population freeze, sampling, preview, finalization, split files
- **Consolidation Service** — returned file import, identity cross-checks, reconciliation pipeline, consolidated export, override handling
- **QC Service** — QC import and QC Rule Evaluator execution
- **Error Service** — imported and generated error processing using Error Rule Configuration
- **Insights Service** — deterministic analytics; historical comparison against previous completed Run for same program
- **Outlook Service** — dynamic draft generation via Outlook Platform Adapter

---

# 5. Core Engine

Core engines are pure or near-pure business logic components. They operate on canonical domain objects and Run Configuration Snapshots, not UI state or raw Excel headers.

| Engine | Responsibility |
|--------|----------------|
| Validation Engine | Required columns, identifier checks, severity classification (Critical/Warning/Information), duplicate ID detection requiring manual resolution |
| Randomizer | Deterministic sampling from frozen eligible population; percentage rounding |
| Allocation Strategy | Target/capacity allocation; inactive associate exclusion; above-target confirmation; shortage detection |
| Reconciliation Pipeline | Returned file identity cross-checks, exception classification, quarantine, override support |
| QC Rule Evaluator | Declarative QC rule execution at item, associate, and run levels |
| Analytics Engine | Deterministic insights; historical comparison vs previous completed Run for same program |

Engines must not depend on PySide6, Outlook, or platform-specific APIs.

---

# 6. Data Access and File Processing

## 6.1 Data Access

SQLite is the local persistence layer.

Repositories must isolate SQL from business logic and UI.

Minimum repository areas:

- Programs and program configuration versions
- Runs and Run state
- Run Configuration Snapshots
- Associate Master (global)
- Eligible population records
- Audit events
- Artifact index
- Execution manifests and versioned resolution records

## 6.2 File Processing

V1 input support: `.xlsx` and `.csv` only. `.xls` is deferred.

V1 performance target: approximately 100,000 rows per input file.

Excel and CSV processing uses Pandas plus openpyxl and/or XlsxWriter.

Pipeline:

```text
Excel/CSV
→ Raw table
→ Column mapping (from Run Configuration Snapshot)
→ Canonical item records
→ Core engines
→ Output mappers
→ Excel/CSV artifacts
```

File processing must preserve original source values where required (for example, original and normalized Product ID).

The authoritative processed source is the imported local artifact registered for the Run, not a mutable external path. Relevant parser and import settings must be persisted with the artifact.

---

# 7. Canonical Internal Data Model

The application must use a canonical internal model independent of source file column headers.

## 7.1 Domain Entities

### Program

An operational program definition (for example, MX PT).

Key attributes:

- Program ID
- Program name
- Active configuration version reference

### ProgramConfigVersion

A versioned, editable program configuration.

Contains:

- Schema version, primary identifier, identifier normalization, and case-sensitivity policy
- Input and response column mappings, requiredness, data types, field ownership, and output ordering
- Validation rules
- Sampling rules
- Allocation and tie-breaking rules
- QC rules
- Error rules
- Output configuration
- Email template configuration

### Run

The central workflow record.

Key attributes:

- Run ID (`{PROGRAM}-{YYYYMMDD}-{SEQUENCE}`)
- Program ID
- Current state (`DRAFT`, `SNAPSHOT_FROZEN`, `VALIDATED`, `ELIGIBLE_POPULATION_FROZEN`, `SAMPLED`, `ALLOCATED`, `DISTRIBUTED`, `RETURNED`, `CONSOLIDATED`, `QC_COMPLETED`, `COMPLETED`, `CANCELLED`, `FAILED`, or `ABANDONED`)
- Created timestamp
- Configuration snapshot reference

Run IDs reset sequence daily per program, are unique, and never reused.

A Run connects all downstream records and artifacts.

### RunConfigurationSnapshot

Immutable frozen configuration for one Run.

Contains:

- Program configuration version identifier
- Column mappings
- Sampling configuration
- Random seed
- Associate targets
- Associate capacities
- Associate experience/configuration and active/inactive status at snapshot time
- Due date
- QC rules
- Error rules
- Email template configuration

### AssociateMaster

Global associate master record.

Key attributes:

- Associate ID
- Associate Name
- Email
- Team / Program
- Experience Level
- Default Target
- Default Maximum Capacity
- Active / Inactive status

At Run creation, target, capacity, and run-specific settings are copied into the Run Configuration Snapshot.

Inactive associates are automatically excluded from allocation.

### Associate (Run Snapshot Copy)

An assignable worker as frozen in the Run Configuration Snapshot.

Key attributes:

- Associate ID
- Associate Name
- Email
- Team / Program
- Experience Level
- Target
- Maximum Capacity
- Active / Inactive status at snapshot freezing

Run processing uses the snapshot copy, not mutable master data alone.

### Item (Canonical Item Model)

A canonical operational record identified by the program primary identifier.

For MX PT, the primary identifier field is Product ID.

Key attributes:

- Original primary identifier value
- Normalized primary identifier value
- Source fields
- Generated/system fields (for example, Run ID and Allocated To)
- Associate-editable response fields after consolidation

Product IDs are strings internally. Normalization trims whitespace, preserves leading zeros, does not convert scientific notation, and uses case-sensitive matching for MX PT unless configured otherwise.

Source evidence must never be overwritten. When a source file contains a response-style field name, source and associate-returned values are stored separately.

### EligiblePopulation

The frozen set of items eligible for sampling for a Run.

Must be recorded after validation and user-approved exclusions/resolution.

Key attributes:

- Run ID
- Immutable item membership / normalized identifier list
- Freeze timestamp
- Exclusion audit references
- Canonical ordering and population fingerprint/hash

### SamplingResult

The outcome of random sampling for a Run.

Key attributes:

- Run ID
- Sampling method
- Requested percentage or requested count
- Calculated sample count before rounding
- Actual sample count
- Random seed
- RNG algorithm and version
- Sampling algorithm and version
- Selected item identifiers

### AllocationPlan / AllocationResult

Planned and finalized associate assignments.

Key attributes:

- Run ID
- Associate ID
- Target (normal allocation level)
- Maximum Capacity
- Planned count
- Assigned items
- Unallocated items
- Capacity shortage indicators
- Unused capacity
- Above-target allocation requiring confirmation
- Overflow strategy and version

Allocation rules:

- Block finalization if total available capacity < sample count
- If capacity > sample count, allocate only sampled items and show unused capacity
- Inactive associates excluded automatically
- Allocation above target but below maximum capacity requires explicit user confirmation
- If sample count exceeds total target but not total maximum capacity, v1 overflow uses proportional distribution based on remaining capacity with deterministic Associate ID tie-breaking

### ReconciliationReport

Consolidation exception summary for a Run.

Key attributes:

- Raw imported returned rows
- Reconciled valid rows
- Quarantined and versioned resolved rows used by final export
- Missing items, duplicate items, unexpected items, wrong-associate assignments (quarantined for manual resolution), and conflicting response data
- Invalid Run ID findings
- Identity mismatch findings
- Critical exceptions blocking export by default
- Override reason (when user finalizes with open critical exceptions)

The reconciliation pipeline must never silently select between conflicting returned responses. Every conflict requires a versioned manual resolution record. Critical exceptions are missing allocated items, duplicate items, wrong-associate items, unexpected items, invalid Run IDs, and conflicting response data.

### QCResult

QC metrics for a Run, associate, or item.

Supports item-level, associate-level, and run-level metrics.

Produced using the QC Rule Evaluator and program-configured QC rules from the Run Configuration Snapshot.

If Audited Count = 0 for MX PT v1, QC result is N/A.

### ErrorRecord

Program-configured error classification result from imported or generated errors.

Must use program-defined categories and types from the Run Configuration Snapshot, not hard-coded taxonomies.

### Artifact

A file generated or imported for a Run.

Key attributes:

- Run ID
- Artifact type
- File path
- Created timestamp
- Related associate ID (if applicable)
- SHA-256 hash
- Byte size
- Original filename
- Import/generation timestamp

### AuditEvent

Immutable record of a significant Run operation.

Must include Run ID, operation type, OS username, application display name, timestamp, and relevant counts/configuration references.

### ExecutionManifest

Immutable reproducibility record for one Run. It contains Run ID, configuration snapshot hash, source artifact hash, eligible-population hash, sampling algorithm/version, RNG algorithm/version, random seed, allocation strategy/version, and output artifact hashes.

## 7.2 Primary Identifier Normalization

Product ID (MX PT primary identifier) must be handled as strings internally.

Normalization rules:

- Trim leading and trailing whitespace
- Preserve leading zeros
- Do not silently alter identifier values
- Do not convert scientific notation into another value
- Preserve both original and normalized identifier values
- MX PT comparisons are case-sensitive unless explicitly configured otherwise

All matching for allocation, consolidation, QC, and errors must use the normalized identifier unless audit inspection requires original values.

If normalization creates duplicate values, create a Critical duplicate-ID exception. In v1, affected records are excluded from the eligible population until manually resolved; the system must not automatically retain first/last records or merge them. Resolution records capture original and normalized values, action, user, timestamp, and reason.

---

# 8. Key Processing Flows

## 8.1 Validation and Sampling Flow

```text
Input
→ Validation
→ User-approved exclusions / resolution
→ Freeze eligible population
→ Random sampling
```

Sampling must occur only after validation and user-approved exclusions.

Duplicate Product IDs require manual resolution before sampling.

Validation uses severity levels:

- **Critical** — blocks processing
- **Warning** — requires user acknowledgement where appropriate
- **Information** — does not block processing

The eligible population must be recorded for auditability and reproducibility.

The frozen population records immutable membership, canonical ordering/fingerprint, and exclusion-resolution references. Sampling records eligible-population count and membership, requested percentage/count, pre-round count, actual count, random seed, RNG algorithm/version, sampling algorithm/version, and canonical ordering/fingerprint.

Percentage sampling must use explicit HALF-UP rounding: `1692.5 → 1693` and `1692.4 → 1692`. The default Python `round()` behavior must not be used where it differs.

Store:

- Requested percentage
- Calculated sample count before rounding
- Actual sample count

## 8.2 Allocation Flow

After sampling:

1. Build allocation preview from sample and associate targets/capacities in the Run Configuration Snapshot
2. Exclude inactive associates automatically
3. Detect insufficient capacity, unused capacity, unallocated items, and above-target allocations
4. Block allocation finalization if total maximum associate capacity is less than the sample count
5. Require explicit user confirmation before generating outputs
6. Require separate explicit confirmation for allocation above target but below maximum capacity

If total maximum capacity exceeds the sample count:

- Allocate only the sampled items
- Do not automatically increase sampling
- Show unused capacity in the allocation preview

Target is the normal allocation level. Maximum Capacity is the upper bound.

If the sample count exceeds total target capacity but maximum capacity is sufficient, finalization requires explicit confirmation of additional capacity. V1 overflow uses proportional distribution based on remaining capacity, with deterministic Associate ID tie-breaking; no work is silently redistributed.

## 8.3 Associate File Identity Contract

Generated associate files must expose identity at three levels:

1. **Filename** — `{PROGRAM}_{ASSOCIATE_ID}_{ASSOCIATE_NAME}_{RUN_ID}.xlsx`
2. **Metadata sheet** — Run ID, Program, Associate ID, Associate Name, Generation timestamp
3. **Data columns** — Run ID, Allocated To

Consolidation must cross-check all available identity information against the Run Configuration Snapshot and allocation records.

Associate ID is the authoritative machine identifier. Associate Name is display-only and must be sanitized for use in the filename.

## 8.4 Reconciliation Pipeline

```text
Import returned files
→ Parse filename, metadata sheet, and data-column identity
→ Cross-check all available identity information
→ Match items by normalized primary identifier
→ Classify exceptions
→ Quarantine wrong-associate rows for manual resolution
→ Present reconciliation summary
→ Block final consolidated export if critical exceptions are open (default)
→ Allow explicit override with reason (audited)
→ Consolidated export
```

The pipeline retains three layers: raw imported returned rows, reconciled valid rows, and quarantined or versioned resolved rows used by final export. Overrides must record user, timestamp, reason, and exception/reconciliation version.

Historical comparison uses the previous **completed** Run for the same Program. If none exists, comparison is N/A.

---

# 9. QC and Error Rule Architecture

## 9.1 QC Rules

QC rules must use a restricted declarative configuration model via the **QC Rule Evaluator**.

Forbidden:

- `eval()`
- `exec()`
- Arbitrary Python expressions
- Unrestricted user-entered formulas

Initial supported rule type:

- `ratio_percentage`

Configurable fields:

- `numerator`
- `denominator`
- `zero_denominator_behavior`

Example intent for MX PT:

Pass Count / Audited Count × 100

If Audited Count = 0, QC result is **N/A**.

For MX PT, Error Rate is `Fail Count / Audited Count × 100`; if Audited Count is zero, Error Rate is **N/A**.

QC supports item-level, associate-level, and run-level metrics.

The generic QC engine must obtain the rule from the Run Configuration Snapshot and evaluate it through the QC Rule Evaluator.

## 9.2 Error Rules

Error categories and types must be configurable by program through **Error Rule Configuration**.

Do not hard-code error taxonomies from other Operations programs.

Error reporting supports both imported and generated errors.

Error rules are frozen in the Run Configuration Snapshot for each Run.

Any future error classification logic must use the same restricted, declarative evaluation model as QC rules.

---

# 10. UI Architecture Rules

- PySide6 UI components must not contain business logic
- UI calls application services only
- Application services coordinate repositories, core engines, artifact manager, and platform adapter
- Preview and finalization must use the same core allocation logic

Correct:

```text
UI → Run Orchestration Service → Allocation Engine
```

Incorrect:

```text
UI → allocation calculations → database
```

---

# 11. Cross-Platform Development and Windows Deployment

Development may occur on macOS, but production validation must occur on Windows.

Requirements:

- Core engines and services must run without Outlook installed
- Windows-only dependencies (for example, `pywin32`) must be isolated behind the Outlook Platform Adapter
- V1 Outlook support is Classic desktop Outlook via COM on Windows; draft creation only, never automatic sending
- When Outlook is unavailable, a manual email fallback must be available and core allocation must remain usable
- Packaging for `AllocationTool.exe` must use a user-writable Windows local application data directory for mutable data
- Do not store mutable production data (SQLite, logs, Run artifacts, settings) inside the EXE installation directory
- V1 performance target: approximately 100,000 rows per input file

---

# 12. Architectural Component Index

The following components must be explicitly modeled in implementation:

| Component | Role |
|-----------|------|
| Program Configuration Service | Mutable program definitions and versions |
| Run Orchestration Service | Run lifecycle coordination |
| Run State Machine | Valid Run transitions and guards |
| Run Configuration Snapshot | Immutable per-Run frozen configuration |
| Associate Master | Global associate master data |
| Canonical Item Model | Normalized item records independent of Excel headers |
| Eligible Population | Frozen post-validation sampling population |
| Allocation Strategy | Target/capacity allocation with v1 business rules |
| Reconciliation Pipeline | Returned file validation, quarantine, override handling |
| QC Rule Evaluator | Restricted declarative QC rule execution |
| Error Rule Configuration | Program-configurable error taxonomy and rules |
| File Artifact Manager | Run output directories and artifact index |
| Outlook Platform Adapter | Windows Outlook draft integration |
| Audit Service | Immutable audit event recording |
| Reporting Service | Operational report generation |

---

# 13. Testing Architecture

Unit tests must target core engines and restricted rule evaluation directly using canonical domain objects and Run Configuration Snapshots.

Required coverage areas:

- Validation severity (Critical/Warning/Information)
- Duplicate Product ID manual resolution blocking sampling
- Eligible population freeze
- Randomization and rounding
- Allocation preview, insufficient-capacity blocking, above-target confirmation, inactive associate exclusion
- Product ID normalization
- Associate file identity validation and filename convention
- Reconciliation pipeline, quarantine, override auditing
- QC Rule Evaluator (`ratio_percentage`, N/A when Audited Count = 0)
- Historical comparison against previous completed Run
- Analytics

Integration tests should use fixture Excel/CSV files and Run output contracts without requiring Outlook.

Windows-specific Outlook Platform Adapter tests must run on Windows or through mocked COM interfaces.
