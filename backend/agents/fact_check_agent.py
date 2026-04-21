import os
import httpx

GOOGLE_FACT_CHECK_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


class FactCheckAgent:
    """呼叫 Google Fact Check API 進行跨平台查核。"""

    def __init__(self):
        self.api_key = os.environ.get("GOOGLE_FACT_CHECK_API_KEY", "")

    async def check(self, query: str, language_code: str = "zh") -> dict:
        if not self.api_key:
            return {"claims": [], "warning": "GOOGLE_FACT_CHECK_API_KEY 未設定"}

        params = {
            "key": self.api_key,
            "query": query,
            "languageCode": language_code,
            "pageSize": 5,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(GOOGLE_FACT_CHECK_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return {"claims": [], "error": str(e)}

        claims = []
        for item in data.get("claims", []):
            review = item.get("claimReview", [{}])[0]
            claims.append({
                "text": item.get("text", ""),
                "claimant": item.get("claimant", ""),
                "rating": review.get("textualRating", ""),
                "url": review.get("url", ""),
                "publisher": review.get("publisher", {}).get("name", ""),
                "review_date": review.get("reviewDate", ""),
            })

        return {"claims": claims}
