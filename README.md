# Multimodal AI Chat with Gemini

This project demonstrates a multimodal AI chat application using Google's Gemini model. It allows users to interact with the
AI through both text and audio input. This version introduces **input logging** and **background information management**, powered by
**LLM function calling**, allowing for a more personalized and stateful interaction.

## Features

-   **Text Chat:** Engage in text-based conversations with the Gemini model.
-   **Audio Chat:** Record and send audio messages to the AI, which will transcribe and process them.
-   **Input Logging:** Log thoughts, observations, or any text input via a dedicated "Input Log" tab. These logs can be processed (e.g., categorized) by the LLM.
-   **Background Information Management:** Provide and update personal background information (goals, values, preferences) in the "Background Info" tab. The LLM can use this information to tailor its responses.
-   **LLM Function Calling:** The Gemini model can now intelligently decide to call specific functions to:
    *   Log user input.
    *   Update user background information.
    This enables more dynamic and context-aware interactions.
-   **Conversation History:** The application maintains a history of the conversation, allowing the AI to provide contextually
relevant responses.
-   **Streamlit Interface:** A user-friendly web interface built with Streamlit, now featuring tabs for Chat, Input Log, and Background Info for organized interaction.
-   **Dockerized Deployment:** The application is containerized using Docker for simple deployment and portability.

## Prerequisites

Before running this application, you'll need the following:

-   **Google GenAI API Key:** Obtain a free API key from [Google AI Studio](https://aistudio.google.com/apikey).
-   **Python 3.12:** Ensure you have Python 3.12 installed on your system.
-   **Docker (Optional):** If you plan to deploy using Docker, make sure you have Docker installed and running.

## Installation

### Using Pip

1. **Install the Google GenAI Python SDK:**

    ```bash
    pip3 install google-genai
    ```

2. **Install other required Python packages:**

    ```bash
    pip3 install -r requirements.txt
    ```

### Using Docker

1. **Build the Docker image:**

    ```bash
    docker build -t multimodal-gemini-chat .
    ```

## Configuration

1. **Environment Variables:**
    -   Create a `.env` file in the root directory of the project.
    -   Add your Google GenAI API key to the `.env` file:

        ```
        LLM_API_KEY=your_api_key_here
        ```

## Usage

### Running Locally with Pip

1. **Start the Streamlit application:**

    ```bash
    streamlit run app.py
    ```

2. **Access the application:** Open your web browser and go to `http://localhost:8501` (or the URL provided by Streamlit).

### Running with Docker

1. **Run the Docker container:**

    ```bash
    docker run -p 8080:8080 -d --env-file .env multimodal-gemini-chat
    ```

2. **Access the application:** Open your web browser and go to `http://localhost:8080`.

## Interacting with the Chatbot

The application interface is organized into three main tabs:

-   **Chat Tab:**
    -   **Text Input:** Type your message in the chat input box and press Enter.
    -   **Audio Input:**
        1. Click the "Start Recording" button.
        2. Speak your message.
        3. Click the "Stop Recording" button.
        4. The audio will be sent to the AI for processing.
    -   The AI may use function calling to log your input or update background information based on your conversation.

-   **Input Log Tab:**
    -   Use the text area to enter any thoughts, observations, or information you want to log.
    -   Click "Add to Log". The LLM might be involved in categorizing this input.
    -   View your logged entries in the table below the form.

-   **Background Info Tab:**
    -   View your current background information.
    -   Use the text area to provide or update details about yourself, such as goals, values, preferences, or any other context you want the AI to remember.
    -   Click "Save Background Info". The LLM will process this text to update the structured background information stored in the session.

## Code Overview

-   **`app.py`:** Contains the Streamlit application logic, including UI elements for the chat, input log, and background info tabs. It manages audio recording, chat input handling, form submissions for logging and background updates, and displays information from the session state. It calls `get_chat_response` from `utils.py` to interact with the Gemini model.
-   **`utils.py`:** Handles the communication with the Gemini API.
    -   `start_new_chat`: Initializes a new chat session.
    -   `get_chat_response`: Gets a response from the model, supporting text, audio, and now **function calling**. It includes a system prompt that guides the LLM on when and how to use the defined tools.
    -   **Tool Definitions:** Defines `process_text_input_for_log` and `update_background_info_in_session` as tools available to the LLM.
    -   **Implementation Functions (`_impl`):** Contains `process_text_input_for_log_impl` and `update_background_info_in_session_impl` which are executed when the LLM calls the respective functions. These update `st.session_state.input_log` and `st.session_state.background_info`.
    -   Manages safety settings and provides a schema example for background information.
-   **`Dockerfile`:** Defines the Docker image for the application, including the necessary dependencies and commands to run the
application.

## Notes

-   The audio recording functionality uses the `audiorecorder` library within Streamlit.
-   Temporary audio files are created and deleted during audio processing.
-   Conversation history, input logs, and background information are stored in the Streamlit session state.
-   The Docker image uses a slim Python base image and installs `ffmpeg` for audio processing.

## Limitations

-   This is a demo and may not handle all edge cases or complex conversation scenarios.
-   The audio processing is limited to `.wav` files.
-   Error handling is minimal.
-   The LLM's ability to perfectly categorize logs or structure background information from free text is dependent on the model's capabilities and the clarity of user input.

## Future Enhancements

-   Improve error handling and robustness.
-   Support additional audio formats.
-   Implement more sophisticated conversation management.
-   Expand function calling capabilities with more tools.
-   Allow for more structured editing of background information.
-   Persist logs and background information beyond the current session (e.g., to a database).

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.
