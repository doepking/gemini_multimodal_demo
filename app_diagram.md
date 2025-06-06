graph TD
    A["User"] --> TABS{"App Tabs (st.tabs)"}

    subgraph "Chat Tab"
        direction TB
        TABS -- "Chat" --> CHAT_UI{"Chat Interface"}
        CHAT_UI --> INPUT_METHOD{"Input Method?"}
        INPUT_METHOD -- "Text" --> TEXT_IN["st.chat_input"]
        INPUT_METHOD -- "Audio" --> AUDIO_IN["audiorecorder"]
        
        TEXT_IN --> PROC_USER_CHAT_INPUT{"Process User Chat Input (app.py)"}
        AUDIO_IN --> PROC_USER_CHAT_INPUT
        
        PROC_USER_CHAT_INPUT --> ADD_USER_MSG_HIST["Add User Message to History (st.session_state.messages)"]
        ADD_USER_MSG_HIST --> DISP_USER_MSG["Display User Message (st.chat_message)"]
        DISP_USER_MSG --> GET_RESPONSE("utils.get_chat_response")
    end

    subgraph "LLM Interaction (within utils.get_chat_response)"
        direction TB
        GET_RESPONSE --> LLM_DECIDES{"LLM Decides Action (Gemini Model)"}
        LLM_DECIDES -- "Direct Text Response" --> GEN_TEXT_RESP["Generate Text Response"]
        LLM_DECIDES -- "Function Call" --> CHOOSE_FUNC{"Choose Function"}
        
        CHOOSE_FUNC -- "Log Input?" --> CALL_LOG_FUNC["Tool Call: process_text_input_for_log"]
        CALL_LOG_FUNC --> LOG_IMPL["process_text_input_for_log_impl (updates st.session_state.input_log)"]
        LOG_IMPL --> FUNC_RESULT{"Function Execution Result"}
        
        CHOOSE_FUNC -- "Update Background?" --> CALL_BG_FUNC["Tool Call: update_background_info_in_session"]
        CALL_BG_FUNC --> BG_IMPL["update_background_info_in_session_impl"]
        
        CHOOSE_FUNC -- "Manage Tasks?" --> CALL_TASK_FUNC["Tool Call: manage_tasks_in_session"]
        CALL_TASK_FUNC --> TASK_IMPL["manage_tasks_in_session_impl"]

        BG_IMPL --> SAVE_BG["save_background_info"]
        LOG_IMPL --> SAVE_LOG["save_input_log"]
        TASK_IMPL --> SAVE_TASK["save_tasks"]

        SAVE_BG --> BG_JSON["data/background_information.json"]
        SAVE_LOG --> LOG_CSV["data/input_logs.csv"]
        SAVE_TASK --> TASK_CSV["data/tasks.csv"]

        BG_IMPL --> FUNC_RESULT{"Function Execution Result"}
        LOG_IMPL --> FUNC_RESULT
        TASK_IMPL --> FUNC_RESULT

        FUNC_RESULT --> GEN_TEXT_RESP_POST_FUNC["LLM Formulates Response (using function result)"]
        GEN_TEXT_RESP_POST_FUNC --> ADD_ASSISTANT_MSG_HIST_FC["Add Assistant Response to History"]
        GEN_TEXT_RESP --> ADD_ASSISTANT_MSG_HIST_DIRECT["Add Assistant Response to History"]
        
        ADD_ASSISTANT_MSG_HIST_FC --> DISP_ASSISTANT_MSG["Display Assistant Response (st.chat_message)"]
        ADD_ASSISTANT_MSG_HIST_DIRECT --> DISP_ASSISTANT_MSG
        DISP_ASSISTANT_MSG --> CHAT_UI
    end

    subgraph "Input Log Tab"
        direction TB
        TABS -- "Input Log" --> LOG_UI{"Input Log Interface"}
        LOG_UI --> LOG_FORM["User Enters Log in Form (st.text_area)"]
        LOG_FORM -- "Submit" --> APP_CALLS_LOG["app.py calls utils.process_text_input_for_log"]
        APP_CALLS_LOG --> LOG_IMPL_MANUAL["process_text_input_for_log_impl (updates st.session_state.input_log)"]
        LOG_IMPL_MANUAL --> DISP_LOGS["Display Input Logs (st.dataframe)"]
        DISP_LOGS --> LOG_UI
    end

    subgraph "Background Info Tab"
        direction TB
        TABS -- "Background Info" --> BG_UI{"Background Info Interface"}
        BG_UI --> BG_FORM["User Enters Info in Form (st.text_area)"]
        BG_FORM -- "Submit" --> APP_CALLS_BG["app.py calls utils.update_background_info_in_session"]
        APP_CALLS_BG --> BG_IMPL_MANUAL["update_background_info_in_session_impl"]
        BG_IMPL_MANUAL --> SAVE_BG_MANUAL["save_background_info"]
        SAVE_BG_MANUAL --> BG_JSON
        BG_IMPL_MANUAL --> DISP_BG_INFO["Display Background Info (st.json)"]
        DISP_BG_INFO --> BG_UI
    end

    subgraph "Tasks Tab"
        direction TB
        TABS -- "Tasks" --> TASK_UI{"Tasks Interface"}
        TASK_UI --> TASK_EDITOR["User Adds/Edits Tasks (st.data_editor)"]
        TASK_EDITOR -- "Save" --> APP_CALLS_TASK["app.py calls utils.save_tasks"]
        APP_CALLS_TASK --> TASK_CSV
        TASK_UI --> DISP_TASKS["Display Tasks (st.dataframe)"]
        DISP_TASKS --> TASK_UI
    end

    classDef llmNode fill:#f9f,stroke:#333,stroke-width:2px;
    classDef functionCallNode fill:#e6e6fa,stroke:#333,stroke-width:2px;
    classDef implNode fill:#dcdcdc,stroke:#333,stroke-width:1px,stroke-dasharray: 5 5;
    classDef fileNode fill:#cce5ff,stroke:#333,stroke-width:1px,shape:cylinder;

    class GET_RESPONSE,LLM_DECIDES,GEN_TEXT_RESP,GEN_TEXT_RESP_POST_FUNC llmNode;
    class CALL_LOG_FUNC,CALL_BG_FUNC,CALL_TASK_FUNC functionCallNode;
    class LOG_IMPL,BG_IMPL,LOG_IMPL_MANUAL,BG_IMPL_MANUAL,TASK_IMPL,SAVE_LOG,SAVE_BG,SAVE_TASK,SAVE_BG_MANUAL,APP_CALLS_TASK implNode;
    class LOG_CSV,BG_JSON,TASK_CSV fileNode;
