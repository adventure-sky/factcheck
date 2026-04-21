FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 套件
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製全部程式碼
COPY . .

# 啟動
WORKDIR /app/backend
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
