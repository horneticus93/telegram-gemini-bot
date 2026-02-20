# Datasette Web UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Datasette container that serves the bot's SQLite memory database as a read-write web UI on port 8001, accessible from the local network.

**Architecture:** A second Docker service (`datasette`) is added to `docker-compose.yml`. It uses a dedicated `Dockerfile.datasette` that installs `datasette` and the `datasette-write-ui` plugin. Both the bot and datasette containers share the existing `bot_data` named volume, so they both access the same `memory.db` file.

**Tech Stack:** Python `datasette` + `datasette-write-ui` plugin, Docker multi-service compose.

---

## Task 1: Create Dockerfile.datasette and update docker-compose.yml

This task has no application code, so there are no unit tests. Verification is done by building and running the containers.

**Files:**
- Create: `Dockerfile.datasette`
- Modify: `docker-compose.yml`

**Step 1: Create `Dockerfile.datasette`** with exactly this content:

```dockerfile
FROM python:3.12-slim

RUN pip install --no-cache-dir datasette datasette-write-ui

EXPOSE 8001

CMD ["datasette", "/app/data/memory.db", \
     "--host", "0.0.0.0", \
     "--port", "8001", \
     "--setting", "allow_execute_sql", "on"]
```

**Step 2: Replace `docker-compose.yml`** with exactly this content:

```yaml
services:
  bot:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file: .env
    volumes:
      - bot_data:/app/data
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  datasette:
    build:
      context: .
      dockerfile: Dockerfile.datasette
    restart: unless-stopped
    ports:
      - "8001:8001"
    volumes:
      - bot_data:/app/data
    logging:
      driver: "json-file"
      options:
        max-size: "5m"
        max-file: "2"

volumes:
  bot_data:
```

**Step 3: Build and verify locally**

```bash
docker compose build datasette
```

Expected: builds successfully with no errors.

```bash
docker compose up -d
```

Expected: both `bot` and `datasette` containers start.

```bash
docker compose ps
```

Expected: both services show as `running`.

**Step 4: Open the UI**

Open `http://localhost:8001` in your browser.

Expected: Datasette UI loads showing `memory.db` with the `user_profiles` table.

Click a row → you should see an edit button (from `datasette-write-ui`).

**Step 5: Stop local containers**

```bash
docker compose down
```

**Step 6: Commit**

```bash
git add Dockerfile.datasette docker-compose.yml
git commit -m "feat: add Datasette web UI for browsing and editing user profiles"
```

---

## Task 2: Push via PR and deploy on NAS

**Step 1: Push branch and open PR**

Create a feature branch and push:

```bash
git checkout -b feature/datasette-web-ui
git push -u origin feature/datasette-web-ui
```

Open PR at: `https://github.com/horneticus93/telegram-gemini-bot/compare/feature/datasette-web-ui`

**Step 2: After PR is merged — deploy on NAS**

SSH into NAS:

```bash
cd ~/app/horneticus93/telegram-gemini-bot
git pull
sudo docker compose down
sudo docker compose up -d --build
sudo docker compose logs -f
```

Expected: both `bot` and `datasette` services start with no errors.

**Step 3: Verify**

Open `http://<NAS-IP>:8001` from your Mac browser.

Expected: Datasette UI loads showing `user_profiles` table with all stored profiles.
