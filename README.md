# Quiz Game

Мультиплеерная викторина на FastAPI с WebSocket, комнатами и таблицей лидеров.

## Возможности

- Создание и подключение к комнатам по коду
- Игра в командах (до 4 игроков в команде, 2 команды на комнату)
- 12 вопросов за игру, 20 секунд на ответ
- Вопросы с картинками и пояснениями
- Админ-панель для управления вопросами
- Таблица лидеров
- Автозакрытие неактивных комнат

## Запуск

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск сервера
python run.py
```

Сервер запустится на `http://0.0.0.0:8000`.

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `QUIZ_SECRET_KEY` | `super-secret-quiz-key-2024` | Секретный ключ для JWT |
| `QUIZ_DATABASE_URL` | `sqlite+aiosqlite:///./data/quiz.db` | URL базы данных |

## Структура проекта

```
app/
  main.py           # Точка входа FastAPI
  config.py          # Настройки приложения
  database.py        # SQLAlchemy async engine
  models.py          # Модели данных
  auth.py            # JWT-аутентификация
  routers/
    rooms.py         # Создание и управление комнатами
    game.py          # Игровая логика
    ws.py            # WebSocket обработчики
    admin.py         # Админ-панель
    leaderboard.py   # Таблица лидеров
    auth_router.py   # Регистрация и вход
  templates/         # Jinja2 шаблоны
  static/            # CSS
data/
  questions.csv      # База вопросов
pictures/            # Картинки к вопросам
tests/               # Pytest тесты
```

## Тесты

```bash
pytest
```
