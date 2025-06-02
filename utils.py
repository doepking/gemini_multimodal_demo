import os
import logging

from google import genai
from google.genai import types

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()

# Gemini API initialization
client = genai.Client(api_key=os.environ.get("LLM_API_KEY"))
MODEL_NAME = "gemini-2.0-flash-exp"

# Safety settings (optional)
safety_settings = [
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_CIVIC_INTEGRITY",
        "threshold": "BLOCK_NONE",
    },
]

def start_new_chat():
    """Starts a new chat session."""
    return []  # Initialize an empty conversation history

def get_chat_response(conversation_history, user_prompt=None, audio_file_path=None):
    """Gets a response from the Gemini model, handling both text and audio."""

    contents = []

    # Add conversation history to the contents
    for turn in conversation_history:
        if turn["role"] == "user":
            contents.append(turn["content"])
        elif turn["role"] == "model":
            contents.append(turn["content"])

    # Add the current user input (text or audio)
    if user_prompt:
        contents.append(user_prompt)
        conversation_history.append({"role": "user", "content": user_prompt})
    elif audio_file_path:
        with open(audio_file_path, "rb") as audio_file:
            audio_content = audio_file.read()
        audio_part = types.Part(inline_data=types.Blob(data=audio_content, mime_type="audio/wav"))
        contents.append("(Audio input - transcribe and process)")
        contents.append(audio_part)
        conversation_history.append({"role": "user", "content": "Audio input received."})
    else:
        return "Error: No input provided."

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                max_output_tokens=2048,
                temperature=0.7,
                top_p=0.95,
                top_k=40,
                safety_settings=[
                    types.SafetySetting(category=setting["category"],
                                        threshold=setting["threshold"])
                    for setting in safety_settings
                ],
            ),
        )

        if not response.candidates:
            return "Sorry, I couldn't generate a response."

        candidate = response.candidates[0]

        if not hasattr(candidate, 'content') \
            or not candidate.content \
            or not hasattr(candidate.content, 'parts') \
            or not candidate.content.parts:
            return "Sorry, I couldn't generate a response."

        final_response = ""
        for part in candidate.content.parts:
            if hasattr(part, "text") and part.text:
                final_response += part.text
                conversation_history.append({"role": "model", "content": part.text})

        return final_response

    except Exception as e:
        logging.info(f"An error occurred: {e}")
        return "Something went wrong. Can you try again?"
