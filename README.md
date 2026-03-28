# Avivi Automation Manager

Monorepo with **Avivi_Client** (PyQt6) and **Avivi_Master** (FastAPI).

## Setup

```bash
cd avivi-auto
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## Run Master server

```bash
avivi-master
# or: uvicorn avivi_master.main:app --reload --host 0.0.0.0 --port 8000
```

Set `AVIVI_MASTER_SECRET`, `AVIVI_ADMIN_API_KEY`, and optional Telegram vars (see `avivi_master/config.py`).

## Run Client

```bash
avivi-client
```

Configure Master URL and API key in Settings.

## WhatsApp bridge (optional)

```bash
cd Avivi_Client/avivi_client/node_bridge
npm install
```

Requires Node.js 18+ (client bootstrap can install on Windows).

## Security (encryption)

Client–Master payloads (heartbeat, missions, commands, events) use **Fernet** from the `cryptography` library ([`avivi_shared/crypto.py`](shared/avivi_shared/crypto.py)): AES-128 in CBC mode plus HMAC-SHA256 for authentication, not raw “AES-256” end-to-end. For stricter algorithms, define a separate spec before changing wire format.
