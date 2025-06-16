import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, time

from google_apis import create_service
from googleapiclient.errors import HttpError
import dateutil.parser
from dateutil.tz import gettz

load_dotenv()

GOOGLE_CLIENT_SECRET_PATH = os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")
CALENDAR_API_NAME = 'calendar'
CALENDAR_API_VERSION = 'v3'
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar'] 

# Function for Date Parsing 
def parse_datetime_for_api(datetime_str: str, default_time: Optional[time] = None, prefer_future: bool = True) -> Optional[str]:
    """
    Parses a datetime string into a timezone-aware ISO 8601 string suitable for Google Calendar API.
    Handles common relative terms like "today", "tomorrow", "yesterday", "now" using a dynamic approach.
    If only a date is provided (or implied by a relative term), attaches a default_time (e.g., start/end of day).
    """
    local_tz = gettz()
    now_local = datetime.now(local_tz)
    today_local_date = now_local.date()

    def _combine_dt(date_part, time_part):
        return datetime.combine(date_part, time_part, tzinfo=local_tz)

    # Handlers for relative date strings
    # Lambdas capture local_tz, now_local, today_local_date from the outer scope
    relative_date_handlers = {
        "now": lambda: now_local,
        "today": lambda: _combine_dt(today_local_date, time.min),
        "start of today": lambda: _combine_dt(today_local_date, time.min),
        "beginning of today": lambda: _combine_dt(today_local_date, time.min),
        "end of today": lambda: _combine_dt(today_local_date, time.max),
        "tonight": lambda: _combine_dt(today_local_date, time.max), # Assumes 'tonight' means end of current day for API calls
        "tomorrow": lambda: _combine_dt(today_local_date + timedelta(days=1), time.min),
        "start of tomorrow": lambda: _combine_dt(today_local_date + timedelta(days=1), time.min),
        "beginning of tomorrow": lambda: _combine_dt(today_local_date + timedelta(days=1), time.min),
        "end of tomorrow": lambda: _combine_dt(today_local_date + timedelta(days=1), time.max),
        "yesterday": lambda: _combine_dt(today_local_date - timedelta(days=1), time.min),
        "start of yesterday": lambda: _combine_dt(today_local_date - timedelta(days=1), time.min),
        "beginning of yesterday": lambda: _combine_dt(today_local_date - timedelta(days=1), time.min),
        "end of yesterday": lambda: _combine_dt(today_local_date - timedelta(days=1), time.max),
    }

    normalized_datetime_str = datetime_str.lower().strip().replace("_", " ")
    dt_obj: Optional[datetime] = None

    handler = relative_date_handlers.get(normalized_datetime_str)
    if handler:
        dt_obj = handler()
    
    if dt_obj:
        # If the handler resulted in a start-of-day (midnight) datetime,
        # and a specific default_time is provided (e.g., time.max for end-of-day),
        # apply that default_time.
        if dt_obj.time() == time.min and default_time:
            dt_obj = datetime.combine(dt_obj.date(), default_time, tzinfo=dt_obj.tzinfo)
        return dt_obj.isoformat()

    # If not a recognized relative string, try parsing with dateutil.parser
    try:
        dt_parsed = dateutil.parser.parse(datetime_str, tzinfos={"local": local_tz})

        # Ensure timezone information is present
        if dt_parsed.tzinfo is None or dt_parsed.tzinfo.utcoffset(dt_parsed) is None:
            dt_parsed = dt_parsed.replace(tzinfo=local_tz)
        
        # If parsing resulted in a start-of-day (midnight) datetime (e.g. from "2023-10-10"),
        # and a specific default_time is provided, apply it.
        if dt_parsed.time() == time.min and default_time:
            dt_parsed = datetime.combine(dt_parsed.date(), default_time, tzinfo=dt_parsed.tzinfo)

        return dt_parsed.isoformat()
    except (ValueError, TypeError, OverflowError) as e:
        # It's useful to log the original string that failed parsing
        print(f"Error parsing date string '{datetime_str}' with dateutil.parser: {e}")
        return None

class CalendarEventInput(BaseModel):
    summary: str = Field(..., description="The title or summary of the event.")
    start_time_str: str = Field(..., description="The start date and time of the event (e.g., 'May 21st at 3pm', 'next Tuesday at 10 AM for 1 hour', '2025-12-25T09:00:00'). The agent should resolve this to a specific date and time based on the current date if relative.")
    duration_minutes: Optional[int] = Field(None, description="The duration of the event in minutes. E.g., 60 for 1 hour. Provide this OR end_time_str.")
    end_time_str: Optional[str] = Field(None, description="The end date and time of the event (e.g., 'May 21st at 4pm', '2025-12-25T10:00:00'). Provide this OR duration_minutes.")
    description: Optional[str] = Field(None, description="A more detailed description of the event.")
    location: Optional[str] = Field(None, description="The location of the event.")


def create_event(details: CalendarEventInput) -> str:
    """
    Creates an event on the user's primary Google Calendar.
    The agent should extract the event summary, a specific start date/time, and either a duration or a specific end date/time.
    The current date is {current_date_for_llm_context}. Use this to resolve relative dates.
    """
    service = create_service(GOOGLE_CLIENT_SECRET_PATH, CALENDAR_API_NAME, CALENDAR_API_VERSION, CALENDAR_SCOPES)
    if not service:
        return "Failed to connect to Google Calendar service. Please check authentication and client_secret.json."

    start_iso = parse_datetime_for_api(details.start_time_str)
    if not start_iso:
        return f"Could not understand the start time: '{details.start_time_str}'. Please provide a clearer date and time (e.g., 'June 5th 2025 at 2pm' or '2025-06-05T14:00:00')."

    start_dt = dateutil.parser.isoparse(start_iso)

    if details.end_time_str:
        end_iso = parse_datetime_for_api(details.end_time_str)
        if not end_iso:
            return f"Could not understand the end time: '{details.end_time_str}'."
        end_dt = dateutil.parser.isoparse(end_iso)
    elif details.duration_minutes:
        if details.duration_minutes <= 0:
            return "Event duration must be positive."
        end_dt = start_dt + timedelta(minutes=details.duration_minutes)
        end_iso = end_dt.isoformat()
    else:
        end_dt = start_dt + timedelta(minutes=60) 
        end_iso = end_dt.isoformat()

    if end_dt <= start_dt:
        return f"The event's end time ({end_iso}) must be after its start time ({start_iso})."
    
    event_body = {
        'summary': details.summary,
        'location': details.location,
        'description': details.description,
        'start': {'dateTime': start_iso},
        'end': {'dateTime': end_iso},
        'reminders': {'useDefault': True},
    }

    try:
        created_event = service.events().insert(calendarId='primary', body=event_body).execute()
        event_url = created_event.get('htmlLink')
        return f"Event '{details.summary}' created successfully! View it here: {event_url}"
    except HttpError as error:
        return f"Google Calendar API error while creating event: {error.resp.reason}. Details: {error.content.decode()}"
    except Exception as e:
        return f"An unexpected error occurred while creating event: {str(e)}"

# Tool for Listing/Finding Calendar Events 
class ListEventsInput(BaseModel):
    time_min_str: Optional[str] = Field(None, description="The start of the date/time range to search (e.g., 'today', 'tomorrow at 9am', '2025-06-01'). If only a date, assumes start of day. Defaults to now if not set.")
    time_max_str: Optional[str] = Field(None, description="The end of the date/time range to search (e.g., 'end of today', 'next Monday at 5pm', '2025-06-07'). If only a date, assumes end of day.")
    search_query: Optional[str] = Field(None, description="A text query to search within event summaries, descriptions, or locations (e.g., 'Project X meeting', 'dentist').")
    max_results: int = Field(10, description="Maximum number of events to return. Default is 10, max is 250.")


def list_event(details: ListEventsInput) -> str:
    """
    Lists calendar events based on a date range and/or a search query.
    Use this to find specific events (to get their IDs for updating or canceling) or to get an overview of the calendar.
    The current date is {current_date_for_llm_context}. Use this to help resolve relative dates like 'today', 'next week'.
    The function will return a list of events with their summaries, start times, and IDs.
    """
    service = create_service(GOOGLE_CLIENT_SECRET_PATH, CALENDAR_API_NAME, CALENDAR_API_VERSION, CALENDAR_SCOPES)
    if not service:
        return "Failed to connect to Google Calendar service."

    time_min_iso = None
    if details.time_min_str:
        time_min_iso = parse_datetime_for_api(details.time_min_str, default_time=time.min) 
    else:
        time_min_iso = datetime.now(gettz()).isoformat()


    time_max_iso = None
    if details.time_max_str:
        time_max_iso = parse_datetime_for_api(details.time_max_str, default_time=time.max) 
    
    if not time_min_iso: # Should not happen if default works, but as a safeguard
        return "Could not parse time_min_str. Please provide a valid start date/time."

    try:
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min_iso,
            timeMax=time_max_iso,
            q=details.search_query,
            maxResults=min(details.max_results, 250), 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        items = events_result.get('items', [])
        if not items:
            return "No events found matching your criteria."

        event_list_str = "Found events:\n"
        for item in items:
            start = item['start'].get('dateTime', item['start'].get('date')) 
            try:
                start_dt = dateutil.parser.isoparse(start)
                formatted_start = start_dt.strftime('%Y-%m-%d %I:%M %p %Z') if start_dt.time() != time.min else start_dt.strftime('%Y-%m-%d (All-day)')
            except:
                formatted_start = start
            event_list_str += f"- '{item.get('summary', 'No Title')}' on {formatted_start} (ID: {item['id']})\n"
        
        if events_result.get('nextPageToken'):
            event_list_str += "\nNote: There may be more events than shown. You can refine your search or increase max_results."
            
        return event_list_str.strip()
    except HttpError as error:
        return f"Google Calendar API error while listing events: {error.resp.reason}. Details: {error.content.decode()}"
    except Exception as e:
        return f"An unexpected error occurred while listing events: {str(e)}"

# Tool for Updating/Editing/Rescheduling Calendar Events
class UpdateEventInput(BaseModel):
    event_id: str = Field(..., description="The unique ID of the event to update. This ID MUST be obtained first, e.g., by using 'list_calendar_events'.")
    new_summary: Optional[str] = Field(None, description="The new title for the event. If None, summary is unchanged.")
    new_start_time_str: Optional[str] = Field(None, description="The new start date and time (e.g., 'tomorrow at 3pm', '2025-06-01T15:00:00'). Requires new_end_time_str or new_duration_minutes if provided.")
    new_end_time_str: Optional[str] = Field(None, description="The new end date and time. Use if changing event timing.")
    new_duration_minutes: Optional[int] = Field(None, description="The new duration in minutes. Use with new_start_time_str if new_end_time_str is not specified.")
    new_description: Optional[str] = Field(None, description="The new detailed description. Provide an empty string ('') to clear the existing description. If None, description is unchanged.")
    new_location: Optional[str] = Field(None, description="The new location. Provide an empty string ('') to clear. If None, location is unchanged.")


def change_event(details: UpdateEventInput) -> str:
    """
    Updates an existing calendar event identified by its event_id.
    You MUST provide the event_id. Use 'list_calendar_events' to find the event ID if needed.
    Only fields explicitly provided in the input (e.g., new_summary, new_start_time_str) will be changed.
    To reschedule, provide new_start_time_str and either new_end_time_str or new_duration_minutes.
    The current date is {current_date_for_llm_context}.
    """
    service = create_service(GOOGLE_CLIENT_SECRET_PATH, CALENDAR_API_NAME, CALENDAR_API_VERSION, CALENDAR_SCOPES)
    if not service:
        return "Failed to connect to Google Calendar service."

    try:
        event_to_update = service.events().get(calendarId='primary', eventId=details.event_id).execute()
        if not event_to_update:
            return f"Event with ID '{details.event_id}' not found."
        
        update_body: Dict[str, Any] = {}

        if details.new_summary is not None:
            update_body['summary'] = details.new_summary
        if details.new_description is not None:
            update_body['description'] = details.new_description
        if details.new_location is not None:
            update_body['location'] = details.new_location

        current_start_dt = dateutil.parser.isoparse(event_to_update['start'].get('dateTime', event_to_update['start'].get('date')))
        current_end_dt = dateutil.parser.isoparse(event_to_update['end'].get('dateTime', event_to_update['end'].get('date')))
        
        new_start_iso: Optional[str] = None
        new_end_iso: Optional[str] = None

        if details.new_start_time_str:
            new_start_iso = parse_datetime_for_api(details.new_start_time_str)
            if not new_start_iso:
                return f"Could not parse new_start_time_str: '{details.new_start_time_str}'"
            update_body['start'] = {'dateTime': new_start_iso}
            
            new_start_dt = dateutil.parser.isoparse(new_start_iso)
            if details.new_end_time_str:
                new_end_iso = parse_datetime_for_api(details.new_end_time_str)
                if not new_end_iso:
                    return f"Could not parse new_end_time_str: '{details.new_end_time_str}'"
            elif details.new_duration_minutes:
                if details.new_duration_minutes <= 0: return "New duration must be positive."
                new_end_dt = new_start_dt + timedelta(minutes=details.new_duration_minutes)
                new_end_iso = new_end_dt.isoformat()
            else: 
                original_duration = current_end_dt - current_start_dt
                new_end_dt = new_start_dt + original_duration
                new_end_iso = new_end_dt.isoformat()
            
            update_body['end'] = {'dateTime': new_end_iso}
            
            if dateutil.parser.isoparse(new_end_iso) <= new_start_dt:
                 return f"The event's new end time ({new_end_iso}) must be after its new start time ({new_start_iso})."

        elif details.new_end_time_str or details.new_duration_minutes:
            new_start_dt_for_calc = current_start_dt
            update_body['start'] = {'dateTime': new_start_dt_for_calc.isoformat()} 

            if details.new_end_time_str:
                new_end_iso = parse_datetime_for_api(details.new_end_time_str)
                if not new_end_iso:
                    return f"Could not parse new_end_time_str: '{details.new_end_time_str}'"
            elif details.new_duration_minutes: 
                 if details.new_duration_minutes <= 0: return "New duration must be positive."
                 new_end_dt = new_start_dt_for_calc + timedelta(minutes=details.new_duration_minutes)
                 new_end_iso = new_end_dt.isoformat()
            
            if new_end_iso:
                 update_body['end'] = {'dateTime': new_end_iso}
                 if dateutil.parser.isoparse(new_end_iso) <= new_start_dt_for_calc:
                     return f"The event's new end time ({new_end_iso}) must be after its start time ({new_start_dt_for_calc.isoformat()})."


        if not update_body:
            return "No changes specified for the event. Please provide fields to update."

        updated_event = service.events().patch(calendarId='primary', eventId=details.event_id, body=update_body, sendUpdates='all').execute()
        return f"Event '{updated_event.get('summary')}' updated successfully. View it here: {updated_event.get('htmlLink')}"

    except HttpError as error:
        return f"Google Calendar API error while updating event: {error.resp.reason}. Details: {error.content.decode()}"
    except Exception as e:
        return f"An unexpected error occurred while updating event: {str(e)}"


class CancelEventInput(BaseModel):
    event_id: str = Field(..., description="The unique ID of the event to cancel. Obtain this ID using 'list_calendar_events' if not directly provided or known.")
    send_notifications: bool = Field(True, description="Whether to send notifications to attendees about the cancellation. Defaults to True (sendUpdates='all').")


def cancel_event(details: CancelEventInput) -> str:
    """
    Cancels (deletes) an existing calendar event identified by its event_id.
    You MUST provide the event_id. If the user refers to an event vaguely (e.g., "cancel my meeting tomorrow afternoon"), first use 'list_calendar_events' to find the specific event and confirm its ID.
    The current date is {current_date_for_llm_context}.
    """
    service = create_service(GOOGLE_CLIENT_SECRET_PATH, CALENDAR_API_NAME, CALENDAR_API_VERSION, CALENDAR_SCOPES)
    if not service:
        return "Failed to connect to Google Calendar service."

    try:
        # Check if event exists before trying to delete (optional, delete will fail if not found anyway)
        # service.events().get(calendarId='primary', eventId=details.event_id).execute()
        
        send_updates_option = 'all' if details.send_notifications else 'none'
        service.events().delete(calendarId='primary', eventId=details.event_id, sendUpdates=send_updates_option).execute()
        return f"Event with ID '{details.event_id}' cancelled successfully."
    except HttpError as error:
        if error.resp.status == 404:
            return f"Event with ID '{details.event_id}' not found. Cannot cancel."
        return f"Google Calendar API error while canceling event: {error.resp.reason}. Details: {error.content.decode()}"
    except Exception as e:
        return f"An unexpected error occurred while canceling event: {str(e)}"

_current_date_str = datetime.now(gettz()).strftime("%Y-%m-%d, %A, %I:%M %p %Z")
create_event.__doc__ = (create_event.__doc__ or "").format(current_date_for_llm_context=_current_date_str)
list_event.__doc__ = (list_event.__doc__ or "").format(current_date_for_llm_context=_current_date_str)
change_event.__doc__ = (change_event.__doc__ or "").format(current_date_for_llm_context=_current_date_str)
cancel_event.__doc__ = (cancel_event.__doc__ or "").format(current_date_for_llm_context=_current_date_str)