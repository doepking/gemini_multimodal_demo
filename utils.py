import os
import logging
import json
import datetime as dt
import pandas as pd
from google import genai
from google.genai import types
from dotenv import load_dotenv
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import case

from database import SessionLocal
from models import User, TextInput, BackgroundInfo, Task, NewsletterLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Gemini API initialization
client = genai.Client(api_key=os.environ.get("LLM_API_KEY"))
MODEL_NAME = "gemini-2.5-flash-preview-05-20"
WEAK_MODEL = "gemini-2.0-flash-exp"
# Safety settings
safety_settings = [
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]

# --- Background Info Schema Example (Simplified for session state) ---
BACKGROUND_INFO_SCHEMA_EXAMPLE = """
{
    // This schema is a loose guideline. None of the fields are strictly required.
    // The assistant should only populate fields for which the user has provided information.
    // It's a flexible key-value store that can be updated dynamically.
  "user_profile": {
    // Examples: "name": "Jane Doe", gender: "female", "age": 30, "location": { "city": "Munich", "country": "Germany" }, "preferred_language": "EN", "communication_style_preference": "brutally honest, direct, to the point", "occupation": "Software Engineer"
    // Example: "name": "John Doe", gender: "male", "age": 35, "location": { "city": "Los Angeles", "country": "USA" }, "mbti_type": "INFJ", "preferred_language": "EN", "communication_style_preference": "friendly, patient, and kind"
  },
  "goals": [
    // Example: "Go to the gym 3 times a week for 1 hour each time for the next 6 months"
    // Example: "Read 5 books in the next 2 months"
  ],
  "values": [
    // Example: "Continuous learning"
    // Example: "Healthy lifestyle"
    // Example: "Financial stability"
    // Example: "Personal growth"
  ],
  "challenges": [
    // Example: "Work-life balance"
    // Example: "Stress management"
    // Example: "Time management"
  ],
  "habits": [
    // Example: "Daily planning"
  ],
  // Add any other relevant information here
}
"""

manage_tasks_func = types.Tool(
    function_declarations=[
        {
            "name": "manage_tasks",
            "description": (
                "Manages tasks in the session state. Use this to add, update, or list tasks based on user input. "
                "The 'action' parameter determines the operation: 'add', 'update', 'list'."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "action": {
                        "type": "STRING",
                        "description": "The action to perform on the tasks.",
                        "enum": ["add", "update", "list"]
                    },
                    "task_description": {
                        "type": "STRING",
                        "description": "The description of the task to add or update."
                    },
                    "task_id": {
                        "type": "INTEGER",
                        "description": "The ID of the task to update."
                    },
                    "task_status": {
                        "type": "STRING",
                        "description": "The status of the task. Used when updating a task's status, or to filter tasks by status when listing them.",
                        "enum": ["open", "in_progress", "completed"]
                    },
                    "deadline": {
                        "type": "STRING",
                        "description": "The deadline for the task in ISO format (e.g., YYYY-MM-DDTHH:MM:SSZ)."
                    }
                },
                "required": ["action"],
            },
        }
    ]
)

# --- Function Declarations for LLM ---
add_log_entry_func = types.Tool(
    function_declarations=[
        {
            "name": "add_log_entry",
            "description": (
                "Logs a user's text input. Before logging, lightly clean the input to improve clarity while preserving the original tone and meaning. "
                "You must correct typos, add necessary commas, remove filler words (e.g., 'um', 'like', 'you know'), and refine the structure while preserving the meaning, original tone and all essential information."
                "Use this function to record any statements about their actions, decisions, plans, reflections, feelings or observations."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "text_input": {
                        "type": "STRING",
                        "description": (
                            "The lightly cleaned text input from the user with all essential information & context preserved. "
                        ),
                    },
                    "category_suggestion": {
                        "type": "STRING",
                        "description": "Your best guess for the category for the input: 'Note', 'Decision', 'Action', 'Plan', 'Observation', 'Reflection', 'Feeling'.",
                    }
                },
                "required": ["text_input"],
            },
        }
    ]
)

update_background_info_func = types.Tool(
    function_declarations=[
        {
            "name": "update_background_info",
            "description": (
                "Updates the user's background information stored in the session state. "
                "Use this when the user explicitly provides or modifies their personal details, goals, values, or preferences. "
                "You should interpret the user's free-form text and construct a JSON string containing only the relevant fields and values to be updated, guided by the provided schema. "
                "This JSON string will be passed as the 'background_update_json' argument."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "background_update_json": {
                        "type": "STRING",
                        "description": "A JSON string containing the key-value pairs of background information to be updated or added. This JSON should be derived from the user's input text and align with the structure suggested by the BACKGROUND_INFO_SCHEMA_EXAMPLE. The generated JSON string itself must be valid; ensure that any string values within the JSON are properly escaped (e.g., quotes within strings should be escaped as \\\", backslashes as \\\\, newlines as \\n). For example, if the user says 'My name is Jane and my goal is to run a marathon', you might provide: '{\"user_profile\": {\"name\": \"Jane\"}, \"goals\": [\"Run a marathon\"]}'. Only include fields that are being changed or added.",
                    }
                },
                "required": ["background_update_json"],
            },
        }
    ]
)

# Combine tools for the LLM
chat_tools = types.Tool(
    function_declarations=[
        add_log_entry_func.function_declarations[0],
        update_background_info_func.function_declarations[0],
        manage_tasks_func.function_declarations[0],
    ]
)

# --- Database Functions ---
def get_db():
    """Generator function to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_or_create_user(db, user_email: str, user_name: str) -> User:
    """Gets a user from the database or creates one if it doesn't exist."""
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        user = User(email=user_email, username=user_name)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def load_input_log(db, user_id):
    return db.query(TextInput).filter(TextInput.user_id == user_id).all()

def load_tasks(db, user_id):
    """Loads tasks for a user, with open/in_progress tasks first, then by creation date."""
    status_order = case(
        (Task.status.in_(['open', 'in_progress']), 0),
        else_=1
    )
    return db.query(Task).filter(Task.user_id == user_id).order_by(status_order, Task.created_at.desc()).all()

def load_background_info(db, user_id):
    background_info = db.query(BackgroundInfo).filter(BackgroundInfo.user_id == user_id).order_by(BackgroundInfo.created_at.desc()).first()
    return background_info.content if background_info else {}

# --- Helper Functions for Serialization ---
def task_to_dict(task: Task) -> dict:
    """Converts a Task SQLAlchemy object to a dictionary."""
    if not task:
        return None
    return {
        "id": task.id,
        "user_id": task.user_id,
        "description": task.description,
        "status": task.status,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }

def log_entry_to_dict(log_entry: TextInput) -> dict:
    """Converts a TextInput SQLAlchemy object to a dictionary."""
    if not log_entry:
        return None
    return {
        "id": log_entry.id,
        "user_id": log_entry.user_id,
        "content": log_entry.content,
        "category": log_entry.category,
        "created_at": log_entry.created_at.isoformat() if log_entry.created_at else None,
    }

# --- Core Implementation Functions (to be called by LLM-triggered functions) ---

def manage_tasks_and_persist_impl(action: str, user: User, task_description: str = None, task_id: int = None, task_status: str = None, deadline: str = None):
    """
    Core logic to manage tasks in the database.
    """
    db = next(get_db())

    if action == "add":
        if not task_description:
            return {"status": "error", "message": "Task description is required to add a task."}
        
        task_deadline = None
        if deadline:
            try:
                task_deadline = dt.datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                try:
                    d = dt.datetime.strptime(deadline, "%Y-%m-%d").date()
                    now_time = dt.datetime.now(dt.timezone.utc).time()
                    task_deadline = dt.datetime.combine(d, now_time, tzinfo=dt.timezone.utc)
                except (ValueError, TypeError):
                    return {"status": "error", "message": "Invalid deadline format. Please use ISO format or YYYY-MM-DD."}

        new_task = Task(
            user_id=user.id,
            description=task_description,
            status="open",
            deadline=task_deadline,
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
        logger.info(f"Task added: {new_task}")
        success_message = f"Task added successfully!  \n- **Description:** '{task_description}'"
        if new_task.deadline:
            success_message += f"  \n- **Deadline:** {new_task.deadline.strftime('%Y-%m-%d %H:%M')}"
        return {"status": "success", "message": success_message, "task": task_to_dict(new_task)}

    elif action == "update":
        if task_id is None:
            return {"status": "error", "message": "Task ID is required to update a task."}
        
        task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
        if not task:
            return {"status": "error", "message": f"Task with ID {task_id} not found."}

        if task_status:
            task.status = task_status
            if task_status == "completed":
                task.completed_at = dt.datetime.now(dt.timezone.utc)
            else:
                # If status is changed to something other than completed, clear completed_at
                task.completed_at = None

        if deadline:
            try:
                task.deadline = dt.datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                try:
                    d = dt.datetime.strptime(deadline, "%Y-%m-%d").date()
                    now_time = dt.datetime.now(dt.timezone.utc).time()
                    task.deadline = dt.datetime.combine(d, now_time, tzinfo=dt.timezone.utc)
                except (ValueError, TypeError):
                    return {"status": "error", "message": "Invalid deadline format. Please use ISO format or YYYY-MM-DD."}
        
        if task_description:
            task.description = task_description

        db.commit()
        db.refresh(task)
        logger.info(f"Task {task_id} updated. Status: {task.status}, Description: {task.description}")
        
        # Construct a more detailed success message
        update_details = []
        if task_status:
            update_details.append(f"status to '{task_status}'")
        if task_description:
            update_details.append(f"description to '{task_description}'")
        if deadline:
            update_details.append(f"deadline to '{deadline}'")
        
        task_desc_preview = task.description[:75] + "..." if len(task.description) > 75 else task.description
        success_message = f"Okay, I've updated the task '{task_desc_preview}' ({', '.join(update_details)})."
        return {"status": "success", "message": success_message, "task": task_to_dict(task)}

    elif action == "list":
        query = db.query(Task).filter(Task.user_id == user.id)
        if task_status and task_status in ["open", "in_progress", "completed"]:
            query = query.filter(Task.status == task_status)

        status_order = case(
            (Task.status == 'in_progress', 0),
            (Task.status == 'open', 1),
            (Task.status == 'completed', 2),
            else_=3
        )
        tasks = query.order_by(status_order, Task.created_at.desc()).all()
        return {"status": "success", "tasks": [task_to_dict(t) for t in tasks]}

    else:
        return {"status": "error", "message": f"Unknown task action: {action}"}

def deep_update(source, overrides):
    """
    Recursively update a dictionary.
    """
    for key, value in overrides.items():
        if isinstance(value, dict) and value:
            # get the existing dict or a new one
            existing_dict = source.get(key, {})
            if not isinstance(existing_dict, dict):
                existing_dict = {}
            source[key] = deep_update(existing_dict, value)
        elif isinstance(value, list) and value:
            if key not in source or not isinstance(source.get(key), list):
                source[key] = []
            source[key].extend(item for item in value if item not in source[key])
        else:
            source[key] = value
    return source


def add_log_entry_and_persist_impl(text_input: str, user: User, category_suggestion: str = None):
    """
    Core logic to process and log text input to the database.
    """
    if user is None:
        logger.error("User not provided to add_log_entry_and_persist_impl")
        return {"status": "error", "message": "User missing."}

    db = next(get_db())

    log_entry = TextInput(
        user_id=user.id,
        content=text_input,
        category=category_suggestion if category_suggestion else "Note",
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    
    content_preview = text_input[:100] + "..." if len(text_input) > 100 else text_input
    logger.info(f"Input logged: {content_preview}")
    
    final_category = category_suggestion if category_suggestion else "Note"
    success_message = (
        f"Log added successfully!  \n"
        f"- **Content:** '{content_preview}'  \n"
        f"- **Category:** {final_category}"
    )
    
    return {"status": "success", "message": success_message, "entry": log_entry_to_dict(log_entry)}

def update_background_info_and_persist_impl(background_update_json: str, user: User, replace: bool = False):
    """
    Core logic to update background information in the database.
    If 'replace' is True, the entire content is overwritten.
    Otherwise, a deep update is performed.
    """
    if user is None:
        logger.error("User not provided to update_background_info_and_persist_impl")
        return {"status": "error", "message": "User missing."}

    db = next(get_db())

    try:
        update_data = json.loads(background_update_json)
        
        background_info = db.query(BackgroundInfo).filter(BackgroundInfo.user_id == user.id).order_by(BackgroundInfo.created_at.desc()).first()
        if not background_info:
            background_info = BackgroundInfo(user_id=user.id, content={})
            db.add(background_info)

        if replace:
            # Direct replacement for UI edits
            updated_content = update_data
        else:
            # Recursive update for AI-driven changes
            current_content = (background_info.content or {}).copy()
            updated_content = deep_update(current_content, update_data)
        
        background_info.content = updated_content
        flag_modified(background_info, "content")  # Mark the JSON field as modified
        db.commit()
        db.refresh(background_info)
        
        message = "Background information updated."
        logger.info(f"Background info updated. Replace mode: {replace}. Current: {background_info.content}")
        return {"status": "success", "message": message, "updated_info": background_info.content}

    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON format for background update."}
    except Exception as e:
        logger.error(f"Error updating background info: {e}", exc_info=True)
        db.rollback()
        return {"status": "error", "message": "An unexpected error occurred."}


# --- App-Facing Functions ---
# These are called directly by the Streamlit UI. They handle persistence.

def add_log_entry_and_persist(text_input: str, user: User, category_suggestion: str = None):
    """App-facing function to add a log entry and persist it."""
    return add_log_entry_and_persist_impl(text_input, user, category_suggestion)

def update_background_info_and_persist(background_update_json: str, user: User, replace: bool = False):
    """App-facing function to update background info and persist it."""
    return update_background_info_and_persist_impl(background_update_json, user, replace=replace)

def add_task_and_persist(task_description: str, user: User, deadline: str = None):
    """App-facing function to add a new task and persist it."""
    return manage_tasks_and_persist_impl(action="add", user=user, task_description=task_description, deadline=deadline)

def update_tasks_and_persist(tasks_list: list, user: User):
    """App-facing function to update the entire task list and persist it."""
    db = next(get_db())
    
    submitted_task_ids = {task_data['id'] for task_data in tasks_list if 'id' in task_data}
    current_task_ids_db = {task.id for task in db.query(Task).filter(Task.user_id == user.id).all()}
    
    ids_to_delete = current_task_ids_db - submitted_task_ids
    if ids_to_delete:
        db.query(Task).filter(Task.id.in_(ids_to_delete), Task.user_id == user.id).delete(synchronize_session=False)

    for task_data in tasks_list:
        if 'id' in task_data:
            task = db.query(Task).filter(Task.id == task_data['id'], Task.user_id == user.id).first()
            if task:
                task.description = task_data['description']
                task.status = task_data['status']
                task.deadline = task_data['deadline']
                if task_data['status'] == 'completed' and task.completed_at is None:
                    task.completed_at = dt.datetime.now(dt.timezone.utc)
                elif task_data['status'] != 'completed':
                    task.completed_at = None
    
    db.commit()
    return {"status": "success", "message": "Tasks updated successfully."}

def update_input_log_and_persist(log_list: list, user: User):
    """App-facing function to update the entire input log and persist it."""
    db = next(get_db())

    submitted_log_ids = {log_data['id'] for log_data in log_list if 'id' in log_data}
    current_log_ids_db = {log.id for log in db.query(TextInput).filter(TextInput.user_id == user.id).all()}

    ids_to_delete = current_log_ids_db - submitted_log_ids
    if ids_to_delete:
        db.query(TextInput).filter(TextInput.id.in_(ids_to_delete), TextInput.user_id == user.id).delete(synchronize_session=False)

    for log_data in log_list:
        if 'id' in log_data:
            log = db.query(TextInput).filter(TextInput.id == log_data['id'], TextInput.user_id == user.id).first()
            if log:
                log.content = log_data['content']
                log.category = log_data['category']

    db.commit()
    return {"status": "success", "message": "Input log updated successfully."}


# --- Chat Functions ---
def start_new_chat():
    """Starts a new chat session."""
    return []  # Initialize an empty conversation history

def transcribe_audio(audio_file_path: str) -> str:
    """Transcribes an audio file using a weaker, faster model."""
    logger.info(f"Transcribing audio file: {audio_file_path}")
    try:
        with open(audio_file_path, "rb") as audio_file:
            audio_content = audio_file.read()
        audio_part = types.Part(inline_data=types.Blob(data=audio_content, mime_type="audio/wav"))

        transcription_prompt = "Please transcribe the following audio input:"
        
        transcription_config = types.GenerateContentConfig(
            max_output_tokens=2048,
            temperature=0.0,
            top_p=1,
            top_k=32,
            safety_settings=[
                types.SafetySetting(category=s["category"], threshold=s["threshold"])
                for s in safety_settings
            ],
        )

        response = client.models.generate_content(
            model=WEAK_MODEL,
            contents=[transcription_prompt, audio_part],
            config=transcription_config
        )

        if not response.candidates:
            logger.warning("Transcription failed: No candidates in response.")
            return None

        candidate = response.candidates[0]
        if not (hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts') and candidate.content.parts):
            logger.warning(f"Transcription failed: Candidate has no content or parts. Finish reason: {getattr(candidate, 'finish_reason', 'N/A')}")
            return None

        transcribed_text = "".join(part.text for part in candidate.content.parts if hasattr(part, "text") and part.text)
        logger.info(f"Successfully transcribed audio: '{transcribed_text[:100]}...'")
        return transcribed_text

    except Exception as e:
        logger.error(f"Error during audio transcription: {e}", exc_info=True)
        return None

def get_chat_response(conversation_history, session_state, user_prompt=None, audio_file_path=None):
    """Gets a response from the Gemini model, handling text, audio, and function calls."""
    user = session_state.get('user')
    background_info = session_state.get('background_info', {})
    input_log = session_state.get('input_log', [])
    tasks = session_state.get('tasks', [])
    current_bg_info_str = json.dumps(background_info, indent=2)
    
    recent_logs_preview = []
    for log in input_log[-50:]: # Last 50 logs
        timestamp = log.created_at.strftime('%Y-%m-%d %H:%M:%S (%A)') if log.created_at else 'No timestamp'
        content_preview = log.content[:500] + "..." if len(log.content) > 500 else log.content
        recent_logs_preview.append(f"[{timestamp}] {content_preview}")
    recent_logs_str = "\n- ".join(recent_logs_preview) if recent_logs_preview else "No recent logs."
    
    active_tasks = [task for task in tasks if task.status in ['open', 'in_progress']]
    tasks_preview = [f"ID: {task.id}, Desc: {task.description}, Status: {task.status}, Deadline: {task.deadline}" for task in active_tasks[:20]] # Last 20 active tasks
    tasks_str = "\n- ".join(tasks_preview) if tasks_preview else "No open or in-progress tasks."
    
    now = dt.datetime.now(dt.timezone.utc)
    current_time_str = now.isoformat()
    current_weekday_str = now.strftime('%A')

    system_prompt = f"""
    Your role is to be a proactive and intelligent assistant, helping the user organize their thoughts, tasks, and personal information.
    Listen carefully to the user's input to decide whether to respond directly, use one of your tools, or use multiple tools in combination.

    CURRENT TIME (UTC):
    - ISO Format: {current_time_str}
    - Weekday: {current_weekday_str}

    Schema for background info (as a loose guideline, when the user provides updates):
    ```json
    {BACKGROUND_INFO_SCHEMA_EXAMPLE}
    ```

    CURRENT USER BACKGROUND INFO:
    ```json
    {current_bg_info_str}
    ```

    RECENT USER LOGS (most recent 50):
    - {recent_logs_str}

    CURRENT TASKS: (most recent 20)
    - {tasks_str}

    --- FUNCTION CALLING RULES ---

    1.  **Call `add_log_entry` when:**
        - The user provides any statement about their actions, decisions, plans, reflections, feelings or observations.
        - The input can be categorized as a "Note", "Action", "Decision", "Plan", "Reflection", "Feeling", or "Observation".
        - If the input ALSO contains information for other function calls (task creation, task updates or background information updates), other functions should be called IN ADDITION to this one.
        - Example: "I decided to start exercising." → call `add_log_entry`
        - Example: "I'm planning to finish the report by Friday, and I'm feeling good about it." → call `add_log_entry` AND `manage_tasks`
        - Example: "I just finished the presentation slides, it was a lot of work! I also realized my core value is continuous learning." → call `add_log_entry` AND `manage_tasks` AND `update_background_info`
        - Non-Example: "My name's Mike. I'm 30 years old. I'm a guy living in Munich, Germany." → DO NOT call `add_log_entry`, call `update_background_info` ONLY
        - Non-Example: "Can you create a task that I need to take out the trash tomorrow morning at 11:00 a.m.?" → DO NOT call `add_log_entry`, call `manage_tasks` with `action='add'` ONLY
        - Non-Example: "Should I take job A or job B, considering my values & goals?" → DO NOT call `add_log_entry`. Respond directly to the user with a text response.

    2.  **Call `update_background_info` when:**
        - The user provides personal information (e.g. name, age, gender, location, occupation, family status etc.) or information/updates about their goals, values, challenges, habits, etc.
        - This function should be called even if the input is also being logged by `add_log_entry`.
        - You must interpret the user's text and construct a valid, escaped JSON string for the `background_update_json` argument.
        - Example: "My new goal is to learn Python." -> call `update_background_info` with `background_update_json='{{"goals": ["Learn Python"]}}'`.
        - Example: "I've been reflecting and realized my main value is 'impact'." -> call `add_log_entry` AND `update_background_info` with `background_update_json='{{"values": ["impact"]}}'`.

    3.  **Call `manage_tasks` when:**
        - The user's input describes new, concrete, actionable to-do items, plans, or intentions that *should clearly become tasks*. This applies even if the input is also being logged by `add_log_entry`.
        - **action='add'**:
            - This includes explicit requests like "remind me to..." or "add a task to...".
            - This ALSO includes statements of future actions, plans, or intentions like "I'm going to...", "I will...", "I plan to...", "I intend to...", "I need to..." that are specific enough to be a task.
            - Example (Explicit): "Remind me to buy groceries tomorrow."
            - Example (Intention/Plan): "I'm planning to draft the project proposal this afternoon."
            - Example (Need/Goal-driven action): "To effectively develop this, I may need to analyze example inputs." (This implies a task: "Analyze example inputs")
            - Non-Example: "Going for my morning walk. I'll also think about my next project, maybe something about implementation, and check how my current one is doing." → DO NOT call `manage_tasks`. This is a reflective thought process, not a set of concrete to-do items.
        - **action='update'**:
            - The user's input describes an action they've taken, progress they've made, or the completion of something that relates to an existing task. This also includes requests to modify a task's description or deadline.
            - This includes explicit commands like "mark 'X' as done" or "change the deadline for task Y".
            - This ALSO includes statements like "I finished X", "I completed Y", "I've made progress on Z", "I worked on A", "I'm done with B".
            - The function will attempt to link the statement to an existing task and update its status (e.g., to 'completed' or 'in_progress'), description, or deadline. To do this accurately, you MUST identify the correct `task_id` from the 'CURRENT TASKS' list and pass it to the function call.
            - Be proactive: If a user's log entry clearly corresponds to a task, update it. For example, if there is a task "Go for a run" and the user says "I just went for a run", you should update the task to 'completed'.
            - ONLY call this function if the task status, description, or deadline is changed.
            - Example (Explicit Status): "Mark 'buy groceries' as done."
            - Example (Implicit Completion): "I just managed to sit down for a bit and finish the report." -> update task to 'completed'.
            - Example (Implicit Progress): "I worked on the presentation slides for a couple of hours." -> update task to 'in_progress'.
            - Example (Proactive Completion): User says "Just got back from my run." and a task "Go for a run" exists -> update task to 'completed'.
            - Example (Deadline Update): "Can you move the deadline for the 'project proposal' task to next Friday?" -> update task deadline.
            - Example (Description Update): "Change the task 'buy groceries' to 'buy groceries for the week, including milk and bread'." -> update task description.
        - **action='list'**:
            - The user requests to see their tasks. This can be filtered by status (e.g., 'open', 'in_progress', 'completed').
            - If no status is specified, all tasks will be listed.
            - Example: "Show me my open tasks." -> list tasks with status "open".
            - Example: "List my completed tasks." -> list tasks with status "completed".
            - Example: "What are all my tasks?" -> list all tasks.

    --- MULTI-FUNCTION CALL EXAMPLES ---
    *   User Input: "Feeling productive today! I'm going to draft the project proposal this morning and then review the Q2 financials in the afternoon. This new focus on time blocking is really helping."
        *   Call `add_log_entry` with the cleaned-up input.
        *   AND Call `manage_tasks` with `action='add'` and the relevant task details.
        *   AND respond with a text response to me (the user) to acknowledge my input and confirm the actions you've taken via function calls.

    *   User Input: "I just finished the presentation slides! That took longer than expected. I also realized my core goal for this month should be to improve my design skills."
        *   Call `add_log_entry` with the cleaned-up input.
        *   AND Call `manage_tasks` with `action='update'` to mark the task as 'completed'.
        *   AND Call `update_background_info` with the new goal
        *   AND respond with a text response to me (the user) to acknowledge my input and confirm the actions you've taken via function calls.

    *   User Input: "Okay, I've decided to take the new job offer. It means relocating, which is a big step. I need to give notice at my current job by next Friday and start looking for apartments."
        *   Call `add_log_entry` with the cleaned-up input.
        *   AND Call `manage_tasks` with `action='add'` to create tasks for giving notice and looking for apartments
        *   AND respond with a text response to me (the user) to acknowledge my input and confirm the actions you've taken via function calls.

    --- RESPONSE GUIDELINES ---
    -   **IMPORTANT**: You MUST ALWAYS provide a text response to me (the user), even when you are making a function call. Your text response should be conversational and helpful. Acknowledge my input and confirm the actions you've taken via function calls. For example, if I say "I live in Munich", you should call `update_background_info` AND respond with something like "Thanks for letting me know you live in Munich! I've updated your profile. What can I help you with?".
    -   If there is yet limited or no background information about me, PROACTIVELY engage in conversation to learn more about my personal details, values and goals.
    -   Use function calls proactively and intelligently, including MULTIPLE function calls per turn when appropriate.
    -   You may combine a function call with a text response. For example, you could use 'add_log_entry' to record my decision and also respond with text to acknowledge the decision and ask a follow-up question.
    -   Always provide a brief text response to acknowledge my input, even when calling function(s).
    -   If I engage in casual conversation or ask a general question, don't unnecessarily log irrelevant information via function calls.
    -   If no function call is needed, just respond directly to the user.
    """

    contents = [] # Initialize contents as an empty list

    # Add conversation history
    for turn in conversation_history:
        role = "user" if turn["role"] == "user" else "model"
        # Handle cases where turn['content'] might be a list of parts (from previous function calls)
        if isinstance(turn["content"], list):
            # The content is already a list of parts (or dicts representing parts)
            contents.append({"role": role, "parts": turn["content"]})
        else:
            # For simple text content, wrap it in a Part object
            contents.append({"role": role, "parts": [types.Part(text=turn["content"])]})


    # If audio is provided, transcribe it first and use the text as the prompt.
    if audio_file_path:
        transcribed_text = transcribe_audio(audio_file_path)
        if transcribed_text:
            user_prompt = transcribed_text
        else:
            # Handle transcription failure
            return {"text_response": "Sorry, I couldn't understand the audio. Please try again.", "ui_message": "Audio transcription failed."}

    # At this point, all inputs are treated as text prompts.
    if not user_prompt:
        logger.error("No user prompt available after processing inputs.")
        return {"text_response": "Error: No input provided.", "ui_message": None}

    # Add the final user prompt to the conversation history
    conversation_history.append({"role": "user", "content": user_prompt})

    # Add the current user prompt to the contents for the API call
    contents.append({"role": "user", "parts": [types.Part(text=user_prompt)]})


    # --- First LLM Call (to decide on function call or direct response) ---
    logger.info(f"Sending request to LLM. Content length: {len(contents)}")
    try:
        # Explicitly set tool_config to AUTO to let the model decide.
        tool_config = types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode="AUTO"
            )
        )
        thinking_config = types.ThinkingConfig(
            thinking_budget=2048,
            include_thoughts=False
        )
        generation_config_with_tools = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[chat_tools],  # Tools included in the config
            tool_config=tool_config, # Let the model intelligently decide to use tools
            thinking_config=thinking_config, # Set thinking budget to 2048 tokens
            max_output_tokens=4096,
            temperature=0.7,
            safety_settings=[
                types.SafetySetting(category=s["category"], threshold=s["threshold"])
                for s in safety_settings
            ],
        )
        response = client.models.generate_content( # Use the client object
            model=MODEL_NAME, # Specify the model name
            contents=contents,
            config=generation_config_with_tools, # Pass the config object
        )

        # Log token usage and thoughts
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage_metadata = response.usage_metadata
            logger.info(f"Prompt Token Count: {usage_metadata.prompt_token_count}")
            thoughts_token_count = getattr(usage_metadata, 'thoughts_token_count') or 0
            if thoughts_token_count > 0:
                logger.info(f"Thoughts Token Count: {thoughts_token_count}")
            logger.info(f"Candidates Token Count: {usage_metadata.candidates_token_count}")
            logger.info(f"Total Token Count: {usage_metadata.total_token_count}")
    except Exception as e:
        logger.error(f"LLM generation error: {e}", exc_info=True)
        return {"text_response": f"Sorry, an error occurred with the AI model: {e}", "ui_message": None}

    if not response.candidates:
        if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
            logger.warning(f"No candidates in LLM response. Prompt feedback: {response.prompt_feedback}")
        else:
            logger.warning("No candidates in LLM response.")
        return {"text_response": "Sorry, I couldn't generate a response. Please try again.", "ui_message": None}

    candidate = response.candidates[0]

    if not (hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts') and candidate.content.parts):
        logger.warning(f"LLM response candidate has no content or parts. Finish reason: {getattr(candidate, 'finish_reason', 'N/A')}, Safety ratings: {getattr(candidate, 'safety_ratings', 'N/A')}")
        return {"text_response": "Sorry, I couldn't generate a response. Please try again.", "ui_message": None}

    # --- Process LLM Response: Text and Function Calls ---
    llm_text_responses = []
    function_calls_to_process = []
    model_turn_content_for_history = [] # To store parts for history
    function_calls_exist = any(hasattr(part, "function_call") and part.function_call for part in candidate.content.parts)

    # 1. First pass: Collect all text parts and function calls
    for part in candidate.content.parts:
        if hasattr(part, "text") and part.text:
            llm_text_responses.append(part.text)
        if hasattr(part, "function_call") and part.function_call:
            function_calls_to_process.append(part.function_call)

    # Add the initial model response (text and function call requests) to history
    # This captures the model's "thought process"
    if llm_text_responses:
        model_turn_content_for_history.append({"text": " ".join(llm_text_responses)})
    if function_calls_to_process:
        for fc in function_calls_to_process:
             model_turn_content_for_history.append({"function_call": fc})

    # 2. Execute function calls if any were requested
    ui_update_messages = []
    if function_calls_to_process:
        for fc in function_calls_to_process:
            function_name = fc.name
            function_args = dict(fc.args)
            logger.info(f"LLM requested function call: {function_name} with args: {function_args}")

            # --- Execute the function ---
            function_response_content = {}
            ui_message_for_this_call = None
            if function_name == "add_log_entry":
                result = add_log_entry_and_persist_impl(
                    text_input=function_args.get("text_input"),
                    user=user,
                    category_suggestion=function_args.get("category_suggestion")
                )
                function_response_content = result
                if result.get("status") == "success":
                    ui_message_for_this_call = result.get("message")

            elif function_name == "update_background_info":
                result = update_background_info_and_persist_impl(
                    background_update_json=function_args.get("background_update_json"),
                    user=user
                )
                function_response_content = result
                if result.get("status") == "success":
                    ui_message_for_this_call = result.get("message")

            elif function_name == "manage_tasks":
                result = manage_tasks_and_persist_impl(
                    action=function_args.get("action"),
                    user=user,
                    task_description=function_args.get("task_description"),
                    task_id=function_args.get("task_id"),
                    task_status=function_args.get("task_status"),
                    deadline=function_args.get("deadline")
                )
                function_response_content = result
                if result.get("status") == "success":
                    if result.get("tasks"):
                        tasks = result.get("tasks")
                        status_filter = function_args.get("task_status")
                        if tasks:
                            if status_filter:
                                header = f"These are your '{status_filter}' tasks:"
                            else:
                                header = "These are all your current tasks:"
                            formatted_tasks = [header]
                            for task in tasks:
                                deadline_str = ""
                                if task.get("deadline"):
                                    try:
                                        deadline_dt = dt.datetime.fromisoformat(task["deadline"].replace("Z", "+00:00"))
                                        deadline_str = f", Deadline: {deadline_dt.strftime('%Y-%m-%d %H:%M')}"
                                    except (ValueError, TypeError):
                                        deadline_str = f", Deadline: {task.get('deadline')}" # Fallback
                                formatted_tasks.append(
                                    f"- **Task {task['id']}**: {task['description']} (Status: {task['status']}{deadline_str})"
                                )
                            ui_message_for_this_call = "\n".join(formatted_tasks)
                        else:
                            if status_filter:
                                ui_message_for_this_call = f"You have no tasks with status '{status_filter}'."
                            else:
                                ui_message_for_this_call = "You have no tasks."
                    else:
                        ui_message_for_this_call = result.get("message")
            else:
                logger.warning(f"LLM called unknown function: {function_name}")
                function_response_content = {"status": "error", "message": f"Unknown function: {function_name}"}
                ui_message_for_this_call = f"Error: Unknown function '{function_name}' called."

            if ui_message_for_this_call:
                ui_update_messages.append(ui_message_for_this_call)

            # Add function execution result to history for the *next* turn's context
            conversation_history.append({
                "role": "function",
                "content": [{"function_response": {"name": function_name, "response": function_response_content}}]
            })

    # 3. Assemble the final response for the user
    final_text_response_to_user = " ".join(llm_text_responses).strip()
    
    # The UI message for toast/notification can be the aggregation of all messages
    ui_update_message = "  \n\n".join(ui_update_messages) if ui_update_messages else None

    # If the LLM provided a text response, use it. Otherwise, use the UI message.
    if not final_text_response_to_user and ui_update_message:
        final_text_response_to_user = ui_update_message
    elif final_text_response_to_user and ui_update_message:
        # Optionally combine them if both exist
        final_text_response_to_user = f"{final_text_response_to_user}\n\n{ui_update_message}"


    # Add the complete model turn (text + all function calls) to history
    if model_turn_content_for_history:
        conversation_history.append({"role": "model", "content": model_turn_content_for_history})

    # Handle case where there was no function call and no text response
    if not function_calls_exist and not final_text_response_to_user:
        logger.warning("LLM response had no function calls and no text in parts.")
        final_text_response_to_user = "I'm not sure how to respond to that."
        conversation_history.append({"role": "model", "content": final_text_response_to_user})

    # The UI message for toast/notification can be the aggregation of all messages
    ui_update_message = "  \n\n".join(ui_update_messages) if ui_update_messages else None

    logger.info(f"Final text response to user: {final_text_response_to_user}")
    if ui_update_message:
        logger.info(f"Aggregated UI update message: {ui_update_message}")

    return {"text_response": final_text_response_to_user, "ui_message": ui_update_message}

def purge_user_data(user_id: int):
    """
    Deletes all data associated with a user ID from the database.
    """
    db = next(get_db())
    try:
        # Delete all tasks, background info, text inputs, and newsletter logs for the user
        db.query(NewsletterLog).filter(NewsletterLog.user_id == user_id).delete(synchronize_session=False)
        db.query(Task).filter(Task.user_id == user_id).delete(synchronize_session=False)
        db.query(BackgroundInfo).filter(BackgroundInfo.user_id == user_id).delete(synchronize_session=False)
        db.query(TextInput).filter(TextInput.user_id == user_id).delete(synchronize_session=False)
        
        # Delete the user
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            db.delete(user)
        
        db.commit()
        logger.info(f"All data for user ID {user_id} has been purged.")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error purging data for user ID {user_id}: {e}", exc_info=True)
        return False
    finally:
        db.close()
