from datetime import (
    datetime,
    timedelta
)
from app.core.google_auth import get_calendar_service

def create_tax_reminder():

    service = get_calendar_service()

    start_time = (
        datetime.utcnow()
        + timedelta(days=1)
    )

    end_time = (
        start_time
        + timedelta(hours=1)
    )

    event = {

        "summary":
        "ITR Filing Reminder",

        "description":
        "Review and file Income Tax Return",

        "start": {
            "dateTime":
            start_time.isoformat(),
            "timeZone":
            "Asia/Kolkata"
        },

        "end": {
            "dateTime":
            end_time.isoformat(),
            "timeZone":
            "Asia/Kolkata"
        }
    }

    created_event = (
        service.events()
        .insert(
            calendarId="primary",
            body=event
        )
        .execute()
    )

    return {
        "event_id":
        created_event["id"]
    }
