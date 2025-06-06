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
MODEL_NAME = "gemini-2.0-flash-exp"

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
    """Loads data from a CSV file."""
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        return df.to_dict('records')
    return []

def _save_json(data, file_path):
    """Saves a dictionary to a JSON file."""
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def _load_json(file_path):
    """Loads data from a JSON file."""
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
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

def manage_tasks_and_persist_impl(action: str, session_state, task_description: str = None, task_id: int = None, task_status: str = None):
    """
    Core logic to manage tasks in st.session_state.tasks and save changes to CSV.
    """
    if 'tasks' not in session_state:
        session_state.tasks = []

    if action == "add":
        if not task_description:
            return {"status": "error", "message": "Task description is required to add a task."}
        new_task = {
            "id": len(session_state.tasks) + 1,
            "description": task_description,
            "status": "open",
            "created_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                return {"status": "success", "message": f"Task {task_id} updated to {task_status}", "task": task}
        if not task_found:
            return {"status": "error", "message": f"Task with ID {task_id} not found."}

    elif action == "list":
        return {"status": "success", "tasks": session_state.tasks}

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

def add_task_and_persist(task_description: str, session_state):
    """App-facing function to add a new task and persist it."""
    return manage_tasks_and_persist_impl(action="add", session_state=session_state, task_description=task_description)

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

    system_prompt = f"""
    You are a helpful AI assistant. Your user is interacting with you through a multimodal chat interface.
    You can process text and audio. You also have access to tools to log information and update user background.

    CURRENT USER BACKGROUND INFO (stored in session):
    ```json
    {current_bg_info_str}
    ```
    (Use the `update_background_info` function if the user provides personal details, goals, values, or preferences.
    When calling this function, provide a `background_update_json` argument which is a JSON string containing the extracted information to be updated, structured according to the schema below.)
    Schema for background info (as a loose guideline, when the user provides updates):
    ```json
    {BACKGROUND_INFO_SCHEMA_EXAMPLE}
    ```

    RECENT USER LOGS (last 5, stored in session):
    - {recent_logs_str}
    (Use the `add_log_entry` function if the user makes a statement that should be logged.)

    CURRENT TASKS (stored in session):
    - {tasks_str}
    (Use the `manage_tasks` function to add, update, or list tasks.)

    FUNCTION CALLING RULES:
    1.  If the user provides a general statement, observation, thought, or event they want to record,
        call `add_log_entry` with their `text_input`. You can also suggest a `category_suggestion`.
        Example: User says "The weather is nice today." -> Call `add_log_entry` with text_input="The weather is nice today.", category_suggestion="Observation".
    2.  If the user explicitly provides or modifies their personal details, goals, values, or preferences,
        interpret their free-form text, extract the relevant information, structure it as a JSON string according to the schema,
        and call `update_background_info` with the `background_update_json` argument containing this JSON string.
        The JSON string you provide for `background_update_json` must be valid. If string values within your generated JSON contain special characters (like quotes, backslashes, newlines), ensure they are properly escaped (e.g., \" for quotes, \\\\ for backslashes, \\n for newlines).
        Example: User says "My main goal now is to exercise more, and I live in Berlin." -> Call `update_background_info` with background_update_json='{{"goals": ["Exercise more"], "user_profile": {{"location": {{"city": "Berlin"}}}}}}'.
        Example with escaping: User says "My note is about \"quotes\" and backslashes \\." -> Call `update_background_info` with background_update_json='{{"user_provided_info": "My note is about \\\"quotes\\\" and backslashes \\\\."}}'.
    3.  If the user wants to add, update, or see their tasks, call `manage_tasks`.
        - To add: `action='add'`, `task_description='...'`
        - To update: `action='update'`, `task_id=...`, `task_status='...'`
        - To list: `action='list'`
    4.  You can call multiple functions if appropriate. For example, if a user says "I learned that my value is 'kindness' and I want to log that I had a good day", you could call both functions.
    5.  After a function call, I will provide you with the result. You should then formulate a natural language response to the user based on that result and the conversation context.
    6.  If no function call is needed, respond directly to the user's query or statement.
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

    # Check for function calls
    if candidate.content.parts and candidate.content.parts[0].function_call:
        fc = candidate.content.parts[0].function_call
        function_name = fc.name
        function_args = dict(fc.args)
        logger.info(f"LLM requested function call: {function_name} with args: {function_args}")

        # Extract any text parts from the LLM's response that decided to call a function
        initial_llm_text_parts = []
        for part in candidate.content.parts:
            if hasattr(part, "text") and part.text:
                initial_llm_text_parts.append(part.text)
        
        final_text_response_to_user = " ".join(initial_llm_text_parts).strip()

        # Add LLM's intent to call function to history
        # The content for the history should represent the model's turn accurately.
        # If the model's turn included text and a function call, both should be there.
        model_turn_content_for_history = []
        if final_text_response_to_user:
             model_turn_content_for_history.append({"text": final_text_response_to_user})
        model_turn_content_for_history.append({"function_call": fc})
        conversation_history.append({"role": "model", "content": model_turn_content_for_history})

        function_response_content = {}
        if function_name == "add_log_entry":
            result = add_log_entry_and_persist_impl(
                text_input=function_args.get("text_input"),
                category_suggestion=function_args.get("category_suggestion"),
                session_state=session_state
            )
            function_response_content = result
            if result.get("status") == "success":
                ui_update_message = result.get("message") # This is for the UI toast/message

        elif function_name == "update_background_info":
            result = update_background_info_and_persist_impl(
                background_update_json=function_args.get("background_update_json"), # Corrected param name
                session_state=session_state
            )
            function_response_content = result
            if result.get("status") == "success":
                ui_update_message = result.get("message") # This is for the UI toast/message
        elif function_name == "manage_tasks":
            result = manage_tasks_and_persist_impl(
                action=function_args.get("action"),
                session_state=session_state,
                task_description=function_args.get("task_description"),
                task_id=function_args.get("task_id"),
                task_status=function_args.get("task_status")
            )
            function_response_content = result
            if result.get("status") == "success":
                if result.get("tasks"):
                     ui_update_message = f"Current tasks: {json.dumps(result.get('tasks'))}"
                else:
                    ui_update_message = result.get("message")
        else:
            logger.warning(f"LLM called unknown function: {function_name}")
            function_response_content = {"status": "error", "message": f"Unknown function: {function_name}"}
            ui_update_message = f"Error: Unknown function '{function_name}' called."

        # Add function execution result to history (for LLM's context in future turns if needed)
        conversation_history.append({
            "role": "function", 
            "content": [{"function_response": {"name": function_name, "response": function_response_content}}]
        })

        # Construct final response to user by combining initial LLM text and function UI message
        if ui_update_message:
            if final_text_response_to_user: # If LLM gave some initial text
                final_text_response_to_user += f"\n\n{ui_update_message}"
            else: # If LLM only called a function without preceding text
                final_text_response_to_user = ui_update_message
        elif not final_text_response_to_user: # Fallback if no initial text and no UI message
            final_text_response_to_user = "I've processed that."
            
    else: # No function call, direct text response from LLM
        if candidate.content.parts:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    final_text_response_to_user += part.text
            conversation_history.append({"role": "model", "content": final_text_response_to_user})
        else:
            logger.warning("LLM response had no parts or no text in parts.")
            final_text_response_to_user = "I'm not sure how to respond to that."
            conversation_history.append({"role": "model", "content": final_text_response_to_user})

    # Ensure there's always some response text
    if not final_text_response_to_user.strip():
        final_text_response_to_user = "Processed."
        # If history already has the model turn from function call path, don't add again.
        # Only add if it was a direct text response path that somehow ended up empty.
        if not (candidate.content.parts and candidate.content.parts[0].function_call):
             conversation_history.append({"role": "model", "content": final_text_response_to_user})


    logger.info(f"Final text response to user: {final_text_response_to_user}")
    if ui_update_message:
        logger.info(f"UI update message: {ui_update_message}")

    return {"text_response": final_text_response_to_user, "ui_message": ui_update_message}
