import os
import re
import base64
import asyncio
import hashlib
import time
from contextlib import asynccontextmanager

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from agents import FactCheckAgent, RAGAgent, VisionAgent, SynthesisAgent, WebSearchAgent

# ── 啟動時初始化所有 Agent ──────────────────────────────────────────────────
fact_check_agent: FactCheckAgent
rag_agent: RAGAgent
vision_agent: VisionAgent
synthesis_agent: SynthesisAgent
web_search_agent: WebSearchAgent


@asynccontextmanager
async def lifespan(app: FastAPI):
    global fact_check_agent, rag_agent, vision_agent, synthesis_agent, web_search_agent
    print("初始化 Agents...")
    fact_check_agent = FactCheckAgent()
    rag_agent = RAGAgent()
    vision_agent = VisionAgent()
    synthesis_agent = SynthesisAgent()
    web_search_agent = WebSearchAgent()
    print("Agents 初始化完成")
    yield


app = FastAPI(title="假訊息情報中心", version="1.0.0", lifespan=lifespan)

# ── 查核結果快取（in-memory，TTL 1 小時）─────────────────────────────────────
_check_cache: dict[str, tuple[float, dict]] = {}   # key -> (timestamp, result)
_CACHE_TTL = 3600  # seconds

def _cache_key(content: str, mode: str) -> str:
    return hashlib.sha256(f"{mode}::{content.strip()}".encode()).hexdigest()

def _cache_get(key: str) -> dict | None:
    entry = _check_cache.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    if entry:
        del _check_cache[key]
    return None

def _cache_set(key: str, result: dict) -> None:
    _check_cache[key] = (time.time(), result)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")


# ── Request / Response Models ─────────────────────────────────────────────────

class CheckRequest(BaseModel):
    content: str
    mode: str = "citizen"          # "citizen" | "professional"
    follow_up: Optional[str] = None
    conversation_history: Optional[list] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "假訊息情報中心 API 運行中", "docs": "/docs"}


def _is_url(text: str) -> bool:
    return bool(re.match(r"https?://\S+", text.strip()))


async def _fetch_article(url: str) -> str:
    """抓取網頁內文，回傳純文字（最多 3000 字）。失敗時回傳空字串。"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            # 讓 BeautifulSoup 自動偵測編碼（傳 bytes）
            soup = BeautifulSoup(resp.content, "html.parser")
            # 移除 script / style / nav / footer
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            # 優先取 article 或 main，否則取 body
            body = soup.find("article") or soup.find("main") or soup.body
            text = body.get_text(separator="\n", strip=True) if body else ""
            # 壓縮多餘空行
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            return "\n".join(lines)[:3000]
    except Exception:
        return ""


@app.post("/check")
async def check_message(req: CheckRequest):
    """文字 / 網址查核（一般民眾或專業人員模式）。"""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content 不能為空")

    # follow_up 追問不走快取（每次問題不同）
    if not req.follow_up:
        cache_key = _cache_key(req.content, req.mode)
        cached = _cache_get(cache_key)
        if cached:
            cached["cached"] = True
            return cached

    # URL 輸入時先抓取文章內文
    analysis_content = req.content
    fetched_text = ""
    if _is_url(req.content):
        fetched_text = await _fetch_article(req.content)
        if fetched_text:
            analysis_content = f"來源網址：{req.content}\n\n文章內容：\n{fetched_text}"

    # 1. RAG + Fact Check + Web Search 並行執行
    rag_results, fact_check_results, web_search_results = await asyncio.gather(
        rag_agent.retrieve(analysis_content),
        fact_check_agent.check(req.content),
        web_search_agent.search(analysis_content),
    )

    # 2. Synthesis：匯整結果並生成最終報告
    synthesis = await synthesis_agent.synthesize(
        content=analysis_content,
        rag_results=rag_results,
        fact_check_results=fact_check_results,
        web_search_results=web_search_results,
        mode=req.mode,
        follow_up=req.follow_up,
        conversation_history=req.conversation_history,
    )

    result = {
        "mode": req.mode,
        "credibility_score": synthesis.get("credibility_score", 0.5),
        "credibility_label": synthesis.get("credibility_label", "待查證"),
        "analysis": synthesis.get("analysis", ""),
        "steps": synthesis.get("steps", []),
        "dimensions": synthesis.get("dimensions"),
        "key_findings": synthesis.get("key_findings", []),
        "uncertainties": synthesis.get("uncertainties", []),
        "media_literacy_tip": synthesis.get("media_literacy_tip", ""),
        "rag_sources": await _format_rag_sources(rag_results),
        "fact_check_claims": fact_check_results.get("claims", []),
        "cached": False,
    }

    if not req.follow_up:
        _cache_set(cache_key, result)

    return result


async def _fetch_title(url: str) -> str:
    """抓取網頁 <title>，失敗回傳空字串。"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")
            tag = soup.find("title")
            return tag.get_text(strip=True) if tag else ""
    except Exception:
        return ""


async def _format_rag_sources(rag_results: dict, min_similarity: int = 50) -> list:
    docs = rag_results.get("documents", [])
    metas = rag_results.get("metadatas", [])
    distances = rag_results.get("distances", [])
    candidates = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        if meta is None:
            meta = {}
        distance = distances[i] if i < len(distances) else 1.0
        similarity = round((1 - distance) * 100)
        if similarity < min_similarity:
            continue
        text = meta.get("original_text") or doc[:200]
        reply = meta.get("reply") or ""
        article_id = meta.get("article_id", "")
        if article_id:
            cofacts_url = f"https://cofacts.tw/article/{article_id}"
        else:
            import urllib.parse
            cofacts_url = "https://cofacts.tw/search?q=" + urllib.parse.quote(text[:80], safe="")
        candidates.append({
            "text": text,
            "reply": reply,
            "has_reply": bool(reply.strip()),
            "category": meta.get("category", "未分類"),
            "similarity": similarity,
            "cofacts_url": cofacts_url,
        })

    if not candidates:
        return []

    # 若 text 本身是 URL，並行抓取頁面標題
    async def enrich(src: dict) -> dict:
        t = src["text"].strip()
        url_match = re.match(r"(https?://\S+)", t)
        if url_match:
            first_url = url_match.group(1).rstrip(".,)")
            src["url"] = first_url
            src["title"] = await _fetch_title(first_url)
        return src

    return list(await asyncio.gather(*[enrich(s) for s in candidates]))


@app.post("/check/image")
async def check_image(
    image: UploadFile = File(...),
    mode: str = Form("citizen"),
):
    """圖片查核：AI 生成辨識（Gemini Vision + Chain-of-Thought）。"""
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if image.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"不支援的圖片格式：{image.content_type}")

    image_bytes = await image.read()
    image_b64 = base64.b64encode(image_bytes).decode()

    vision_results = await vision_agent.analyze(image_b64, image.content_type)
    synthesis = await synthesis_agent.synthesize_image(vision_results, mode)

    return {
        "mode": mode,
        "credibility_label": synthesis.get("credibility_label", "待查證"),
        "analysis": synthesis.get("analysis", ""),
        "media_literacy_tip": synthesis.get("media_literacy_tip", ""),
        "ai_probability": vision_results.get("ai_probability", 0.5),
        "ai_label": vision_results.get("ai_label", "無法判斷"),
        "anomalies": vision_results.get("anomalies", []),
        "visual_description": vision_results.get("visual_description", ""),
        "confidence": vision_results.get("confidence", "低"),
        # professional mode 專用欄位
        "key_findings": synthesis.get("key_findings", []),
        "technical_dimensions": synthesis.get("technical_dimensions", []),
        "uncertainties": synthesis.get("uncertainties", []),
    }


class QuickCheckRequest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None


@app.post("/check/quick")
async def quick_check(req: QuickCheckRequest):
    """快速查核指定 URL 或文字，回傳可信度標籤與摘要，供 RAG 卡片內嵌使用。"""
    if req.url and _is_url(req.url.strip()):
        article_text = await _fetch_article(req.url.strip())
        content = f"來源網址：{req.url}\n\n文章內容：\n{article_text}" if article_text else req.url
    elif req.text and req.text.strip():
        content = req.text.strip()
    else:
        raise HTTPException(status_code=400, detail="請提供 url 或 text")
    result = await synthesis_agent.quick_check(content)
    return result


@app.get("/dashboard")
async def get_dashboard():
    """回傳假訊息分類統計，供儀表板使用。"""
    return rag_agent.get_dashboard_stats()


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}



# 提供前端靜態檔案（放最後，避免攔截 API 路由）
if os.path.isdir(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
