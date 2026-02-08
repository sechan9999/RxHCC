
# 2026 RxHCC Risk Adjustment - Updates & fixes

## 1.2 "Sagemaker Replication" Error Fix
**Issue**: The `sagemaker_replication.py` script failed with `Did not find winutils.exe`.
**Cause**: PySpark (the engine used) requires Hadoop binaries (`winutils.exe`) to run on Windows, even for local testing.
**Solution**: 
- Modified `sagemaker_replication.py` to include a **Smart Fallback**.
- If `winutils.exe` is missing (Standard Windows setup), it automatically switches to a **Pandas-based engine** for local validation.
- The script now works seamlessly on your local machine while keeping the Spark code intact for future Cloud deployment.

## Integrity Agent Enhancements (Option 1.2)
Updated `langgraph_integrity.py` with:
1.  **Type 1 vs Type 2 Conflict**: Detects impossible simultaneous diagnoses of E10.x and E11.x.
2.  **GLP-1 / Insulin Crosswalk**: Flags claims where expensive GLP-1 (e.g., Ozempic) or Insulin drugs are present WITHOUT a supporting Diabetes diagnosis (E11.x or E10.x).

## How to test
1.  **Replication Logic**:
    ```bash
    python sagemaker_replication.py
    ```
    *Expectation*: Should print "Falling back to Local Pandas Engine" and complete successfully.

2.  **Integrity Checks**:
    ```bash
    python langgraph_integrity.py
    ```
    *Expectation*: Checks 4 test cases, including the new GLP-1 warning.
