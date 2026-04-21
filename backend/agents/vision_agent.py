import os
import json
import base64
import httpx
from groq import Groq

VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

AIORNOT_ENDPOINT = "https://api.aiornot.com/v2/image/sync"
HIVE_ENDPOINT = "https://api.thehive.ai/api/v2/task/sync"

VISION_PROMPT = """你是一位專業的視覺分析專家，專門辨識 AI 生成圖片。請用繁體中文回答。

請用 Chain-of-Thought 方式分析這張圖片，依序執行以下步驟：

### 第一步：描述視覺內容
描述圖片中的主要元素、人物、場景與文字。

### 第二步：檢查 AI 生成跡象
1. **手指結構**：數量、關節是否自然？
2. **光影一致性**：光源方向是否統一，陰影是否合理？
3. **背景細節**：是否有重複紋理、異常模糊或扭曲？
4. **文字可讀性**：圖中文字是否清晰，有無亂碼或扭曲字形？
5. **整體異常**：臉部比例、物體邊緣等是否不自然？

### 第三步：綜合判斷
根據以上觀察，評估 AI 生成可能性並給出判斷依據。

請嚴格以以下 JSON 格式回覆：
{
  "visual_description": "圖片視覺描述",
  "anomalies": ["觀察到的異常1", "觀察到的異常2"],
  "ai_probability": 0.0,
  "ai_label": "高度疑似 AI 生成 / 可能為 AI 生成 / 疑似真實照片 / 確認為真實照片",
  "analysis": "詳細分析說明",
  "confidence": "高 / 中 / 低"
}
"""


def _score_to_label(ai_score: float) -> tuple[str, str]:
    """將 AI 概率分數轉為中文標籤與信心等級。"""
    if ai_score >= 0.75:
        return "高度疑似 AI 生成", "高"
    elif ai_score >= 0.45:
        return "可能為 AI 生成", "中"
    elif ai_score >= 0.2:
        return "疑似真實照片", "中"
    else:
        return "確認為真實照片", "高"


class VisionAgent:
    """圖片分析 Agent：AI or Not（主）→ Hive AI（次）→ Groq Vision（fallback）。"""

    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

    async def _call_aiornot(self, image_bytes: bytes, content_type: str) -> dict | None:
        """呼叫 AI or Not API（98.9% 準確率），回傳解析後結果。失敗時回傳 None。"""
        AIORNOT_API_KEY = os.environ.get("AIORNOT_API_KEY", "")
        if not AIORNOT_API_KEY:
            return None
        try:
            ext = content_type.split("/")[-1] if "/" in content_type else "jpeg"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    AIORNOT_ENDPOINT,
                    headers={"Authorization": f"Bearer {AIORNOT_API_KEY}"},
                    files={"image": (f"image.{ext}", image_bytes, content_type)},
                )
                resp.raise_for_status()
                data = resp.json()

            # 回應結構：{ report: { ai_generated: { verdict, ai: {confidence}, human: {confidence} } } }
            ai_generated = data.get("report", {}).get("ai_generated", {})
            verdict = ai_generated.get("verdict", "unknown")
            ai_conf = ai_generated.get("ai", {}).get("confidence", None)
            human_conf = ai_generated.get("human", {}).get("confidence", None)

            if ai_conf is None and human_conf is None:
                return None

            # 以 ai confidence 作為 ai_probability
            if ai_conf is not None:
                ai_score = float(ai_conf)
            else:
                ai_score = 1.0 - float(human_conf)

            label, confidence = _score_to_label(ai_score)

            return {
                "ai_probability": round(ai_score, 3),
                "ai_label": label,
                "confidence": confidence,
                "_aiornot_verdict": verdict,
            }
        except Exception as e:
            print(f"[AIorNot API Error] {e}")
            return None

    async def _call_hive(self, image_bytes: bytes, content_type: str) -> dict | None:
        """呼叫 Hive AI 生成圖片偵測 API，回傳解析後結果。失敗時回傳 None。"""
        HIVE_API_KEY = os.environ.get("HIVE_API_KEY", "")
        if not HIVE_API_KEY:
            return None
        try:
            ext = content_type.split("/")[-1] if "/" in content_type else "jpeg"
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    HIVE_ENDPOINT,
                    headers={"Authorization": f"Token {HIVE_API_KEY}"},
                    files={"media": (f"image.{ext}", image_bytes, content_type)},
                )
                resp.raise_for_status()
                data = resp.json()

            classes = (
                data.get("status", [{}])[0]
                .get("response", {})
                .get("output", [{}])[0]
                .get("classes", [])
            )
            ai_score = next(
                (c["score"] for c in classes if c.get("class") == "ai_generated"),
                None,
            )
            if ai_score is None:
                return None

            label, confidence = _score_to_label(ai_score)
            return {
                "ai_probability": round(ai_score, 3),
                "ai_label": label,
                "confidence": confidence,
            }
        except Exception as e:
            print(f"[Hive API Error] {e}")
            return None

    async def analyze(self, image_b64: str, content_type: str = "image/jpeg") -> dict:
        image_bytes = base64.b64decode(image_b64)

        # ── 1. AI or Not（主要偵測器）────────────────────────────
        detector_result = await self._call_aiornot(image_bytes, content_type)
        source_label = "AI or Not + Groq Vision"

        # ── 2. Hive AI（備用偵測器）─────────────────────────────
        if detector_result is None:
            detector_result = await self._call_hive(image_bytes, content_type)
            source_label = "Hive AI Detection + Groq Vision"

        # ── 3. Groq Vision：取得視覺描述與異常分析 ───────────────
        try:
            groq_response = self.client.chat.completions.create(
                model=VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{content_type};base64,{image_b64}"
                                },
                            },
                        ],
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            groq_data = json.loads(groq_response.choices[0].message.content)
        except Exception as e:
            groq_data = {
                "visual_description": "",
                "anomalies": [],
                "ai_probability": 0.5,
                "ai_label": "無法分析",
                "analysis": f"視覺分析失敗：{e}",
                "confidence": "低",
            }

        # ── 4. 合併結果：偵測器概率優先，Groq 描述補充 ───────────
        if detector_result:
            return {
                "visual_description": groq_data.get("visual_description", ""),
                "anomalies": groq_data.get("anomalies", []),
                "ai_probability": detector_result["ai_probability"],
                "ai_label": detector_result["ai_label"],
                "analysis": groq_data.get("analysis", ""),
                "confidence": detector_result["confidence"],
                "source": source_label,
            }
        else:
            # 所有偵測器不可用時 fallback 純 Groq Vision
            groq_data["source"] = "Groq Vision (detectors unavailable)"
            return groq_data
