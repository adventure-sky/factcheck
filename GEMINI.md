# 假訊息情報中心（Disinformation Intelligence Center）

AI 驅動的假訊息查核工具，核心差異在「教你怎麼判斷」而非只給答案，並支援 AI 生成圖片辨識。面試作品集專案。

## 技術架構

| 層級 | 技術 |
|------|------|
| 前端 | 純 HTML + CSS + JS（Intelligence HUD 風格） |
| 後端 | Python FastAPI（`backend/main.py`） |
| 文字 AI | Groq API — llama-3.3-70b-versatile |
| 圖片 AI | AI or Not API（主）+ Groq Vision llama-4-scout（描述輔助） |
| 向量 DB | ChromaDB — 265,952 筆 Cofacts 查核資料 |
| Embedding | paraphrase-multilingual-MiniLM-L12-v2（中文語義） |
| 事實查核 | Google Fact Check API |

## 目錄結構

```
fact-checking/
├── backend/
│   ├── main.py                  # FastAPI 主程式，所有 API 路由
│   ├── .env                     # API keys（GROQ / AIORNOT / GOOGLE_FACT_CHECK）
│   ├── agents/
│   │   ├── vision_agent.py      # 圖片 AI 生成偵測（AI or Not + Groq Vision）
│   │   ├── synthesis_agent.py   # 報告生成（llama-3.3-70b）
│   │   ├── fact_check_agent.py  # Google Fact Check API
│   │   └── rag_agent.py         # ChromaDB 語義檢索
│   └── chroma_db/               # 向量資料庫（本地）
└── frontend/
    ├── index.html               # 查核首頁（文字 / URL / 圖片輸入）
    ├── result-citizen.html      # 逐步查核結果（公民版）
    ├── result-professional.html # 完整情報報告（專業版）
    ├── css/style.css            # 全站設計系統（HUD 風格）
    └── js/app.js                # 前端邏輯（送出查核、存 sessionStorage）
```

## API 路由

| 路由 | 說明 |
|------|------|
| `POST /check` | 文字 / URL 查核，回傳步驟、分析、可信度分數 |
| `POST /check/image` | 圖片查核，回傳 ai_probability、ai_label、視覺描述 |
| `GET /dashboard` | 儀表板統計資料 |
| `GET /health` | 健康檢查 |

## 啟動方式

```bash
cd backend
venv/Scripts/activate      # Windows
uvicorn main:app --reload --port 8000
```

前端靜態檔由後端 `app.mount("/", StaticFiles(...))` 提供，從 `http://localhost:8000` 瀏覽。

## 查核流程（文字）

1. `FactCheckAgent` — Google Fact Check API 搜尋
2. `RAGAgent` — ChromaDB 語義檢索（≥50% 相似度）
3. `SynthesisAgent` — llama-3.3-70b 整合結果，輸出步驟化報告 + credibility_score

## 查核流程（圖片）

1. `VisionAgent._call_aiornot()` — AI or Not API，回傳 ai_probability（0–1）
2. `VisionAgent` Groq Vision — 視覺描述與異常分析（永遠執行）
3. `SynthesisAgent.synthesize_image()` — 整合輸出

## 前端資料流

- 查核結果存入 `sessionStorage("checkResult")`（含 inputType、imageDataURL）
- 結果頁讀取 sessionStorage 渲染，圖片查核使用 `IMAGE_LABEL_CONFIG`（非文字用的 `LABEL_CONFIG`）

## 重要設計決策

- `AIORNOT_API_KEY` 必須在函式內讀取（`os.environ.get`），不能放 module 頂層，否則 `load_dotenv()` 尚未執行時會讀到空值
- 圖片查核標籤獨立於文字查核（高度疑似 AI 生成 / 可能為 AI 生成 / 疑似真實照片 / 確認為真實照片）
- gauge 對圖片顯示 AI PROBABILITY，對文字顯示 CREDIBILITY

## 優化與加強方向（Interview Roadmap）

### 1. UX 體驗增強（Storytelling）
- **Agent 動態處理進度**：Loading 期間循環顯示後端 Agent 的即時動作（`[DB] 正在檢索向量資料庫...`），減少用戶焦慮並展現後端複雜度
- **公民/專業版無縫切換**：結果頁提供一鍵 Toggle，無需重新查核即可在兩種報告之間切換（利用 `sessionStorage` 狀態管理）
- **打字機效果**：AI 追問功能的回覆改用逐字輸出，提升對話互動感

### 2. UI 視覺細節（Visual Fidelity）
- **數字解碼動畫**：可信度分數載入時做「隨機數字快速跳動後定格」效果，強化即時運算儀式感
- **圖片掃描動畫**：圖片查核頁面對原圖覆蓋掃描線 CSS 動畫，並加偽座標分析裝飾字
- **HUD 風格 Error Modal**：取代原生 `alert()`，建立符合全站視覺的異常處理彈窗

### 3. 技術架構深度（Technical Depth）
- **快取機制**：針對重複查核實作本地 JSON 或 Redis 快取，展現對 API 成本的控制意識
- **RAG Reranking**：在 ChromaDB 檢索後加一層 LLM 過濾，排除相似但無關的結果，提升報告精準度
- **引文來源連結**：SynthesisAgent 生成報告時強制標註來源（Cofacts #ID），UI 上可點擊跳轉

### 4. 程式碼品質
- **CSS 語意化變數**：色彩變數進一步語意化（`--color-fakenews`, `--color-verified`）
- **響應式優化**：sys-bar 狀態燈在手機版保留，維持品牌感
