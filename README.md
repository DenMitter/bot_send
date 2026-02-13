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

## Deploy (server)

This project runs:
- the bot (aiogram long polling)
- a small HTTP server for the web-auth page (`/auth/<token>`)

To make the web-auth link work for users outside your server, you must change the bind host and (most importantly) the public base URL.

1) Build the web-auth frontend (optional but recommended):

```
cd app/web_auth
node -v
npm ci
npm run build
```

Note: `app/web_auth` uses Vite and requires Node.js 18+ (recommended: 20 LTS+). If you see `SyntaxError: Unexpected token {` from `node_modules/vite/...`, your server Node.js is too old — upgrade Node.js or build locally and copy `app/web_auth/dist` to the server.

2) Set production env vars in `.env`:

- `WEB_AUTH_BASE_URL` must be your public URL (no trailing slash), e.g. `https://example.com`
- if you expose the port directly: `WEB_AUTH_HOST=0.0.0.0` and open `WEB_AUTH_PORT` in firewall
- if you use Nginx/Caddy as HTTPS reverse proxy (recommended): keep `WEB_AUTH_HOST=127.0.0.1` and proxy to `WEB_AUTH_PORT`

Example Nginx location:

```
location / {
  proxy_pass http://127.0.0.1:8080;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
}
```

3) Run migrations and start the app on the server:

```
alembic upgrade head
python -m app.main
```

## Add account session

Use bot command `/account_add`.
You can log in with QR or via a web page (code/password are not sent in Telegram).

## Console session file

If you need to create a Telegram `.session` file without the bot UI, run the helper script after configuring `.env`:
```
python scripts/generate_session_file.py --phone +380501234567
```
The script writes the file to `storage/sessions` by default, accepts `--session-dir` to override the folder, `--force` to overwrite an existing file, and `--print-string` to echo the StringSession representation when you later add accounts manually.

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
