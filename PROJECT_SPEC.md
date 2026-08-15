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

- Program name
- Input column mapping
- Response column mapping
- Allocation rules
- Sampling rules
- QC rules
- Error configuration
- Output configuration
- Email template configuration

The first program will be:

MX PT

---

# 5. Input Data

The application must accept common operational data formats:

- `.xlsx`
- `.xls` where technically supported
- `.csv`

The original source file must never be modified.

The application must create a working copy or process the source in memory.

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

---

# 7. Product ID

Product ID is the primary unique identifier for an item.

The application must:

- Validate that Product ID exists.
- Detect blank Product IDs.
- Detect duplicate Product IDs.
- Use Product ID for reconciliation.
- Never use Excel row number as the permanent item identifier.

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

The user should not be allowed to proceed if critical validation failures exist unless the user explicitly resolves or excludes the affected records.

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

- Select unique items.
- Use Product ID as the unique identifier.
- Never modify the original dataset.
- Record the sampling percentage.
- Record the selected item count.
- Record the input item count.
- Record the random seed.
- Record timestamp.
- Associate the sample with a Run ID.

---

# 10. Random Seed

Randomization must support a reproducible random seed.

The user may choose:

- Automatic seed
- User-defined seed

The seed must be stored with the allocation run.

If the same source dataset, sampling configuration, and random seed are used, the randomizer should produce the same selection.

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

---

# 12. Associate Configuration

Associate information should be configurable.

Minimum fields:

- Associate ID
- Associate Name
- Email
- Team / Program
- Experience Level
- Target
- Maximum Capacity
- Active / Inactive status

Target and maximum capacity must be configurable per allocation run.

The system must support new associates with lower targets and experienced associates with higher targets.

---

# 13. Allocation Preview

Before final allocation, the application must provide a preview.

The preview should display:

- Total input items
- Valid items
- Sampling percentage
- Sample count
- Number of associates
- Target allocation per associate
- Total planned allocation
- Remaining items
- Capacity issues
- Allocation exceptions

The user must explicitly confirm the allocation before final output is generated.

---

# 14. Allocation Run

Every allocation execution must generate a unique Run ID.

Example:

MX-PT-20260815-001

The Run ID must be associated with:

- Source dataset
- Sampling configuration
- Random seed
- Associate list
- Allocation configuration
- Allocation output
- Split files
- Consolidation
- QC results
- Error results
- Insights
- Audit information

---

# 15. Associate File Splitting

After allocation, the application must generate separate Excel files for each associate.

Example:

A001_Kumar.xlsx
A002_Ravi.xlsx
A003_Priya.xlsx

Each file must contain only the items assigned to that associate.

The generated files should include relevant metadata such as:

- Run ID
- Associate ID
- Associate Name
- Allocation Date

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

The exact response fields must be configurable by program.

The consolidation engine must not assume that every program uses the same response fields.

---

# 18. Outlook Draft Generation

The application must be able to generate Outlook email drafts based on the allocation.

The email content must be dynamic.

The draft may contain:

- Associate name
- Run ID
- Number of assigned items
- Due date
- Program name
- Instructions
- Attachment

The application must support:

1. Consolidated team email draft.
2. Individual associate email drafts.

The application must NEVER automatically send emails.

The user must review and send the draft manually.

Outlook integration is Windows-specific and should be isolated from the core business logic.

---

# 19. Consolidation

The application must support importing completed associate files.

Users should be able to select multiple returned files at once.

The consolidation engine must:

1. Identify the Run ID.
2. Identify the associate.
3. Match records using Product ID.
4. Compare returned records against the original allocation.
5. Detect missing items.
6. Detect duplicate items.
7. Detect unexpected items.
8. Detect incorrect associate assignments.
9. Detect incomplete returned files.
10. Generate a consolidated master dataset.

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

QC rules must be configurable by program.

For the initial MX PT workflow:

QC Score is calculated as:

Pass Count / Audited Count × 100

Example:

Audited:
10

Pass:
8

Fail:
2

QC Score:
80%

---

# 23. QC Metrics

The application should calculate at minimum:

- Items audited
- Pass count
- Fail count
- QC score
- Error rate

The application should support:

- Overall QC score
- Associate-level QC score
- Run-level QC score
- Program-level QC score
- Historical QC trend

---

# 24. Error Reporting

Error reporting must be configurable by program.

Error categories must NOT be hard-coded.

Each program may define its own:

- Error categories
- Error types
- Error fields
- Error severity
- Error classification rules

MX PT may have one error structure while another program may use a completely different structure.

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

Users should be able to compare:

- Current QC vs previous run
- Current error rate vs previous run
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
- User
- Timestamp
- Source file
- Input count
- Valid count
- Sampling percentage
- Random seed
- Sample count
- Associate count
- Allocation count
- Consolidation count
- QC count
- Error count
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

The development environment may be macOS, but Windows testing is mandatory before production release.

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

The application should use a modular architecture.

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