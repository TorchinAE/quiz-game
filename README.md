# Quiz Game (Квиз)

Мультиплеерная викторина на FastAPI с WebSocket, комнатами и таблицей лидеров.

## Возможности

- Создание и подключение к комнатам по коду или QR-ссылке
- Игра в командах (до 4 игроков в команде, 2 команды на комнату)
- Настраиваемое время на ответ и чтение результата
- Вопросы с картинками, пояснениями и уровнями сложности (1–3 балла)
- Наблюдатели — смотрят игру без участия
- Регистрация и гостевой вход
- Предложение тем для голосования
- Таблица лидеров и статистика
- Админ-панель с управлением вопросами, темами, пользователями и настройками
- Email-уведомления (SMTP) и Telegram-бот
- Автоматические бэкапы
- Автозакрытие неактивных комнат

## Запуск

```bash
pip install -r requirements.txt
python run.py
```

Сервер запустится на `http://0.0.0.0:8080`.

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `QUIZ_PORT` | `8080` | Порт сервера |
| `QUIZ_SECRET_KEY` | `super-secret-quiz-key-2024` | Секретный ключ для JWT |
| `QUIZ_DATABASE_URL` | `sqlite+aiosqlite:///./data/quiz.db` | URL базы данных |
| `QUIZ_ADMIN_USERNAME` | — | Логин администратора |
| `QUIZ_ADMIN_PASSWORD` | — | Пароль администратора |
| `QUIZ_TELEGRAM_BOT_TOKEN` | — | Токен Telegram-бота |
| `QUIZ_TELEGRAM_ADMIN_ID` | — | ID администратора в Telegram |
| `DEPLOY_HOST` | — | Адрес сервера (для ссылок в письмах) |
| `QUIZ_BASE_URL` | — | Базовый URL (переопределяет DEPLOY_HOST) |
| `ADMIN_MAIL` | — | Email администратора |
| `ADMIN_MAIL_SERVER` | — | SMTP-сервер |
| `ADMIN_MAIL_PORT` | `587` | SMTP-порт |
| `ADMIN_MAIL_DEFAULT_SENDER` | — | Email отправителя |
| `ADMIN_MAIL_PASSWORD` | — | Пароль SMTP |
| `ADMIN_MAIL_USE_SSL` | `false` | Использовать SSL |
| `ADMIN_MAIL_USE_TLS` | `true` | Использовать STARTTLS |

## Структура проекта

```
app/
  main.py           # Точка входа FastAPI, фоновые задачи
  config.py          # Настройки приложения
  settings.py        # Игровые настройки из БД
  database.py        # SQLAlchemy async engine
  models.py          # Модели данных
  auth.py            # JWT-аутентификация
  email_notifier.py  # Email-уведомления (фоновые)
  telegram_bot.py    # Telegram-бот
  backup.py          # Автоматические бэкапы
  routers/
    rooms.py         # Создание и управление комнатами
    game.py          # Игровая логика (legacy)
    ws.py            # WebSocket обработчики
    admin.py         # Админ-панель API
    leaderboard.py   # Таблица лидеров
    auth_router.py   # Регистрация и вход
    suggestions.py   # Предложение и голосование за темы
  templates/         # Jinja2 шаблоны
  static/            # CSS, статические файлы
  bot/               # Telegram-бот (хендлеры)
data/
  questions.csv      # База вопросов
pictures/            # Картинки к вопросам
tests/               # Pytest тесты
```

## Тесты

```bash
pytest
```

## Деплой

Деплой автоматизирован через GitHub Actions: при пуше в ветку `quiz-game` запускаются линтинг, тесты и деплой на сервер через SSH.
