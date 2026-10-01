# Marco Bot

Marco Bot is a Hebrew-language Telegram assistant for recording and retrieving work, inventory, planning, and activity information. It uses Gemini to extract structured details from natural-language messages and stores records in Google Sheets.

## Features

- Record inventory and material orders.
- Create scheduled Telegram reminders and recover pending reminders after a restart.
- Record project and work planning details.
- Record additional work and labor hours.
- Submit daily activity summaries from text, photos, or documents.
- Search records in selected Google Sheets worksheets.
- Back up the configured spreadsheet to Google Drive on a daily schedule.

## Telegram Commands

| Command | Description |
| --- | --- |
| `/start` | Start interacting with the bot. |
| `/new_order` | Enter an inventory or material order. |
| `/set_reminder` | Create a reminder with a topic, date, and time. |
| `/report_planning` | Record project or work planning details. |
| `/additional_working_hours` | Record additional work and labor hours. |
| `/daily_summary` | Submit a daily activity report as text or a file. |
| `/retrieve_data` | Select a worksheet and search its records. |

The bot's prompts and user-facing conversations are primarily in Hebrew. Some workflows let the user review, edit, or cancel Gemini-extracted data before saving.

## Technology

- Python
- aiogram 3
- aiohttp webhook server
- Google Gemini API
- Google Sheets via `gspread`
- Google Drive API
- APScheduler

## Local Setup

Use a Python version compatible with the pinned packages in `requirements.txt`.

1. Create and activate a virtual environment.
2. Install dependencies:

   ```cmd
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in the required values.
4. Add the Google service-account file as `credentials.json`.
5. For scheduled Drive backups, provide the OAuth token file `token.json` and set `BACKUP_FOLDER_ID`.
6. Create the required worksheets in the configured Google spreadsheet and share it with the service account.

Never commit `.env`, `credentials.json`, `token.json`, OAuth client secrets, or API tokens.

## Local Webhook Testing

Telegram requires a public HTTPS endpoint to deliver webhook updates. For local testing, use ngrok:

```cmd
ngrok http 8080
```

Set `WEBHOOK_BASE_URL` to the HTTPS URL ngrok displays, without a trailing path. For example:

```env
WEBHOOK_BASE_URL=https://example.ngrok-free.app
WEBHOOK_PATH=/telegram/webhook
WEBHOOK_SECRET=your-private-webhook-secret
HOST=0.0.0.0
PORT=8080
```

Then start the bot:

```cmd
python bot_main.py
```

The complete webhook URL is `WEBHOOK_BASE_URL` plus `WEBHOOK_PATH`. The ngrok URL may change between runs; update the environment value when it does. Do not run polling and webhook delivery simultaneously.

## Configuration

See `.env.example` for the current configuration list. Key settings include:

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_TOKEN` | Telegram bot token. |
| `GEMINI_API_KEY` | Gemini API key. |
| `GOOGLE_SHEET_NAME` | Google spreadsheet title. |
| `UPLOAD_FILES_FOLDER_ID` | Drive folder for daily-summary uploads. |
| `BACKUP_FOLDER_ID` | Drive folder for spreadsheet backups. |
| `WEBHOOK_BASE_URL` | Public HTTPS origin used by Telegram. |
| `WEBHOOK_PATH` | Webhook route; defaults to `/telegram/webhook`. |
| `WEBHOOK_SECRET` | Secret used to validate webhook requests. |
| `HOST` | HTTP server bind address; defaults to `0.0.0.0`. |
| `PORT` | HTTP server port; defaults to `8080`. |
| `MAX_ROW_RETRIEVE` | Maximum number of records returned by retrieval. |
| `REMINDER_STATUS_COLUMN` | Reminder status column number; defaults to `8` (H). |

## Google Sheets

The bot uses feature-specific worksheets, including `main_events`, `orders`, `reminders`, `planning`, `additional_working_hours`, `daily_activity_summary`, and `daily_activity_details`.

The `reminders` worksheet uses positional columns. Column H (or the configured status column) stores the lifecycle status:

- `set`: scheduled and not yet sent; restored at service startup.
- `sent`: notification sent successfully.

New reminder dates in the past are rejected. If the service was down when a pending reminder became due, it is delivered after restart with a delayed-delivery notice. Reminder times use the machine's local time; configure the local machine's timezone appropriately.

## Project Layout

```text
bot_main.py
handlers/
  additinal_working_hours.py
  backup.py
  daily_activity_summary.py
  orders.py
  planning_activity.py
  reminders.py
  retrieve.py
  states.py
  utils.py
requirements.txt
.env.example
tests/
```

## Security

Do not publish credentials, access tokens, private webhook secrets, or personal data from the Google Sheets. Review `.gitignore` and your Git changes before pushing the repository to GitHub.
