import os

PORT = int(os.getenv("QUIZ_PORT", "8080"))

SECRET_KEY = os.getenv("QUIZ_SECRET_KEY", "super-secret-quiz-key-2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

ADMIN_USERNAME = os.getenv("QUIZ_ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("QUIZ_ADMIN_PASSWORD", "")

DATABASE_URL = os.getenv("QUIZ_DATABASE_URL", "sqlite+aiosqlite:///./data/quiz.db")

MAX_TEAMS = 2
QUESTIONS_PER_GAME = 12
ANSWER_TIME_SECONDS = 20
ANSWER_GRACE_MULTIPLIER = 2  # grace timeout = ANSWER_TIME_SECONDS * this
READING_TIME_SECONDS = 8  # time to read the answer result

# Room system
ROOM_INACTIVITY_TIMEOUT_SECONDS = 60
MAX_PLAYERS_PER_TEAM = 4
ROOM_CODE_LENGTH = 6

# Telegram bot
TELEGRAM_BOT_TOKEN = os.getenv("QUIZ_TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = os.getenv("QUIZ_TELEGRAM_ADMIN_ID", "")
BASE_URL = os.getenv("QUIZ_BASE_URL", "")  # e.g. https://example.com/quiz

# Backup
BACKUP_SERVER_HOST = os.getenv("QUIZ_BACKUP_HOST", "")
BACKUP_SERVER_USER = os.getenv("QUIZ_BACKUP_USER", "")
BACKUP_SERVER_KEY = os.getenv("QUIZ_BACKUP_KEY", "")
BACKUP_SERVER_PATH = os.getenv("QUIZ_BACKUP_PATH", "/backups/quiz-game/")
BACKUP_INTERVAL_DAYS = int(os.getenv("QUIZ_BACKUP_INTERVAL_DAYS", "7"))
