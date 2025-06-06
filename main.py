from fastapi import FastAPI, HTTPException, Body
from typing import Any, Dict

from tools import (
    create_event, CalendarEventInput,
    list_event, ListEventsInput,
    change_event, UpdateEventInput,
    cancel_event, CancelEventInput
)

app = FastAPI(
    title="Google Calendar Agent API",
    description="API for interacting with the Google Calendar agent, designed for Vapi integration.",
    version="0.1.0"
)

TOOL_REGISTRY = {
    "create_event": (create_event, CalendarEventInput),
    "list_event": (list_event, ListEventsInput),
    "change_event": (change_event, UpdateEventInput),
    "cancel_event": (cancel_event, CancelEventInput),
}

class ToolInvocationRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]

@app.post("/invoke-tool", summary="Invoke a calendar tool")
async def invoke_tool(request_body: ToolInvocationRequest = Body(...)):
    """
    Receives a tool name and its parameters, then invokes the corresponding
    Google Calendar function.

    Expected Vapi Request Body Format (example for create_event):
    ```json
    {
        "tool_name": "create_event",
        "parameters": {
            "summary": "Team Meeting",
            "start_time_str": "Tomorrow at 10am",
            "duration_minutes": 60
        }
    }
    ```

    The 'parameters' field should match the Pydantic model for the specified tool_name.
    Returns the string result from the tool function.
    """
    tool_name = request_body.tool_name
    parameters = request_body.parameters

    if tool_name not in TOOL_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Tool '{tool_name}' not found.")

    tool_function, input_model = TOOL_REGISTRY[tool_name]

    try:
        validated_params = input_model(**parameters)
    except Exception as e: 
        raise HTTPException(status_code=422, detail=f"Invalid parameters for tool '{tool_name}': {e}")

    try:
        result = tool_function(validated_params)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing tool '{tool_name}': {str(e)}")

# To run this application:
# 1. Ensure you have FastAPI and Uvicorn installed: pip install fastapi uvicorn[standard]
# 2. Run the server: uvicorn main:app --reload
# The API will be available at http://127.0.0.1:8000
