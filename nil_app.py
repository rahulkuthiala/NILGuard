from datetime import datetime, timezone
import streamlit as st
import anthropic
import gspread
from google.oauth2.service_account import Credentials
from pypdf import PdfReader
from fpdf import FPDF

# ── PAGE CONFIG ───────────────────────────────────────────────
st.set_page_config(
    page_title="NIL Contract Risk Analyzer",
    page_icon="⚖️",
    layout="centered"
)

# ── STYLES ────────────────────────────────────────────────────
st.markdown("""
    <style>
        .main { max-width: 780px; margin: auto; }
        .risk-card {
            background-color: #1e1e1e;
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 14px;
        }
        .risk-title { font-size: 16px; font-weight: 700; margin-bottom: 6px; }
        .risk-desc  { font-size: 14px; color: #cccccc; line-height: 1.6; }
        .score-badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 700;
            margin-right: 8px;
        }
        .high   { background-color: #ff4444; color: white; }
        .medium { background-color: #ffaa00; color: black; }
        .low    { background-color: #22bb55; color: white; }
        .summary-box {
            background-color: #1a1a2e;
            border-left: 4px solid #4a90e2;
            border-radius: 6px;
            padding: 16px 20px;
            font-size: 15px;
            line-height: 1.7;
            color: #e0e0e0;
            margin-bottom: 24px;
        }
        .verdict-box {
            border-radius: 10px;
            padding: 18px 22px;
            font-size: 15px;
            line-height: 1.7;
            margin-top: 10px;
        }
        .disclaimer {
            font-size: 12px;
            color: #888888;
            text-align: center;
            margin-top: 30px;
            padding-top: 16px;
            border-top: 1px solid #333;
        }
    </style>
""", unsafe_allow_html=True)

# ── SESSION STATE / NAVIGATION ────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "landing"

def go_to_tool():
    st.session_state.page = "tool"

# ── ANALYTICS LOGGING ─────────────────────────────────────────
def log_analytics_event():
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=scopes
        )
        gc = gspread.authorize(creds)
        sheet = gc.open("NILGuard Analytics").sheet1
        sheet.append_row([datetime.now(timezone.utc).isoformat()])
    except Exception:
        pass

# ── PDF REPORT BUILDER ────────────────────────────────────────
def sanitize_pdf_text(text):
    return text.encode("latin-1", "replace").decode("latin-1")

def build_report_pdf(summary_text, risks_list, overall_text):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, sanitize_pdf_text("NIL Contract Risk Analysis Report"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Contract Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 7, sanitize_pdf_text(summary_text.strip()), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Risks Identified", new_x="LMARGIN", new_y="NEXT")
    for risk in risks_list:
        parts = risk.split(" - ", 2)
        pdf.set_font("Helvetica", "", 11)
        if len(parts) == 3:
            score_part, name_part, desc_part = parts
            score_clean = score_part.replace("[", "").replace("]", "")
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 7, sanitize_pdf_text(f"[{score_clean}] {name_part}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 7, sanitize_pdf_text(desc_part), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 7, sanitize_pdf_text(risk), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Overall Verdict", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 7, sanitize_pdf_text(overall_text.strip()), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 5, sanitize_pdf_text(
        "This tool is for informational purposes only and does not constitute legal advice. "
        "Always consult your athletic compliance office or a licensed attorney before signing any NIL agreement."
    ), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())

# ── SYSTEM PROMPT ─────────────────────────────────────────────
def build_system_prompt(state):
    if state and state != "Select your state":
        state_instruction = (
            f"The athlete is based in {state}. As part of your analysis, evaluate the contract against "
            f"{state}'s specific NIL laws and regulations, including any state statutes on disclosure "
            f"requirements, agent/representative registration, prohibited compensation categories "
            f"(e.g. alcohol, tobacco, gambling, adult entertainment, firearms), contract length limits, "
            f"or required school/compliance office disclosures. If a clause conflicts with or is restricted "
            f"by {state}'s NIL law, include it as its own entry in the RISKS list, scored using the same "
            f"scale below, with the risk name referencing the specific state rule (e.g. '[STATE] Disclosure "
            f"Requirement Violation'). If {state} has no NIL law provision relevant to a given clause, do not "
            f"invent one."
        )
    else:
        state_instruction = (
            "No state was provided, so skip state-specific NIL law analysis entirely and evaluate the "
            "contract only against general NCAA compliance guidelines."
        )

    return f"""
You are an NCAA compliance expert reviewing an NIL contract for a student-athlete.

{state_instruction}

Return your response in exactly this format and nothing else:

SUMMARY:
Write 3-4 plain English sentences summarizing what this contract is, who it is with, what the athlete is being paid, and what they are being asked to do. Write it like you are explaining it to a college student.

RISKS:
List every risk you find in the contract, including any state-specific NIL law issues identified above. For each one use exactly this format on a single line:
[SCORE/10] - RISK NAME - One sentence explaining why this is risky in plain English.

Rate each risk from 1 to 10 using this scale, and apply it strictly:
- 1-3: Minor inconvenience with no real impact.
- 4: Semi-meaningful but not urgent.
- 5-7: A genuine risk that could realistically cause problems.
- 8-10: Reserved strictly for a direct NCAA eligibility threat or serious financial harm — pay-for-play, booster involvement, prohibited products, school-tied compensation, large clawbacks, or NDAs that block compliance reporting.
Nothing may score above 7 unless it is a direct eligibility threat or one of the serious financial harms listed above.

Posting frequency, content approval rights, scheduling obligations, and workload requirements are inconveniences, not eligibility or financial threats, and must never score above 4/10. Only score one of these above 4 if it includes an explicit financial penalty for non-compliance (e.g. a fee, forfeiture, or clawback triggered by missing a post or deadline) — in that case, score it based on the severity of the penalty itself.

Order the list from highest score to lowest score.
If a section of the contract is fine, do not include it.

OVERALL SCORE:
Overall Risk Score: X/10 - One sentence verdict on whether the athlete should sign, negotiate, or walk away.
"""

# ── LANDING PAGE ───────────────────────────────────────────────
if st.session_state.page == "landing":
    st.markdown(
        """
        <style>
            .stApp {
                background-image:
                    linear-gradient(rgba(8, 12, 24, 0.72), rgba(8, 12, 24, 0.8)),
                    url('https://images.unsplash.com/photo-1461896836934-ffe607ba8211');
                background-size: cover;
                background-position: center center;
                background-repeat: no-repeat;
                background-attachment: fixed;
            }
            .main .block-container {
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                padding-top: 0;
                padding-bottom: 80px;
                max-width: 1000px;
            }
            .nilguard-title {
                font-size: 64px;
                font-weight: 800;
                color: #ffffff;
                text-align: center;
                letter-spacing: 0.5px;
                margin: 0;
                text-shadow: 0 2px 24px rgba(0, 0, 0, 0.6);
            }
            .landing-desc {
                font-size: 18px;
                line-height: 2;
                color: #ffffff;
                text-align: center;
                max-width: 640px;
                margin: 28px auto 40px auto;
                text-shadow: 0 1px 10px rgba(0, 0, 0, 0.5);
            }
            div[data-testid="stButton"] > button {
                background: linear-gradient(135deg, #f5c451, #d4af37);
                color: #0a0f1e;
                font-weight: 700;
                font-size: 16px;
                border: none;
                border-radius: 8px;
                padding: 0.85rem 0;
                box-shadow: 0 0 18px rgba(245, 196, 81, 0.55), 0 0 40px rgba(212, 175, 55, 0.25);
                transition: box-shadow 0.2s ease, transform 0.2s ease;
            }
            div[data-testid="stButton"] > button:hover {
                box-shadow: 0 0 26px rgba(245, 196, 81, 0.8), 0 0 55px rgba(212, 175, 55, 0.4);
                transform: translateY(-1px);
                color: #0a0f1e;
                border: none;
            }
            .section-heading {
                font-size: 32px;
                font-weight: 800;
                color: #ffffff;
                text-align: center;
                margin: 70px 0 40px 0;
                text-shadow: 0 2px 16px rgba(0, 0, 0, 0.6);
            }
            .step-card {
                background: rgba(10, 15, 30, 0.55);
                border: 1px solid rgba(212, 175, 55, 0.25);
                border-radius: 12px;
                padding: 28px 20px;
                text-align: center;
                height: 100%;
            }
            .step-number {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: linear-gradient(135deg, #f5c451, #d4af37);
                color: #0a0f1e;
                font-weight: 800;
                font-size: 18px;
                margin-bottom: 16px;
            }
            .step-title {
                font-size: 17px;
                font-weight: 700;
                color: #ffffff;
                margin-bottom: 10px;
            }
            .step-desc {
                font-size: 14px;
                line-height: 1.6;
                color: #cbd2de;
            }
            .why-it-matters-text {
                font-size: 18px;
                line-height: 1.9;
                color: #ffffff;
                text-align: center;
                max-width: 680px;
                margin: 0 auto;
                text-shadow: 0 1px 10px rgba(0, 0, 0, 0.5);
            }
            div[data-testid="stExpander"] {
                background: rgba(10, 15, 30, 0.55);
                border: 1px solid rgba(212, 175, 55, 0.25);
                border-radius: 10px;
                margin-bottom: 12px;
            }
            div[data-testid="stExpander"] summary,
            div[data-testid="stExpander"] summary p {
                color: #ffffff;
                font-weight: 600;
                font-size: 15px;
            }
            .faq-answer {
                font-size: 14px;
                line-height: 1.7;
                color: #cbd2de;
                padding: 4px 4px 8px 4px;
            }
        </style>

        <div class="nilguard-title">⚖️ NILGuard</div>
        <div class="landing-desc">
        Welcome to NILGuard — an AI-powered contract analysis tool built for college athletes.
        Paste your contract or upload a PDF and get an instant plain-English breakdown of every
        risky clause, scored by severity and tailored to your state's NIL laws so you know exactly
        what you're signing before you sign it.
        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.button("Let's Get Started", type="primary", use_container_width=True, on_click=go_to_tool)

    # ── HOW IT WORKS ─────────────────────────────────────────
    with st.expander("How It Works"):
        steps = [
            ("1", "Upload or Paste Your Contract", "Upload a PDF or paste the full text of your NIL contract directly into the tool."),
            ("2", "Select Your State", "Choose the state where you compete so the analysis is tailored to your state's specific NIL laws."),
            ("3", "Get Your Risk Report", "Receive an instant plain-English breakdown of every risky clause scored by severity with a downloadable PDF report."),
        ]

        step_col1, step_col2, step_col3 = st.columns(3)
        for col, (num, step_title, step_desc) in zip([step_col1, step_col2, step_col3], steps):
            with col:
                st.markdown(
                    f"""
                    <div class="step-card">
                        <div class="step-number">{num}</div>
                        <div class="step-title">{step_title}</div>
                        <div class="step-desc">{step_desc}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    # ── WHY IT MATTERS ───────────────────────────────────────
    with st.expander("Why It Matters"):
        st.markdown(
            """
            <div class="why-it-matters-text">
            Most college athletes sign NIL contracts without fully understanding what they are agreeing to.
            A single clause can put your eligibility, finances, and future at risk.
            </div>
            """,
            unsafe_allow_html=True
        )

    # ── FAQ ───────────────────────────────────────────────────
    st.markdown('<div class="section-heading">FAQ</div>', unsafe_allow_html=True)

    faqs = [
        (
            "What is NIL?",
            "NIL stands for Name, Image, and Likeness. It refers to a college athlete's right to profit "
            "from their own identity through endorsement deals, sponsorships, social media partnerships, "
            "and appearances."
        ),
        (
            "What can brands legally ask me to do?",
            "Brands can ask you to post sponsored content, make appearances, and promote their products. "
            "They cannot tie your compensation to your athletic performance, require you to stay at a "
            "specific school, or ask you to promote prohibited products like alcohol, gambling, or banned "
            "supplements."
        ),
        (
            "What should every NIL contract include?",
            "Every contract should clearly state your compensation, the length of the deal, exactly what "
            "you are required to do, who owns the content you create, and how either party can exit the "
            "agreement."
        ),
        (
            "Do I need to report my NIL deals to my school?",
            "In most states yes. Most state NIL laws require you to disclose your deals to your athletic "
            "compliance office before or shortly after signing. Failing to disclose can put your "
            "eligibility at risk."
        ),
    ]

    faq_col1, faq_col2, faq_col3 = st.columns([1, 3, 1])
    with faq_col2:
        for question, answer in faqs:
            with st.expander(question):
                st.markdown(f'<div class="faq-answer">{answer}</div>', unsafe_allow_html=True)

# ── MAIN TOOL ────────────────────────────────────────────────
else:
    # ── HEADER ────────────────────────────────────────────────
    st.title("⚖️ NIL Contract Risk Analyzer")
    st.markdown("Paste your NIL contract below and get an instant risk assessment based on NCAA compliance guidelines.")
    st.divider()

    # ── API KEY INPUT ─────────────────────────────────────────
    api_key = st.secrets["ANTHROPIC_API_KEY"]

    # ── STATE SELECTION ───────────────────────────────────────
    US_STATES = [
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
        "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
        "New Hampshire", "New Jersey", "New Mexico", "New York",
        "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
        "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
        "West Virginia", "Wisconsin", "Wyoming"
    ]

    selected_state = st.selectbox(
        "Select Your State",
        ["Select your state"] + US_STATES
    )

    # ── CONTRACT INPUT ─────────────────────────────────────────
    input_mode = st.radio(
        "How would you like to provide your contract?",
        ["Paste Text", "Upload PDF"],
        horizontal=True
    )

    contract_text = ""

    if input_mode == "Paste Text":
        contract_text = st.text_area(
            "Paste Your NIL Contract Here",
            height=300,
            placeholder="Paste the full text of your NIL contract here..."
        )
    else:
        uploaded_pdf = st.file_uploader("Upload Your NIL Contract (PDF)", type=["pdf"])
        if uploaded_pdf is not None:
            try:
                reader = PdfReader(uploaded_pdf)
                extracted_pages = [page.extract_text() or "" for page in reader.pages]
                contract_text = "\n".join(extracted_pages).strip()
                if contract_text:
                    st.success(f"Extracted text from {len(reader.pages)} page(s).")
                    with st.expander("Preview extracted text"):
                        st.text_area("Extracted Contract Text", value=contract_text, height=200, disabled=True)
                else:
                    st.warning("No selectable text found in this PDF. It may be a scanned image — try pasting the text instead.")
            except Exception as e:
                st.error(f"Could not read PDF: {e}")

    analyze_btn = st.button("Analyze Contract", type="primary", use_container_width=True)

    # ── ANALYSIS ──────────────────────────────────────────────
    if analyze_btn:
        if not api_key.strip():
            st.error("Please enter your Anthropic API key.")
        elif not contract_text.strip():
            st.error("Please paste your contract text or upload a PDF before analyzing.")
        else:
            with st.spinner("Analyzing your contract..."):
                try:
                    client = anthropic.Anthropic(api_key=api_key)
                    message = client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=2048,
                        system=build_system_prompt(selected_state),
                        messages=[
                            {
                                "role": "user",
                                "content": f"Analyze this NIL contract:\n\n{contract_text.strip()}"
                            }
                        ]
                    )
                    response = message.content[0].text

                    log_analytics_event()

                    # ── PARSE RESPONSE ──────────────────────────
                    summary_text  = ""
                    risks_list    = []
                    overall_text  = ""
                    current       = ""

                    for line in response.splitlines():
                        s = line.strip()
                        if s == "SUMMARY:":
                            current = "summary"
                        elif s == "RISKS:":
                            current = "risks"
                        elif s == "OVERALL SCORE:":
                            current = "overall"
                        elif not s:
                            continue
                        elif current == "summary":
                            summary_text += s + " "
                        elif current == "risks" and s.startswith("["):
                            risks_list.append(s)
                        elif current == "overall":
                            overall_text += s + " "

                    # ── RENDER SUMMARY ──────────────────────────
                    st.subheader("📋 Contract Summary")
                    st.markdown(f'<div class="summary-box">{summary_text.strip()}</div>', unsafe_allow_html=True)

                    # ── RENDER RISKS ─────────────────────────────
                    st.subheader("⚠️ Risks Identified")

                    for risk in risks_list:
                        parts = risk.split(" - ", 2)
                        if len(parts) == 3:
                            score_part = parts[0]
                            name_part  = parts[1]
                            desc_part  = parts[2]

                            try:
                                score = int(score_part.replace("[", "").replace("]", "").replace("/10", "").strip())
                            except:
                                score = 0

                            if score >= 8:
                                badge_class = "high"
                                icon = "🔴"
                            elif score >= 5:
                                badge_class = "medium"
                                icon = "🟡"
                            else:
                                badge_class = "low"
                                icon = "🟢"

                            st.markdown(f"""
                            <div class="risk-card">
                                <div class="risk-title">
                                    <span class="score-badge {badge_class}">{score_part.replace("[","").replace("]","")}</span>
                                    {icon} {name_part}
                                </div>
                                <div class="risk-desc">{desc_part}</div>
                            </div>
                            """, unsafe_allow_html=True)

                    # ── RENDER OVERALL VERDICT ──────────────────
                    st.subheader("📌 Overall Verdict")

                    overall_parts = overall_text.strip().split(" - ", 1)
                    if len(overall_parts) == 2:
                        score_line = overall_parts[0]
                        verdict    = overall_parts[1]

                        try:
                            overall_score = int(score_line.replace("Overall Risk Score:", "").replace("/10", "").strip())
                        except:
                            overall_score = 0

                        if overall_score >= 8:
                            verdict_color = "#ff4444"
                            verdict_bg    = "#2a1010"
                        elif overall_score >= 5:
                            verdict_color = "#ffaa00"
                            verdict_bg    = "#2a2010"
                        else:
                            verdict_color = "#22bb55"
                            verdict_bg    = "#102a18"

                        st.markdown(f"""
                        <div class="verdict-box" style="background-color:{verdict_bg}; border-left: 4px solid {verdict_color};">
                            <strong style="color:{verdict_color}; font-size:18px;">{score_line}</strong><br><br>
                            {verdict}
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="verdict-box">{overall_text.strip()}</div>', unsafe_allow_html=True)

                    # ── DISCLAIMER ───────────────────────────────
                    st.markdown("""
                    <div class="disclaimer">
                        ⚠️ This tool is for informational purposes only and does not constitute legal advice.
                        Always consult your athletic compliance office or a licensed attorney before signing any NIL agreement.
                    </div>
                    """, unsafe_allow_html=True)

                    # ── DOWNLOAD REPORT ─────────────────────────
                    pdf_bytes = build_report_pdf(summary_text, risks_list, overall_text)
                    st.download_button(
                        label="⬇️ Download Report (PDF)",
                        data=pdf_bytes,
                        file_name="nil_contract_risk_report.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

                except anthropic.AuthenticationError:
                    st.error("Invalid API key. Double-check your key at https://console.anthropic.com")
                except anthropic.RateLimitError:
                    st.error("Rate limit hit. Wait a moment and try again.")
                except Exception as e:
                    st.error(f"Something went wrong: {e}")
