from email.mime.text import MIMEText
import base64
from app.utils.google_auth import get_gmail_service

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

def read_email(
    message_id
):

    service = get_gmail_service()

    message = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id
        )
        .execute()
    )

    return message

