import os
import httpx
from typing import Optional

SEARCH_API_URL = "https://www.googleapis.com/customsearch/v1"


class WebSearchAgent:
    """Google Custom Search：從可信新聞來源搜尋佐證資料。"""

    def __init__(self):
        self.api_key = os.environ.get("GOOGLE_SEARCH_API_KEY", "")
        self.cx = os.environ.get("GOOGLE_SEARCH_CX", "")

    def _extract_query(self, content: str) -> str:
        """從查核內容擷取搜尋關鍵字（取前 120 字，去除 URL）。"""
        import re
        text = re.sub(r"https?://\S+", "", content).strip()
        # 取前 120 字作為查詢
        return text[:120].strip()

    async def search(self, content: str, num: int = 4) -> dict:
        """搜尋並回傳結果清單。失敗時靜默回傳空結果。"""
        if not self.api_key or not self.cx:
            return {"results": []}

        query = self._extract_query(content)
        if not query:
            return {"results": []}

        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": num,
            "lr": "lang_zh-TW",          # 優先繁體中文
            "safe": "active",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(SEARCH_API_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            items = data.get("items", [])
            results = [
                {
                    "title":   item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url":     item.get("link", ""),
                    "source":  item.get("displayLink", ""),
                }
                for item in items
            ]
            return {"results": results}

        except Exception as e:
            print(f"[WebSearchAgent] search failed: {e}")
            return {"results": []}
