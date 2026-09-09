#!/bin/bash
cd /home/mi/quiz-game
while true; do
    echo "$(date) - Starting server..."
    python3 -u -c "import uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=8000)"
    echo "$(date) - Server crashed, restarting in 3 seconds..."
    sleep 3
done
