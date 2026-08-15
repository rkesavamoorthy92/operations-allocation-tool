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

---

# 2. High-Level Architecture

The application will use a layered desktop architecture.

```text
┌──────────────────────────────────────────────┐
│                  PySide6 UI                  │
│                                              │
│ Dashboard | Allocation | Consolidation | QC │
│ Errors | Insights | Audit | Settings         │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│              Application Services            │
│                                              │
│ Allocation Service                           │
│ Consolidation Service                        │
│ QC Service                                   │
│ Error Service                                │
│ Insights Service                             │
│ Report Service                               │
│ Outlook Service                              │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                 Core Engine                  │
│                                              │
│ Randomizer                                   │
│ Allocation Engine                            │
│ Validation Engine                            │
│ Reconciliation Engine                        │
│ QC Calculation Engine                        │
│ Analytics Engine                             │
└──────────────────────┬───────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────────┐  ┌───────────────────┐
│    Data Access       │  │  File Processing  │
│                      │  │                   │
│ SQLite Repository    │  │ Pandas            │
│ Configuration        │  │ openpyxl          │
│ Audit Repository     │  │ XlsxWriter        │
└──────────┬───────────┘  └─────────┬─────────┘
           │                        │
           ▼                        ▼
      SQLite DB                 Excel / CSV
      