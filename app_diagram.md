graph TD
    subgraph "User Interaction"
        direction LR
        User([User]) -->|Accesses URL| App{Streamlit App}
        App -->|First Visit| Consent(Consent Banner)
        Consent -->|Accept| Login(Google OAuth Login)
        Login --> App
    end

    subgraph "Google Cloud Platform"
        direction TB
        subgraph "Cloud Run Service"
            direction TB
            App -- Deployed in --> Container[Container: app.py]
            Container -->|Handles UI & State| AppLogic[UI/State Management]
            AppLogic -->|Calls| Utils[utils.py]
            Utils -->|Interacts with| Gemini[Gemini API]
            Utils -->|Reads/Writes| DB[(Cloud SQL Database)]
            Container -->|Triggers Newsletter| Newsletter[newsletter.py]
            Newsletter -->|Reads| DB
            Newsletter -->|Sends via| SMTP[SMTP Service]
        end

        subgraph "Data & Auth"
            DB[(Cloud SQL Database)]
            OAuth[Google OAuth Service]
        end

        Login -- Authenticates against --> OAuth
    end

    subgraph "Deployment Pipeline"
        direction TB
        Dev[Developer Machine] -->|Runs| BuildScript(build.sh)
        BuildScript -->|Builds| Dockerfile[Dockerfile]
        BuildScript -->|Pushes to| GCR[Google Container Registry]
        Dev -->|Runs| DeployScript(deploy.sh)
        DeployScript -->|Deploys Image from| GCR
        DeployScript -->|Configures| Container
    end

    subgraph "Function Calling Logic (within utils.py)"
        direction TB
        Gemini -->|Decides Action| FunctionCall{Function Calling}
        FunctionCall -- "add_log_entry" --> DB
        FunctionCall -- "update_background_info" --> DB
        FunctionCall -- "manage_tasks" --> DB
    end

    classDef user fill:#ffb3ba,stroke:#333,stroke-width:2px;
    classDef gcp fill:#c2d4dd,stroke:#333,stroke-width:1px;
    classDef deploy fill:#fdebd0,stroke:#333,stroke-width:1px;
    classDef logic fill:#d5f5e3,stroke:#333,stroke-width:1px;
    classDef db fill:#e8daef,stroke:#333,stroke-width:2px,shape:cylinder;

    class User user;
    class App,Consent,Login,Container,AppLogic,Utils,Newsletter,Gemini,SMTP,DB,OAuth gcp;
    class Dev,BuildScript,DeployScript,Dockerfile,GCR deploy;
    class FunctionCall logic;
