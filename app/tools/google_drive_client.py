from google_auth_oauthlib.flow import (
    InstalledAppFlow
)

from googleapiclient.discovery import (
    build
)


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",

    "https://www.googleapis.com/auth/gmail.send",

    "https://www.googleapis.com/auth/gmail.readonly",

    "https://www.googleapis.com/auth/calendar"
]


def get_drive_service():

    flow = (
        InstalledAppFlow
        .from_client_secrets_file(
            "credentials/client_secret.json",
            SCOPES
        )
    )

    creds = (
        flow.run_local_server(
            port=0
        )
    )

    service = build(
        "drive",
        "v3",
        credentials=creds
    )

    return service