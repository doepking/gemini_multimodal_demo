import os
import logging
import json
import datetime as dt
import pandas as pd
from google import genai
from google.genai import types
from dotenv import load_dotenv

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

# --- File Paths for Persistence ---
INPUT_LOG_FILE = "data/input_logs.csv"
BACKGROUND_INFO_FILE = "data/background_information.json"
TASKS_FILE = "data/tasks.csv"

# --- Data Persistence Functions ---
def _save_csv(df, file_path):
    """Saves a DataFrame to a CSV file."""
    df.to_csv(file_path, index=False)

def _load_csv(file_path):
    """Loads data from a CSV file, handling empty files."""
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        try:
            df = pd.read_csv(file_path)
            return df.to_dict('records')
        except pd.errors.EmptyDataError:
            logger.warning(f"CSV file is empty: {file_path}")
            return []
    return []

def _save_json(data, file_path):
    """Saves a dictionary to a JSON file."""
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def _load_json(file_path):
    """Loads data from a JSON file, handling empty files."""
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"JSON file is invalid or empty: {file_path}")
            return {}
    return {}

# --- Public Data Handling Functions ---
def load_input_log():
    return _load_csv(INPUT_LOG_FILE)

def save_input_log(data):
    _save_csv(pd.DataFrame(data), INPUT_LOG_FILE)

def load_tasks():
    return _load_csv(TASKS_FILE)

def save_tasks(data):
    _save_csv(pd.DataFrame(data), TASKS_FILE)

def load_background_info():
    return _load_json(BACKGROUND_INFO_FILE)

def save_background_info(data):
    _save_json(data, BACKGROUND_INFO_FILE)

# --- Core Implementation Functions (to be called by LLM-triggered functions) ---

def manage_tasks_and_persist_impl(action: str, session_state, task_description: str = None, task_id: int = None, task_status: str = None, deadline: str = None):
    """
    Core logic to manage tasks in st.session_state.tasks and save changes to CSV.
    """
    if 'tasks' not in session_state:
        session_state.tasks = []

    if action == "add":
        if not task_description:
            return {"status": "error", "message": "Task description is required to add a task."}
        
        task_deadline = None
        if deadline:
            try:
                # Try parsing as a full ISO datetime first
                dt.datetime.fromisoformat(deadline.replace("Z", "+00:00"))
                task_deadline = deadline
            except (ValueError, TypeError):
                 # If that fails, it might be a date-only string (e.g., from a date picker)
                try:
                    d = dt.datetime.strptime(deadline, "%Y-%m-%d").date()
                    # Combine the date with the current time to fulfill the "time now" aspect
                    now_time = dt.datetime.now(dt.timezone.utc).time()
                    task_deadline_dt = dt.datetime.combine(d, now_time, tzinfo=dt.timezone.utc)
                    task_deadline = task_deadline_dt.isoformat()
                except (ValueError, TypeError):
                    return {"status": "error", "message": "Invalid deadline format. Please use ISO format or YYYY-MM-DD."}

        new_task = {
            "id": len(session_state.tasks) + 1,
            "description": task_description,
            "status": "open",
            "deadline": task_deadline,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }
        session_state.tasks.append(new_task)
        save_tasks(session_state.tasks)
        logger.info(f"Task added: {new_task}")
        return {"status": "success", "message": f"Task added: '{task_description}'", "task": new_task}

    elif action == "update":
        if task_id is None or task_status is None:
            return {"status": "error", "message": "Task ID and status are required to update a task."}
        task_found = False
        for task in session_state.tasks:
            if task["id"] == task_id:
                task["status"] = task_status
                task_found = True
                save_tasks(session_state.tasks)
                logger.info(f"Task {task_id} updated to {task_status}")
                # More descriptive success message
                success_message = f"Okay, I've updated Task {task['id']}: '{task['description']}' to '{task_status}'."
                return {"status": "success", "message": success_message, "task": task}
        if not task_found:
            return {"status": "error", "message": f"Task with ID {task_id} not found."}

    elif action == "list":
        # Filter for open and in_progress tasks
        active_tasks = [task for task in session_state.tasks if task.get("status") in ["open", "in_progress"]]
        return {"status": "success", "tasks": active_tasks}

    else:
        return {"status": "error", "message": f"Unknown task action: {action}"}

def add_log_entry_and_persist_impl(text_input: str, category_suggestion: str = None, session_state=None):
    """
    Core logic to process and log text input to st.session_state.input_log and save to CSV.
    """
    if session_state is None:
        logger.error("Session state not provided to add_log_entry_and_persist_impl")
        return {"status": "error", "message": "Session state missing."}

    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "original_content": text_input,
        "content_preview": text_input[:100] + "..." if len(text_input) > 100 else text_input, # For display
        "category": category_suggestion if category_suggestion else "General Log",
        "details": "Processed by LLM function call." # Placeholder
    }
    if 'input_log' not in session_state:
        session_state.input_log = []
    session_state.input_log.append(log_entry)
    save_input_log(session_state.input_log)
    logger.info(f"Input logged: {log_entry['content_preview']}")
    return {"status": "success", "message": f"Log added: '{log_entry['content_preview']}'", "entry": log_entry}

def update_background_info_and_persist_impl(background_update_json: str, session_state=None):
    """
    Core logic to update background information in st.session_state.background_info and save to CSV.
    """
    if session_state is None:
        logger.error("Session state not provided to update_background_info_and_persist_impl")
        return {"status": "error", "message": "Session state missing."}

    if 'background_info' not in session_state:
        session_state.background_info = {}

    # For this demo, we'll primarily update/overwrite the 'user_provided_info' field
    # A more sophisticated version would parse background_update_text and merge into structured fields.
    try:
        # Attempt to parse as JSON if user provides structured data
        potential_json = json.loads(background_update_json)
        if isinstance(potential_json, dict):
            for key, value in potential_json.items():
                if key in session_state.background_info and isinstance(session_state.background_info[key], list) and isinstance(value, list):
                    # Extend lists if both are lists
                    session_state.background_info[key].extend(item for item in value if item not in session_state.background_info[key])
                elif key in session_state.background_info and isinstance(session_state.background_info[key], dict) and isinstance(value, dict):
                    # Merge dicts
                    session_state.background_info[key].update(value)
                else:
                    # Overwrite or add new key
                    session_state.background_info[key] = value
            message = "Background information merged from structured input."
        else: # Not a dict, treat as free text for 'user_provided_info'
            session_state.background_info["user_provided_info"] = background_update_json
            message = "Background information updated with free text."
    except json.JSONDecodeError:
        # If not JSON, assume it's free text for the general info field
        session_state.background_info["user_provided_info"] = background_update_json
        message = "Background information updated with free text."

    # Save the updated background info to CSV
    save_background_info(session_state.background_info)

    logger.info(f"Background info updated. Current: {session_state.background_info}")
    return {"status": "success", "message": message, "updated_info": session_state.background_info}


# --- App-Facing Functions ---
# These are called directly by the Streamlit UI. They handle persistence.

def add_log_entry_and_persist(text_input: str, session_state, category_suggestion: str = None):
    """App-facing function to add a log entry and persist it."""
    return add_log_entry_and_persist_impl(text_input, category_suggestion, session_state)

def update_background_info_and_persist(background_update_json: str, session_state):
    """App-facing function to update background info and persist it."""
    return update_background_info_and_persist_impl(background_update_json, session_state)

def add_task_and_persist(task_description: str, session_state, deadline: str = None):
    """App-facing function to add a new task and persist it."""
    return manage_tasks_and_persist_impl(action="add", session_state=session_state, task_description=task_description, deadline=deadline)

def update_tasks_and_persist(tasks_list: list, session_state):
    """App-facing function to update the entire task list and persist it."""
    session_state.tasks = tasks_list
    save_tasks(session_state.tasks)
    return {"status": "success", "message": "Tasks updated successfully."}

def update_input_log_and_persist(log_list: list, session_state):
    """App-facing function to update the entire input log and persist it."""
    session_state.input_log = log_list
    save_input_log(session_state.input_log)
    return {"status": "success", "message": "Input log updated successfully."}


# --- Chat Functions ---
def start_new_chat():
    """Starts a new chat session."""
    return []  # Initialize an empty conversation history

def get_chat_response(conversation_history, session_state, user_prompt=None, audio_file_path=None):
    """Gets a response from the Gemini model, handling text, audio, and function calls."""
    current_bg_info_str = json.dumps(session_state.get('background_info', {}), indent=2)
    recent_logs_preview = [log.get('content_preview', 'Log entry') for log in session_state.get('input_log', [])[-5:]] # Last 5 logs
    recent_logs_str = "\n- ".join(recent_logs_preview) if recent_logs_preview else "No recent logs."
    tasks_preview = [f"ID: {task['id']}, Desc: {task['description']}, Status: {task['status']}" for task in session_state.get('tasks', [])]
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
                        category_suggestion=function_args.get("category_suggestion"),
                        session_state=session_state
                    )
                    function_response_content = result
                    if result.get("status") == "success":
                        ui_message_for_this_call = result.get("message")

                elif function_name == "update_background_info":
                    result = update_background_info_and_persist_impl(
                        background_update_json=function_args.get("background_update_json"),
                        session_state=session_state
                    )
                    function_response_content = result
                    if result.get("status") == "success":
                        ui_message_for_this_call = result.get("message")

                elif function_name == "manage_tasks":
                    result = manage_tasks_and_persist_impl(
                        action=function_args.get("action"),
                        session_state=session_state,
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
            aggregated_ui_messages = "\n\n".join(ui_update_messages)
            if final_text_response_to_user:
                final_text_response_to_user += f"\n\n{aggregated_ui_messages}"
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
