# RxHCC 2026 Risk Adjustment & ICD-10 Mapping Project

## Project Overview
This project establishes a modern data engineering workflow for the **2026 RxHCC Risk Adjustment Model**, focusing on **Type 2 Diabetes** mappings. It leverages AWS Cloud-native services (SageMaker, Glue, Amazon Q) for scalability and **LangGraph** for autonomous data integrity validation.

## 2026 RxHCC & ICD-10 Updates
The 2026 model introduces critical changes driven by the **Inflation Reduction Act (IRA)** and full **V28 Model** implementation.

### Key Diagnosis Code Changes (Diabetes Type 2)
| ICD-10 Code | Description | RxHCC (2026) | Notes |
| :--- | :--- | :--- | :--- |
| **E11.9** | Type 2 diabetes mellitus without complications | **RxHCC31** | Coefficient reduced due to IRA negotiated prices. |
| **E11.42** | Type 2 DM with diabetic polyneuropathy | **RxHCC30** | **MUST** use this combination code. `E11.9` + `G62.9` implies lower specificity and may miss risk capture. |
| **E11.A** | Type 2 DM in remission | **N/A** | New code. Does not map to active Diabetes RxHCCs if no complications present. |
| **E11.69** | Type 2 DM with other specified complication | **RxHCC30** | High-risk category. |

### Impact on RAF Scores & Reimbursement
- **Coefficient Reduction**: RxHCC30 (Diabetes with complications) and RxHCC31 (Diabetes without complications) have **lower coefficients** in 2026 (approx -1.047 and -0.995 relative change) due to lower costs of negotiated drugs (MFP).
- **Specificity Requirement**: Using generic codes (like `G62.9` for neuropathy without linking to diabetes) may result in **ZERO** RxHCC capture under V28 rules. Accurate coding of `E11.42` is essential for reimbursement accuracy.

## Workflow Architecture

1.  **Distributed Processing (SageMaker/Spark)**:
    - Migrated Stanford legacy replication scripts to **Amazon SageMaker**.
    - Uses PySpark for multi-million record processing.
    - *Script*: `sagemaker_replication.py`

2.  **Mapping Logic Automation (AWS Glue + Amazon Q)**:
    - **Amazon Q** generates the complex SQL/PySpark logic for ICD-10 <> RxHCC <> NDC cross-walks.
    - Self-documenting ETL process.
    - *Script*: `glue_mapping_logic.py`

    - Autonomous agents validate claims *before* reporting.
    - Checks for:
        - "Impossible Combinations" (e.g., Type 1 and Type 2 on same claim).
        - "Remission Conflicts" (e.g. Active and Remission codes together).
        - "Specificity Gaps" (e.g., missing `E11.42` linkage).
    - *Script*: `langgraph_integrity.py`

## Directory Structure
- `sagemaker_replication.py`: Distributed data processing script.
- `glue_mapping_logic.py`: AWS Glue ETL script with Amazon Q generated logic.
- `langgraph_integrity.py`: AI Agent validation logic.
- `rxhcc_sample_data.csv`: Sample input data structure.
