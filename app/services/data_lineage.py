def build_lineage(
    document_data,
    source_doc_id
):

    lineage = {}

    for key in document_data:

        if key == "confidence_scores":

            continue

        lineage[key] = {

            "source_doc":
                source_doc_id,

            "field":
                key
        }

    return lineage
