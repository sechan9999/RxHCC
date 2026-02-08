
import streamlit as st
import pandas as pd
from langgraph_integrity import app
# To view the structure of AgentState, we could inspect it directly, but 'app.invoke' returns it naturally.

st.set_page_config(
    page_title="2026 RxHCC Integrity Checker",
    page_icon="🏥",
    layout="wide"
)

st.title("🏥 2026 RxHCC Integrity & Validation Dashboard")

st.markdown("""
This dashboard visualizes the **LangGraph Integrity Agent** logic. 
It validates medical claims against **2026 RxHCC Risk Adjustment Rules** (e.g., Diabetes specificity, Drug-Diagnosis crosswalks).
""")

# --- Sidebar ---
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to:", ["Interactive Checker", "Batch Validation Demo", "Replicated Data Preview"])

# --- Helper Function for Visualization
def display_result(result):
    status = result['integrity_status']
    messages = result['messages']
    
    if status == "PASSED":
        st.success(f"**Status: {status}**")
    elif status == "PENDING_SPECIFICITY":
        st.warning(f"**Status: {status} (Needs Review)**")
    elif status == "FAILED":
        st.error(f"**Status: {status}**")
    else:
        st.info(f"**Status: {status}**")
    
    if messages:
        st.write("Checking Logs:")
        for msg in messages:
            if "CRITICAL" in msg or "ERROR" in msg:
                 st.markdown(f"- 🔴 {msg}")
            elif "WARNING" in msg:
                 st.markdown(f"- 🟠 {msg}")
            else:
                 st.markdown(f"- ⚪ {msg}")
    else:
        st.write("No issues found.")

# ------------------------------------------------------------------
# PAGE 1: INTERACTIVE CHECKER
# ------------------------------------------------------------------
if page == "Interactive Checker":
    st.header("📝 Interactive Claim Validator")
    st.write("Enter clinical data to simulate the Agent's response.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        claim_id = st.text_input("Claim ID", "CLM-MANUAL-001")
        icd_input = st.text_area("ICD-10 Codes (comma separated)", "E11.9, G62.9")
        st.caption("Common Codes: E11.9 (Type 2 DM), E11.42 (Polyneuropathy), E10.9 (Type 1 DM), I10 (Hypertension)")
    
    with col2:
        ndc_input = st.text_area("NDC / Drug Codes (comma separated)", "RX_METFORMIN")
        st.caption("Common Drugs: RX_INSULIN, RX_GLP1_OZEMPIC, RX_METFORMIN")
    
    if st.button("Run Integrity Check 🚀"):
        # Parse Input
        icd_codes = [code.strip() for code in icd_input.split(",") if code.strip()]
        ndc_codes = [code.strip() for code in ndc_input.split(",") if code.strip()]
        
        # Prepare State
        input_state = {
            "claim_id": claim_id,
            "icd_codes": icd_codes,
            "ndc_codes": ndc_codes,
            "messages": [],
            "integrity_status": "NEW"
        }
        
        # Run Agent
        with st.spinner("Agent analyzing clinical logic..."):
            result = app.invoke(input_state)
        
        # Display
        st.subheader("Agent Analysis Result")
        display_result(result)

# ------------------------------------------------------------------
# PAGE 2: BATCH VALIDATION DEMO
# ------------------------------------------------------------------
elif page == "Batch Validation Demo":
    st.header("🧪 Batch Validation Scenarios")
    st.write("Running pre-defined test cases to demonstrate all rules.")
    
    # Define scenarios
    scenarios = [
        {
            "name": "Scenario 1: Specificity Gap (E11.9 + G62.9)",
            "desc": "A generic diabetic code and neuropathy code exist, but are not linked.",
            "data": {"claim_id": "CLM-001", "icd_codes": ["E11.9", "G62.9"], "ndc_codes": ["RX_METFORMIN"], "messages": [], "integrity_status": "NEW"}
        },
        {
            "name": "Scenario 2: Remission / Active Conflict",
            "desc": "Claim contains both 'Remission' and 'Active' diabetes codes.",
            "data": {"claim_id": "CLM-002", "icd_codes": ["E11.A", "E11.9"], "ndc_codes": [], "messages": [], "integrity_status": "NEW"}
        },
        {
            "name": "Scenario 3: Type 1 vs Type 2 Conflict",
            "desc": "Claim contains both Type 1 and Type 2 diagnosis codes.",
            "data": {"claim_id": "CLM-003", "icd_codes": ["E10.9", "E11.9"], "ndc_codes": [], "messages": [], "integrity_status": "NEW"}
        },
        {
            "name": "Scenario 4: GLP-1 without Diabetes",
            "desc": "Patient prescribed Ozempic (GLP-1) but no Diabetes diagnosis found.",
            "data": {"claim_id": "CLM-004", "icd_codes": ["I10"], "ndc_codes": ["RX_GLP1_OZEMPIC"], "messages": [], "integrity_status": "NEW"}
        },
        {
            "name": "Scenario 5: Clean Claim",
            "desc": "Perfectly coded claim.",
            "data": {"claim_id": "CLM-005", "icd_codes": ["E11.42"], "ndc_codes": ["RX_INSULIN"], "messages": [], "integrity_status": "NEW"}
        }
    ]
    
    for scen in scenarios:
        with st.expander(f"**{scen['name']}**", expanded=True):
            st.write(f"_{scen['desc']}_")
            cols = st.columns([1, 2])
            with cols[0]:
                st.code(f"ICD: {scen['data']['icd_codes']}\nNDC: {scen['data']['ndc_codes']}")
            with cols[1]:
                if st.button(f"Test {scen['data']['claim_id']}", key=scen['name']):
                    res = app.invoke(scen['data'])
                    display_result(res)

# ------------------------------------------------------------------
# PAGE 3: DATA PREVIEW
# ------------------------------------------------------------------
elif page == "Replicated Data Preview":
    st.header("📊 Replicated Claims Data (Preview)")
    
    import os
    
    # Try multiple paths
    path_output = "rxhcc_output_data"
    path_sample = "rxhcc_sample_data/sample_claims.parquet"
    
    df = None
    source = ""
    
    if os.path.exists(path_output):
        st.success(f"Found Replicated Output at `{path_output}`")
        # Load one partition for preview 
        # (Parquet partitions are folders, need to find a .parquet file inside)
        try:
             # Walk to find first parquet file
            for root, dirs, files in os.walk(path_output):
                for file in files:
                    if file.endswith(".parquet"):
                        full_path = os.path.join(root, file)
                        df = pd.read_parquet(full_path)
                        source = f"Partition: {root}"
                        break
                if df is not None: break
        except Exception as e:
            st.error(f"Error reading output: {e}")

    if df is None and os.path.exists(path_sample):
        st.info(f"Output not found. Showing RAW INPUT sample data from `{path_sample}` instead.")
        df = pd.read_parquet(path_sample)
        source = "Raw Sample Data"
        
    if df is not None:
        st.write(f"**Source**: {source}")
        st.dataframe(df.head(50))
        st.write(f"Showing first {len(df)} rows.")
    else:
        st.warning("No data found. Run `sagemaker_replication.py` or `generate_sample_data.py` first.")
