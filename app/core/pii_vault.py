"""
PII Vault — the gateway between raw personal data and the AI layer.

CLAUDE.md: "The agent must never ingest raw personally identifiable information."
Inbound data is tokenised here (real value -> synthetic token) BEFORE it reaches
any AI/agent code; the token->value map (the "vault") stays in the local execution
layer and is used to reconstruct real values immediately before outbound writes
(Gmail / Sheets) via `deanonymize`.

Design goals:
  - Comprehensive: covers known PII fields AND PII embedded in free text.
  - Crash-safe: never raises on missing fields; handles nested dicts/lists.
  - Reversible: deanonymize() restores the originals for the local layer only.
  - Deterministic: the same value always maps to the same token within a vault,
    so downstream joins stay consistent and tokens don't multiply.
"""
import re
import uuid

# Field name (lowercased) -> token type. Covers ITR ledger + Form 16 PII.
_PII_FIELDS = {
    "employee_name": "PERSON", "name": "PERSON", "first_name": "PERSON",
    "middle_name": "PERSON", "last_name": "PERSON", "father_name": "PERSON",
    "deductee_name": "PERSON", "deductor_name": "ORG", "employer_name": "ORG",
    "donee_name": "ORG",
    "pan": "PAN", "pan_number": "PAN", "deductor_pan": "PAN", "deductee_pan": "PAN",
    "tan": "TAN", "deductor_tan": "TAN",
    "aadhaar": "AADHAAR", "aadhaar_number": "AADHAAR", "uid": "AADHAAR",
    "email": "EMAIL", "email_address": "EMAIL",
    "mobile": "PHONE", "mobile_number": "PHONE", "phone": "PHONE", "phone_number": "PHONE",
    "bank_account_number": "ACCT", "account_number": "ACCT", "account_no": "ACCT",
    "ifsc": "IFSC", "ifsc_code": "IFSC",
    "address": "ADDRESS", "permanent_address": "ADDRESS",
    "date_of_birth": "DOB", "dob": "DOB",
}

# Patterns to catch PII embedded inside free-text string VALUES.
_PATTERNS = [
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("AADHAAR", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("PHONE", re.compile(r"\b(?:\+91[-\s]?)?[6-9]\d{9}\b")),
]


def anonymize_document(document_data, vault: dict = None) -> dict:
    """
    Replace every PII value with a synthetic token before the AI layer sees it.

    Args:
        document_data: Arbitrary dict/list/scalar structure (possibly nested).
        vault: Optional existing token->value map to extend (keeps tokens stable
               across multiple documents for the same user).

    Returns:
        {"anonymized": <same shape, PII tokenised>, "vault": {token: real_value}}
    """
    vault = dict(vault) if vault else {}
    reverse = {str(v): k for k, v in vault.items()}  # real_value -> token

    def token_for(value, kind: str) -> str:
        key = str(value)
        if key in reverse:
            return reverse[key]
        token = f"{kind}_{uuid.uuid4().hex[:10]}"
        vault[token] = value
        reverse[key] = token
        return token

    def scrub_text(text: str) -> str:
        for kind, pattern in _PATTERNS:
            text = pattern.sub(lambda m: token_for(m.group(0), kind), text)
        return text

    def process(obj, field_name=None):
        if isinstance(obj, dict):
            return {k: process(v, k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [process(x, field_name) for x in obj]
        if isinstance(obj, str):
            kind = _PII_FIELDS.get((field_name or "").lower())
            if kind and obj.strip():
                return token_for(obj, kind)        # whole field is PII
            return scrub_text(obj)                  # PII embedded in free text
        return obj                                  # numbers / bools / None untouched

    return {"anonymized": process(document_data), "vault": vault}


def deanonymize(data, vault: dict):
    """
    Reconstruct real PII from tokens, for the local execution layer ONLY (e.g.
    immediately before writing to Gmail/Sheets). Never call this on data headed
    back into the AI layer.
    """
    if not vault:
        return data

    def process(obj):
        if isinstance(obj, dict):
            return {k: process(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [process(x) for x in obj]
        if isinstance(obj, str):
            # Exact-token match is the common case; substring covers embedded tokens.
            if obj in vault:
                return vault[obj]
            for token, value in vault.items():
                if token in obj:
                    obj = obj.replace(token, str(value))
            return obj
        return obj

    return process(data)
