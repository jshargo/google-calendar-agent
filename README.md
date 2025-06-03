# Google Calendar Agent

This project contains an Agent which can take in a natural language query and create, change, list, or delete Google Calendar events. I use Pydantic-Ai as the agent framework, Supabase for chat_id tracing, Google Calendar API for all calendar related tasks, and OpenAI for the LLM. 

## Setup Instructions

### 1. Clone the Repository 

If you haven't already, clone the repository to your local machine.

### 2. Create and Activate a Virtual Environment

Create a Python virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

### 3. Install Dependencies

Install the required Python packages listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 4. Configure Google Calendar API

We will then need to setup a Google Calendar API instance which our Agent will then access via an API key.

1.  **Go to Google Cloud Console:** Navigate to [https://console.cloud.google.com/](https://console.cloud.google.com/) and log in or create an account.

2.  **Create a New Project:**
    *   Create a new project (top left of the home page) and name it something like "google-calendar-agent".

3.  **Enable Google Calendar API:**
    *  Once your project has been created, select your project and navigate to the left sidebar and find APIs & Services -> Library, and click on it. This opens the API Library; find and enable the "Google Calendar API". 

4.  **Configure OAuth Consent Screen:**
    *  We now need to setup the OAuth consent screen, which you can do by navigating to the left sidebar and clicking on APIs & Services -> OAuth consent screen. Name your app, and for you user type, choose "External". Make sure to add your email as a "Test User" inside of the "Audience" tab as well. 
    
5.  **Create OAuth 2.0 Client ID:**
    *   After this is done, we need to create an OAuth Client account by navigating to the left sidebar once again and clicking on API & Services -> Credentials. Once here, click "Create Credentials" and select "OAuth client ID". Set your application type to "Desktop App" and click create. Make sure your click "Download JSON" and save it as "client_secret.json" in your folder. 

        **Important:** This file contains sensitive credentials. Ensure it's listed in your `.gitignore` file to prevent accidental commits.

### 5. Configure Supabase for Chat Logging

In this project I used Supabase to store all chats sent to, and recieved by the agent. To setup the table we will use, navigate to https://supabase.com, and login or create an account. 

1.  **Create a New Project:**
    *   Create an organization and a project and then give it a name.
2.  **Create `chats` Table:**
    *   From here, go to the left sidebar and click on "SQL Editor". Paste in this SQL code to create a basic table to store our chat history,
    *   Paste and run the following SQL to create the `chats` table:

        ```sql
        CREATE TABLE chats (
            chat_id VARCHAR,
            message VARCHAR,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        ```
### 6. Set Up Environment Variables

1.  In your Supabase project dashboard, go to **Project Settings** (gear icon) > **API**.
2.  You will find your **Project URL** and **Project API Keys**.
3.  Create a file named `.env` in the directory by copying the `.env.sample` file.
4.  Add your Supabase URL and Key to the `.env` file.
5.  Also include your `OPENAI_API_KEY` for the agent LLM. 

## Running the Agent

Once all setup steps are complete:

1.  Ensure your virtual environment is activated:
    ```bash
    source .venv/bin/activate
    ```
2.  Run the agent script:
    ```bash
    python agent.py
    ```
3.  The agent will start an interactive chat session. You'll see a prompt like:
    ```
    Starting new chat session. Session ID: <your-session-id>
    How can I help you with your scheduling?
    -> 
    ```
4.  Type your natural language queries to interact with your Google Calendar.

## Usage Examples

Here are a few examples of how you can interact with the agent:

*   `-> Create an event for a meeting with John tomorrow at 2 PM for 1 hour titled 'Project Sync'`
*   `-> What's on my calendar for next Monday?`
*   `-> Cancel my 3 PM meeting on Friday.`
*   `-> Change the 'Team Lunch' event on Wednesday to 1 PM.`


## Important Notes

*   **Security:** Be mindful of the `client_secret.json` file, the `token-files/` directory, and the `.env` file. They contain sensitive credentials and should **NEVER** be committed to a public repository. The provided `.gitignore` file helps prevent this.
*   **First Run & Authentication:** The first time you run the agent and it needs to access your calendar, it will likely open a web browser page asking you to authorize access to your Google Account. Follow the prompts to grant permission.
*   **Error Handling:** Basic error handling is in place, but further enhancements may be needed for a production-ready application. This project is still a work-in-progress.


