# 假訊息情報中心 · Disinformation Intelligence Center

> **「不只告訴你答案，而是教你怎麼判斷。」**

AI 驅動的假訊息查核工具，結合 RAG 語義檢索、Google Fact Check、圖片 AI 偵測，以 Intelligence HUD 介面引導使用者建立批判性思考能力。

---

## 特色

| 一般工具 | 本工具 |
|---------|--------|
| 只給「真/假」結論 | 逐步拆解查核邏輯，說明判斷依據 |
| 純文字查核 | 文字 / 網址 / 圖片三種輸入 |
| 單一結果頁 | 公民版（教育式）+ 專業版（情報報告）|

---

## 技術架構

```
前端          純 HTML + CSS + JS（Intelligence HUD 風格）
後端          Python FastAPI
AI 分析       Groq API — llama-3.3-70b-versatile
AI 圖片辨識   AI or Not API（98.9% 準確率）+ Groq Vision
語義檢索      ChromaDB + paraphrase-multilingual-MiniLM-L12-v2
資料來源      Cofacts 台灣事實查核資料庫（265,952 筆）
事實查核      Google Fact Check Tools API
網路搜尋      Google Custom Search API
```

---

## 功能

- **文字查核**：輸入訊息或謠言，AI 逐步拆解查核依據
- **網址查核**：貼上新聞連結，自動擷取內文並分析
- **圖片查核**：上傳圖片，偵測是否為 AI 生成，信心值 + 掃描動畫
- **公民版**：3–4 步驟引導式分析，附識讀小撇步
- **專業版**：情報報告格式，含四維度評分、關鍵發現、技術鑑識
- **Cofacts 相似案例**：語義最近的歷史查核記錄，附相似度 % 與回應
- **追問 AI 分析師**：查核結果後可持續對話深入追問
- **分享連結**：一鍵產生 base64 share URL，無須後端即可還原結果
- **儀表板**：Cofacts 資料庫分類統計（TEXT / IMAGE / VIDEO / AUDIO）

---

## 快速開始

### 1. 複製專案

```bash
git clone https://github.com/adventure-sky/factcheck.git
cd factcheck
```

### 2. 下載 Cofacts 資料

從 [Cofacts Dataset](https://github.com/cofacts/opendata) 下載以下三個 CSV，放入 `backend/data/cofacts/`：

- `articles.csv`
- `replies.csv`
- `article_replies.csv`

### 3. 設定環境變數

```bash
cp backend/.env.example backend/.env
```

填入以下 API Key（`.env`）：

```
GROQ_API_KEY=           # 必填：Groq Console 取得
GOOGLE_FACT_CHECK_API_KEY=  # 必填：Google Cloud Console
AIORNOT_API_KEY=        # 必填：AI or Not 平台
GOOGLE_SEARCH_API_KEY=  # 選填：Google Custom Search
GOOGLE_SEARCH_CX=       # 選填：Custom Search Engine ID
```

### 4. 建立 Python 環境

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Mac/Linux

pip install -r requirements.txt
```

### 5. 建置向量資料庫

```bash
python scripts/build_vector_db.py
python scripts/gen_stats.py
```

> 建置約需 30–60 分鐘（265K 筆資料向量化）

### 6. 啟動伺服器

```bash
uvicorn main:app --reload --port 8000
```

開啟 [http://localhost:8000](http://localhost:8000)

---

## 目錄結構

```
factcheck/
├── backend/
│   ├── main.py                  # FastAPI 主程式
│   ├── agents/
│   │   ├── fact_check_agent.py  # Google Fact Check API
│   │   ├── rag_agent.py         # ChromaDB 語義檢索 + Reranking
│   │   ├── vision_agent.py      # AI or Not + Groq Vision 圖片辨識
│   │   ├── synthesis_agent.py   # Groq llama-3.3-70b 查核報告生成
│   │   └── web_search_agent.py  # Google Custom Search
│   ├── scripts/
│   │   ├── build_vector_db.py   # 建置 ChromaDB
│   │   ├── gen_stats.py         # 產生儀表板統計快取
│   │   └── backup_db.py         # 備份向量資料庫
│   ├── data/cofacts/            # Cofacts CSV（需自行下載）
│   └── requirements.txt
├── frontend/
│   ├── index.html               # 查核終端（首頁）
│   ├── result-citizen.html      # 公民版結果頁
│   ├── result-professional.html # 專業版結果頁
│   ├── dashboard.html           # 統計儀表板
│   ├── css/style.css
│   └── js/app.js
└── .env.example
```

---

## 部署（Zeabur）

1. 連結此 GitHub repo
2. 設定 `backend/` 為根目錄，啟動指令：`uvicorn main:app --host 0.0.0.0 --port 8080`
3. 掛載 Volume 至 `/app/chroma_db`（儲存向量資料庫）
4. 設定所有環境變數
5. 部署完成後執行：`python scripts/gen_stats.py`

---

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| `POST` | `/check` | 文字 / 網址查核 |
| `POST` | `/check/image` | 圖片查核 |
| `POST` | `/check/quick` | RAG 卡片快速查核 |
| `GET` | `/dashboard` | 資料庫統計 |
| `GET` | `/health` | 服務健康檢查 |

---

## 資料來源

- [Cofacts 台灣事實查核資料庫](https://cofacts.tw) — CC0 開放資料
- [Google Fact Check Tools](https://developers.google.com/fact-check/tools/api)
- [AI or Not](https://www.aiornot.com) — AI 圖片辨識

---

## 免責聲明

本工具為輔助判斷用途，查核結果僅供參考，不構成最終事實認定。重要決策請以官方查核機構（如[台灣事實查核中心](https://tfc-taiwan.org.tw)）為準。
