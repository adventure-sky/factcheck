FROM python:3.11-slim

# PYTHONUNBUFFERED：讓 lifespan 的 print() 即時出現在 Railway logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先裝套件再複製程式碼，改 code 時可重用 layer cache（部署更快）
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# main.py 以 __file__/../frontend 找靜態檔，兩者需維持同層
COPY backend/ ./backend/
COPY frontend/ ./frontend/

WORKDIR /app/backend

# exec 形式：uvicorn 成為 PID 1，Serverless 休眠時能收到 SIGTERM 乾淨關閉
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
