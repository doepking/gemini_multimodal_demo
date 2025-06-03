import os
import logging
import json # Added
import datetime as dt # Added
from google import genai
from google.genai import types
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__) # Use a logger

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

# --- Function Declarations for LLM ---
add_log_entry_func = types.Tool(
    function_declarations=[
        {
            "name": "process_text_input_for_log",
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
            "name": "update_background_info_in_session",
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
    ]
)

# --- Core Implementation Functions (to be called by LLM-triggered functions) ---

def process_text_input_for_log_impl(text_input: str, category_suggestion: str = None, session_state=None):
    """
    Processes and logs text input to st.session_state.input_log.
    (Simplified version for session state)
    """
    if session_state is None:
        logger.error("Session state not provided to process_text_input_for_log_impl")
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
    logger.info(f"Input logged: {log_entry['content_preview']}")
    return {"status": "success", "message": f"Log added: '{log_entry['content_preview']}'", "entry": log_entry}

def update_background_info_in_session_impl(background_update_text: str, session_state=None):
    """
    Updates background information in st.session_state.background_info.
    (Simplified version for session state - attempts a basic merge or overwrite for 'user_provided_info')
    """
    if session_state is None:
        logger.error("Session state not provided to update_background_info_in_session_impl")
        return {"status": "error", "message": "Session state missing."}

    if 'background_info' not in session_state:
        session_state.background_info = {}

    # For this demo, we'll primarily update/overwrite the 'user_provided_info' field
    # A more sophisticated version would parse background_update_text and merge into structured fields.
    try:
        # Attempt to parse as JSON if user provides structured data
        potential_json = json.loads(background_update_text)
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
            session_state.background_info["user_provided_info"] = background_update_text
            message = "Background information updated with free text."
    except json.JSONDecodeError:
        # If not JSON, assume it's free text for the general info field
        session_state.background_info["user_provided_info"] = background_update_text
        message = "Background information updated with free text."

    logger.info(f"Background info updated. Current: {session_state.background_info}")
    return {"status": "success", "message": message, "updated_info": session_state.background_info}


# --- Placeholder functions (imported by app.py) ---
# These will be called by the Streamlit app and will then call the _impl versions.
# This structure allows for future expansion if needed (e.g., async calls, more complex logic).

def process_text_input_for_log(text_input: str, session_state, category_suggestion: str = None):
    """App-facing function to log text input."""
    # For now, directly calls the implementation.
    # In a more complex app, this might involve more steps or async handling.
    return process_text_input_for_log_impl(text_input, category_suggestion, session_state)

def update_background_info_in_session(background_update_json: str, session_state): # Changed parameter name
    """App-facing function to update background info."""
    # For now, directly calls the implementation.
    return update_background_info_in_session_impl(background_update_json, session_state) # Changed parameter name


# --- Chat Functions ---
def start_new_chat():
    """Starts a new chat session."""
    return []  # Initialize an empty conversation history

def get_chat_response(conversation_history, session_state, user_prompt=None, audio_file_path=None):
    """
    Gets a response from the Gemini model, handling text, audio, and function calls.
    """
    current_bg_info_str = json.dumps(session_state.get('background_info', {}), indent=2)
    recent_logs_preview = [log.get('content_preview', 'Log entry') for log in session_state.get('input_log', [])[-5:]] # Last 5 logs
    recent_logs_str = "\n- ".join(recent_logs_preview) if recent_logs_preview else "No recent logs."

    system_prompt = f"""
    You are a helpful AI assistant. Your user is interacting with you through a multimodal chat interface.
    You can process text and audio. You also have access to tools to log information and update user background.

    CURRENT USER BACKGROUND INFO (stored in session):
    ```json
    {current_bg_info_str}
    ```
    (Use the `update_background_info_in_session` function if the user provides personal details, goals, values, or preferences.
    When calling this function, provide a `background_update_json` argument which is a JSON string containing the extracted information to be updated, structured according to the schema below.)
    Schema for background info (as a loose guideline, when the user provides updates):
    ```json
    {BACKGROUND_INFO_SCHEMA_EXAMPLE}
    ```

    RECENT USER LOGS (last 5, stored in session):
    - {recent_logs_str}
    (Use the `process_text_input_for_log` function if the user makes a statement that should be logged.)

    FUNCTION CALLING RULES:
    1.  If the user provides a general statement, observation, thought, or event they want to record,
        call `process_text_input_for_log` with their `text_input`. You can also suggest a `category_suggestion`.
        Example: User says "The weather is nice today." -> Call `process_text_input_for_log` with text_input="The weather is nice today.", category_suggestion="Observation".
    2.  If the user explicitly provides or modifies their personal details, goals, values, or preferences,
        interpret their free-form text, extract the relevant information, structure it as a JSON string according to the schema,
        and call `update_background_info_in_session` with the `background_update_json` argument containing this JSON string.
        The JSON string you provide for `background_update_json` must be valid. If string values within your generated JSON contain special characters (like quotes, backslashes, newlines), ensure they are properly escaped (e.g., \" for quotes, \\\\ for backslashes, \\n for newlines).
        Example: User says "My main goal now is to exercise more, and I live in Berlin." -> Call `update_background_info_in_session` with background_update_json='{"goals": ["Exercise more"], "user_profile": {"location": {"city": "Berlin"}}}'.
        Example with escaping: User says "My note is about \"quotes\" and backslashes \\." -> Call `update_background_info_in_session` with background_update_json='{"user_provided_info": "My note is about \\\"quotes\\\" and backslashes \\\\."}'.
    3.  You can call multiple functions if appropriate. For example, if a user says "I learned that my value is 'kindness' and I want to log that I had a good day", you could call both functions.
    4.  After a function call, I will provide you with the result. You should then formulate a natural language response to the user based on that result and the conversation context.
    5.  If no function call is needed, respond directly to the user's query or statement.
    """

    contents = [{"role": "system", "parts": [{"text": system_prompt}]}] # Start with system prompt

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
        response = client.models.generate_content(
            model=MODEL_NAME, # Ensure this model supports function calling
            contents=contents,
            tools=[chat_tools], # Pass the defined tools
            config=types.GenerateContentConfig(
                max_output_tokens=2048,
                temperature=0.7, # Adjust as needed
                safety_settings=[
                    types.SafetySetting(category=s["category"], threshold=s["threshold"])
                    for s in safety_settings
                ],
            ),
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

        # Add LLM's intent to call function to history
        conversation_history.append({"role": "model", "content": [{"function_call": fc}]})


        function_response_content = {}
        if function_name == "process_text_input_for_log":
            result = process_text_input_for_log_impl(
                text_input=function_args.get("text_input"),
                category_suggestion=function_args.get("category_suggestion"),
                session_state=session_state
            )
            function_response_content = result
            if result.get("status") == "success":
                ui_update_message = result.get("message")

        elif function_name == "update_background_info_in_session":
            result = update_background_info_in_session_impl(
                background_update_json=function_args.get("background_update_json"),
                session_state=session_state
            )
            function_response_content = result
            if result.get("status") == "success":
                ui_update_message = result.get("message")
        else:
            logger.warning(f"LLM called unknown function: {function_name}")
            function_response_content = {"status": "error", "message": f"Unknown function: {function_name}"}

        # --- Second LLM Call (to get natural language response after function execution) ---
        # Add function execution result to contents for the next LLM call
        contents.append({
            "role": "model", # LLM's turn that decided to call function
            "parts": [{"function_call": fc}] 
        })
        contents.append({
            "role": "function", # Function's turn providing the result
            "parts": [{"function_response": {"name": function_name, "response": function_response_content}}]
        })
        # Add function response to history
        conversation_history.append({"role": "function", "content": [{"function_response": {"name": function_name, "response": function_response_content}}]})


        logger.info("Sending request to LLM again with function response.")
        try:
            response_after_fc = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents, # Send updated contents
                # No tools needed here, expecting a text response
                config=types.GenerateContentConfig(
                    max_output_tokens=1024, # Shorter response expected
                    temperature=0.7,
                    safety_settings=[
                        types.SafetySetting(category=s["category"], threshold=s["threshold"])
                        for s in safety_settings
                    ],
                ),
            )
            if response_after_fc.candidates and response_after_fc.candidates[0].content.parts:
                for part in response_after_fc.candidates[0].content.parts:
                    if hasattr(part, "text") and part.text:
                        final_text_response_to_user += part.text
            else:
                final_text_response_to_user = "Okay, I've processed that." # Fallback
        except Exception as e_fc_resp:
            logger.error(f"LLM error after function call: {e_fc_resp}", exc_info=True)
            final_text_response_to_user = f"I processed the function, but had trouble forming a follow-up: {e_fc_resp}"

    else: # No function call, direct text response from LLM
        if candidate.content.parts:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    final_text_response_to_user += part.text
        else:
            logger.warning("LLM response had no parts or no text in parts.")
            final_text_response_to_user = "I'm not sure how to respond to that."

    if not final_text_response_to_user.strip(): # If LLM returns empty string after function call
        final_text_response_to_user = ui_update_message if ui_update_message else "Processed."

    # Add final assistant response to history
    conversation_history.append({"role": "model", "content": final_text_response_to_user})

    logger.info(f"Final text response to user: {final_text_response_to_user}")
    if ui_update_message:
        logger.info(f"UI update message: {ui_update_message}")

    return {"text_response": final_text_response_to_user, "ui_message": ui_update_message}
