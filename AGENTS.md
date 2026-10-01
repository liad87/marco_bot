# Project Guide for AI Assistants

## Project Overview

Marco Bot is a Hebrew-language Telegram bot for recording and retrieving work, inventory, planning, and activity information. It uses aiogram 3 for Telegram updates, Gemini to extract structured data, Google Sheets as its primary data store, Google Drive for files and spreadsheet backups, and APScheduler for reminders and daily backup jobs.

The application currently uses an aiohttp webhook server. Local webhook testing is intended to use ngrok. Do not assume a production host has been selected or configured.

## Repository Structure

- `bot_main.py` creates the Telegram bot and dispatcher, registers feature routers, starts the scheduler, restores scheduled reminders from Google Sheets, configures Telegram's webhook, and runs the aiohttp server.
- `handlers/orders.py` handles inventory and material order requests.
- `handlers/reminders.py` creates reminders, writes them to Google Sheets, schedules notifications, updates reminder status after delivery, and restores pending reminders after restart.
- `handlers/planning_activity.py` records work and project planning details.
- `handlers/additinal_working_hours.py` records additional work and labor-hour details. Keep the existing filename spelling unless a deliberate rename updates all imports.
- `handlers/daily_activity_summary.py` accepts text or uploaded images/documents and extracts daily activity and bill-of-quantities details.
- `handlers/retrieve.py` searches data in selected Google Sheets worksheets.
- `handlers/backup.py` copies the configured Google spreadsheet into a Google Drive backup folder.
- `handlers/utils.py` contains shared helpers, including Google Drive upload functionality.
- `handlers/states.py` defines aiogram FSM states. FSM state uses the dispatcher's in-memory storage and may be lost when the process restarts.
- `requirements.txt` pins Python dependencies.
- `.env.example` documents configuration variable names. It must not contain real secrets.
- `tests/` includes test and manual-run scripts. Inspect a script before treating it as an automated test or running it against live services.

## Telegram Commands

- `/start`: start interacting with the bot.
- `/new_order`: enter an inventory or material order.
- `/set_reminder`: create a scheduled reminder.
- `/report_planning`: record project or work planning information.
- `/additional_working_hours`: record additional work and hours.
- `/daily_summary`: submit a daily activity report as text or a file.
- `/retrieve_data`: choose a worksheet and search its records.

Most data-entry handlers use Gemini to turn free text into structured fields and save the result to a feature worksheet and/or `main_events`. Preserve existing confirmation/edit/cancel flows when changing those handlers.

## Reminder Behavior and Sheet Layout

The `reminders` worksheet is read and written by positional column, not by header text:

- A: created-at timestamp
- B: Telegram chat ID
- C: Telegram message ID
- D: user name
- E: reminder topic
- F: target date in `YYYY-MM-DD` format
- G: target time in `HH:MM` format
- H (or the configured `REMINDER_STATUS_COLUMN`): reminder status

Status values:

- `set`: scheduled, not yet sent. Startup recovery scans these rows and restores their scheduler jobs.
- `sent`: Telegram successfully sent the notification and the bot updated the row.

Reject invalid or past reminder date/time values before writing to Sheets. If a pending reminder's scheduled time passed while the server was down, recovery schedules it immediately and sends a delayed-delivery notice. Do not mark it `sent` before Telegram send succeeds.

The row lookup after appending uses the pair `(chat_id, message_id)` from columns B and C to obtain the sheet row number. That row number is used to update column H after delivery. If changing the sheet layout, update creation, lookup, recovery, and status update together.

## Configuration and Secrets

Configuration is read from environment variables, commonly via `.env` for local development. See `.env.example` for the current list. Important variables include:

- `TELEGRAM_TOKEN`: Telegram bot token.
- `GEMINI_API_KEY`: Gemini API key.
- `GOOGLE_SHEET_NAME`: spreadsheet title.
- `UPLOAD_FILES_FOLDER_ID`: Google Drive folder for uploaded daily-summary files.
- `BACKUP_FOLDER_ID`: Google Drive folder for spreadsheet backups.
- `WEBHOOK_BASE_URL`: public HTTPS origin for Telegram, such as the current ngrok URL in local testing. Do not append `WEBHOOK_PATH` here.
- `WEBHOOK_PATH`: webhook route; defaults to `/telegram/webhook` and must match the aiohttp route.
- `WEBHOOK_SECRET`: secret used to validate webhook requests.
- `HOST`: HTTP bind interface; defaults to `0.0.0.0`.
- `PORT`: HTTP listening port; defaults to `8080` and may be supplied by the hosting environment.
- `MAX_ROW_RETRIEVE`: maximum number of records returned by retrieval.
- `REMINDER_STATUS_COLUMN`: reminder status column number; defaults to `8` (column H).

The app expects Google service-account credentials in `credentials.json`. The Drive backup also expects an OAuth `token.json`. Never commit `.env`, tokens, credentials, private webhook secrets, or their contents. Do not print secrets in logs or documentation.

## Development Guidance

- Follow the existing aiogram router and FSM patterns in neighboring handlers.
- Keep changes scoped to the relevant feature and avoid unrelated refactors.
- Preserve Google Sheets column order unless a deliberate migration is part of the change.
- Treat user input and AI-extracted values as untrusted; validate required values, dates, and times before saving or scheduling.
- Avoid running live Telegram, Google Sheets, Gemini, or Drive operations during tests unless the target account and side effects are understood and authorized.
- Do not run long polling alongside webhook delivery.
- Do not add persistent FSM storage or another database unless requirements change.
- Respect existing user modifications; do not discard unrelated working-tree changes.

## Local Development

Install dependencies in a virtual environment, configure `.env` and the required Google credential files, then expose the HTTP port with ngrok. Set `WEBHOOK_BASE_URL` to the public HTTPS URL ngrok provides, without the path, and run:

```powershell
python bot_main.py
```

The ngrok URL may change between runs, so update `WEBHOOK_BASE_URL` when it changes. The webhook server's route is the base URL plus `WEBHOOK_PATH`.

## Validation

For a focused syntax check after changing the entry point or reminder module:

```powershell
python -m py_compile bot_main.py handlers/reminders.py
```

Run focused tests where available. Do not assume manual scripts in `tests/` are safe to execute against live credentials without inspecting them first.
