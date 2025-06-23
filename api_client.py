import requests
import json
import os
from typing import List, Dict, Any
import uuid

API_URL = os.getenv("API_BASE_URL", "http://localhost:8080")

def get_or_create_user(user_email: str, user_name: str) -> Dict[str, Any]:
    """Gets a user from the backend or creates one if it doesn't exist."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    response = requests.get(f"{API_URL}/users/by_email/{user_email}", headers=headers)
    response.raise_for_status()
    return response.json()

def load_input_log(user_id: int, user_email: str, user_name: str) -> List[Dict[str, Any]]:
    """Loads the input log for a user from the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    response = requests.get(f"{API_URL}/users/{user_id}/text_inputs", headers=headers)
    response.raise_for_status()
    return response.json()

def load_tasks(user_id: int, user_email: str, user_name: str) -> List[Dict[str, Any]]:
    """Loads the tasks for a user from the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    response = requests.get(f"{API_URL}/users/{user_id}/tasks", headers=headers)
    response.raise_for_status()
    return response.json()

def load_background_info(user_id: int, user_email: str, user_name: str) -> Dict[str, Any]:
    """Loads the background info for a user from the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    response = requests.get(f"{API_URL}/users/{user_id}/background_info", headers=headers)
    response.raise_for_status()
    return response.json()

def create_session(user_email: str, session_id: str):
    """Creates a new session for the agent."""
    headers = {"X-User-Email": user_email}
    response = requests.post(f"{API_URL}/apps/gemini_adk_demo/users/{user_email}/sessions/{session_id}", headers=headers, json={"state": {}})
    response.raise_for_status()
    return response.json()

def get_chat_response(conversation_history: List[Dict[str, Any]], session_state: Dict[str, Any], user_prompt: str = None, audio_file_path: str = None) -> Dict[str, Any]:
    """Gets a chat response from the backend."""
    user = session_state.get("user")
    session_id = f"test-session-{uuid.uuid4()}"
    create_session(user["email"], session_id)
    headers = {"X-User-Email": user["email"], "X-User-Name": user["username"]}
    
    # Convert SessionStateProxy to a serializable dictionary
    serializable_session_state = {key: value for key, value in session_state.items()}
    
    payload = {
        "app_name": "gemini_adk_demo",
        "user_id": user["email"],
        "session_id": session_id,
        "new_message": {
            "role": "user",
            "parts": [{"text": user_prompt}]
        },
        "streaming": False,
        "session_state": serializable_session_state,
    }
    if audio_file_path:
        with open(audio_file_path, "rb") as f:
            files = {"audio_file": f}
            response = requests.post(f"{API_URL}/run_sse", headers=headers, data={"payload": json.dumps(payload)}, files=files, timeout=120, stream=False)
    else:
        response = requests.post(f"{API_URL}/run_sse", headers=headers, json=payload, timeout=120, stream=False)
    
    response.raise_for_status()
    return response.json()

def add_log_entry_and_persist(text_input: str, user_id: int, user_email: str, user_name: str, category_suggestion: str = None):
    """Adds a log entry and persists it via the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    response = requests.post(f"{API_URL}/users/{user_id}/text_inputs", headers=headers, json={"content": text_input, "category": category_suggestion})
    response.raise_for_status()
    return response.json()

def update_background_info_and_persist(background_update_json: str, user_id: int, user_email: str, user_name: str, replace: bool = False):
    """Updates background info and persists it via the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    response = requests.put(f"{API_URL}/users/{user_id}/background_info", headers=headers, json={"content": json.loads(background_update_json)})
    response.raise_for_status()
    return response.json()

def add_task_and_persist(task_description: str, user_id: int, user_email: str, user_name: str, deadline: str = None):
    """Adds a task and persists it via the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    response = requests.post(f"{API_URL}/users/{user_id}/tasks", headers=headers, json={"description": task_description, "deadline": deadline})
    response.raise_for_status()
    return response.json()

def update_tasks_and_persist(tasks_list: list, user_id: int, user_email: str, user_name: str):
    """Updates the task list and persists it via the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    results = []
    for task in tasks_list:
        task_id = task.get("id")
        if task_id:
            response = requests.put(f"{API_URL}/users/{user_id}/tasks/{task_id}", headers=headers, json=task)
            response.raise_for_status()
            results.append(response.json())
    return results

def update_input_log_and_persist(log_list: list, user_id: int, user_email: str, user_name: str):
    """Updates the input log and persists it via the backend."""
    headers = {"X-User-Email": user_email, "X-User-Name": user_name}
    response = requests.put(f"{API_URL}/users/{user_id}/text_inputs", headers=headers, json=log_list)
    response.raise_for_status()
    return response.json()

def start_new_chat():
    """Starts a new chat session."""
    return []
