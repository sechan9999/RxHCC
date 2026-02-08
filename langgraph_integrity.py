from typing import TypedDict, List
from langgraph.graph import StateGraph, END

# Define the State of the Agent
class AgentState(TypedDict):
    claim_id: str
    icd_codes: List[str]
    ndc_codes: List[str]
    messages: List[str]
    integrity_status: str

# --------------------------------------------------------
# NODE 1: Cross-Walk Validation Agent
# --------------------------------------------------------
def validate_crosswalk(state: AgentState):
    """
    Checks consistency between Diagnosis (ICD) and Drug (NDC).
    """
    icd_codes = state['icd_codes']
    ndc_codes = state['ndc_codes']
    messages = state['messages'] or []
    
    print(f"Validating Claim {state['claim_id']}...")
    
    # Rule 1: Diabetes Drug without Diabetes Diagnosis
    has_diabetes_rx = any(code.startswith("RX_INSULIN") for code in ndc_codes)
    has_glp1_rx = any(code.startswith("RX_GLP1") for code in ndc_codes)
    
    has_diabetes_dx = any(code.startswith("E11") or code.startswith("E10") for code in icd_codes)
    
    if (has_diabetes_rx or has_glp1_rx) and not has_diabetes_dx:
        messages.append("ERROR: Anti-diabetic drug (Insulin/GLP-1) dispensed without E11.x/E10.x diagnosis.")
        return {"integrity_status": "FAILED", "messages": messages}
        
    return {"integrity_status": "PENDING_SPECIFICITY", "messages": messages}

# --------------------------------------------------------
# NODE 2: Specificity Check Agent
# --------------------------------------------------------
def check_specificity(state: AgentState):
    """
    Checks if codes are specific enough for V28/RxHCC 2026 Model.
    """
    icd_codes = state['icd_codes']
    messages = state['messages']
    
    # Rule 2: Unspecified Neuropathy with Diabetes
    if "E11.9" in icd_codes and "G62.9" in icd_codes:
        messages.append("WARNING: Specificity Gap. 'E11.9' + 'G62.9' found. Recommend 'E11.42' (Diabetes w/ Polyneuropathy) to capture RxHCC30.")
        
    # Rule 3: Remission Conflict
    if "E11.A" in icd_codes and "E11.9" in icd_codes:
        messages.append("CRITICAL: 'Remission' (E11.A) and 'Active' (E11.9) codes cannot coexist.")
        return {"integrity_status": "FAILED", "messages": messages}
    
    # Rule 4: Type 1 and Type 2 Conflict
    has_type1 = any(code.startswith("E10") for code in icd_codes)
    has_type2 = any(code.startswith("E11") for code in icd_codes)
    
    if has_type1 and has_type2:
        messages.append("CRITICAL: Type 1 (E10.x) and Type 2 (E11.x) cannot coexist on the same claim.")
        return {"integrity_status": "FAILED", "messages": messages}

    return {"integrity_status": "PASSED", "messages": messages}

# --------------------------------------------------------
# Workflow Definition
# --------------------------------------------------------
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("crosswalk_validator", validate_crosswalk)
workflow.add_node("specificity_checker", check_specificity)

# Define Edges
workflow.set_entry_point("crosswalk_validator")

def router(state: AgentState):
    if state['integrity_status'] == "FAILED":
        return END
    return "specificity_checker"

workflow.add_conditional_edges(
    "crosswalk_validator",
    router
)
workflow.add_edge("specificity_checker", END)

# Compile
app = workflow.compile()

# --------------------------------------------------------
# Simulation Run
# --------------------------------------------------------
if __name__ == "__main__":
    # Test Case 1: Specificity Gap
    sample_claim = {
        "claim_id": "CLM-001",
        "icd_codes": ["E11.9", "G62.9"], # Missed opportunity for E11.42
        "ndc_codes": ["RX_METFORMIN"],
        "messages": [],
        "integrity_status": "NEW"
    }
    
    print("\n--- Processing Claim CLM-001 ---")
    result = app.invoke(sample_claim)
    print(f"Result: {result['integrity_status']}")
    print(f"Logs: {result['messages']}")
    
    # Test Case 2: Remission Error
    sample_claim_2 = {
        "claim_id": "CLM-002",
        "icd_codes": ["E11.A", "E11.9"], # Impossible state
        "ndc_codes": [],
        "messages": [],
        "integrity_status": "NEW"
    }
    
    print("\n--- Processing Claim CLM-002 ---")
    result_2 = app.invoke(sample_claim_2)
    print(f"Result: {result_2['integrity_status']}")
    print(f"Logs: {result_2['messages']}")
    
    # Test Case 3: Type 1 and Type 2 Conflict
    sample_claim_3 = {
        "claim_id": "CLM-003",
        "icd_codes": ["E10.9", "E11.9"], # Impossible state
        "ndc_codes": [],
        "messages": [],
        "integrity_status": "NEW"
    }
    
    print("\n--- Processing Claim CLM-003 ---")
    result_3 = app.invoke(sample_claim_3)
    print(f"Result: {result_3['integrity_status']}")
    print(f"Logs: {result_3['messages']}")
    
    # Test Case 4: GLP-1 without Diabetes Diagnosis
    sample_claim_4 = {
        "claim_id": "CLM-004",
        "icd_codes": ["I10"], # Hypertension only
        "ndc_codes": ["RX_GLP1_OZEMPIC"],
        "messages": [],
        "integrity_status": "NEW"
    }
    
    print("\n--- Processing Claim CLM-004 ---")
    result_4 = app.invoke(sample_claim_4)
    print(f"Result: {result_4['integrity_status']}")
    print(f"Logs: {result_4['messages']}")
