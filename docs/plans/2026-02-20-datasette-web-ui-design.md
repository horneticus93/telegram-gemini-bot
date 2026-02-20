# Datasette Web UI Design

**Goal:** Add a read-write web UI for browsing and editing the bot's SQLite memory database, accessible from the local home network.

**Architecture:** A second `datasette` container is added to `docker-compose.yml`. It shares the existing `bot_data` named volume (read-write) and serves `memory.db` over HTTP on port `8001`. The bot container is unchanged.

**Components:**
- `datasette` service using a small custom Dockerfile based on `python:3.12-slim`
- Installs `datasette` and `datasette-write` plugin via pip
- Mounts `bot_data:/app/data` (same volume as the bot)
- Starts with `datasette /app/data/memory.db --host 0.0.0.0 --port 8001`
- Port `8001` exposed on the NAS — accessible at `http://nas-ip:8001`
- `restart: unless-stopped`

**Data flow:** Both containers share the same named Docker volume. Datasette opens the SQLite file directly. The bot writes profiles; the user edits via browser. SQLite handles concurrent access safely at this traffic level.

**Security:** No authentication — local network only.

**No changes to:** bot code, `bot/memory.py`, `bot/handlers.py`, or any tests.
