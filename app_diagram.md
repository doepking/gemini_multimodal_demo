graph TD
    A["User"] --> B{"Input Type?"}
    B -- Text --> C["Text Input via st.chat_input"]
    B -- Audio --> D["Audio Input via audiorecorder"]
    C --> E{"Process Input"}
    D --> E
    E --> G["Add User Input to History"]
    G --> H["Display User Input"]
    H --> I("utils.get_chat_response")
    I --> J["Add Assistant Response to History"]
    J --> K["Display Assistant Response"]
    K --> A
    style I fill:#f9f,stroke:#333,stroke-width:2px;
