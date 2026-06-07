from googleapiclient.discovery import (
    build
)

from email.mime.text import MIMEText

import base64

from tools.google_drive_client import (
    get_drive_service
)


def get_gmail_service():

    creds = (
        get_drive_service()
        ._http.credentials
    )

    service = build(
        "gmail",
        "v1",
        credentials=creds
    )

    return service


def send_email(
    to_email,
    subject,
    body
):

    service = get_gmail_service()

    message = MIMEText(body)

    message["to"] = to_email

    message["subject"] = subject

    raw = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode()

    service.users().messages().send(
        userId="me",
        body={
            "raw": raw
        }
    ).execute()

    return {
        "status": "EMAIL_SENT"
    }