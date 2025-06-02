import os
import tempfile
import streamlit as st
from audiorecorder import audiorecorder
from utils import get_chat_response, start_new_chat

# --- Page Configuration ---
st.set_page_config(
    page_title="Gemini Multimodal Demo",
    page_icon=":speech_balloon:",
    layout="centered"
)

# --- Main App Content ---
st.title("Multimodal AI Chat with Gemini")
st.write(
    "This is a simple demo showcasing basic audio and text chat with Google's multi-modal Gemini model."
)

# Initialize the chat session
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = start_new_chat()

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Audio Recorder & Chat Input Logic ---
if "last_audio_duration" not in st.session_state:
    st.session_state.last_audio_duration = -1.0
    st.session_state.audio_recordings = []
    st.session_state.counter = 0

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
            response = get_chat_response(
                st.session_state.conversation_history,
                audio_file_path=tmp_audio_path
            )

        st.session_state.messages.append({"role": "assistant", "content": response})

        # Rerun to update chat messages and show input area again
        st.rerun()

    finally:
        os.unlink(tmp_audio_path)

# Text input logic
elif prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Remove the input area
    input_placeholder.empty()

    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.spinner("Thinking..."):
        response = get_chat_response(
            st.session_state.conversation_history,
            user_prompt=prompt
        )

    st.session_state.messages.append({"role": "assistant", "content": response})

    # Rerun to update chat messages and show input area again
    st.session_state.counter += 1
    st.rerun()
