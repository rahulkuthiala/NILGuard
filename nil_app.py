import streamlit as st
import anthropic
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

# ── HEADER ────────────────────────────────────────────────────
st.title("⚖️ NIL Contract Risk Analyzer")
st.markdown("Paste your NIL contract below and get an instant risk assessment based on NCAA compliance guidelines.")
st.divider()

# ── API KEY INPUT ─────────────────────────────────────────────
api_key = st.secrets["ANTHROPIC_API_KEY"]

# ── CONTRACT INPUT ────────────────────────────────────────────
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
SYSTEM_PROMPT = """
You are an NCAA compliance expert reviewing an NIL contract for a student-athlete.

Return your response in exactly this format and nothing else:

SUMMARY:
Write 3-4 plain English sentences summarizing what this contract is, who it is with, what the athlete is being paid, and what they are being asked to do. Write it like you are explaining it to a college student.

RISKS:
List every risk you find in the contract. For each one use exactly this format on a single line:
[SCORE/10] - RISK NAME - One sentence explaining why this is risky in plain English.

Rate each risk from 1 to 10 where 10 is the most serious eligibility threat and 1 is a very minor concern.
Order the list from highest score to lowest score.
If a section of the contract is fine, do not include it.

OVERALL SCORE:
Overall Risk Score: X/10 - One sentence verdict on whether the athlete should sign, negotiate, or walk away.
"""

# ── ANALYSIS ──────────────────────────────────────────────────
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
                    system=SYSTEM_PROMPT,
                    messages=[
                        {
                            "role": "user",
                            "content": f"Analyze this NIL contract:\n\n{contract_text.strip()}"
                        }
                    ]
                )
                response = message.content[0].text

                # ── PARSE RESPONSE ────────────────────────────
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

                # ── RENDER SUMMARY ────────────────────────────
                st.subheader("📋 Contract Summary")
                st.markdown(f'<div class="summary-box">{summary_text.strip()}</div>', unsafe_allow_html=True)

                # ── RENDER RISKS ──────────────────────────────
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

                # ── RENDER OVERALL VERDICT ────────────────────
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

                # ── DISCLAIMER ────────────────────────────────
                st.markdown("""
                <div class="disclaimer">
                    ⚠️ This tool is for informational purposes only and does not constitute legal advice.
                    Always consult your athletic compliance office or a licensed attorney before signing any NIL agreement.
                </div>
                """, unsafe_allow_html=True)

                # ── DOWNLOAD REPORT ────────────────────────────
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
