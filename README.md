# Bot Send

Python Telegram bot (aiogram) + Telegram client (Telethon) with MySQL, SOLID-style layering.

## Setup

1) Create virtual environment:

```
python -m venv .venv
```

2) Activate:

Windows (PowerShell):

```
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```
source .venv/bin/activate
```

3) Install dependencies:

```
pip install -r requirements.txt
```

4) Create `.env` from `.env.example` and fill tokens.
5) Ensure MySQL is running locally.

Web auth page runs at `http://127.0.0.1:8080` by default (see `.env`).

Example SQL:

```
CREATE DATABASE bot;
CREATE USER 'bot'@'%' IDENTIFIED BY 'bot';
GRANT ALL PRIVILEGES ON bot.* TO 'bot'@'%';
```

## Migrations

```
alembic upgrade head
```

## Run

```
python -m app.main
```

## Add account session

Use bot command `/account_add`.
You can log in with QR or via a web page (code/password are not sent in Telegram).

## Admin commands

- `/admin`
- `/account_add`
- `/account_list`
- `/account_activate <id>`
- `/account_deactivate <id>`
- `/parse <chat_username_or_link>`
- `/parse_chats`
- `/mailing_new`
- `/mailing_pause <id>`
- `/mailing_resume <id>`
- `/mailing_status <id>`

## Notes

- Accounts are added via the bot (no console auth).
- Mailings are sent via Telegram accounts (Telethon), not the Bot API.
- Users can manage their own accounts and mailings (SaaS-style).
- QR login is the safest. Web login is useful if QR is not available.
