from app.tools.pdf_processor import (
    extract_pdf_text
)


def process_file(
    file_path
):

    if file_path.endswith(
        ".pdf"
    ):
        return extract_pdf_text(
            file_path
        )

    return None
