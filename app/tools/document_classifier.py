def classify_document(text):

    text = text.lower()

    if "form 16" in text:

        return {
            "document_type": "FORM16",
            "confidence": 0.95
        }

    elif "account statement" in text:

        return {
            "document_type": "BANK_STATEMENT",
            "confidence": 0.90
        }

    elif "ais" in text:

        return {
            "document_type": "AIS",
            "confidence": 0.90
        }

    elif "26as" in text:

        return {
            "document_type": "FORM26AS",
            "confidence": 0.90
        }

    return {
        "document_type": "UNKNOWN",
        "confidence": 0.50
    }
