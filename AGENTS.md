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

The architecture must allow future programs to define their own primary identifier.

---

# 7. Run ID

Every allocation workflow must have a unique Run ID.

Example:

MX-PT-20260815-001

All related records must be traceable through the Run ID.

The Run ID should be associated with:

- Input
- Sampling
- Allocation
- Associate files
- Returned files
- Consolidation
- QC
- Errors
- Reports
- Audit

---

# 8. Randomization

Random sampling must be reproducible when a seed is provided.

Always record:

- Input count
- Sampling method
- Sampling percentage or requested count
- Actual sample count
- Random seed
- Run ID
- Timestamp

Never use uncontrolled randomness when the operation requires auditability.

Do not modify the source dataset during sampling.

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

Do not silently discard unallocated items.

Do not silently redistribute items when the redistribution rule has not been defined.

---

# 10. Allocation Preview

Allocation must provide a preview before finalization.

The user must be able to see:

- Total items
- Sample count
- Associate count
- Target per associate
- Planned allocation
- Remaining items
- Exceptions

Final allocation requires explicit confirmation.

---

# 11. Consolidation

Returned associate files must be reconciled against the original allocation.

The system must detect:

- Missing items
- Duplicate items
- Unexpected items
- Wrong associate
- Incomplete files
- Invalid Run ID

Never assume a returned file is correct merely because it contains a valid Product ID.

---

# 12. QC

QC calculations must be configurable by program.

For MX PT, the initial rule is:

Pass Count / Audited Count × 100

Do not hard-code this formula into the generic QC engine.

The engine must obtain the calculation rule from configuration.

Never silently treat missing QC results as Pass.

---

# 13. Error Classification

Error categories must be configurable.

Do not hard-code categories from other Operations programs.

Do not assume that MX PT uses the same error taxonomy as another program.

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

If a future LLM is introduced, it should consume validated metrics and generate narrative summaries.

---

# 15. Auditability

Every important operation must be auditable.

Record:

- Run ID
- Program
- User
- Timestamp
- Input count
- Sampling information
- Random seed
- Associate information
- Allocation count
- Consolidation status
- QC results
- Error results
- Output files
- Processing status

Do not remove audit information merely to simplify implementation.

---

# 16. Outlook

Outlook integration must create drafts only.

The application must NEVER automatically send emails.

Email content must be dynamically generated from the current Run.

The Outlook implementation must remain isolated from the core business logic.

The application should remain usable if Outlook is unavailable.

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
- Application services
- Core business logic
- Data access
- File processing
- Reporting
- Outlook integration

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

Use application-relative paths or configurable paths.

The application must work for different users.

---

# 21. Configuration

Configuration must be externalized where appropriate.

Do not embed program-specific configuration directly into Python source code.

Program configuration should be stored in:

- SQLite
- JSON
- Other explicitly approved configuration mechanisms

The configuration used for a Run must be preserved so the Run remains reproducible.

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
- Duplicate IDs
- Missing IDs
- Invalid percentages
- Zero capacity
- Insufficient capacity
- Duplicate returned records
- Missing returned records
- Invalid Run ID
- Zero audited records

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