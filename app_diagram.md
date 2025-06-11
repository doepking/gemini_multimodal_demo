graph TD
    subgraph "User Interface (app.py)"
        direction LR
        A["User"] --> TABS{"App Tabs (st.tabs)"}

        TABS -- "Chat" --> CHAT_UI{"Chat Interface"}
        CHAT_UI -- "Text/Audio Input" --> GET_RESPONSE("utils.get_chat_response")

        TABS -- "Input Log" --> LOG_UI{"Input Log UI"}
        LOG_UI -- "Add Entry" --> CALL_ADD_LOG["calls utils.add_log_entry_and_persist"]
        LOG_UI -- "Save Changes" --> CALL_UPDATE_LOG["calls utils.update_input_log_and_persist"]

        TABS -- "Tasks" --> TASK_UI{"Tasks UI"}
        TASK_UI -- "Add Task" --> CALL_ADD_TASK["calls utils.add_task_and_persist"]
        TASK_UI -- "Save Changes" --> CALL_UPDATE_TASKS["calls utils.update_tasks_and_persist"]

        TABS -- "Background Info" --> BG_UI{"Background Info UI"}
        BG_UI -- "Save Changes" --> CALL_UPDATE_BG["calls utils.update_background_info_and_persist"]
    end

    subgraph "Business Logic & Persistence (utils.py)"
        direction TB
        
        subgraph "App-Facing Functions (Called by UI)"
            direction TB
            CALL_ADD_LOG --> ADD_LOG_PERSIST["add_log_entry_and_persist()"]
            CALL_UPDATE_LOG --> UPDATE_LOG_PERSIST["update_input_log_and_persist()"]
            CALL_ADD_TASK --> ADD_TASK_PERSIST["add_task_and_persist()"]
            CALL_UPDATE_TASKS --> UPDATE_TASKS_PERSIST["update_tasks_and_persist()"]
            CALL_UPDATE_BG --> UPDATE_BG_PERSIST["update_background_info_and_persist()"]

            ADD_LOG_PERSIST --> ADD_LOG_IMPL["add_log_entry_and_persist_impl()"]
            UPDATE_BG_PERSIST --> UPDATE_BG_IMPL["update_background_info_and_persist_impl()"]
            ADD_TASK_PERSIST --> MANAGE_TASKS_IMPL_ADD["manage_tasks_and_persist_impl(action='add')"]
            
            UPDATE_LOG_PERSIST --> SAVE_LOG["save_input_log()"]
            UPDATE_TASKS_PERSIST --> SAVE_TASKS["save_tasks()"]
        end

        subgraph "LLM-Facing Logic (Function Calling)"
            direction TB
            GET_RESPONSE --> LLM_DECIDES{"LLM Decides Action"}
            LLM_DECIDES -- "Direct Response" --> GEN_TEXT["Generate Text"]
            LLM_DECIDES -- "Function Call" --> CHOOSE_FUNC{"Choose Tool"}

            CHOOSE_FUNC -- "add_log_entry" --> ADD_LOG_IMPL
            CHOOSE_FUNC -- "update_background_info" --> UPDATE_BG_IMPL
            CHOOSE_FUNC -- "manage_tasks" --> MANAGE_TASKS_IMPL_LLM["manage_tasks_and_persist_impl()"]
            
            GEN_TEXT --> RENDER_UI["Render Response in UI"]
            ADD_LOG_IMPL --> RENDER_UI
            UPDATE_BG_IMPL --> RENDER_UI
            MANAGE_TASKS_IMPL_LLM --> RENDER_UI
        end

        subgraph "Core Implementation & Persistence"
            direction RL
            
            ADD_LOG_IMPL --> SAVE_LOG
            UPDATE_BG_IMPL --> SAVE_BG["save_background_info()"]
            MANAGE_TASKS_IMPL_ADD --> SAVE_TASKS
            MANAGE_TASKS_IMPL_LLM --> SAVE_TASKS

            SAVE_LOG --> LOG_CSV["data/input_logs.csv"]
            SAVE_TASKS --> TASK_CSV["data/tasks.csv"]
            SAVE_BG --> BG_JSON["data/background_information.json"]
        end
    end

    classDef uiNode fill:#cde4ff,stroke:#333,stroke-width:2px;
    classDef utilNode fill:#e6e6fa,stroke:#333,stroke-width:1px;
    classDef persistNode fill:#d4edda,stroke:#333,stroke-width:1px,stroke-dasharray: 5 5;
    classDef llmNode fill:#f9f,stroke:#333,stroke-width:2px;
    classDef fileNode fill:#fff2cc,stroke:#333,stroke-width:1px,shape:cylinder;

    class A,TABS,CHAT_UI,LOG_UI,TASK_UI,BG_UI uiNode;
    class GET_RESPONSE,LLM_DECIDES,GEN_TEXT,CHOOSE_FUNC llmNode;
    class CALL_ADD_LOG,CALL_UPDATE_LOG,CALL_ADD_TASK,CALL_UPDATE_TASKS,CALL_UPDATE_BG utilNode;
    class ADD_LOG_PERSIST,UPDATE_LOG_PERSIST,ADD_TASK_PERSIST,UPDATE_TASKS_PERSIST,UPDATE_BG_PERSIST utilNode;
    class ADD_LOG_IMPL,UPDATE_BG_IMPL,MANAGE_TASKS_IMPL_ADD,MANAGE_TASKS_IMPL_LLM utilNode;
    class SAVE_LOG,SAVE_TASKS,SAVE_BG persistNode;
    class LOG_CSV,TASK_CSV,BG_JSON fileNode;
