"""
RxHCC Integrity Dashboard
==========================
Streamlit 기반 보험 청구 무결성 검증 대시보드.
실행: streamlit run app/integrity_app.py
"""
import streamlit as st
import pandas as pd
import json
import sys
import os
from datetime import datetime

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.rules import (
    RxHCCRuleEngine,
    ClaimRecord, 
    ValidationResult,
    Severity,
    ICD_NDC_VALID_MAPPINGS,
    GLP1_NDC_PREFIXES,
    GLP1_VALID_ICD_PREFIXES
)
from engine.langgraph_integrity import run_validation
from engine.sagemaker_replication import SyntheticClaimGenerator, PandasBatchValidator

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="RxHCC Integrity Dashboard",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 스타일링
st.markdown("""
<style>
    .severity-critical {
        background-color: #FF4B4B;
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.85em;
    }
    .severity-warning {
        background-color: #FFA62F;
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.85em;
    }
    .severity-pass {
        background-color: #21BA45;
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.85em;
    }
    .severity-info {
        background-color: #54C8FF;
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.85em;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 12px;
        color: white;
        text-align: center;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 세션 상태 초기화
# ============================================================
if "validation_history" not in st.session_state:
    st.session_state.validation_history = []
if "batch_results" not in st.session_state:
    st.session_state.batch_results = None
if "generated_data" not in st.session_state:
    st.session_state.generated_data = None

# ============================================================
# 사이드바
# ============================================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/hospital.png", width=64)
    st.title("RxHCC")
    st.caption("보험 청구 무결성 검증 시스템")
    st.divider()
    
    # 네비게이션
    # 네비게이션 / Navigation
    page = st.radio(
        "📍 Navigation", 
        [
            "🔍 실시간 검사 (Real-time Scan)", 
            "📋 배치 데모 (Batch Demo)", 
            "📊 데이터 미리보기 (Data Preview)", 
            "📖 규칙 사전 (Rule Dictionary)", 
            "📈 분석 대시보드 (Analytics Dashboard)"
        ],
        index=0
    )
    
    st.divider()
    # 시스템 상태
    st.subheader("⚙️ 시스템 상태")
    try:
        from langgraph.graph import StateGraph
        st.success("✅ LangGraph 활성")
    except ImportError:
        st.warning("⚠️ LangGraph 미설치 (순차 실행 모드)")
        
    try:
        import sagemaker
        st.success("✅ SageMaker SDK 활성")
    except ImportError:
        st.info("ℹ️ Pandas 로컬 모드")
        
    st.caption(f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    st.divider()
    st.markdown("**[GitHub Repository](https://github.com/sechan9999/RxHCC)**")

# ============================================================
# 헬퍼 함수
# ============================================================
def severity_badge(severity: str) -> str:
    """심각도 배지 HTML"""
    css_class = f"severity-{severity.lower()}"
    emoji = {"CRITICAL": "🔴", "WARNING": "🟡", "PASS": "🟢", "INFO": "🔵"}.get(severity, "⚪")
    return f'<span class="{css_class}">{emoji} {severity}</span>'

def render_results(results: list):
    """검증 결과를 보기 좋게 렌더링"""
    if not results:
        st.info("검증 결과가 없습니다.")
        return
        
    for r in results:
        sev = r.get("severity", "INFO")
        if sev == "CRITICAL":
            icon = "🔴"
            expander_type = "error"
        elif sev == "WARNING":
            icon = "🟡"
            expander_type = "warning"
        elif sev == "PASS":
            icon = "🟢"
            expander_type = "success"
        else:
            icon = "🔵"
            expander_type = "info"
            
        with st.expander(f"{icon} [{sev}] {r.get('rule_name', 'Unknown')}"):
            st.markdown(f"**규칙 ID:** `{r.get('rule_id', 'N/A')}`")
            st.markdown(f"**메시지:** {r.get('message', '')}")
            
            details = r.get("details", {})
            if details:
                st.json(details)

def get_predefined_scenarios():
    """사전 정의된 테스트 시나리오"""
    return {
        "✅ 정상: 제2형 당뇨 + Metformin": {
            "claim_id": "DEMO-001",
            "patient_id": "PAT-10001",
            "icd_codes": "E11.9",
            "ndc_codes": "00002-1433-80",
            "hcc_codes": "HCC19",
            "description": "제2형 당뇨(E11.9) 환자에게 Metformin 처방. 정상 케이스."
        },
        "🔴 충돌: 제1형 + 제2형 당뇨 동시 진단": {
            "claim_id": "DEMO-002",
            "patient_id": "PAT-10002",
            "icd_codes": "E10.9,E11.65",
            "ndc_codes": "00088-2500-33",
            "hcc_codes": "HCC18",
            "description": "제1형과 제2형 당뇨가 동시에 진단됨. 상호 배타적 코드 충돌."
        },
        "🔴 GLP-1 오남용: 적응증 없이 처방": {
            "claim_id": "DEMO-003",
            "patient_id": "PAT-10003",
            "icd_codes": "I10",
            "ndc_codes": "00169-4060-12",
            "hcc_codes": "",
            "description": "고혈압(I10) 환자에게 GLP-1(Ozempic) 처방. 적응증(당뇨/비만) 없음."
        },
        "🔴 GLP-1 + 제1형 당뇨": {
            "claim_id": "DEMO-004",
            "patient_id": "PAT-10004",
            "icd_codes": "E10.9",
            "ndc_codes": "00169-4060-12",
            "hcc_codes": "",
            "description": "제1형 당뇨(E10) 환자에게 GLP-1 처방. GLP-1은 제1형 적응증이 아님."
        },
        "🔴 HCC Upcoding: 합병증 없는 당뇨에 HCC18": {
            "claim_id": "DEMO-005",
            "patient_id": "PAT-10005",
            "icd_codes": "E11.9",
            "ndc_codes": "00002-1433-80",
            "hcc_codes": "HCC18",
            "description": "합병증 없는 당뇨(E11.9)에 합병증 HCC(HCC18) 매핑. Upcoding 의심."
        },
        "🟡 NDC 불일치: 고혈압에 인슐린": {
            "claim_id": "DEMO-006",
            "patient_id": "PAT-10006",
            "icd_codes": "I10",
            "ndc_codes": "00088-2500-33",
            "hcc_codes": "",
            "description": "고혈압 진단에 인슐린 처방. 진단-약물 불일치."
        },
        "✅ 정상: 비만 + Wegovy (GLP-1)": {
            "claim_id": "DEMO-007",
            "patient_id": "PAT-10007",
            "icd_codes": "E66.01",
            "ndc_codes": "00169-4060-13",
            "hcc_codes": "",
            "description": "비만(E66.01) 환자에게 Wegovy 처방. GLP-1 적응증 있음."
        },
    }

# ============================================================
# 페이지 1: 실시간 검사
# ============================================================
if page == "🔍 실시간 검사 (Real-time Scan)":
    st.title("🔍 실시간 무결성 검사 (Real-time Integrity Scan)")
    st.markdown("환자의 **진단코드(ICD)**와 **약물코드(NDC)**를 입력하여 검증합니다.\n\nVerify claims by entering Patient **Diagnosis (ICD)** and **Drug (NDC)** codes.")
    
    tab1, tab2 = st.tabs(["📝 직접 입력 (Manual Input)", "📋 시나리오 선택 (Scenario Selection)"])
    
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("환자 정보 (Patient Info)")
            claim_id = st.text_input("Claim ID", value="CLM-TEST-001", key="manual_claim_id")
            patient_id = st.text_input("Patient ID", value="PAT-00001", key="manual_patient_id")
            provider_id = st.text_input("Provider ID", value="PRV-1234", key="manual_provider_id")
            
        with col2:
            st.subheader("코드 입력 (Code Input)")
            icd_input = st.text_input(
                "ICD 코드 (쉼표로 구분)", 
                value="E11.9",
                help="예: E11.9, E10.65, I10",
                key="manual_icd"
            )
            ndc_input = st.text_input(
                "NDC 코드 (쉼표로 구분)", 
                value="00002-1433-80",
                help="예: 00002-1433-80, 00169-4060-12",
                key="manual_ndc"
            )
            hcc_input = st.text_input(
                "HCC 코드 (쉼표로 구분, 선택사항)",
                value="",
                help="예: HCC18, HCC19",
                key="manual_hcc"
            )
            
        if st.button("🚀 검증 실행 (Run Validation)", type="primary", use_container_width=True, key="manual_validate"):
            if not icd_input.strip() or not ndc_input.strip():
                st.error("ICD 코드와 NDC 코드를 모두 입력해주세요.")
            else:
                claim_data = {
                    "claim_id": claim_id,
                    "patient_id": patient_id,
                    "icd_codes": icd_input,
                    "ndc_codes": ndc_input,
                    "hcc_codes": hcc_input,
                    "provider_id": provider_id,
                    "claim_date": datetime.now().strftime("%Y-%m-%d"),
                    "claim_amount": 0
                }
                
                with st.spinner("검증 중..."):
                    result = run_validation(claim_data)
                    
                # 결과 표시
                st.divider()
                risk_level = result.get("metadata", {}).get("risk_level", "UNKNOWN")
                risk_score = result.get("metadata", {}).get("risk_score", 0)
                
                # 메트릭 카드
                m1, m2, m3, m4 = st.columns(4)
                with m1: st.metric("리스크 등급", risk_level)
                with m2: st.metric("리스크 스코어", risk_score)
                with m3:
                    critical_count = sum(1 for r in result["results"] if r.get("severity") == "CRITICAL")
                    st.metric("🔴 Critical", critical_count)
                with m4:
                    warning_count = sum(1 for r in result["results"] if r.get("severity") == "WARNING")
                    st.metric("🟡 Warning", warning_count)
                    
                st.divider()
                render_results(result["results"])
                
                # 히스토리에 추가
                st.session_state.validation_history.append({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "claim_id": claim_id,
                    "icd": icd_input,
                    "ndc": ndc_input,
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                    "n_critical": critical_count,
                    "n_warning": warning_count,
                })

    with tab2:
        st.subheader("사전 정의된 시나리오 (Predefined Scenarios)")
        scenarios = get_predefined_scenarios()
        selected = st.selectbox("시나리오 선택 (Select Scenario)", list(scenarios.keys()))
        scenario = scenarios[selected]
        
        st.info(f"**설명:** {scenario['description']}")
        
        # 시나리오 데이터 표시
        col_a, col_b = st.columns(2)
        with col_a:
            st.code(f"ICD: {scenario['icd_codes']}\nNDC: {scenario['ndc_codes']}\nHCC: {scenario['hcc_codes']}")
            
        if st.button("🎯 시나리오 검증 (Validate Scenario)", type="primary", use_container_width=True, key="scenario_validate"):
            with st.spinner("검증 중..."):
                result = run_validation(scenario)
                
            risk_level = result.get("metadata", {}).get("risk_level", "UNKNOWN")
            risk_score = result.get("metadata", {}).get("risk_score", 0)
            
            m1, m2 = st.columns(2)
            with m1: st.metric("리스크 등급", risk_level)
            with m2: st.metric("리스크 스코어", risk_score)
            
            render_results(result["results"])

    # 검증 히스토리
    if st.session_state.validation_history:
        st.divider()
        st.subheader("📜 검증 히스토리")
        history_df = pd.DataFrame(st.session_state.validation_history)
        st.dataframe(history_df, use_container_width=True, hide_index=True)
        
        if st.button("🗑️ 히스토리 초기화 (Clear History)"):
            st.session_state.validation_history = []
            st.rerun()

# ============================================================
# 페이지 2: 배치 데모
# ============================================================
elif page == "📋 배치 데모 (Batch Demo)":
    st.title("📋 배치 검증 데모 (Batch Validation Demo)")
    st.markdown("사전 정의된 시나리오를 배치로 검증하거나, 합성 데이터를 생성하여 대량 검증합니다.\n\nValidate scenarios in batch or generate synthetic data for large-scale testing.")
    
    tab1, tab2 = st.tabs(["🎯 시나리오 배치 (Scenario Batch)", "🔬 합성 데이터 생성/검증 (Synthetic Data)"])
    
    with tab1:
        st.subheader("7개 시나리오 일괄 검증 (Batch Validate 7 Scenarios)")
        if st.button("▶️ 전체 시나리오 검증 실행 (Run All)", type="primary", use_container_width=True, key="batch_scenarios"):
            scenarios = get_predefined_scenarios()
            progress = st.progress(0)
            all_results = []
            
            for i, (name, scenario) in enumerate(scenarios.items()):
                result = run_validation(scenario)
                risk_level = result.get("metadata", {}).get("risk_level", "UNKNOWN")
                risk_score = result.get("metadata", {}).get("risk_score", 0)
                critical_count = sum(1 for r in result["results"] if r.get("severity") == "CRITICAL")
                warning_count = sum(1 for r in result["results"] if r.get("severity") == "WARNING")
                
                all_results.append({
                    "시나리오": name,
                    "Claim ID": scenario["claim_id"],
                    "ICD": scenario["icd_codes"],
                    "NDC": scenario["ndc_codes"],
                    "리스크 등급": risk_level,
                    "스코어": risk_score,
                    "🔴 Critical": critical_count,
                    "🟡 Warning": warning_count,
                })
                progress.progress((i + 1) / len(scenarios))
                
            st.session_state.batch_results = pd.DataFrame(all_results)
            
        if st.session_state.batch_results is not None:
            df = st.session_state.batch_results
            
            # 요약 메트릭
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("전체 시나리오", len(df))
            with c2: 
                high_risk = len(df[df["리스크 등급"].isin(["HIGH", "MEDIUM"])])
                st.metric("위험 감지", high_risk)
            with c3:
                total_critical = df["🔴 Critical"].sum()
                st.metric("총 Critical", int(total_critical))
            with c4:
                total_warning = df["🟡 Warning"].sum()
                st.metric("총 Warning", int(total_warning))
                
            st.divider()
            
            # 결과 테이블 (조건부 색상)
            def color_risk(val):
                colors = {
                    "HIGH": "background-color: #FF4B4B; color: white;",
                    "MEDIUM": "background-color: #FFA62F; color: white;",
                    "LOW": "background-color: #FECF33;",
                    "MINIMAL": "background-color: #21BA45; color: white;",
                }
                return colors.get(val, "")

            styled_df = df.style.applymap(color_risk, subset=["리스크 등급"])
            st.dataframe(styled_df, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("합성 데이터 생성 & 대량 검증 (Generate Synthetic Data)")
        col1, col2, col3 = st.columns(3)
        with col1: n_records = st.slider("레코드 수 (Count)", 100, 5000, 1000, step=100)
        with col2: anomaly_rate = st.slider("이상 비율 (Anomaly Rate %)", 5, 50, 15)
        with col3: seed = st.number_input("랜덤 시드 (Random Seed)", value=42, min_value=0)
        
        if st.button("🔬 데이터 생성 & 검증 (Generate & Validate)", type="primary", use_container_width=True, key="generate_validate"):
            with st.spinner(f"{n_records}개 레코드 생성 중..."):
                generator = SyntheticClaimGenerator(seed=seed)
                df = generator.generate(n_records=n_records, anomaly_rate=anomaly_rate / 100)
            
            st.success(f"✅ {len(df)}개 레코드 생성 완료!")
            
            with st.spinner("배치 검증 중..."):
                validator = PandasBatchValidator()
                validated_df = validator.validate_dataframe(df)
                summary = validator.get_summary(validated_df)
                
            st.session_state.generated_data = validated_df
            
            # 요약 대시보드
            st.divider()
            st.subheader("📊 검증 결과 요약")
            m1, m2, m3, m4 = st.columns(4)
            with m1: st.metric("총 청구", summary["total_claims"])
            with m2: st.metric("🚩 플래그", summary["flagged_claims"])
            with m3: st.metric("통과율", f"{summary['pass_rate']}%")
            with m4: st.metric("위험 금액", f"${summary['total_amount_at_risk']:,.0f}")
            
            # 심각도 분포 차트
            st.divider()
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("심각도 분포")
                sev_df = pd.DataFrame(
                    list(summary["severity_distribution"].items()),
                    columns=["Severity", "Count"]
                )
                st.bar_chart(sev_df.set_index("Severity"))
            with col_b:
                if summary["anomaly_distribution"]:
                    st.subheader("이상 유형 분포")
                    anom_df = pd.DataFrame(
                        list(summary["anomaly_distribution"].items()),
                        columns=["Type", "Count"]
                    )
                    st.bar_chart(anom_df.set_index("Type"))

# ============================================================
# 페이지 3: 데이터 미리보기
# ============================================================
elif page == "📊 데이터 미리보기 (Data Preview)":
    st.title("📊 데이터 미리보기 (Data Preview)")
    
    tab1, tab2 = st.tabs(["📁 생성된 데이터 (Generated)", "📤 CSV 업로드 (Upload CSV)"])
    
    with tab1:
        if st.session_state.generated_data is not None:
            df = st.session_state.generated_data
            st.metric("총 레코드", len(df))
            
            # 필터링
            col1, col2 = st.columns(2)
            with col1:
                severity_filter = st.multiselect(
                    "심각도 필터 (Severity Filter)", ["PASS", "WARNING", "CRITICAL"], default=["PASS", "WARNING", "CRITICAL"]
                )
            with col2:
                if "anomaly_type" in df.columns:
                    anomaly_filter = st.multiselect(
                        "이상 유형 필터 (Anomaly Type Filter)", df["anomaly_type"].unique().tolist(), default=df["anomaly_type"].unique().tolist()
                    )
                else:
                    anomaly_filter = None
                    
            filtered = df[df["max_severity"].isin(severity_filter)]
            if anomaly_filter is not None and "anomaly_type" in filtered.columns:
                filtered = filtered[filtered["anomaly_type"].isin(anomaly_filter)]
                
            st.dataframe(
                filtered.drop(columns=["validation_results"], errors="ignore"),
                use_container_width=True,
                hide_index=True
            )
            
            # 다운로드 버튼
            csv = filtered.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 CSV 다운로드",
                csv,
                f"rxhcc_validated_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv"
            )
            
            # 특정 레코드 상세 보기
            st.divider()
            st.subheader("🔎 레코드 상세 검증 결과")
            selected_claim = st.selectbox(
                "Claim ID 선택", filtered["claim_id"].tolist()[:50] # 상위 50개만
            )
            
            if selected_claim:
                row = filtered[filtered["claim_id"] == selected_claim].iloc[0]
                c1, c2, c3 = st.columns(3)
                with c1: st.code(f"ICD: {row['icd_codes']}")
                with c2: st.code(f"NDC: {row['ndc_codes']}")
                with c3: st.code(f"Severity: {row['max_severity']}")
                
                if "validation_results" in row:
                    try:
                        results = json.loads(row["validation_results"])
                        render_results(results)
                    except json.JSONDecodeError:
                        st.warning("검증 결과를 파싱할 수 없습니다.")
        else:
            st.info("💡 '배치 데모' 탭에서 먼저 데이터를 생성해주세요.")

    with tab2:
        st.subheader("CSV 파일 업로드하여 검증")
        st.markdown("""
        **필수 컬럼:**
        - `claim_id`: 청구 ID
        - `icd_codes`: ICD 코드 (쉼표 구분)
        - `ndc_codes`: NDC 코드 (쉼표 구분)
        
        **선택 컬럼:**
        `patient_id`, `hcc_codes`, `provider_id`, `claim_amount`
        """)
        
        uploaded = st.file_uploader("CSV 파일 업로드", type=["csv"])
        if uploaded:
            df = pd.read_csv(uploaded)
            st.success(f"✅ {len(df)}개 레코드 로드됨")
            st.dataframe(df.head(10), use_container_width=True)
            
            if st.button("🚀 업로드 데이터 검증", type="primary", key="upload_validate"):
                with st.spinner("검증 중..."):
                    validator = PandasBatchValidator()
                    validated = validator.validate_dataframe(df)
                    summary = validator.get_summary(validated)
                    
                st.session_state.generated_data = validated
                
                m1, m2, m3 = st.columns(3)
                with m1: st.metric("총 청구", summary["total_claims"])
                with m2: st.metric("🚩 플래그", summary["flagged_claims"])
                with m3: st.metric("통과율", f"{summary['pass_rate']}%")
                
                st.dataframe(
                    validated.drop(columns=["validation_results"], errors="ignore"),
                    use_container_width=True
                )

# ============================================================
# 페이지 4: 규칙 사전
# ============================================================
elif page == "📖 규칙 사전 (Rule Dictionary)":
    st.title("📖 검증 규칙 사전 (Rule Dictionary)")
    st.markdown("현재 시스템에 등록된 모든 검증 규칙과 매핑 테이블을 조회합니다.\n\nBrowse all validation rules and mapping tables registered in the system.")
    
    tab1, tab2, tab3 = st.tabs(["📋 ICD-NDC 매핑 (Mapping)", "⚡ 충돌 규칙 (Conflicts)", "💊 GLP-1 규칙 (GLP-1 Rules)"])
    
    with tab1:
        st.subheader("ICD-NDC 허용 매핑 테이블")
        for icd_prefix, mapping in ICD_NDC_VALID_MAPPINGS.items():
            with st.expander(f"**{icd_prefix}** — {mapping['description']}"):
                for ndc in mapping["valid_ndc_prefixes"]:
                    st.code(ndc, language=None)
                    
    with tab2:
        st.subheader("ICD 코드 충돌 규칙")
        from engine.rules import ICD_CONFLICT_RULES
        for rule in ICD_CONFLICT_RULES:
            severity_color = "🔴" if rule["severity"] == Severity.CRITICAL else "🟡"
            with st.expander(f"{severity_color} {rule['rule_id']}: {rule['name']}"):
                st.markdown(f"**그룹 A:** `{rule['codes_a']}`")
                st.markdown(f"**그룹 B:** `{rule['codes_b']}`")
                st.markdown(f"**심각도:** {rule['severity'].value}")
                st.markdown(f"**메시지:** {rule['message']}")
                
    with tab3:
        st.subheader("GLP-1 특별 검증 규칙")
        st.markdown("### GLP-1 NDC 코드")
        for ndc in GLP1_NDC_PREFIXES:
            st.code(ndc, language=None)
            
        st.markdown("### 허용 적응증 (ICD prefix)")
        for icd in GLP1_VALID_ICD_PREFIXES:
            desc = ICD_NDC_VALID_MAPPINGS.get(icd, {}).get("description", "")
            st.markdown(f"- **{icd}**: {desc}")
            
        st.warning("""
        **GLP-1 검증 규칙:**
        1. GLP-1 처방 시 E11(제2형 당뇨) 또는 E66(비만) 진단이 반드시 필요
        2. E10(제1형 당뇨)에 GLP-1 처방은 CRITICAL 위반
        """)

# ============================================================
# 페이지 5: 분석 대시보드
# ============================================================
elif page == "📈 분석 대시보드 (Analytics Dashboard)":
    st.title("📈 분석 대시보드 (Analytics Dashboard)")
    
    if st.session_state.generated_data is not None:
        df = st.session_state.generated_data
        
        # KPI 카드
        total = len(df)
        flagged = df["is_flagged"].sum()
        pass_rate = (total - flagged) / total * 100 if total > 0 else 0
        
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: st.metric("총 청구", f"{total:,}")
        with c2: st.metric("🚩 플래그", f"{int(flagged):,}")
        with c3: st.metric("통과율", f"{pass_rate:.1f}%")
        with c4: 
            if "claim_amount" in df.columns:
                total_amt = df["claim_amount"].sum()
                st.metric("총 청구액", f"${total_amt:,.0f}")
        with c5:
            if "claim_amount" in df.columns:
                risk_amt = df[df["is_flagged"]]["claim_amount"].sum()
                st.metric("위험 금액", f"${risk_amt:,.0f}")
                
        st.divider()
        
        # 차트들
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("심각도 분포")
            sev_counts = df["max_severity"].value_counts()
            st.bar_chart(sev_counts)
        with col_b:
            if "anomaly_type" in df.columns:
                st.subheader("이상 유형 분포")
                anom_counts = df["anomaly_type"].value_counts()
                st.bar_chart(anom_counts)
                
        # Provider 분석
        if "provider_id" in df.columns:
            st.divider()
            st.subheader("🏥 Provider별 위반 현황")
            provider_stats = df.groupby("provider_id").agg(
                total_claims=("claim_id", "count"),
                flagged_claims=("is_flagged", "sum"),
                total_amount=("claim_amount", "sum") if "claim_amount" in df.columns else ("claim_id", "count"),
            ).reset_index()
            
            provider_stats["flag_rate"] = (
                provider_stats["flagged_claims"] / provider_stats["total_claims"] * 100
            ).round(1)
            
            # 위반율 높은 순
            top_providers = provider_stats.nlargest(10, "flag_rate")
            st.dataframe(top_providers, use_container_width=True, hide_index=True)
            
        # 시간대별 분석
        if "claim_date" in df.columns:
            st.divider()
            st.subheader("📅 월별 청구 추이")
            try:
                df_time = df.copy()
                df_time["claim_date"] = pd.to_datetime(df_time["claim_date"])
                df_time["month"] = df_time["claim_date"].dt.to_period("M").astype(str)
                
                monthly = df_time.groupby("month").agg(
                    total=("claim_id", "count"),
                    flagged=("is_flagged", "sum")
                ).reset_index()
                
                st.line_chart(monthly.set_index("month"))
            except Exception:
                st.info("날짜 데이터 파싱 중 오류가 발생했습니다.")
    else:
        st.info("💡 '배치 데모' 탭에서 먼저 데이터를 생성해주세요. (Please generate data in 'Batch Demo' tab first.)")
        
        if st.button("🔬 샘플 데이터 빠르게 생성 (Generate 500 Samples)", type="primary"):
            with st.spinner("생성 중..."):
                gen = SyntheticClaimGenerator(seed=42)
                df = gen.generate(500, 0.15)
                validator = PandasBatchValidator()
                validated = validator.validate_dataframe(df)
            
            st.session_state.generated_data = validated
            st.success("✅ 완료! 페이지를 새로고침합니다.")
            st.rerun()

# ============================================================
# 푸터
# ============================================================
st.divider()
st.markdown(
    """
    <div style="text-align: center; color: #888; font-size: 0.85em;">
        RxHCC Integrity Dashboard v2.0 | 
        <a href="https://github.com/sechan9999/RxHCC" target="_blank">GitHub</a> | 
        Built with Streamlit, LangGraph, Pandas
    </div>
    """,
    unsafe_allow_html=True
)
