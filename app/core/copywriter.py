from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class ChannelNotificationCopy(BaseModel):
    ui_toast_message: str = Field(description="Toast message to display in the user interface")
    gmail_subject: str = Field(description="Email subject line for notification")
    gmail_body: str = Field(description="Detailed plain text body of the email")
    calendar_title: str = Field(description="Title of the calendar reminder event")
    calendar_description: str = Field(description="Short description of the calendar event")

def generate_channel_copy(notification_block: dict) -> ChannelNotificationCopy:
    """
    Invokes Gemini-2.5-Flash to write human copy from DB metadata without markdown.
    """
    client = genai.Client()
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=f"Generate plain-text human copy for the following notification metadata block: {notification_block}",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ChannelNotificationCopy,
            system_instruction=(
                "Act as a precise copywriter transforming database metadata parameters "
                "into plain human text strings without markdown."
            )
        )
    )
    
    # Parse and validate returned JSON content
    return ChannelNotificationCopy.model_validate_json(response.text)
