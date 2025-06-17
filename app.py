import os
import tempfile
import json
import streamlit as st
from audiorecorder import audiorecorder
import datetime as dt
import pandas as pd
import requests
import base64
import random
from streamlit_extras.stylable_container import stylable_container
import logging

from utils import (
    get_chat_response,
    start_new_chat,
    add_log_entry_and_persist,
    add_task_and_persist,
    update_background_info_and_persist,
    update_tasks_and_persist,
    update_input_log_and_persist,
    load_input_log,
    load_tasks,
    load_background_info,
    get_or_create_user,
    get_db
)
from newsletter import send_newsletter_for_user
from database import init_db

# --- Page Configuration ---
st.set_page_config(
    page_title="AI-enabled Life Tracker",
    page_icon=":clipboard:",
    layout="wide"
)

# Configure logging
logger = logging.getLogger("app")
if not logger.handlers:  # Prevent duplicate handlers if script reruns
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# --- Database Initialization ---
try:
    init_db()
    logger.info("Database initialization successful.")
except Exception as e:
    logger.error(f"Error initializing database: {e}", exc_info=True)
    st.error("Error initializing database. Please check the logs.")
    st.stop()

# --- Consent State Initialization ---
if 'consent_given' not in st.session_state:
    st.session_state.consent_given = None # None = Not yet chosen, True = Accepted, False = Declined

# --- Load Privacy Policy & Impressum ---
try:
    with open("privacy_policy.md", "r") as f:
        privacy_policy_content = f.read()
except FileNotFoundError:
    privacy_policy_content = "Privacy Policy file not found. Please contact support."

try:
    with open("imprint.md", "r") as f:
        impressum_content = f.read()
except FileNotFoundError:
    impressum_content = "Imprint/Legal Notice file not found. Please contact support."


# --- Consent Banner Logic ---
consent_placeholder = st.empty() # Placeholder for the banner

def show_consent_banner():
    with consent_placeholder.container():
        # Center the banner content
        _consent_banner_col1, consent_banner_col_main, _consent_banner_col3 = st.columns([0.2, 3, 0.2]) # More mobile-friendly ratio
        with consent_banner_col_main:
            with stylable_container(
                key="consent_banner",
                css_styles="""
                    {
                        /* Use Streamlit theme variables for dark mode compatibility */
                        background-color: var(--secondary-background-color);
                        color: var(--text-color);
                        border: 1px solid var(--gray-40);
                        border-radius: 10px;
                        padding: 25px;
                        box-shadow: 0 4px 12px 0 rgba(0,0,0,0.05);
                    }
                    /* Mobile-friendly adjustments */
                    @media (max-width: 640px) {
                        {
                            padding: 15px;
                            border-radius: 5px; /* Slightly smaller radius for smaller screens */
                        }
                    }
                """
            ):
                st.warning("🍪 **Privacy & Cookies Notice**")

                st.info("""
                This app uses essential cookies and services to function.
                Please review the details before proceeding.
                """)

                with st.expander("View Details", expanded=False):
                    st.subheader("Core Services Overview")
                    st.markdown("""
                    - **Authentication & Session Management**: We use essential services from Google and Streamlit to securely log you in and manage your session.
                    - **AI-Powered Features**: Your interactions are processed by Google's Gemini models to provide chat responses, analysis, and other AI capabilities.
                    - **Secure Cloud Database**: Your inputs, tasks, and background information are stored in a secure **Google Cloud SQL** database to personalize the app and persist your data across sessions.
                    """)

                    st.subheader("Your Data & Rights")
                    st.markdown("For detailed information on data collection, usage, your rights under GDPR, and who to contact, please review our full legal documents.")

                    # Using columns for a cleaner layout of download buttons
                    col_privacy, col_imprint = st.columns(2)
                    with col_privacy:
                        st.download_button(
                            label="Download Privacy Policy",
                            data=privacy_policy_content,
                            file_name="privacy_policy.md",
                            mime="text/markdown",
                            key="consent_download_privacy",
                            use_container_width=True
                        )
                    with col_imprint:
                        st.download_button(
                            label="Download Imprint / Legal Notice",
                            data=impressum_content,
                            file_name="imprint.md",
                            mime="text/markdown",
                            key="consent_download_imprint",
                            use_container_width=True
                        )

                st.markdown("""
                    <div style='text-align: center; margin-bottom: 1rem;'>
                    By clicking <b>Accept</b>, you consent to this.<br>If you <b>Decline</b>, you will not be able to use the app.
                    </div>
                """, unsafe_allow_html=True)

                # Center the buttons
                _btn_spacer1, btn_col1, btn_col2, _btn_spacer2 = st.columns([1.5, 1, 1, 1.5])
                if btn_col1.button("✅ Accept", key="accept_consent", use_container_width=True):
                    st.session_state.consent_given = True
                    consent_placeholder.empty()
                    st.rerun()
                if btn_col2.button("❌ Decline", key="decline_consent", use_container_width=True):
                    st.session_state.consent_given = False
                    consent_placeholder.empty()
                    st.rerun()

# --- Initialize Session State ---
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = start_new_chat()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_audio_duration" not in st.session_state:
    st.session_state.last_audio_duration = -1.0
    st.session_state.audio_recordings = []
    st.session_state.counter = 0 # Used for unique keys for recorder/input

# --- Helper Functions ---
def load_all_data():
    """Loads all data from the database into the session state."""
    db = next(get_db())
    try:
        user = get_or_create_user(db, st.user.email, st.user.name)
        st.session_state.user = user
        st.session_state.input_log = load_input_log(db, user.id)
        st.session_state.background_info = load_background_info(db, user.id)
        st.session_state.tasks = load_tasks(db, user.id)
        logger.info("Session state refreshed from database.")
    finally:
        db.close()

# --- Initialize Session State and Data ---
if hasattr(st, 'user') and st.user.is_logged_in:
    load_all_data() # Always load fresh data for logged-in users on each run

    if 'edit_background' not in st.session_state:
        st.session_state.edit_background = False
else:
    # Ensure data is cleared if user logs out
    st.session_state.user = None
    st.session_state.input_log = []
    st.session_state.tasks = []
    st.session_state.background_info = {}


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
            grid-template-columns: repeat(7, auto);
            justify-content: center;
            gap: 4px;
            margin-bottom: 10px;
        }
        .calendar-day-box {
            width: 16px;
            height: 16px;
            border-radius: 3px;
            border: 1px solid rgba(0,0,0,0.05);
            transition: transform 0.2s ease-in-out;
        }
        .calendar-day-box:hover {
            transform: scale(1.1);
        }
        .calendar-legend {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            color: #586069;
            gap: 8px;
        }
        .legend-colors {
            display: flex;
            gap: 4px;
        }
        .legend-color-box {
            width: 16px;
            height: 16px;
            border-radius: 3px;
        }
        @media (max-width: 640px) {
            .calendar-day-box {
                width: 14px;
                height: 14px;
            }
            .legend-color-box {
                width: 14px;
                height: 14px;
            }
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
        <div class='legend-colors'>
            <div class='legend-color-box' style='background-color: #EBEDF0;'></div>
            <div class='legend-color-box' style='background-color: #9BE9A8;'></div>
            <div class='legend-color-box' style='background-color: #40C463;'></div>
            <div class='legend-color-box' style='background-color: #30A14E;'></div>
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

    # Convert tasks (which are likely ORM objects) to a list of dicts
    tasks_for_df = [
        {
            "id": task.id,
            "description": task.description,
            "status": task.status,
            "deadline": task.deadline,
            "created_at": task.created_at
        }
        for task in tasks
    ]
    
    df = pd.DataFrame(tasks_for_df)
    
    # Now, the 'status' column should exist
    open_tasks = df[df['status'].isin(['open', 'in_progress'])].shape[0]
    completed_tasks = df[df['status'] == 'completed'].shape[0]
    
    return {"open_tasks": open_tasks, "completed_tasks": completed_tasks}

def calculate_activity_data(input_log, tasks):
    """Calculates activity data including calendar HTML, streaks and task stats."""
    task_stats = calculate_task_stats(tasks)
    today = dt.date.today()

    if not input_log:
        calendar_html = generate_calendar_html(today, {})
        return {
            "calendar_html": calendar_html, 
            "current_streak": 0,
            "longest_streak": 0,
            "todays_logs": 0,
            "num_inputs": 0,
            **task_stats
        }

    df = pd.DataFrame([
        {
            "id": log.id,
            "user_id": log.user_id,
            "content": log.content,
            "category": log.category,
            "created_at": log.created_at
        }
        for log in input_log
    ])
    df['date'] = pd.to_datetime(df['created_at']).dt.date
    
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

# --- Main Application Logic ---

# 1. Check Consent Status FIRST
if st.session_state.consent_given is None and not (hasattr(st.user, 'is_logged_in') and st.user.is_logged_in):
    # Show consent banner if no choice has been made
    show_consent_banner()
    st.stop() # Stop execution until consent is given or declined

elif st.session_state.consent_given is False:
     # Show message if consent declined
     st.error("🍪 Consent Declined: You have declined the use of cookies and data processing required for AI features. Please refresh the page if you wish to reconsider.")
     st.stop() # Stop execution

# 2. Check Authentication Status (only if consent is True)
elif st.session_state.consent_given is True and not (hasattr(st.user, 'is_logged_in') and st.user.is_logged_in):
    # --- User NOT Logged In ---
    faq_modal_style = """
    <style>
    /* Target Streamlit expanders specifically */
    div[data-testid="stExpander"] {
        border: none;
        box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2);
        border-radius: 10px;
    }
    div[data-testid="stExpander"] .stExpanderHeader {
        background-color: #f0f2f6;
        padding: 10px;
        font-weight: bold;
    }
    div[data-testid="stExpander"] .stExpanderContent {
        padding: 20px;
        color: black;
    }
    </style>
    """
    st.markdown(faq_modal_style, unsafe_allow_html=True) # Apply style before the expander
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        with st.expander("Frequently Asked Questions", expanded=False):
            st.markdown(
            """
            **What is this?**

            This app is a multimodal AI chat application using Google's Gemini model. It allows users to interact with the AI through both text and audio input.

            **What are the main features?**

            - **Chat with AI:** Engage in text-based and audio conversations with the Gemini model.
            - **Input Log:** Keep a record of your thoughts, decisions, and actions in a structured format.
            - **Background Info:** Provide context about yourself (goals, values, etc.) to help the AI understand you better.
            - **Task Management:** Create and manage tasks, which can be updated by the AI based on your conversation.
            - **Secure Data Storage:** All your data (inputs, tasks, background info) is securely stored in a **Google Cloud SQL** database.

            **What happens with my data?**

            - **Cloud-Based & Secure:** Your data is stored in a secure, private Google Cloud SQL database, protected by Google Cloud's robust security measures.
            - **You Are in Control:** You have complete control over your data. You can view, edit, and permanently delete your information at any time through the app's interface.
            """
        )

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
            border: 2px solid transparent;
            background-image: linear-gradient(white, white), 
                              linear-gradient(135deg, #4285F4 25%, #EA4335 50%, #FBBC05 75%, #34A853 100%);
            background-origin: border-box;
            background-clip: content-box, border-box;
            box-shadow: 0 4px 12px rgba(0,0,0,0.25);
        }
        .username { 
            font-weight: bold; 
            font-size: 20px; 
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
    image_url = getattr(st.user, 'picture', None) # Safely get the attribute
    image_src = "" # Initialize with a fallback for the <img> tag

    if image_url:
        try:
            response = requests.get(image_url)
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            image_data = base64.b64encode(response.content).decode("utf-8")
            image_src = f"data:image/jpeg;base64,{image_data}"
        except requests.exceptions.RequestException as e:
            # image_src remains "" as initialized
            logger.warning(f"Failed to load profile image from {image_url} for user {st.user.email}: {e}")
            st.warning(f"Could not load your profile image. It might be unavailable or the link broken.") # User-facing warning
    else:
        logger.info(f"No profile picture URL found for user {st.user.email}.")
        # image_src remains "", resulting in no image or a broken image icon. No error/warning to user.

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
    
    st.markdown("---") # Separator

    # --- Data Deletion Section ---
    with st.expander("⚠️ Danger Zone", expanded=False):
        if 'confirm_purge' not in st.session_state:
            st.session_state.confirm_purge = False

        if not st.session_state.confirm_purge:
            if st.button("Withdraw Consent & Purge Data", key="purge_initial", type="primary", use_container_width=True):
                    st.session_state.confirm_purge = True
                    st.rerun()
        else:
            st.warning("This action is irreversible. All your data (inputs, tasks & background info) will be permanently deleted.")
            if st.button("Confirm Purge", key="purge_confirm", type="primary", use_container_width=True):
                try:
                    db = next(get_db())
                    user = get_or_create_user(db, st.user.email, st.user.name)
                    if user:
                        logger.info(f"Initiating data purge for user: {user.email}")
                        from utils import purge_user_data
                        purge_success = purge_user_data(user.id)
                        if purge_success:
                            logger.info(f"Main app data purge successful for user: {user.email}")
                            
                            # Proceed with logout and session reset
                            st.session_state.consent_given = None # Reset consent state
                            st.session_state.confirm_purge = False # Reset confirmation
                            st.logout() # Log the user out
                        else:
                            logger.error(f"Main app data purge failed for user: {user.email}")
                            st.error("An error occurred during data deletion. Please contact support.")
                            st.session_state.confirm_purge = False # Reset confirmation on error
                    else:
                        logger.warning(f"Attempted purge for non-existent user: {st.user.email}")
                        st.error("User not found.")
                        st.session_state.confirm_purge = False
                except Exception as e:
                    logger.error(f"Exception during data purge confirmation for {st.user.email}: {e}", exc_info=True)
                    st.error("An unexpected error occurred during data deletion.")
                    st.session_state.confirm_purge = False
                finally:
                    if 'db' in locals() and db:
                        db.close()
                    st.rerun()
    
    st.markdown("---") # Separator
    # Link to Privacy Policy and Impressum in sidebar as well
    with st.expander("Legal Information", expanded=True):
        st.download_button(
            label="Download Privacy Policy",
            data=privacy_policy_content,
            file_name="privacy_policy.md",
            mime="text/markdown",
            key="sidebar_download_privacy"
        )
        st.download_button(
            label="Download Imprint / Legal Notice",
            data=impressum_content,
            file_name="impressum.md",
            mime="text/markdown",
            key="sidebar_download_imprint"
        )

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Chat", "Input Log", "Tasks", "Background Info", "Newsletter"])

with tab1:
    # --- Determine personalized chat input placeholder and subheader ---
    if 'chat_subheader_text' not in st.session_state:
        user_name = st.user.name
        first_name = user_name.split()[0] if user_name else None
        background_info = st.session_state.get('background_info', {})

        messages_with_name_and_bg = [
            f"Welcome back {first_name} 👋, let's chat!",
            f"Hey {first_name} 👋, what's on your mind?",
            f"Hi {first_name} 👋, ready to explore some ideas?",
        ]
        messages_with_name_no_bg = [
            f"Hey {first_name} 👋, mind sharing your values & goals to get started?",
            f"Hi {first_name} 👋, ready to share some thoughts or define your goals?",
            f"Hi {first_name} 👋, what are you working towards?",
        ]
        messages_no_name_no_bg = [ # Fallback, though name should exist
            "Hey! Mind sharing your values & goals to get started?",
            "Hi! What's on your mind today?",
            "Let's get started! What are your main objectives?",
        ]
        default_messages = [
            "What's on your mind?",
            "Let's chat!",
            "Ready to explore some ideas?",
        ]

        if first_name and background_info:
            st.session_state.chat_subheader_text = random.choice(messages_with_name_and_bg)
        elif first_name:
            st.session_state.chat_subheader_text = random.choice(messages_with_name_no_bg)
        elif background_info: # Has BG but somehow no first_name
            st.session_state.chat_subheader_text = random.choice(default_messages) # Or a specific variant
        else: # No first_name and no BG
            st.session_state.chat_subheader_text = random.choice(messages_no_name_no_bg)

    st.subheader(st.session_state.chat_subheader_text)
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
                st.session_state,
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
        sorted_logs = sorted(st.session_state.input_log, key=lambda x: x.created_at, reverse=True)

        # Convert list of ORM objects to a list of dictionaries for DataFrame creation
        logs_for_df = [
            {
                "id": log.id,
                "created_at": log.created_at,
                "content": log.content,
                "category": log.category
            }
            for log in sorted_logs
        ]

        # Use a data editor to allow for changes
        edited_logs_df = st.data_editor(
            pd.DataFrame(logs_for_df),
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="data_editor_logs",
            column_config={
                "id": None,
                "created_at": st.column_config.DatetimeColumn(
                    "Created At",
                    format="YYYY-MM-DD HH:mm:ss",
                    disabled=True
                ),
                "content": st.column_config.Column("Content"),
                "category": st.column_config.Column("Category"),
            },
            # Reorder columns for better display
            column_order=["created_at", "content", "category"]
        )

        if st.button("Save Log Changes"):
            updated_logs = edited_logs_df.to_dict('records')
            result = update_input_log_and_persist(updated_logs, st.session_state.user)
            st.success(result.get("message", "Logs updated!"))
            st.rerun()

    with st.form("input_log_form"):
        new_log_content = st.text_area("Enter your log:", height=100)
        submit_log = st.form_submit_button("Add to Log")

        if submit_log and new_log_content:
            result = add_log_entry_and_persist(new_log_content, st.session_state.user)
            st.success(result.get("message", "Log added successfully!"))
            st.rerun()

with tab3:
    st.subheader("Manage Tasks")
    if not st.session_state.tasks:
        st.info("No tasks yet. Add one below or ask the chat assistant to add one for you!")
    else:
        # Tasks are already pre-sorted by the load_tasks function
        sorted_tasks = st.session_state.tasks
        
        # Convert list of ORM objects to a list of dictionaries for DataFrame creation
        tasks_for_df = [
            {
                "id": task.id,
                "description": task.description,
                "status": task.status,
                "deadline": task.deadline,
                "created_at": task.created_at,
                "completed_at": task.completed_at
            }
            for task in sorted_tasks
        ]

        # Convert list of dicts to DataFrame for editing
        df_tasks = pd.DataFrame(tasks_for_df)
        # Ensure columns are in a consistent order
        df_tasks = df_tasks[["id", "created_at", "description", "status", "deadline", "completed_at"]]
        df_tasks["deadline"] = pd.to_datetime(df_tasks["deadline"])
        df_tasks.rename(columns={"id": "ID", "description": "Description", "status": "Status", "deadline": "Deadline", "created_at": "Created At", "completed_at": "Completed At"}, inplace=True)

        edited_tasks_df = st.data_editor(
            df_tasks,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="data_editor_tasks",
            column_config={
                "ID": None,
                "Created At": st.column_config.DatetimeColumn(
                    "Created At",
                    format="YYYY-MM-DD HH:mm:ss",
                    disabled=True
                ),
                "Deadline": st.column_config.DatetimeColumn(
                    "Deadline",
                    format="YYYY-MM-DD HH:mm:ss",
                ),
                "Completed At": st.column_config.DatetimeColumn(
                    "Completed At",
                    format="YYYY-MM-DD HH:mm:ss",
                    disabled=True
                ),
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    options=['open', 'in_progress', 'completed'],
                    required=True
                ),
            },
            column_order=["Created At", "Description", "Status", "Deadline", "Completed At"]
        )

        if st.button("Save Task Changes"):
            # Convert deadline back to ISO string before saving
            edited_tasks_df['Deadline'] = edited_tasks_df['Deadline'].apply(lambda x: x.isoformat() if pd.notna(x) else None)
            updated_tasks = edited_tasks_df.rename(columns={"ID": "id", "Description": "description", "Status": "status", "Deadline": "deadline", "Created At": "created_at", "Completed At": "completed_at"}).to_dict('records')
            result = update_tasks_and_persist(updated_tasks, st.session_state.user)
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
            result = add_task_and_persist(new_task_description, st.session_state.user, deadline=deadline_str)
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
                    result = update_background_info_and_persist(background_text, st.session_state.user, replace=True)
                    if result.get("status") == "success":
                        st.session_state.background_info = result["updated_info"]
                        st.success(result.get("message", "Background information updated!"))
                        toggle_edit_mode() # Exit edit mode on success
                        st.rerun()
                    else:
                        st.error(result.get("message", "Failed to update background information."))
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
    st.write("Select a persona and click the button below to trigger a newsletter send to your own email address.")
    st.warning("Note: This requires SMTP environment variables to be set correctly in your project's `.env` file (e.g., `SMTP_HOST`, `SMTP_PORT`, `SMTP_PASSWORD`).", icon="⚠️")

    # --- Persona Selection ---
    persona_dir = "persona_prompts/"
    try:
        persona_files = sorted([f for f in os.listdir(persona_dir) if f.endswith('.txt')])
        persona_names = [os.path.splitext(f)[0].replace('_prompt', '').replace('_', ' ').title() for f in persona_files]
        
        # Default to 'Pragmatist' if available
        default_persona = "Pragmatist"
        default_index = 0
        if default_persona in persona_names:
            default_index = persona_names.index(default_persona)
        
        selected_persona_name = st.selectbox(
            "Choose a Persona for your Newsletter:",
            options=persona_names,
            index=default_index
        )

        if st.button("Send Newsletter Now", key="send_newsletter_btn"):
            # Find the corresponding file for the selected persona name
            selected_persona_file = ""
            for i, name in enumerate(persona_names):
                if name == selected_persona_name:
                    selected_persona_file = persona_files[i]
                    break
            
            if selected_persona_file:
                with open(os.path.join(persona_dir, selected_persona_file), 'r') as f:
                    persona_prompt = f.read()

                with st.spinner(f"Sending newsletter with '{selected_persona_name}' persona..."):
                    result = send_newsletter_for_user(
                        user_id=st.session_state.user.id,
                        user_email=st.user.email,
                        user_name=st.user.name,
                        session_state=st.session_state,
                        persona_prompt=persona_prompt,
                        persona_name=selected_persona_name
                    )

                if result.get("status") == "success":
                    st.success(result.get("message", "Newsletter sent successfully!"))
                else:
                    st.error(result.get("message", "An unknown error occurred."))
            else:
                st.error("Could not find the selected persona file.")

    except FileNotFoundError:
        st.error(f"Persona prompts directory not found at '{persona_dir}'. Please ensure it exists.")
    except Exception as e:
        st.error(f"An error occurred while loading personas: {e}")
