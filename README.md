# Multimodal AI Chat with Gemini

This project demonstrates a simple multimodal AI chat application using Google's Gemini model. It allows users to interact with the 
AI through both text and audio input, providing a basic example of how to integrate different modalities into a conversational 
interface.

## Features

-   **Text Chat:** Engage in text-based conversations with the Gemini model.
-   **Audio Chat:** Record and send audio messages to the AI, which will transcribe and process them.
-   **Conversation History:** The application maintains a history of the conversation, allowing the AI to provide contextually 
relevant responses.
-   **Streamlit Interface:** A user-friendly web interface built with Streamlit for easy interaction.
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
    pip install -r requirements.txt
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

-   **Text Input:** Type your message in the chat input box and press Enter.
-   **Audio Input:**
    1. Click the "Start Recording" button.
    2. Speak your message.
    3. Click the "Stop Recording" button.
    4. The audio will be sent to the AI for processing.

## Code Overview

-   **`app.py`:** Contains the Streamlit application logic, including UI elements, audio recording, and chat input handling. It also 
manages the conversation history and calls the `get_chat_response` function from `utils.py` to interact with the Gemini model.
-   **`utils.py`:** Handles the communication with the Gemini API. It includes functions to start a new chat session 
(`start_new_chat`) and get a response from the model (`get_chat_response`), supporting both text and audio input. It also configures 
safety settings for the model.
-   **`Dockerfile`:** Defines the Docker image for the application, including the necessary dependencies and commands to run the 
application.

## Notes

-   The audio recording functionality uses the `audiorecorder` library within Streamlit.
-   Temporary audio files are created and deleted during audio processing.
-   The conversation history is stored in the Streamlit session state.
-   The Docker image uses a slim Python base image and installs `ffmpeg` for audio processing.

## Limitations

-   This is a basic demo and may not handle all edge cases or complex conversation scenarios.
-   The audio processing is limited to `.wav` files.
-   Error handling is minimal.

## Future Enhancements

-   Improve error handling and robustness.
-   Support additional audio formats.
-   Implement more sophisticated conversation management.
-   Add features like image input and function calling.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.
