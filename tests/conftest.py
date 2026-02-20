import os
import tempfile

# Set DB_PATH before any bot module is imported — prevents PermissionError
# when bot.handlers tries to create /app/data/ on macOS during tests
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "test_memory.db"))
