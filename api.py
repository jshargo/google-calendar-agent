from __future__ import annotations

import logging
from typing import Optional, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from agent import calendar_agent, insert_to_db, SESSION_CHAT_ID 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()] 
)
logger = logging.getLogger(__name__)

chat_history: Any | None = None

app = FastAPI(title="Google Calendar Voice Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # Optional resume of an existing session


class ChatResponse(BaseModel):
    session_id: str
    response: str


@app.get("/")
async def healthcheck() -> dict[str, str]:
    """Simple liveness probe."""
    logger.info("Healthcheck endpoint was called.")
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: Request) -> ChatResponse: 
    """Main entry-point used by Vapi workflows.

    Receives a transcript, forwards it to the calendar agent, and returns the
    agent's textual response. This version includes extensive logging.
    """
    logger.info("--- /chat endpoint hit ---")
    global chat_history  

    raw_body = await request.body()
    logger.info(f"Received raw request body: {raw_body.decode()}")

    try:
        payload = ChatRequest.parse_raw(raw_body)
        logger.info(f"Successfully parsed request payload: message='{payload.message}', session_id='{payload.session_id}'")
    except ValidationError as e:
        logger.error(f"Pydantic validation failed for payload: {raw_body.decode()}. Error: {e}")
        raise HTTPException(status_code=422, detail=f"Invalid payload format: {e}")

    try:
        # If the caller supplies a *different* session id, start a fresh history
        if payload.session_id and payload.session_id != SESSION_CHAT_ID:
            logger.info(f"New session ID '{payload.session_id}' received. Resetting chat history.")
            chat_history = None
        else:
            logger.info(f"Continuing with session ID '{SESSION_CHAT_ID}'. Chat history is {'present' if chat_history else 'empty'}.")

        # Forward the transcript to the agent (returns ToolCall-aware output)
        logger.info(f"Running agent with message: '{payload.message}'")
        agent_output = await calendar_agent.run(
            payload.message, message_history=chat_history
        )
        logger.info(f"Agent returned output: '{agent_output.output}'")
        if hasattr(agent_output, 'tool_calls') and agent_output.tool_calls:
            logger.info(f"Agent made tool calls: {agent_output.tool_calls}")

        logger.info("Inserting interaction to database...")
        insert_to_db(payload.message, agent_output.output)
        logger.info("...insertion to database complete.")

        chat_history = agent_output.all_messages()
        logger.info("Chat history updated for subsequent requests.")

        response_data = ChatResponse(session_id=SESSION_CHAT_ID, response=agent_output.output)
        logger.info(f"Sending response: {response_data.json()}")
        logger.info("--- /chat endpoint finished ---")
        return response_data

    except HTTPException as http_exc:
        logger.error(f"Caught HTTPException: {http_exc.status_code} - {http_exc.detail}", exc_info=True)
        raise http_exc
    except Exception as exc: 
        logger.error(f"An unexpected error occurred in /chat endpoint: {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )
