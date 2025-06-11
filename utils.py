import os
import logging
import json
import datetime as dt
import pandas as pd
from google import genai
from google.genai import types
from dotenv import load_dotenv

from database import SessionLocal
from models import User, TextInput, BackgroundInfo, Task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Gemini API initialization
client = genai.Client(api_key=os.environ.get("LLM_API_KEY"))
MODEL_NAME = "gemini-2.5-flash-preview-05-20"
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
  "user_profile": {
    "name": "String (e.g., Jane Doe)",
    "age": "Integer (e.g., 30)",
    "gender": "String (e.g., Female)",
    "location": "Object (e.g., { 'city': 'New York', 'country': 'USA' })",
    "occupation": "String (e.g., Software Engineer)",
    "current_focus": "String (e.g., Learning to code, Improving health)",
    "communication_style_preference": "String (e.g., direct, empathetic, concise)"
  },
  "goals": [
    "String (e.g., Complete a marathon by end of year)",
    "String (e.g., Read 12 books this year)",
  ],
  "values": [
    "String (e.g., Continuous learning)",
    "String (e.g., Family)"
  ],
  "challenges": [
    "String (e.g., Work-life balance)",
    "String (e.g., Health)",
    "String (e.g., Finances)"
  ],
  "habits": [
    "String (e.g., Daily planning)",
    "String (e.g., Weekly review)",
    "String (e.g., Daily meditation)"
  ]
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
                        "description": "The new status of the task to update.",
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
                "Processes a user's text input, categorizes it (optional, basic for now), "
                "and adds it to a session-based log. Use this when the user provides a general statement, "
                "observation, thought, or event they want to record."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "text_input": {
                        "type": "STRING",
                        "description": "The raw text input provided by the user to be logged.",
                    },
                    "category_suggestion": {
                        "type": "STRING",
                        "description": "An optional category suggested by the LLM (e.g., 'Observation', 'Idea', 'Decision', 'Feeling'). Keep it simple.",
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
    return db.query(Task).filter(Task.user_id == user_id).all()

def load_background_info(db, user_id):
    background_info = db.query(BackgroundInfo).filter(BackgroundInfo.user_id == user_id).order_by(BackgroundInfo.created_at.desc()).first()
    return background_info.content if background_info else {}

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
            due_date=task_deadline,
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
        logger.info(f"Task added: {new_task}")
        return {"status": "success", "message": f"Task added: '{task_description}'", "task": new_task}

    elif action == "update":
        if task_id is None or task_status is None:
            return {"status": "error", "message": "Task ID and status are required to update a task."}
        
        task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
        if task:
            task.status = task_status
            db.commit()
            db.refresh(task)
            logger.info(f"Task {task_id} updated to {task_status}")
            success_message = f"Okay, I've updated Task {task.id}: '{task.description}' to '{task_status}'."
            return {"status": "success", "message": success_message, "task": task}
        else:
            return {"status": "error", "message": f"Task with ID {task_id} not found."}

    elif action == "list":
        active_tasks = db.query(Task).filter(Task.user_id == user.id, Task.status.in_(['open', 'in_progress'])).all()
        return {"status": "success", "tasks": active_tasks}

    else:
        return {"status": "error", "message": f"Unknown task action: {action}"}

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
        category=category_suggestion if category_suggestion else "General Log",
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    
    content_preview = text_input[:100] + "..." if len(text_input) > 100 else text_input
    logger.info(f"Input logged: {content_preview}")
    return {"status": "success", "message": f"Log added: '{content_preview}'", "entry": log_entry}

def update_background_info_and_persist_impl(background_update_json: str, user: User):
    """
    Core logic to update background information in the database.
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

        current_content = background_info.content or {}
        
        for key, value in update_data.items():
            if key in current_content and isinstance(current_content[key], list) and isinstance(value, list):
                current_content[key].extend(item for item in value if item not in current_content[key])
            elif key in current_content and isinstance(current_content[key], dict) and isinstance(value, dict):
                current_content[key].update(value)
            else:
                current_content[key] = value
        
        background_info.content = current_content
        db.commit()
        db.refresh(background_info)
        
        message = "Background information updated."
        logger.info(f"Background info updated. Current: {background_info.content}")
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

def update_background_info_and_persist(background_update_json: str, user: User):
    """App-facing function to update background info and persist it."""
    return update_background_info_and_persist_impl(background_update_json, user)

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
                task.due_date = task_data['deadline']
    
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

def get_chat_response(conversation_history, session_state, user_prompt=None, audio_file_path=None):
    """Gets a response from the Gemini model, handling text, audio, and function calls."""
    user = session_state.get('user')
    background_info = session_state.get('background_info', {})
    input_log = session_state.get('input_log', [])
    tasks = session_state.get('tasks', [])
    current_bg_info_str = json.dumps(background_info, indent=2)
    recent_logs_preview = [log.content[:100] + "..." if len(log.content) > 100 else log.content for log in input_log[-5:]] # Last 5 logs
    recent_logs_str = "\n- ".join(recent_logs_preview) if recent_logs_preview else "No recent logs."
    tasks_preview = [f"ID: {task.id}, Desc: {task.description}, Status: {task.status}" for task in tasks]
    tasks_str = "\n- ".join(tasks_preview) if tasks_preview else "No tasks."
    
    now = dt.datetime.now(dt.timezone.utc)
    current_time_str = now.isoformat()
    current_weekday_str = now.strftime('%A')

    system_prompt = f"""
    Your role is to be a proactive and intelligent assistant, helping the user organize their thoughts, tasks, and personal information.
    Listen carefully to the user's input to decide whether to respond directly, use one of your tools, or use multiple tools in combination.

    CURRENT TIME:
    - ISO Format: {current_time_str}
    - Weekday: {current_weekday_str}

    Schema for background info (as a loose guideline, when the user provides updates):
    ```json
    {BACKGROUND_INFO_SCHEMA_EXAMPLE}
    ```

    CURRENT USER BACKGROUND INFO (stored in session):
    ```json
    {current_bg_info_str}
    ```

    RECENT USER LOGS (last 5, stored in session):
    - {recent_logs_str}

    CURRENT TASKS (stored in session):
    - {tasks_str}

    --- FUNCTION CALLING RULES ---

    1.  **Call `add_log_entry` when:**
        - The user provides any general statement, observation, thought, or event they want to record.
        - If the input also contains information for other function calls (like creating a task or updating background info), call `add_log_entry` IN ADDITION to the other relevant functions.
        - Example: "I'm planning to finish the report by Friday, and I'm feeling good about it." -> Call `add_log_entry` AND `manage_tasks`.
        - Example: "I just finished the presentation slides. I also realized my core value is continuous learning." -> Call `add_log_entry`, `manage_tasks` (to update), AND `update_background_info`.
        - Non-Example: "What are my tasks?" -> DO NOT call `add_log_entry`. Call `manage_tasks` with action='list' ONLY.
        - Non-Example: "My name is Mike." -> DO NOT call `add_log_entry`. Call `update_background_info` ONLY.

    2.  **Call `update_background_info` when:**
        - The user provides personal information (e.g., name, age, location), or updates their goals, values, challenges, or habits.
        - This function should be called even if the input is also being logged by `add_log_entry`.
        - You must interpret the user's text and construct a valid, escaped JSON string for the `background_update_json` argument.
        - Example: "My new goal is to learn Python." -> Call `update_background_info` with `background_update_json='{{"goals": ["Learn Python"]}}'`.
        - Example: "I've been reflecting and realized my main value is 'impact'." -> Call `add_log_entry` AND `update_background_info` with `background_update_json='{{"values": ["impact"]}}'`.

    3.  **Call `manage_tasks` when:**
        - The user wants to add, update, or list tasks.
        - **Add Task (`action='add'`):** Use for explicit requests ("add a task...") AND for statements of future intent ("I will...", "I need to...", "I plan to...").
            - You MUST infer deadlines from text like "tomorrow", "by Friday at 5pm", or "on Dec 25th" and convert them to an ISO string for the `deadline` argument.
            - Example (Intent): "I'm going to draft the project proposal this afternoon." -> Call `manage_tasks` with `action='add'`, `task_description='Draft the project proposal'`, and an inferred `deadline`.
        - **Update Task (`action='update'`):** Use for explicit requests ("mark task 1 as done") AND for statements of progress or completion ("I finished the report", "I worked on the slides").
            - You need to infer the `task_id` and the `task_status` ('completed' or 'in_progress').
            - Example (Implicit Completion): "Just got back from my run." -> If a "Go for a run" task exists, call `manage_tasks` with `action='update'`, the correct `task_id`, and `task_status='completed'`.
        - **List Tasks (`action='list'`):** Use when the user asks to see their tasks.

    --- MULTI-FUNCTION CALL EXAMPLES ---
    -   **User Input:** "Feeling productive today! I'm going to draft the project proposal this morning. This new focus on time blocking is really helping my productivity."
        -   Call `add_log_entry` with the full text.
        -   AND Call `manage_tasks` with `action='add'`, `task_description='Draft the project proposal'`, and an inferred `deadline`.

    -   **User Input:** "I just finished the presentation slides! That took longer than expected. I also realized my main goal for this month should be to improve my design skills."
        -   Call `add_log_entry` with the full text.
        -   AND Call `manage_tasks` with `action='update'` to mark the presentation task as 'completed'.
        -   AND Call `update_background_info` with `background_update_json='{{"goals": ["Improve my design skills"]}}'`.

    --- RESPONSE GUIDELINES ---
    -   Use function calls proactively and intelligently. Combine them in a single turn when appropriate.
    -   Always provide a brief, natural language text response to acknowledge the user's input, even when calling functions.
    -   If you call functions, the final text response should summarize what you've done (e.g., "Okay, I've added that to your log and created a new task for you.").
    -   If no function call is needed, just respond directly to the user.
    """

    contents = [] # Initialize contents as an empty list

    # Add conversation history
    for turn in conversation_history:
        role = "user" if turn["role"] == "user" else "model"
        # Handle cases where turn['content'] might be a list of parts (from previous function calls)
        if isinstance(turn["content"], list):
            contents.append({"role": role, "parts": turn["content"]})
        else:
            contents.append({"role": role, "parts": [{"text": turn["content"]}]})


    # Prepare current user input
    current_input_parts = []
    if user_prompt:
        current_input_parts.append({"text": user_prompt})
        logger.info(f"User text prompt: {user_prompt}")
    elif audio_file_path:
        logger.info(f"Processing audio file: {audio_file_path}")
        try:
            with open(audio_file_path, "rb") as audio_file:
                audio_content_bytes = audio_file.read()
            audio_blob = types.Blob(data=audio_content_bytes, mime_type="audio/wav")
            # For this demo, we'll ask the LLM to transcribe and then respond.
            # A more robust solution might transcribe first, then pass text to a second LLM call.
            current_input_parts.append({"text": "Audio input received. Please transcribe and then respond to the content of the audio."})
            current_input_parts.append({"inline_data": audio_blob})
        except Exception as e:
            logger.error(f"Error reading audio file {audio_file_path}: {e}")
            return {"text_response": "Error processing audio file.", "ui_message": None}
    else:
        logger.error("No input (text or audio) provided to get_chat_response.")
        return {"text_response": "Error: No input provided.", "ui_message": None}

    if current_input_parts:
        contents.append({"role": "user", "parts": current_input_parts})
        # Add to conversation_history for the next turn (simplified for this demo)
        # A more robust history would store the exact parts structure.
        if user_prompt:
            conversation_history.append({"role": "user", "content": user_prompt})
        elif audio_file_path:
             conversation_history.append({"role": "user", "content": "[Audio Input]"})


    # --- First LLM Call (to decide on function call or direct response) ---
    logger.info(f"Sending request to LLM. Content length: {len(contents)}")
    try:
        generation_config_with_tools = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[chat_tools],  # Tools included in the config
            max_output_tokens=2048,
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
    except Exception as e:
        logger.error(f"LLM generation error: {e}", exc_info=True)
        return {"text_response": f"Sorry, an error occurred with the AI model: {e}", "ui_message": None}

    if not response.candidates:
        logger.warning("No candidates in LLM response.")
        return {"text_response": "Sorry, I couldn't generate a response.", "ui_message": None}

    candidate = response.candidates[0]
    final_text_response_to_user = ""
    ui_update_message = None # For messages like "Log added!"

    # --- Process LLM Response: Text and Function Calls ---
    ui_update_messages = [] # To hold messages from multiple function calls
    model_turn_content_for_history = []
    function_calls_exist = any(hasattr(part, "function_call") and part.function_call for part in candidate.content.parts)

    # First, extract any initial text response from the LLM.
    initial_llm_text_parts = [part.text for part in candidate.content.parts if hasattr(part, "text") and part.text]
    final_text_response_to_user = " ".join(initial_llm_text_parts).strip()

    if final_text_response_to_user:
        model_turn_content_for_history.append({"text": final_text_response_to_user})

    # If there are function calls, process them.
    if function_calls_exist:
        # Iterate through all parts to find and execute all function calls
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                function_name = fc.name
                function_args = dict(fc.args)
                logger.info(f"LLM requested function call: {function_name} with args: {function_args}")

                # Add the function call to the history list for this turn
                model_turn_content_for_history.append({"function_call": fc})

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
                            if tasks:
                                formatted_tasks = ["These are your current open tasks:"]
                                for task in tasks:
                                    deadline_str = ""
                                    if task.get("deadline"):
                                        try:
                                            # Parse ISO string and format it
                                            deadline_dt = dt.datetime.fromisoformat(task["deadline"].replace("Z", "+00:00"))
                                            deadline_str = f", Deadline: {deadline_dt.strftime('%Y-%m-%d %H:%M')}"
                                        except (ValueError, TypeError):
                                            deadline_str = f", Deadline: {task.get('deadline')}" # Fallback
                                    formatted_tasks.append(
                                        f"- **Task {task['id']}**: {task['description']} (Status: {task['status']}{deadline_str})"
                                    )
                                ui_message_for_this_call = "\n".join(formatted_tasks)
                            else:
                                ui_message_for_this_call = "You have no open tasks."
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
        
        # Combine initial text with messages from all function calls
        if ui_update_messages:
            aggregated_ui_messages = "  \n".join(ui_update_messages)
            if final_text_response_to_user:
                final_text_response_to_user += f"  \n  \n{aggregated_ui_messages}"
            else:
                final_text_response_to_user = aggregated_ui_messages
        elif not final_text_response_to_user: # Fallback if no initial text and no UI messages
            final_text_response_to_user = "I've processed your request."

    # Add the complete model turn (text + all function calls) to history
    if model_turn_content_for_history:
        conversation_history.append({"role": "model", "content": model_turn_content_for_history})

    # Handle case where there was no function call and no text response
    if not function_calls_exist and not final_text_response_to_user:
        logger.warning("LLM response had no function calls and no text in parts.")
        final_text_response_to_user = "I'm not sure how to respond to that."
        conversation_history.append({"role": "model", "content": final_text_response_to_user})

    # The UI message for toast/notification can be the aggregation of all messages
    ui_update_message = "\n".join(ui_update_messages) if ui_update_messages else None

    logger.info(f"Final text response to user: {final_text_response_to_user}")
    if ui_update_message:
        logger.info(f"Aggregated UI update message: {ui_update_message}")

    return {"text_response": final_text_response_to_user, "ui_message": ui_update_message}
