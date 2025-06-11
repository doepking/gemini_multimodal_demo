import os
import tempfile
import json
import streamlit as st
from audiorecorder import audiorecorder
import datetime as dt
import pandas as pd
import requests
import base64

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
from newsletter import send_newsletter_for_user

# --- Page Configuration ---
st.set_page_config(
    page_title="Gemini Multimodal Demo",
    page_icon=":speech_balloon:",
    layout="wide"
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

# --- Helper Functions ---
def generate_calendar_html(today, dates_with_inputs):
    """Generates a more UI-friendly HTML for the activity calendar for the last 30 days."""
    
    # --- Calendar Styling ---
    style = """
    <style>
        .calendar-container {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            padding: 10px;
            border-radius: 8px;
            background-color: #F8F9FA;
            border: 1px solid #E1E4E8;
        }
        .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 4px;
            margin-bottom: 10px;
        }
        .calendar-day-box {
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid rgba(0,0,0,0.05);
            transition: transform 0.2s ease-in-out;
        }
        .calendar-day-box:hover {
            transform: scale(1.1);
        }
        .calendar-legend {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            font-size: 12px;
            color: #586069;
        }
        .legend-item {
            display: flex;
            align-items: center;
            margin-left: 15px;
        }
        .legend-color-box {
            width: 15px;
            height: 15px;
            border-radius: 3px;
            margin-right: 5px;
        }
    </style>
    """

    # Start of the week for today
    start_of_week = today - dt.timedelta(days=today.weekday())
    # Go back 4 full weeks from the start of this week to get 5 weeks in total
    start_date = start_of_week - dt.timedelta(weeks=4)

    calendar_html = style + "<div class='calendar-container'><div class='calendar-grid'>"

    for i in range(35):
        day = start_date + dt.timedelta(days=i)
        
        if day > today:
            calendar_html += "<div class='calendar-day-box' style='background-color: transparent; border: none;'></div>"
            continue

        date_str = day.strftime("%Y-%m-%d")
        count = dates_with_inputs.get(date_str, 0)

        if count == 0:
            day_color = "#EBEDF0" # Light Grey
        elif 1 <= count <= 2:
            day_color = "#9BE9A8" # Light Green
        elif 3 <= count <= 4:
            day_color = "#40C463" # Medium Green
        elif 5 <= count <= 6:
            day_color = "#30A14E" # Dark Green
        else:
            day_color = "#216E39" # Darkest Green
        
        title_text = f"{count} contribution{'s' if count != 1 else ''} on {day.strftime('%b %d, %Y')}"
        calendar_html += f"<div class='calendar-day-box' title='{title_text}' style='background-color: {day_color};'></div>"
    
    calendar_html += "</div>"

    # Legend
    calendar_html += """
    <div class='calendar-legend'>
        <span>Less</span>
        <div class='legend-item'>
            <div class='legend-color-box' style='background-color: #EBEDF0;'></div>
        </div>
        <div class='legend-item'>
            <div class='legend-color-box' style='background-color: #9BE9A8;'></div>
        </div>
        <div class='legend-item'>
            <div class='legend-color-box' style='background-color: #40C463;'></div>
        </div>
        <div class='legend-item'>
            <div class='legend-color-box' style='background-color: #30A14E;'></div>
        </div>
        <div class='legend-item'>
            <div class='legend-color-box' style='background-color: #216E39;'></div>
        </div>
        <span>More</span>
    </div>
    """
    
    calendar_html += "</div>"
    return calendar_html

def calculate_task_stats(tasks):
    """Calculates statistics for tasks."""
    if not tasks:
        return {"open_tasks": 0, "completed_tasks": 0}
    
    df = pd.DataFrame(tasks)
    open_tasks = df[df['status'].isin(['open', 'in_progress'])].shape[0]
    completed_tasks = df[df['status'] == 'completed'].shape[0]
    
    return {"open_tasks": open_tasks, "completed_tasks": completed_tasks}

def calculate_activity_data(input_log, tasks):
    """Calculates activity data including calendar HTML, streaks and task stats."""
    task_stats = calculate_task_stats(tasks)
    today = dt.date.today()

    if not input_log:
        return {
            "calendar_html": "<div>No activity.</div>", 
            "current_streak": 0,
            "longest_streak": 0,
            "todays_logs": 0,
            "num_inputs": 0,
            **task_stats
        }

    df = pd.DataFrame(input_log)
    df['date'] = pd.to_datetime(df['timestamp']).dt.date
    
    todays_logs = df[df['date'] == today].shape[0]

    dates_with_counts = df.groupby('date').size().to_dict()
    dates_with_counts_str_keys = {k.strftime("%Y-%m-%d"): v for k, v in dates_with_counts.items()}

    calendar_html = generate_calendar_html(today, dates_with_counts_str_keys)

    unique_dates = sorted(df['date'].unique())
    
    if not unique_dates:
        return {
            "calendar_html": calendar_html,
            "current_streak": 0,
            "longest_streak": 0,
            "todays_logs": todays_logs,
            "num_inputs": len(df),
            **task_stats
        }

    longest_streak = 0
    current_streak = 0
    
    # Calculate longest streak
    if unique_dates:
        longest_streak = 1
        current_streak_calc = 1
        for i in range(len(unique_dates) - 1):
            if (unique_dates[i+1] - unique_dates[i]).days == 1:
                current_streak_calc += 1
            else:
                current_streak_calc = 1
            if current_streak_calc > longest_streak:
                longest_streak = current_streak_calc

    # Calculate current streak
    current_streak = 0
    if unique_dates[-1] == today or unique_dates[-1] == today - dt.timedelta(days=1):
        current_streak = 1
        for i in range(len(unique_dates) - 1, 0, -1):
            if (unique_dates[i] - unique_dates[i-1]).days == 1:
                current_streak += 1
            else:
                break

    return {
        "calendar_html": calendar_html, 
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "todays_logs": todays_logs,
        "num_inputs": len(df),
        **task_stats
    }

# --- Main App Content ---
if not (hasattr(st.user, 'is_logged_in') and st.user.is_logged_in):
    st.markdown(
        '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"/>',
        unsafe_allow_html=True,
    )

    # Custom CSS for the Google Sign-In button
    st.markdown("""
        <style>
            div[data-testid="stButton"] > button {
                background-color: white;
                color: black;
                padding: 10px 20px;
                border: 1px solid #DADCE0;
                border-radius: 24px;
                cursor: pointer;
                font-size: 16px;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.3);
                transition: all 0.2s ease-in-out;
                margin-left: auto;
                margin-right: auto;
                width: fit-content;
            }
            div[data-testid="stButton"] > button:hover {
                box-shadow: 0px 6px 8px rgba(0, 0, 0, 0.4);
                transform: translateY(-2px);
            }
            div[data-testid="stButton"] > button:before {
                font-family: 'Font Awesome 5 Brands';
                content: '\\f1a0';
                display: inline-block;
                padding-right: 10px;
                vertical-align: middle;
                font-weight: 900;
            }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        if st.button("Sign in with Google", key="google_login"):
            try:
                st.login("google")
            except Exception as e:
                st.error(f"Login failed: {e}")
    st.stop()

# --- User IS Logged In ---
activity_data = calculate_activity_data(st.session_state.input_log, st.session_state.tasks)

with st.sidebar:
    st.markdown(
        """
    <style>
        .profile-container { 
            display: flex; 
            flex-direction: column; 
            align-items: center; 
            margin-bottom: 20px; 
        }
        .profile-picture {
            border-radius: 50%;
            width: 100px;
            height: 100px;
            object-fit: cover;
            margin-bottom: 15px;
            border: 4px solid transparent;
            background-image: linear-gradient(white, white), 
                              radial-gradient(circle at top left, #fdc468, #df4949);
            background-origin: border-box;
            background-clip: content-box, border-box;
            box-shadow: 0 4px 12px rgba(0,0,0,0.25);
        }
        .username { 
            font-weight: bold; 
            font-size: 24px; 
            margin-bottom: 15px; 
        }
        .stats-grid { 
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            width: 100%; 
            margin-bottom: 20px; 
        }
        .stat-item { 
            text-align: center; 
            background-color: #f0f2f6;
            padding: 5px;
            border-radius: 8px;
        }
        .stat-count { 
            font-weight: bold; 
            font-size: 18px; 
        }
        .stat-label {
            font-size: 12px;
            color: #555;
        }
        .log-stats .stat-count { color: #4A90E2; } /* Softer Blue */
        .task-stats .stat-count { color: #D0021B; } /* Strong Red */
        .streak-stats .stat-count { color: #F5A623; } /* Orange */
        #calendar-container {
            width: 100%;
            display: flex;
            justify-content: center;
            margin-bottom: 15px;
        }
        .motivational-text {
            text-align: center; 
            font-size: 14px; 
            color: #B4B4B4; 
            margin-top: 10px;
            font-style: italic;
        }
    </style>
    """,
        unsafe_allow_html=True
    )
    image_url = st.user.picture
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        image_data = base64.b64encode(response.content).decode("utf-8")
        image_src = f"data:image/jpeg;base64,{image_data}"
    except requests.exceptions.RequestException as e:
        image_src = "" # Fallback to an empty string or a default placeholder image
        st.error(f"Failed to load profile image: {e}")

    st.markdown(
        f"""
        <div class="profile-container">
            <img src="{image_src}" class="profile-picture">
            <div class="username">{st.user.name}</div>
            <div class="stats-grid">
                <div class="stat-item log-stats">
                    <div class="stat-count">{activity_data["todays_logs"]}</div>
                    <div class="stat-label">Today's Logs</div>
                </div>
                <div class="stat-item log-stats">
                    <div class="stat-count">{activity_data["num_inputs"]}</div>
                    <div class="stat-label">Total Logs</div>
                </div>
                <div class="stat-item task-stats">
                    <div class="stat-count">{activity_data["open_tasks"]}</div>
                    <div class="stat-label">Open Tasks</div>
                </div>
                <div class="stat-item task-stats">
                    <div class="stat-count">{activity_data["completed_tasks"]}</div>
                    <div class="stat-label">Completed Tasks</div>
                </div>
                <div class="stat-item streak-stats">
                    <div class="stat-count">{activity_data["current_streak"]}</div>
                    <div class="stat-label">Current Streak</div>
                </div>
                <div class="stat-item streak-stats">
                    <div class="stat-count">{activity_data["longest_streak"]}</div>
                    <div class="stat-label">Longest Streak</div>
                </div>
            </div>
            <div id="calendar-container">{activity_data["calendar_html"]}</div>
            <div class="motivational-text">
                Your digital reflection, one entry at a time.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    if st.button("Logout", key="logout_button", use_container_width=True):
        st.logout()
        st.rerun()

st.title("Life Tracker with Gemini AI")
st.write(
    "This is an AI-powered assistant to help you track your thoughts, tasks, and background information.  \n"
    "Interact with the Gemini model via text or audio, and manage your data across the different tabs.  \n"
    "All data is editable and is persisted locally."
)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Chat", "Input Log", "Tasks", "Background Info", "Newsletter"])

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

with tab5:
    st.header("Manual Newsletter Trigger")
    st.write("Click the button below to trigger a newsletter send to your own email address.")
    st.warning("Note: This requires SMTP environment variables to be set correctly in your project's `.env` file (e.g., `SMTP_HOST`, `SMTP_PORT`, `SMTP_PASSWORD`).", icon="⚠️")

    if st.button("Send Newsletter Now", key="send_newsletter_btn"):
        with st.spinner("Sending newsletter..."):
            result = send_newsletter_for_user(
                user_email=st.user.email,
                user_name=st.user.name,
                session_state=st.session_state
            )

        if result.get("status") == "success":
            st.success(result.get("message", "Newsletter sent successfully!"))
        else:
            st.error(result.get("message", "An unknown error occurred."))
