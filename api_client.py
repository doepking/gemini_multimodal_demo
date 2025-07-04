import httpx
import json
import os
from typing import List, Dict, Any
import uuid
import logging
import base64
import hashlib

# Configure logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

API_URL = os.getenv("API_BASE_URL", "http://localhost:8080")

async def get_or_create_user(user_email: str, user_name: str) -> Dict[str, Any]:
    """Gets a user from the backend or creates one if it doesn't exist."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(f"{API_URL}/users/by_email/{user_email}", headers=headers)
    response.raise_for_status()
    return response.json()

async def load_input_log(user_id: int, user_email: str, user_name: str) -> List[Dict[str, Any]]:
    """Loads the input log for a user from the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(f"{API_URL}/users/{user_id}/text_inputs", headers=headers)
    response.raise_for_status()
    return response.json()

async def load_tasks(user_id: int, user_email: str, user_name: str) -> List[Dict[str, Any]]:
    """Loads the tasks for a user from the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(f"{API_URL}/users/{user_id}/tasks", headers=headers)
    response.raise_for_status()
    return response.json()

async def load_background_info(user_id: int, user_email: str, user_name: str) -> Dict[str, Any]:
    """Loads the background info for a user from the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(f"{API_URL}/users/{user_id}/background_info", headers=headers)
    response.raise_for_status()
    return response.json()

async def create_session(user: Dict[str, Any], session_id: str):
    """Creates a new session for the agent."""
    session_state = {
        "user_id": user["id"],
        "user_email": user["email"],
        "user_name": user.get("username", "Unknown User")
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{API_URL}/apps/gemini_adk_demo/users/{user['id']}/sessions/{session_id}", json=session_state)
    response.raise_for_status()
    return response.json()

async def get_chat_response(user_id: int, user_email: str, user_name: str, user_prompt: str = None, audio_file_path: str = None) -> Dict[str, Any]:
    """Gets a chat response from the backend."""
    logger.info(f"api_client.get_chat_response: user_id: {user_id}")
    session_id = f"test-session-{uuid.uuid4()}"
    
    # Create session with minimal user info
    user_info = {"id": user_id, "email": user_email, "username": user_name}
    await create_session(user_info, session_id)
    
    parts = []
    if user_prompt:
        parts.append({"text": user_prompt})

    if audio_file_path:
        with open(audio_file_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

        encoded_audio = base64.b64encode(audio_bytes).decode('utf-8')

        audio_part = {
            "inline_data": {
                "mime_type": "audio/wav",
                "data": encoded_audio
            }
        }
        parts.append(audio_part)

    payload = {
        "app_name": "gemini_adk_demo",
        "user_id": str(user_id),
        "session_id": session_id,
        "new_message": {
            "role": "user",
            "parts": parts
        },
        "streaming": False,
    }

    logger.info(f"api_client.get_chat_response: sending payload for user {user_id}")

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(f"{API_URL}/run_sse", json=payload)
    
    response.raise_for_status()
    
    # Handle streaming response
    full_response = None
    # Since the original code uses iter_lines, we will simulate a similar behavior with the async response.
    # Note: httpx's streaming response is handled differently. For a simple case, we'll read the whole response.
    # For true async streaming, one would use `async for` on the response object.
    # However, the original logic just finds the last valid JSON, so reading at once is fine here.
    lines = response.text.splitlines()
    for line in lines:
        if line.startswith('data:'):
            try:
                json_data = json.loads(line[5:])
                if "content" in json_data and "parts" in json_data["content"]:
                    for part in json_data["content"]["parts"]:
                        if "text" in part:
                            full_response = json_data
            except json.JSONDecodeError:
                pass
    return full_response

async def add_log_entry_and_persist(text_input: str, user_id: int, user_email: str, user_name: str, category_suggestion: str = None):
    """Adds a log entry and persists it via the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{API_URL}/users/{user_id}/text_inputs", headers=headers, json={"content": text_input, "category": category_suggestion})
    response.raise_for_status()
    return response.json()

async def update_background_info_and_persist(background_update_json: str, user_id: int, user_email: str, user_name: str, replace: bool = False):
    """Updates background info and persists it via the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.put(f"{API_URL}/users/{user_id}/background_info", headers=headers, json={"content": json.loads(background_update_json)})
    response.raise_for_status()
    return response.json()

async def add_task_and_persist(task_description: str, user_id: int, user_email: str, user_name: str, deadline: str = None):
    """Adds a task and persists it via the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{API_URL}/users/{user_id}/tasks", headers=headers, json={"description": task_description, "deadline": deadline})
    response.raise_for_status()
    return response.json()

async def update_tasks_and_persist(tasks_list: list, user_id: int, user_email: str, user_name: str):
    """Updates the task list and persists it via the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.put(f"{API_URL}/users/{user_id}/tasks", headers=headers, json=tasks_list)
    response.raise_for_status()
    return response.json()

async def update_input_log_and_persist(log_list: list, user_id: int, user_email: str, user_name: str):
    """Updates the input log and persists it via the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.put(f"{API_URL}/users/{user_id}/text_inputs", headers=headers, json=log_list)
    response.raise_for_status()
    return response.json()

async def get_recent_metrics(user_email: str, limit: int = 30):
    """Fetches recent mood check-ins for a user."""
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"{API_URL}/metrics/user/{user_email}?limit={limit}")
    # Allow 404s to be handled by the frontend
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()

async def get_subscription_status(user_email: str):
    """Fetches the newsletter subscription status for a user."""
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"{API_URL}/newsletter/preferences/{user_email}")
    if response.status_code == 404:
        return {"subscribed": False}
    response.raise_for_status()
    return response.json()

async def unsubscribe_from_newsletter(user_email: str):
    """Unsubscribes a user from the newsletter."""
    secret_key = os.environ.get("UNSUBSCRIBE_SECRET_KEY")
    if not secret_key:
        raise ValueError("UNSUBSCRIBE_SECRET_KEY is not set in the environment.")
    
    token = hashlib.sha256(f"{user_email}{secret_key}".encode()).hexdigest()
    
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(f"{API_URL}/newsletter/unsubscribe/{user_email}/{token}")
    response.raise_for_status()
    return response.json()

async def subscribe_to_newsletter(user_email: str):
    """Subscribes a user to the newsletter."""
    payload = {"email": user_email}
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(f"{API_URL}/newsletter/subscribe", json=payload)
    response.raise_for_status()
    return response.json()
