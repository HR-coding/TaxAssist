from email.mime.text import MIMEText
import base64
from app.core.google_auth import get_gmail_service
from app.core.email_format import sanitize_email_body

def send_email(
    to_email,
    subject,
    body
):

    service = get_gmail_service()

    # Hard guarantee: no internal field keys/code reach the recipient.
    message = MIMEText(sanitize_email_body(body))

    message["to"] = to_email

    message["subject"] = sanitize_email_body(subject)

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

