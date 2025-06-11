# Privacy Policy

**Last Updated:** 2025-06-11

This Privacy Policy describes how the Gemini Multimodal Demo application ("the App") collects, uses, and handles your information.

## 1. Information We Collect

The App is designed to persist data locally on the machine where it is run. We do not have a central server that collects your data. The following data is collected and stored in the `data/` directory of the project:

*   **Google User Information:** When you authenticate, we receive your basic Google profile information, including your **name**, **email address**, and **profile picture**. This is used for display purposes within the app and to associate data with your profile.
*   **Chat History:** The conversation history with the Gemini AI is stored to provide context for ongoing conversations. This includes both your text and audio inputs.
*   **Input Logs (`input_logs.csv`):** Any thoughts, observations, or general text you explicitly log. This includes the content, a timestamp, and any category assigned by you or the AI.
*   **Tasks (`tasks.csv`):** Tasks you create, including their description, status (e.g., 'open', 'completed'), creation date, and deadline.
*   **Background Information (`background_information.json`):** Information you provide about yourself to personalize the AI's responses. This can include your goals, values, preferences, and other personal details as a JSON object.
*   **Audio Files:** Audio inputs are temporarily saved as `.wav` files for processing by the Gemini API and are deleted immediately after.

## 2. How We Use Your Information

Your information is used for the following purposes:

*   **To Provide and Personalize the Service:** Your background information, chat history, and logs are used by the Gemini model to provide more relevant, context-aware, and personalized responses.
*   **To Enable Application Features:**
    *   Your Google profile information is used to identify you within the app.
    *   Input logs, tasks, and background info are stored so you can view, edit, and manage them across sessions.
*   **To Improve the Application:** By understanding how the AI uses function calling to manage your data, we can improve the tool's capabilities (this analysis happens locally).

## 3. Data Storage and Security

All data listed above is stored in files within the `data/` directory on the local filesystem where the application is running (e.g., your personal computer or a server you control).

*   **No Cloud Storage:** We do not store your personal data, logs, tasks, or background information in a central cloud database.
*   **Local Control:** You have direct control over these files. You can view, edit, or delete them at any time by accessing the `data/` directory.

## 4. Data Sharing and Third Parties

We do not sell or share your personal information with third parties. However, please be aware of the following:

*   **Google Gemini API:** Your chat inputs (text and audio) are sent to the Google Gemini API for processing to generate a response. You can review Google's API policies on their official website.
*   **Google Authentication:** Authentication is handled via Google OAuth. We only request the minimum necessary scopes to identify you.

## 5. Your Rights and Data Control

You have full control over your data:

*   **Access and Edit:** You can access and edit all your logged data (Input Logs, Tasks, Background Info) directly within the application's UI.
*   **Deletion:** You can delete individual items from the UI. You can also delete the corresponding `.csv` and `.json` files from the `data/` directory to permanently remove all associated data.

## 6. Changes to This Privacy Policy

We may update this Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page.

## 7. Contact Us

If you have any questions about this Privacy Policy, please open an issue in the project's GitHub repository.
