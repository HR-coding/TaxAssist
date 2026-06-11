"""
OCR / document-understanding extraction pipeline.
Schema source: schemas.jsonc (General OCR & Extraction Logic)

Designed for *cluttered, dense, multi-page* Indian tax documents (Form 16,
broker P&L statements, AIS, etc.) where labels and values live in separate
table columns and the file may be either a digital PDF or a scanned image.

Strategy (most robust → fallback):
  1. NATIVE PDF VISION  — the raw PDF bytes are handed to Gemini 2.5-flash as a
     document Part. Gemini reads the page visually, so multi-column tables,
     merged cells, stamps and *scanned* pages are all understood. This is the
     primary signal and the big win for packed documents like Form 16.
  2. TEXT + TABLE GROUNDING — pdfplumber also extracts the digital text layer
     AND the table grid (extract_tables). These are passed alongside the PDF as
     a high-precision cross-reference so exact digits are never misread. When
     the PDF is image-only this layer is simply empty and vision carries it.
  3. CANONICAL FIELD DICTIONARY — the prompt enumerates the exact ITR field
     paths the downstream itr_mapper understands, so the model maps
     deterministically instead of inventing paths that get silently dropped.

Temperature is 0.0 for determinism. The extractor returns ONLY numerical
financial values mapped to ITR field paths — never names, PANs or addresses
(PII is handled separately by the pii_vault on structured records).
"""
import io
import json
import hashlib
import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

logger = logging.getLogger("ocr_extractor")

# Inline-data ceiling for the Gemini SDK. Above this the File API is required;
# below it we can embed the PDF bytes directly in the request.
_MAX_INLINE_BYTES = 18 * 1024 * 1024
_DEFAULT_MODEL = "gemini-2.5-flash"


# ─────────────────────────────────────────────
# Canonical ITR field dictionary
# (kept in sync with itr_mapper._ARRAY_FIELD_PREFIXES + the ledger models)
# ─────────────────────────────────────────────

_FIELD_DICTIONARY = """
VALID target_itr_field PATHS — you MUST map every value to one of these exact strings.
Do not invent new paths. If a value does not fit any path, omit it.

ITR-1 (salaried / simple):
  salary_income.gross_salary            -> Form 16 Part B item 1 "Gross Salary"
                                           (the TOTAL of 17(1)+17(2)+17(3); NOT item 6/8)
  salary_income.exempt_allowances       -> allowances exempt u/s 10 (Part B item 2)
  salary_income.professional_tax        -> "Tax on employment" / professional tax (Part B 4(b))
  salary_income.entertainment_allowance -> entertainment allowance (Part B 4(a))
  house_property.gross_rent_received
  house_property.municipal_taxes_paid
  house_property.interest_on_borrowed_capital
  other_sources.family_pension
  other_sources.savings_interest        [ARRAY] savings bank interest
  other_sources.deposit_interest        [ARRAY] FD / RD / term-deposit interest
  other_sources.dividend_income         [ARRAY]
  other_sources.others                  [ARRAY] any other taxable income
  deductions.sec_80c                    [ARRAY] LIC/PPF/ELSS/EPF (use DEDUCTIBLE amount)
  deductions.sec_80ccc                  [ARRAY]
  deductions.sec_80ccd1                 [ARRAY] employee NPS
  deductions.sec_80ccd1b                [ARRAY] additional NPS (50k)
  deductions.sec_80ccd2                 [ARRAY] employer NPS
  deductions.sec_80d                    [ARRAY] health insurance
  deductions.sec_80dd  / sec_80ddb / sec_80u
  deductions.sec_80e   / sec_80ee / sec_80eea / sec_80eeb
  deductions.sec_80g   / sec_80gg / sec_80gga / sec_80ggc
  taxes_paid.tds_on_salary              [ARRAY] Form 16 Part A "Total" tax deducted
  taxes_paid.tds_other_than_salary      [ARRAY] Form 16A TDS
  taxes_paid.advance_tax                [ARRAY]
  taxes_paid.self_assessment_tax        [ARRAY]
  taxes_paid.tcs                        [ARRAY]

ITR-2 (capital gains / multiple employers / VDA) — use when document implies it:
  schedule_salary                       [ARRAY] one item per employer
  schedule_house_property               [ARRAY] one item per property
  schedule_capital_gains.short_term_gains [ARRAY]
  schedule_capital_gains.long_term_gains  [ARRAY]
  schedule_other_sources.savings_interest / fd_interest / dividend_income_domestic [ARRAY]
  schedule_via_deductions.sec_80c / sec_80d [ARRAY]
  schedule_vda.transactions             [ARRAY] crypto / virtual digital assets
""".strip()


_DOC_TYPE_HINTS = """
DOCUMENT-SPECIFIC READING RULES:

FORM_16 (TDS certificate on salary, the most common):
  - It has TWO parts. PART A = TDS summary (quarterly tables + a "Total" row of
    tax deducted). PART B (Annexure) = the salary + deductions breakdown.
  - PART A "Total" under "Amount of tax deducted" -> taxes_paid.tds_on_salary.
  - PART B item 1 "Gross Salary" total -> salary_income.gross_salary. Items
    1(a) 17(1), 1(b) perquisites 17(2), 1(c) 17(3) are its components — report
    the item-1 TOTAL, not the sub-rows, unless only sub-rows have numbers.
  - PART B item 4(b) "Tax on employment" -> salary_income.professional_tax.
  - Chapter VI-A is shown in THREE money columns:
    "Gross Amount" | "Qualifying amount" | "Deductible amount".
    ALWAYS take the rightmost DEDUCTIBLE amount for sec_80* values.
  - IGNORE computed totals item 6 "Income chargeable under salaries",
    item 8 "Gross total income", item 10/11/12/14/16 — these are derived, not inputs.

FORM_16A: TDS on non-salary income -> taxes_paid.tds_other_than_salary.
BROKER_STATEMENT: realised STCG -> schedule_capital_gains.short_term_gains;
    realised LTCG -> schedule_capital_gains.long_term_gains.
BANK_STATEMENT / FD_CERTIFICATE: interest credited -> other_sources.deposit_interest
    (FD) or other_sources.savings_interest (savings).
INVESTMENT_PROOF: map to the matching deductions.sec_80* path.
AIS_STATEMENT: reconcile all reported incomes to their nearest path.
""".strip()


# ─────────────────────────────────────────────
# Extraction models
# ─────────────────────────────────────────────

class SingleExtraction(BaseModel):
    """One financial value mapped to one ITR field path."""
    target_itr_field: str = Field(
        description="Dot-notation ITR schema path from the VALID list, "
                    "e.g. 'salary_income.gross_salary' or 'deductions.sec_80c'"
    )
    extracted_numerical_value: float = Field(
        description="The numerical amount found for this field in INR (digits only, no commas)"
    )
    source_label: str = Field(
        default="",
        description="The exact label/line text in the document this value was read from, "
                    "for human verification (e.g. 'Part B item 1(d) Total')"
    )
    page: int = Field(
        default=0,
        description="1-based page number where this value appears"
    )
    confidence: str = Field(
        default="HIGH",
        description="HIGH | MEDIUM | LOW — confidence in this extraction"
    )


class TaxDocumentExtraction(BaseModel):
    """Structured output schema for Gemini extraction."""
    document_type: str = Field(
        description="One of: FORM_16, FORM_16A, BROKER_STATEMENT, INVESTMENT_PROOF, "
                    "BANK_STATEMENT, FD_CERTIFICATE, AIS_STATEMENT, RENTAL_AGREEMENT, UNKNOWN"
    )
    financial_year: str = Field(
        description="Financial year of the document, e.g. '2025-26'. Empty if not stated."
    )
    extractions: List[SingleExtraction] = Field(
        description="Every financial value found, each mapped to its ITR field path"
    )
    extraction_notes: str = Field(
        default="",
        description="Short note on anything ambiguous, blank, or assumed (e.g. 'template "
                    "form with no filled values')"
    )


# ─────────────────────────────────────────────
# Local text + table grounding (pdfplumber)
# ─────────────────────────────────────────────

def _extract_text_and_tables(file_bytes: bytes) -> tuple[str, str, int]:
    """
    Returns (raw_text, rendered_tables, page_count).
    Either string may be empty when the PDF is image-only — that is fine, the
    native-vision path still handles the document.
    """
    try:
        import pdfplumber
    except ImportError:
        # Grounding layer is an enhancement, not a requirement — native PDF
        # vision still reads the document. Degrade gracefully.
        logger.warning("pdfplumber not installed; using vision-only (pip install pdfplumber for digit grounding).")
        return "", "", 0

    raw_text_parts: List[str] = []
    table_parts: List[str] = []
    page_count = 0

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_count = len(pdf.pages)
            for page_no, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    raw_text_parts.append(f"--- PAGE {page_no} ---\n{text}")

                # Tables preserve the columnar label↔value relationship that
                # flat text extraction destroys — critical for Form 16.
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []
                for t_idx, table in enumerate(tables, start=1):
                    rendered = _render_table(table)
                    if rendered:
                        table_parts.append(
                            f"--- PAGE {page_no} TABLE {t_idx} ---\n{rendered}"
                        )
    except Exception as e:
        logger.warning(f"pdfplumber parse failed: {e}. Falling back to vision-only.")

    return "\n\n".join(raw_text_parts), "\n\n".join(table_parts), page_count


def _render_table(table: List[List[Optional[str]]]) -> str:
    """Render a pdfplumber table as pipe-delimited rows, keeping columns aligned."""
    rows = []
    for row in table:
        cells = [(c or "").replace("\n", " ").strip() for c in row]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


# ─────────────────────────────────────────────
# Prompt assembly
# ─────────────────────────────────────────────

def _build_user_prompt(raw_text: str, rendered_tables: str, page_count: int) -> str:
    grounding = []
    if rendered_tables.strip():
        grounding.append(
            "EXTRACTED TABLE GRID (digital text layer — use to confirm exact digits; "
            "columns are pipe-delimited):\n" + rendered_tables
        )
    if raw_text.strip():
        grounding.append("EXTRACTED RAW TEXT (digital text layer):\n" + raw_text)
    if not grounding:
        grounding.append(
            "(No digital text layer — this is a scanned/image PDF. Read it visually "
            "from the attached document.)"
        )

    return (
        f"Extract all financial values from the attached Indian tax document "
        f"({page_count or 'unknown'} page(s)) and map each to its ITR field path.\n\n"
        f"Read the document PRIMARILY from the attached PDF (visual layout is "
        f"authoritative for which value belongs to which label). Use the extracted "
        f"text/tables below only to confirm exact digits.\n\n"
        f"{_FIELD_DICTIONARY}\n\n"
        f"{_DOC_TYPE_HINTS}\n\n"
        + "\n\n".join(grounding)
    )


_SYSTEM_INSTRUCTION = (
    "You are a strict, deterministic data-extraction engine for Indian income tax "
    "documents. Rules:\n"
    "1. Extract ONLY numerical financial values that are actually present and "
    "filled in. If the document is a blank template or a field is empty, do NOT "
    "emit a value for it — return an empty extractions list and say so in notes.\n"
    "2. Map every value to one EXACT path from the provided VALID list. Never "
    "invent a path.\n"
    "3. In multi-column tables (e.g. Chapter VI-A Gross/Qualifying/Deductible), "
    "pick the column specified by the reading rules (Deductible for deductions).\n"
    "4. Never output names, PAN numbers, addresses, account numbers or any PII — "
    "only financial amounts and their field paths. Strip commas/currency symbols; "
    "values are plain numbers in INR.\n"
    "5. Do not output derived totals that the system recomputes itself "
    "(net income, gross total income, tax payable)."
)


# ─────────────────────────────────────────────
# Core extraction function
# ─────────────────────────────────────────────

def extract_financial_data(
    file_bytes: bytes,
    file_id: str,
    mime_type: str = "application/pdf",
    model: str = _DEFAULT_MODEL,
) -> dict:
    """
    Extract structured financial data from a tax document.

    Uses native Gemini PDF vision (handles dense tables AND scanned pages) with a
    pdfplumber text+table grounding layer for digit-level precision.

    Args:
        file_bytes: Raw document bytes (downloaded from Google Drive).
        file_id:    Drive file ID, for logging/tracing.
        mime_type:  Document MIME type (default application/pdf).
        model:      Gemini model id.

    Returns:
        Dict with:
          - extraction:       TaxDocumentExtraction dict (document_type,
                              financial_year, extractions[], extraction_notes)
          - data_hash:        SHA-256 of the extracted JSON (change detection)
          - raw_text_length:  chars from the digital text layer (0 ⇒ scanned)
          - page_count:       number of PDF pages
          - vision_used:      whether the native PDF Part was sent
    """
    is_pdf = mime_type == "application/pdf"

    # Step 1 — local text + table grounding (skipped for non-PDF inputs).
    raw_text, rendered_tables, page_count = ("", "", 0)
    if is_pdf:
        raw_text, rendered_tables, page_count = _extract_text_and_tables(file_bytes)

    if is_pdf and not raw_text.strip():
        logger.info(f"[{file_id}] No digital text layer — relying on native vision (scanned PDF).")

    # Step 2 — build content. Attach the document natively when it fits inline.
    user_prompt = _build_user_prompt(raw_text, rendered_tables, page_count)
    contents: list = []
    vision_used = False
    if len(file_bytes) <= _MAX_INLINE_BYTES:
        try:
            contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime_type))
            vision_used = True
        except Exception as e:
            logger.warning(f"[{file_id}] Could not attach document for vision: {e}. Text-only.")
    else:
        logger.warning(
            f"[{file_id}] Document is {len(file_bytes)//(1024*1024)}MB (> inline limit); "
            "using text-only extraction."
        )
    contents.append(user_prompt)

    # Step 3 — Gemini extraction with strict schema (one light retry).
    client = genai.Client()
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=TaxDocumentExtraction,
        temperature=0.0,
    )

    last_err: Optional[Exception] = None
    extraction_dict: Optional[dict] = None
    for attempt in (1, 2):
        try:
            response = client.models.generate_content(
                model=model, contents=contents, config=config
            )
            extraction_dict = json.loads(response.text)
            break
        except Exception as e:
            last_err = e
            logger.warning(f"[{file_id}] extraction attempt {attempt} failed: {e}")

    if extraction_dict is None:
        logger.error(f"[{file_id}] extraction failed after retries: {last_err}")
        extraction_dict = {
            "document_type": "UNKNOWN",
            "financial_year": "",
            "extractions": [],
            "extraction_notes": f"extraction_error: {last_err}",
        }

    # Step 4 — hash the extracted financial JSON (content, not filename).
    data_hash = hashlib.sha256(
        json.dumps(extraction_dict, sort_keys=True).encode("utf-8")
    ).hexdigest()

    logger.info(
        f"[{file_id}] {extraction_dict.get('document_type', 'UNKNOWN')} | "
        f"{len(extraction_dict.get('extractions', []))} fields | "
        f"{page_count} page(s) | vision={vision_used} | hash={data_hash[:12]}..."
    )

    return {
        "extraction": extraction_dict,
        "data_hash": data_hash,
        "raw_text_length": len(raw_text),
        "page_count": page_count,
        "vision_used": vision_used,
    }


def hash_extraction(extraction_dict: dict) -> str:
    """Compute SHA-256 of an extraction result dict for the document_registry."""
    return hashlib.sha256(
        json.dumps(extraction_dict, sort_keys=True).encode("utf-8")
    ).hexdigest()
