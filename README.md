# Multimodal AI Chat with Gemini

This project demonstrates a multimodal AI chat application using Google's Gemini model. It allows users to interact with the
AI through both text and audio input. This version introduces **input logging** and **background information management**, powered by
**LLM function calling**, allowing for a more personalized and stateful interaction.

## Features

-   **Text Chat:** Engage in text-based conversations with the Gemini model.
-   **Audio Chat:** Record and send audio messages to the AI, which will transcribe and process them.
-   **Input Logging:** Log thoughts, observations, or any text input via a dedicated "Input Log" tab. Logs are fully editable directly in the UI.
-   **Background Information Management:** Provide and update personal background information (goals, values, preferences) in the "Background Info" tab. The entire information object is editable as a JSON in the UI. The LLM can use this information to tailor its responses.
-   **LLM Function Calling:** The Gemini model can now intelligently decide to call specific functions to:
    *   Log user input.
    *   Update user background information.
    *   Manage tasks (add, update, list).
    This enables more dynamic and context-aware interactions.
-   **Task Management:** A new "Tasks" tab allows users to view, add, delete, and edit tasks in a data grid. Tasks can also be managed via chat by asking the AI.
-   **Data Persistence:** Input logs, background information, and tasks are now persisted to `.csv` and `.json` files in the `data/` directory, so they are not lost when the application restarts.
-   **Conversation History:** The application maintains a history of the conversation, allowing the AI to provide contextually
relevant responses.
-   **Streamlit Interface:** A user-friendly web interface built with Streamlit, now featuring tabs for Chat, Input Log, Tasks, and Background Info for organized interaction.
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

The recommended way to run the application with Docker is to use `docker-compose`, which will also mount the `data` directory to persist your logs, tasks, and background info on your host machine.

1. **Create the `.env` file:**
    -   If you haven't already, create a `.env` file in the root directory.
    -   Add your Google GenAI API key to it:
        ```
        LLM_API_KEY=your_api_key_here
        ```

2. **Build and run with Docker Compose:**
    ```bash
    docker-compose up -d --build
    ```

3. **Access the application:** Open your web browser and go to `http://localhost:8080`.

4. **To stop the application:**
    ```bash
    docker-compose down
    ```

## Usage

### Running Locally with Pip

1. **Start the Streamlit application:**

    ```bash
    streamlit run app.py
    ```

2. **Access the application:** Open your web browser and go to `http://localhost:8501` (or the URL provided by Streamlit).

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
    -   View, edit, add, or delete log entries directly in the data grid. Click "Save Log Changes" to persist modifications.
    -   Use the form at the bottom to quickly add a new log entry.
    -   Logs are saved to `data/input_logs.csv`.

-   **Tasks Tab:**
    -   View, edit, add, or delete tasks directly in the data grid. Click "Save Task Changes" to persist modifications.
    -   Add new tasks using the form at the bottom.
    -   Tasks can also be added or updated by asking the chat assistant (e.g., "add a task to buy milk").
    -   Tasks are saved to `data/tasks.csv`.

-   **Background Info Tab:**
    -   View and edit your background information directly in the JSON text area.
    -   Click "Save Background Info Changes" to persist your modifications.
    -   The LLM can also update this information via function calling during a chat.
    -   Background info is saved to `data/background_information.json`.

## Code Overview

-   **`app.py`:** Contains the Streamlit application logic, including UI elements for the chat, input log, tasks, and background info tabs. It manages audio recording, chat input handling, and form submissions. It calls the appropriate `*_and_persist` functions from `utils.py` whenever data is modified through the UI.
-   **`utils.py`:** A refactored module that cleanly separates responsibilities.
    -   **App-Facing Functions (`*_and_persist`):** A set of functions (`add_log_entry_and_persist`, `update_tasks_and_persist`, etc.) designed to be called directly from the `app.py` UI. Each function handles a specific data modification (like adding a task or updating the entire log) and ensures the changes are saved to a file.
    -   **Core Implementation Functions (`*_impl`):** The internal logic for processing data. These are called by the app-facing functions or by the LLM's function-calling mechanism.
    -   **LLM Chat & Tools:**
        -   `get_chat_response`: The core function for interacting with the Gemini model, handling text, audio, and function calling.
        -   **Tool Definitions:** Defines `add_log_entry`, `update_background_info`, and `manage_tasks` as tools available to the LLM.
    -   **Data Persistence Functions:** Low-level functions for loading and saving data to/from files in the `data/` directory.
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
-   Persist logs, tasks, and background information beyond the current session (e.g., to a database).

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.
