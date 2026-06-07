import os
import time

from app.services.document_registry import (
    register_document
)

from app.services.workflow_service import (
    get_workflow
)

from app.engine.decider import (
    determine_next_step
)

from app.orchestrator.workflow_executor import (
    execute_workflow
)

WATCH_FOLDER = "mock_drive"


def start_poller():

    seen_files = set()

    while True:

        current_files = set(
            os.listdir(WATCH_FOLDER)
        )

        new_files = (
            current_files - seen_files
        )

        for file in new_files:

            full_path = os.path.join(
                WATCH_FOLDER,
                file
            )

            document = register_document(
                file,
                full_path
            )

            print(
                f"Registered: {document['document_id']}"
            )

            workflow = get_workflow(
                document["document_id"]
            )

            print(
                f"Workflow Created: {workflow['user_id']}"
            )

            next_step = determine_next_step(
                workflow
            )

            print(
                f"Next Step: {next_step}"
            )

            result = execute_workflow(
                document["document_id"]
            )

            print(result)

        seen_files = current_files

        time.sleep(10)
