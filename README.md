# Deva Personal AI Voice Assistant

## Start locally on Windows

1. Install and start MySQL Server.
2. Create a local `.env` file by copying `.env.example`, then set `MYSQL_PASSWORD` to your MySQL password. Keep `.env` private.
3. In PowerShell, from the project folder:

   ```powershell
   python -m pip install -r requirements.txt
   python -m uvicorn main:app --reload
   ```

4. Open <http://127.0.0.1:8000>, create an account, and log in. The app creates the configured database and its tables automatically. The configured MySQL user needs permission to create databases and tables.

Accounts use PBKDF2 password hashes. Login sessions and chat history are stored in MySQL; each account can only access its own conversations.

Search replies use a keyless web metasearch and show one relevant result with a link to its source. Search needs an internet connection. Results may come from multiple search providers and are presented as snippets rather than rewritten as a guaranteed-correct answer.

## Rebuild the intent model

To regenerate the curated intent examples and train a fresh model:

```powershell
python src/train_model.py
```

The training script reports held-out accuracy, then fits and saves the final model using word and character features. Alarm and music samples cover supported commands only. Alarms ring in the browser while the page is open; music opens YouTube results for you to choose a video because the browser cannot start YouTube playback without that user action.
