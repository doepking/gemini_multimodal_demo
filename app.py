import os
import tempfile
import streamlit as st
from audiorecorder import audiorecorder
import datetime as dt
import pandas as pd

from utils import get_chat_response, start_new_chat, process_text_input_for_log, update_background_info_in_session

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

# Initialize session state for input log and background info
if 'input_log' not in st.session_state:
    st.session_state.input_log = [] # List of dictionaries
if 'background_info' not in st.session_state:
    st.session_state.background_info = {} # Dictionary
if 'tasks' not in st.session_state:
    st.session_state.tasks = [] # List of task dictionaries

# --- Main App Content ---
st.title("Multimodal AI Chat with Gemini")
st.write(
    "This demo showcases audio and text chat with Google's Gemini model, "
    "along with input logging and background information management using session state."
)

tab1, tab2, tab3, tab4 = st.tabs(["Chat", "Input Log", "Tasks", "Background Info"])

with tab1:
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
        # Display logs in a more structured way, e.g., using pandas DataFrame
        log_data_for_df = []
        for i, entry in enumerate(reversed(st.session_state.input_log)): # Show newest first
            log_data_for_df.append({
                "Timestamp": entry.get("timestamp", "N/A"),
                "Content": entry.get("original_content", entry.get("content", "N/A")),
                "Category": entry.get("category", "N/A"),
                "Details": entry.get("details", "N/A")
            })
        df_logs = pd.DataFrame(log_data_for_df)
        st.dataframe(df_logs, use_container_width=True)

    with st.form("input_log_form"):
        new_log_content = st.text_area("Enter your log:", height=100)
        submit_log = st.form_submit_button("Add to Log")

        if submit_log and new_log_content:
            processed_entry = process_text_input_for_log(new_log_content, st.session_state)
            st.session_state.input_log.append(processed_entry)
            st.success(f"Log added: '{processed_entry.get('content_preview', 'Entry')}'")

with tab3:
    st.header("Task Management")
    st.write("Manage your tasks directly here.")

    if not st.session_state.tasks:
        st.info("No tasks yet. Add one below or ask the chat assistant to add one for you!")
        df_tasks = pd.DataFrame(columns=["ID", "Description", "Status", "Created At"])
    else:
        # Convert list of dicts to DataFrame for editing
        df_tasks = pd.DataFrame(st.session_state.tasks)
        # Ensure columns are in a consistent order
        df_tasks = df_tasks[["id", "description", "status", "created_at"]]
        df_tasks.rename(columns={"id": "ID", "description": "Description", "status": "Status", "created_at": "Created At"}, inplace=True)


    edited_tasks_df = st.data_editor(
        df_tasks,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key="data_editor_tasks",
        column_config={
            "ID": st.column_config.Column("ID", disabled=True),
            "Created At": st.column_config.Column("Created At", disabled=True),
            "Status": st.column_config.SelectboxColumn(
                "Status",
                options=['open', 'in_progress', 'completed'],
                required=True
            ),
        },
    )

    if st.button("Save Task Changes"):
        # Logic to update session state from the edited dataframe
        updated_tasks = edited_tasks_df.rename(columns={"ID": "id", "Description": "description", "Status": "status", "Created At": "created_at"}).to_dict('records')
        
        # A simple overwrite is easiest for session state. For a DB, you'd do updates/deletes.
        st.session_state.tasks = updated_tasks
        st.success("Task changes saved to session!")
        st.rerun()


    with st.form("new_task_form"):
        st.subheader("Add a New Task")
        new_task_description = st.text_input("Task Description")
        submit_new_task = st.form_submit_button("Add Task")

        if submit_new_task and new_task_description:
            new_task = {
                "id": len(st.session_state.tasks) + 1,
                "description": new_task_description,
                "status": "open",
                "created_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            st.session_state.tasks.append(new_task)
            st.success(f"Task '{new_task_description}' added!")
            st.rerun()


with tab4:
    # Display current background info (simple display for now)
    st.subheader("Current Background Information")
    if not st.session_state.background_info:
        st.info("No background information provided yet.")
    else:
        # For complex dicts, st.json might be better, or iterate and display
        st.json(st.session_state.background_info, expanded=False)

    with st.form("background_info_form"):
        st.write("Enter or update your background information (e.g., goals, values, preferences). Use key-value pairs if desired, or free text.")
        # Using a text area for simplicity; could be structured fields or st.data_editor
        background_text = st.text_area(
            "Your background information:",
            value=st.session_state.background_info.get("user_provided_info", ""), # Pre-fill if exists
            height=150
        )
        submit_background = st.form_submit_button("Save Background Info")

        if submit_background and background_text:
            update_background_info_in_session(background_text, st.session_state)
            st.success("Background information updated!")
