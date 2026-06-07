from fastapi import FastAPI, UploadFile, File
import shutil

from app.services.db import db
from app.tools.pdf_processor import extract_pdf_text
from app.orchestrator.engine import execute_workflow
from app.services.workflow_service import (
    create_workflow,
    update_workflow,
    get_workflow
)

app = FastAPI()


@app.get("/")
def root():

    return {
        "message": "Tax Agent Running"
    }


@app.get("/test-db")
def test_db():

    collections = db.list_collection_names()

    return {
        "collections": collections
    }


@app.get("/create-workflow")
def create_new_workflow():

    workflow = create_workflow("usr_101")

    return workflow


@app.get("/get-workflows")
def get_all_workflows():

    workflow = get_workflow("usr_101")

    return {
        "data": workflow
    }


@app.post("/upload-form16")
async def upload_form16(
    file: UploadFile = File(...)
):

    file_path = f"uploads/{file.filename}"

    with open(file_path, "wb") as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    create_workflow("usr_101")

    document_text = extract_pdf_text(
        file_path
    )

    result = execute_workflow(
        document_text
    )

    update_workflow(
        "usr_101",
        {
            "status": "COMPLETED",
            "current_step": "FINISHED",
            "document_data": result["document_processing"],
            "tax_rules": result["tax_rules"],
            "tax_result": result["tax_result"]
        }
    )

    return result


@app.get("/workflow-status")
def workflow_status():

    workflow = get_workflow(
        "usr_101"
    )

    return workflow
