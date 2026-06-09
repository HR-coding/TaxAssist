"""
OCR extraction pipeline.
Schema source: schemas.jsonc (General OCR & Extraction Logic)

Uses pdfplumber for local PDF text extraction and Gemini 2.5-flash with a strict
Pydantic response schema to map document text to ITR field paths deterministically.
Temperature is set to 0.0 for maximum determinism (no hallucinations).
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


# ─────────────────────────────────────────────
# Extraction models
# ─────────────────────────────────────────────

class SingleExtraction(BaseModel):
    """One financial value mapped to one ITR field path."""
    target_itr_field: str = Field(
        description="Dot-notation ITR schema path, e.g. 'salary_income.gross_salary' or 'deductions.sec_80c'"
    )
    extracted_numerical_value: float = Field(
        description="The numerical amount found for this field in INR"
    )
    confidence: str = Field(
        default="HIGH",
        description="HIGH | MEDIUM | LOW — agent's confidence in this extraction"
    )


class TaxDocumentExtraction(BaseModel):
    """
    Structured output schema for Gemini extraction.
    Extends schemas.jsonc TaxTakeawayExtractor to support multiple fields per document.
    """
    document_type: str = Field(
        description="Must be one of: FORM_16, FORM_16A, BROKER_STATEMENT, INVESTMENT_PROOF, "
                    "BANK_STATEMENT, FD_CERTIFICATE, AIS_STATEMENT, RENTAL_AGREEMENT, UNKNOWN"
    )
    financial_year: str = Field(
        description="Financial year of the document, e.g. '2025-26'"
    )
    extractions: List[SingleExtraction] = Field(
        description="All financial values found in this document, each mapped to its ITR field path"
    )


# ─────────────────────────────────────────────
# Core extraction function
# ─────────────────────────────────────────────

def extract_financial_data(file_bytes: bytes, file_id: str) -> dict:
    """
    Extracts structured financial data from a PDF document.

    Steps:
      1. Uses pdfplumber to read raw text from the PDF bytes.
      2. Sends raw text to Gemini 2.5-flash with strict TaxDocumentExtraction schema.
      3. Returns parsed extraction result + SHA-256 hash of the extracted JSON.

    Args:
        file_bytes: Raw PDF file bytes (downloaded from Google Drive).
        file_id: Google Drive file ID (used for logging/tracing).

    Returns:
        Dict with keys:
          - extraction: TaxDocumentExtraction dict
          - data_hash: SHA-256 of the extracted JSON (used for change detection)
          - raw_text_length: number of characters extracted from PDF
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber is not installed. Run: pip install pdfplumber")

    # Step 1: Extract text
    raw_text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            raw_text = "".join(
                (page.extract_text() or "") for page in pdf.pages
            )
    except Exception as e:
        logger.warning(f"[{file_id}] pdfplumber failed: {e}. Sending empty text to Gemini.")

    if not raw_text.strip():
        logger.warning(f"[{file_id}] No text extracted from PDF. Document may be image-only.")

    # Step 2: Gemini extraction with strict schema
    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            f"Extract all financial values from this Indian tax document and map each to its "
            f"ITR-1 or ITR-2 schema field path.\n\nDocument text:\n{raw_text}"
        ),
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a strict data transformation engine for Indian income tax documents. "
                "Extract ONLY numerical financial values present in the text. "
                "Map each value to its exact ITR schema field path (e.g., 'salary_income.gross_salary', "
                "'deductions.sec_80c', 'taxes_paid.tds_on_salary', 'other_sources.savings_interest'). "
                "Do NOT invent values. If a field is not present in the document, omit it. "
                "All amounts must be in INR."
            ),
            response_mime_type="application/json",
            response_schema=TaxDocumentExtraction,
            temperature=0.0  # Maximum determinism — no hallucinations
        )
    )

    extraction_dict = json.loads(response.text)

    # Step 3: Hash the extracted JSON for change detection
    # (Hash of financial data, not filename — per schemas.jsonc)
    data_hash = hashlib.sha256(
        json.dumps(extraction_dict, sort_keys=True).encode("utf-8")
    ).hexdigest()

    logger.info(
        f"[{file_id}] Extracted {len(extraction_dict.get('extractions', []))} fields "
        f"from {extraction_dict.get('document_type', 'UNKNOWN')} | hash={data_hash[:12]}..."
    )

    return {
        "extraction": extraction_dict,
        "data_hash": data_hash,
        "raw_text_length": len(raw_text)
    }


def hash_extraction(extraction_dict: dict) -> str:
    """Compute SHA-256 of an extraction result dict for storage in document_registry."""
    return hashlib.sha256(
        json.dumps(extraction_dict, sort_keys=True).encode("utf-8")
    ).hexdigest()
