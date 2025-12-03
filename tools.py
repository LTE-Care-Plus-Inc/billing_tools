# app.py
import io
import re
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st


# -----------------------------
# PDF → TEXT
# -----------------------------
def pdf_bytes_to_text(pdf_bytes: bytes, preserve_layout: bool = True) -> str:
    """
    Convert PDF bytes to a single text string.
    Adds '--- Page X ---' separators between pages.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    all_text = []

    for page_num in range(total_pages):
        page = doc[page_num]
        if preserve_layout:
            text = page.get_text(
                "text",
                flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
            )
        else:
            text = page.get_text("text")

        all_text.append(f"--- Page {page_num + 1} ---\n{text}\n\n")

    doc.close()
    return "".join(all_text)


# -----------------------------
# TEXT → PARSED NOTES
# -----------------------------
def parse_notes(text: str):
    """
    Parse client notes from text extracted from PDF.
    Returns a list of dicts.
    """
    # Split notes by "Client:" (but keep the keyword)
    blocks = re.split(r"(?=Client:)", text)

    results = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # ----------------------------
        # Client Name
        # ----------------------------
        client_match = re.search(r"Client:\s*([^\n,]+)", block)
        client_name = client_match.group(1).strip() if client_match else ""

        if not client_name:
            # If no client name, skip block
            continue

        # ----------------------------
        # Rendering Provider
        # ----------------------------
        provider_match = re.search(r"Rendering Provider:\s*([^\n]+)", block)
        provider = provider_match.group(1).strip() if provider_match else ""

        # ----------------------------
        # Date (YYYY/MM/DD)
        # ----------------------------
        date_match = re.search(r"Date:\s*([0-9]{4}/[0-9]{2}/[0-9]{2})", block)
        date_value = date_match.group(1) if date_match else ""

        # ----------------------------
        # Session Time
        # - if just "-" or blank → ""
        # - if real time range → keep it
        # ----------------------------
        session_time_match = re.search(
            r"Session Time:\s*(?:"
            r"([0-9]{1,2}:[0-9]{2}\s*(?:AM|PM)?\s*-\s*[0-9]{1,2}:[0-9]{2}\s*(?:AM|PM)?)"  # valid time range
            r"|-"  # OR literal dash
            r")?",
            block,
            re.IGNORECASE,
        )

        if session_time_match:
            session_time = session_time_match.group(1)
            if session_time is None:
                session_time = ""  # dash or missing → blank
        else:
            session_time = ""

        results.append(
            {
                "Client": client_name,
                "Rendering Provider": provider,
                "Date": date_value,
                "Session Time": session_time,
            }
        )

    return results


def results_to_excel_bytes(results, sheet_name="Sheet1") -> bytes:
    """
    Convert results list[dict] → Excel file bytes.
    """
    df = pd.DataFrame(results)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)
    return output


# -----------------------------
# STREAMLIT APP
# -----------------------------
st.set_page_config(page_title="HiRasmus PDF → TXT → Excel", layout="wide")
st.title("📄 HiRasmus Session Notes – PDF → TXT → Excel")

# Keep text across tabs
if "extracted_text" not in st.session_state:
    st.session_state["extracted_text"] = None

tab1, tab2 = st.tabs(["1️⃣ PDF → TXT", "2️⃣ TXT → Excel"])

# -----------------------------
# TAB 1: PDF → TXT
# -----------------------------
with tab1:
    st.header("Step 1: Upload PDF and extract to text")

    pdf_file = st.file_uploader("Upload HiRasmus Session Notes PDF", type=["pdf"])

    preserve_layout = st.checkbox(
        "Preserve layout (columns/tables spacing)",
        value=True,
        help="Uses PyMuPDF flags to preserve whitespace.",
    )

    if pdf_file is not None:
        if st.button("Extract text from PDF"):
            try:
                text = pdf_bytes_to_text(pdf_file.read(), preserve_layout=preserve_layout)
                st.session_state["extracted_text"] = text

                st.success("Text extracted successfully!")

                # Preview a chunk of the text
                st.subheader("Text preview")
                preview_len = 3000
                st.text(text[:preview_len] + ("\n...\n[Truncated preview]" if len(text) > preview_len else ""))

                # Download TXT
                txt_filename = Path(pdf_file.name).with_suffix(".txt").name
                st.download_button(
                    label="⬇️ Download .txt file",
                    data=text,
                    file_name=txt_filename,
                    mime="text/plain",
                )
            except Exception as e:
                st.error(f"Error during PDF → text conversion: {e}")

# -----------------------------
# TAB 2: TXT → Excel
# -----------------------------
with tab2:
    st.header("Step 2: Parse text and generate Excel")

    source_choice = st.radio(
        "Choose text source:",
        ["Use text from Step 1", "Upload a .txt file"],
        index=0,
    )

    text_for_parsing = None

    if source_choice == "Use text from Step 1":
        if st.session_state.get("extracted_text"):
            text_for_parsing = st.session_state["extracted_text"]
            st.info("Using text extracted in Step 1.")
        else:
            st.warning("No extracted text available yet. Go to Step 1 and process a PDF first.")
    else:
        txt_file = st.file_uploader("Upload a .txt file", type=["txt"], key="txt_uploader")
        if txt_file is not None:
            text_for_parsing = txt_file.read().decode("utf-8", errors="ignore")

    if text_for_parsing:
        if st.button("Parse notes and generate Excel"):
            try:
                results = parse_notes(text_for_parsing)
                if not results:
                    st.warning("No notes found. Check that the text contains 'Client:' blocks.")
                else:
                    df = pd.DataFrame(results)
                    st.success(f"Parsed {len(df)} rows.")

                    st.subheader("Parsed data preview")
                    st.dataframe(df.head(50))

                    excel_bytes = results_to_excel_bytes(results)
                    st.download_button(
                        label="⬇️ Download Excel (.xlsx)",
                        data=excel_bytes,
                        file_name="session_notes_parsed.xlsx",
                        mime=(
                            "application/vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet"
                        ),
                    )
            except Exception as e:
                st.error(f"Error during parsing / Excel generation: {e}")
