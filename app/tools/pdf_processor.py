import pdfplumber
import pytesseract

from pdf2image import convert_from_path


pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def extract_pdf_text(file_path):

    text = ""

    with pdfplumber.open(file_path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:
                text += page_text

    if text.strip():

        print("PDF Text Extracted")

        return text

    print("Running OCR...")

    images = convert_from_path(
        file_path
    )

    ocr_text = ""

    for image in images:

        ocr_text += pytesseract.image_to_string(
            image
        )

    return ocr_text