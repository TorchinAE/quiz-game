#!/bin/bash
cd /home/mi/quiz-game
QUIZ_PORT="${QUIZ_PORT:-8080}"
while true; do
    echo "$(date) - Starting server on port $QUIZ_PORT..."
    python3 -u -c "import uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=$QUIZ_PORT)"
    echo "$(date) - Server crashed, restarting in 3 seconds..."
    sleep 3
done
