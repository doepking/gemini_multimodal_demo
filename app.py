import os
import tempfile
import json
import streamlit as st
from audiorecorder import audiorecorder
import datetime as dt
import pandas as pd

from utils import (
    get_chat_response,
    start_new_chat,
    add_log_entry_and_persist,
    update_background_info_and_persist,
    add_task_and_persist,
    update_tasks_and_persist,
    update_input_log_and_persist,
    load_input_log,
    load_tasks,
    load_background_info,
)

# --- Page Configuration ---
st.set_page_config(
    page_title="Gemini Multimodal Demo",
    page_icon=":speech_balloon:",
    layout="centered"
)

# --- Initialize Session State ---
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = start_new_chat()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_audio_duration" not in st.session_state:
    st.session_state.last_audio_duration = -1.0
    st.session_state.audio_recordings = []
    st.session_state.counter = 0 # Used for unique keys for recorder/input

# --- Initialize Session State from Files ---
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = start_new_chat()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_audio_duration" not in st.session_state:
    st.session_state.last_audio_duration = -1.0
    st.session_state.audio_recordings = []
    st.session_state.counter = 0 # Used for unique keys for recorder/input

# Initialize session state for input log, background info, and tasks from files
if 'input_log' not in st.session_state:
    st.session_state.input_log = load_input_log()
if 'background_info' not in st.session_state:
    st.session_state.background_info = load_background_info()
if 'tasks' not in st.session_state:
    st.session_state.tasks = load_tasks()
if 'edit_background' not in st.session_state:
    st.session_state.edit_background = False

# --- Main App Content ---
st.title("Life Tracker with Gemini AI")
st.write(
    "This is an AI-powered assistant to help you track your thoughts, tasks, and background information.  \n"
    "Interact with the Gemini model via text or audio, and manage your data across the different tabs.  \n"
    "All data is editable and is persisted locally."
)

tab1, tab2, tab3, tab4 = st.tabs(["Chat", "Input Log", "Tasks", "Background Info"])

with tab1:
    st.subheader("Hey there 👋, what's on your mind?")
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "audio" in message:
                st.audio(message["audio"], format="audio/wav")

    # Add a placeholder for the input area
    input_placeholder = st.empty()

    with input_placeholder.container():
        # Create columns for static input area
        col1, col2 = st.columns([3, 1])

        with col2:
            # Audio recorder
            audio = audiorecorder(
                start_prompt="Start Recording",
                stop_prompt="Stop Recording",
                key=f"audio_recorder_{st.session_state.counter}"
            )

        with col1:
            # Chat input
            prompt = st.chat_input("Enter your message here", key=f"chat_input_{st.session_state.counter}")

    # Audio processing logic
    if audio is not None and audio.duration_seconds > 0 \
        and audio.duration_seconds != st.session_state.last_audio_duration:
        st.session_state.last_audio_duration = audio.duration_seconds
        st.session_state.counter += 1

        audio_bytes = audio.export().read()
        st.session_state.audio_recordings.append(audio_bytes)

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
                audio.export(tmpfile.name, format="wav")
                tmp_audio_path = tmpfile.name

            st.session_state.messages.append({
                "role": "user",
                "content": f"Audio input recorded ({audio.duration_seconds:.2f}s).",
                "audio": audio_bytes
            })

            # Remove the input area
            input_placeholder.empty()

            # Display audio message
            with st.chat_message("user"):
                st.markdown(f"Audio input recorded ({audio.duration_seconds:.2f}s).")
                st.audio(audio_bytes, format="audio/wav")

            with st.spinner("Thinking..."):
                # Pass session state to get_chat_response for function calling
                response_data = get_chat_response(
                    st.session_state.conversation_history,
                    st.session_state,
                    audio_file_path=tmp_audio_path
                )
            
            # Response_data might be a string or a dict if function calling is involved
            if isinstance(response_data, dict):
                assistant_response = response_data.get("text_response", "Function call processed.")
                # Further handling for UI updates based on function calls can be added here
            else:
                assistant_response = response_data

            st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            st.rerun()

        finally:
            if 'tmp_audio_path' in locals() and os.path.exists(tmp_audio_path):
                os.unlink(tmp_audio_path)

    # Text input logic
    elif prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        input_placeholder.empty()

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("Thinking..."):
            # Pass session state to get_chat_response for function calling
            response_data = get_chat_response(
                st.session_state.conversation_history,
                st.session_state, # Pass the whole session state
                user_prompt=prompt
            )

        if isinstance(response_data, dict):
            assistant_response = response_data.get("text_response", "Function call processed.")
            # Further handling for UI updates based on function calls can be added here
        else:
            assistant_response = response_data

        st.session_state.messages.append({"role": "assistant", "content": assistant_response})
        st.session_state.counter += 1
        st.rerun()

with tab2:
    st.subheader("Logged Inputs")
    if not st.session_state.input_log:
        st.info("No inputs logged yet.")
    else:
        # Sort logs by timestamp descending
        sorted_logs = sorted(st.session_state.input_log, key=lambda x: x.get('timestamp', ''), reverse=True)

        # Use a data editor to allow for changes
        edited_logs_df = st.data_editor(
            pd.DataFrame(sorted_logs),
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="data_editor_logs",
            column_config={
                "timestamp": st.column_config.Column("Timestamp", disabled=True),
                "original_content": st.column_config.Column("Content"),
                "category": st.column_config.Column("Category"),
                "details": st.column_config.Column("Details"),
                "content_preview": None, # Hide the preview column
            },
            # Reorder columns for better display
            column_order=["timestamp", "original_content", "category", "details"]
        )

        if st.button("Save Log Changes"):
            updated_logs = edited_logs_df.to_dict('records')
            result = update_input_log_and_persist(updated_logs, st.session_state)
            st.success(result.get("message", "Logs updated!"))
            st.rerun()

    with st.form("input_log_form"):
        new_log_content = st.text_area("Enter your log:", height=100)
        submit_log = st.form_submit_button("Add to Log")

        if submit_log and new_log_content:
            result = add_log_entry_and_persist(new_log_content, st.session_state)
            st.success(result.get("message", "Log added successfully!"))
            st.rerun()

with tab3:
    st.subheader("Manage Tasks")
    if not st.session_state.tasks:
        st.info("No tasks yet. Add one below or ask the chat assistant to add one for you!")
    else:
        # Sort tasks by creation date descending
        sorted_tasks = sorted(st.session_state.tasks, key=lambda x: x.get('created_at', ''), reverse=True)
        # Convert list of dicts to DataFrame for editing
        df_tasks = pd.DataFrame(sorted_tasks)
        # Ensure columns are in a consistent order
        df_tasks = df_tasks[["id", "description", "status", "deadline", "created_at"]]
        df_tasks["deadline"] = pd.to_datetime(df_tasks["deadline"])
        df_tasks.rename(columns={"id": "ID", "description": "Description", "status": "Status", "deadline": "Deadline", "created_at": "Created At"}, inplace=True)

        edited_tasks_df = st.data_editor(
            df_tasks,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="data_editor_tasks",
            column_config={
                "ID": st.column_config.Column("ID", disabled=True),
                "Created At": st.column_config.Column("Created At", disabled=True),
                "Deadline": st.column_config.DatetimeColumn(
                    "Deadline",
                    format="YYYY-MM-DD HH:mm:ss",
                    required=True,
                ),
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    options=['open', 'in_progress', 'completed'],
                    required=True
                ),
            },
        )

        if st.button("Save Task Changes"):
            # Convert deadline back to ISO string before saving
            edited_tasks_df['Deadline'] = edited_tasks_df['Deadline'].apply(lambda x: x.isoformat())
            updated_tasks = edited_tasks_df.rename(columns={"ID": "id", "Description": "description", "Status": "status", "Deadline": "deadline", "Created At": "created_at"}).to_dict('records')
            result = update_tasks_and_persist(updated_tasks, st.session_state)
            st.success(result.get("message", "Task changes saved!"))
            st.rerun()


    with st.form("new_task_form"):
        st.subheader("Add a New Task")
        new_task_description = st.text_input("Task Description")
        
        # Separate date and time inputs
        col1, col2 = st.columns(2)
        with col1:
            new_task_date = st.date_input("Deadline Date", value=dt.date.today() + dt.timedelta(days=7))
        with col2:
            new_task_time = st.time_input("Deadline Time", value=dt.time(12, 00))

        submit_new_task = st.form_submit_button("Add Task")

        if submit_new_task and new_task_description:
            # Combine date and time into a single datetime object
            new_task_deadline = dt.datetime.combine(new_task_date, new_task_time)
            # Make it timezone-aware (assuming UTC for consistency)
            new_task_deadline_utc = new_task_deadline.astimezone(dt.timezone.utc)
            
            deadline_str = new_task_deadline_utc.isoformat()
            result = add_task_and_persist(new_task_description, st.session_state, deadline=deadline_str)
            st.success(result.get("message", f"Task '{new_task_description}' added!"))
            st.rerun()


with tab4:
    st.subheader("Current Background Information")

    def toggle_edit_mode():
        st.session_state.edit_background = not st.session_state.edit_background

    if st.session_state.edit_background:
        with st.form("edit_background_form"):
            background_text = st.text_area(
                "Edit Background Information (JSON format):",
                value=json.dumps(st.session_state.background_info, indent=2),
                height=300,
                key="background_info_editor"
            )
            submitted = st.form_submit_button("Save Changes")
            if submitted:
                try:
                    # The function expects a JSON string, so this works perfectly
                    result = update_background_info_and_persist(background_text, st.session_state)
                    st.success(result.get("message", "Background information updated!"))
                    toggle_edit_mode() # Exit edit mode on success
                    st.rerun()
                except json.JSONDecodeError:
                    st.error("Invalid JSON format. Please correct it and try again.")
                except Exception as e:
                    st.error(f"An error occurred: {e}")
        
        if st.button("Cancel"):
            toggle_edit_mode()
            st.rerun()
    else:
        if not st.session_state.background_info:
            st.info("No background information provided yet. The LLM can add info via chat.")
        else:
            st.json(st.session_state.background_info, expanded=True)
            if st.button("Edit Background Info"):
                toggle_edit_mode()
                st.rerun()
