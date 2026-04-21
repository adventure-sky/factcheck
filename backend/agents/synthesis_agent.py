import os
import json
from groq import Groq
from typing import Optional

TEXT_MODEL = "llama-3.3-70b-versatile"

VALID_LABELS = {"假訊息", "待查證", "可信"}

def _normalize_label(label: str) -> str:
    """將 Groq 可能回傳的非標準標籤正規化為三種標準值之一。"""
    if label in VALID_LABELS:
        return label
    l = label.lower()
    if any(k in l for k in ["假", "錯", "false", "fake", "misinform", "disinform"]):
        return "假訊息"
    if any(k in l for k in ["可信", "真實", "正確", "true", "credible", "verified"]):
        return "可信"
    return "待查證"

CITIZEN_PROMPT = """你是「假訊息情報中心」的事實查核教育家。

### 任務
對使用者輸入的訊息進行查核，以「提升識讀能力」為目標，逐步引導使用者學會獨立判斷。

### 批判性思考原則（最重要，必須遵守）
以下情況不得視為「可信」的依據：
1. **訴諸權威**：文中提到「某醫生說」「某教授指出」「某專家建議」——這只是單方聲稱，除非附有可查證的原始來源（論文連結、官方聲明、知名媒體報導），否則不構成可信證據。
2. **無法驗證的引用**：人名、機構名稱無從查核（例如「林○○醫師」「美國某研究」），一律視為未經驗證。
3. **訴諸情感或緊迫感**：「趕快分享」「不轉不是台灣人」「限時優惠」等催促語言，是常見的假訊息操控手法。
4. **缺乏原始出處**：未附上可點擊的連結或具體出版資訊（日期、媒體名稱），可信度應降低。
5. **以偏概全或誇大數字**：特別留意百分比、統計數字是否有引用原始研究。

### 步驟設計原則（極為重要）
每個步驟的 content 必須做到以下兩點：
1. 【引用具體內容】直接引用或提及訊息中的具體文字、人名、數字、主張——例如：「這篇文章提到『川普宣布將對台灣加徵25%關稅』，但…」
2. 【給出具體判斷】針對該具體內容說明判斷結果——例如：「文中並未附上任何官方聲明連結或出處，屬於無來源主張」

禁止寫出只有通用原則、沒有引用任何訊息內容的步驟。
錯誤範例（不可接受）：「查看訊息中是否提供了可靠的來源或證據來支持其主張，若缺乏，則可信度降低。」
正確範例：「文章聲稱『伊萬卡出席白宮典禮』，但通篇未提供照片出處或官方聲明，也無其他媒體交叉確認，屬於無佐證的單方說法。」

### 分析（analysis）原則
analysis 必須總結這則訊息的具體問題點，不得只寫「語氣誇大、缺乏來源、可能有謬誤」等通用說法。
必須提及訊息中的至少一個具體主張或細節。

### 評分原則
- 「訊息中有人聲稱某醫生/專家說過某話」不足以提升 credibility_score，除非有外部查核資料佐證。
- 沒有任何外部可驗證來源的訊息，credibility_score 上限為 0.5（待查證），除非語境明顯為無爭議的一般常識。

### 語言規範（最高優先，必須遵守）
- **所有輸出必須使用正確的繁體中文**，包括 steps、analysis、media_literacy_tip 每一個欄位
- 若參考資料為英文，請先理解語意，再以流暢的繁體中文重新表達，**嚴禁逐字翻譯、嚴禁輸出英文單詞夾雜亂碼**
- analysis 和 media_literacy_tip 必須是完整、通順的中文句子，讀起來自然流暢

### 其他指引
- 步驟數量 3-4 個，每步聚焦單一觀察點
- 結尾提供一個「識讀小撇步」
- 保持中立語氣，不帶政治色彩
- 不要提及 Cofacts 或 Google Fact Check

### 輸出格式（嚴格 JSON，不加其他文字）
{
  "steps": [
    {"title": "步驟標題", "content": "分析內容（必須引用訊息具體內容）", "icon": "🔍"}
  ],
  "credibility_score": 0.0,
  "credibility_label": "假訊息",
  "analysis": "針對本訊息具體問題的總結（必須提及至少一個具體主張）",
  "media_literacy_tip": "識讀小撇步"
}

credibility_label 只能是以下三種之一：假訊息 / 待查證 / 可信
credibility_score 範圍 0.0（最不可信）~ 1.0（最可信）
"""

FOLLOW_UP_PROMPT = """你是「假訊息情報中心」的 AI 分析師，正在協助使用者深入理解一則已查核的訊息。

### 任務
直接、精準地回答使用者的追問。不要重新列舉查核步驟，不要輸出 JSON。
用自然語言回答，3-6 句話為佳，聚焦在使用者的問題上。

### 原則
- 根據原始訊息內容和查核結果來回答，不要憑空推測
- 如果問題超出查核範圍，誠實說明「這部分無法從現有資料判斷」
- 保持中立，不帶個人立場
- 請用繁體中文回答

只輸出自然語言回覆，不要任何 JSON 格式。
"""

PROFESSIONAL_PROMPT = """你是「假訊息情報中心」的專業分析引擎。

### 任務
對輸入內容產出完整的專業查核報告，請用繁體中文回答。

### 輸出格式（嚴格 JSON，不加其他文字）
{
  "credibility_score": 0.0,
  "credibility_label": "假訊息",
  "analysis": "綜合判斷說明",
  "dimensions": {
    "source_credibility": {"score": 0.0, "explanation": ""},
    "evidence_strength": {"score": 0.0, "explanation": ""},
    "language_analysis": {"score": 0.0, "explanation": ""},
    "rag_match": {"score": 0.0, "explanation": ""}
  },
  "key_findings": ["關鍵發現1", "關鍵發現2"],
  "uncertainties": ["不確定之處1"],
  "media_literacy_tip": "識讀小撇步"
}

credibility_label 只能是以下三種之一：假訊息 / 待查證 / 可信
"""


class SynthesisAgent:
    """匯整 Agent：整合各 Agent 結果，用 Groq 生成最終查核報告。"""

    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

    def _build_context(self, rag_results: dict, fact_check_results: dict, web_search_results: dict = None) -> str:
        parts = []

        docs = rag_results.get("documents", [])
        if docs:
            parts.append("### Cofacts 歷史查核記錄（語義相近）")
            for i, doc in enumerate(docs, 1):
                parts.append(f"{i}. {doc}")

        claims = fact_check_results.get("claims", [])
        if claims:
            parts.append("\n### Google Fact Check 結果")
            for c in claims:
                parts.append(
                    f"- 聲明：{c.get('text', '')}\n"
                    f"  查核結果：{c.get('rating', '')}\n"
                    f"  來源：{c.get('publisher', '')}（{c.get('url', '')}）"
                )

        if web_search_results:
            results = web_search_results.get("results", [])
            if results:
                parts.append("\n### 網路搜尋結果（來自可信新聞來源）")
                for r in results:
                    parts.append(
                        f"- 標題：{r.get('title', '')}\n"
                        f"  來源：{r.get('source', '')}（{r.get('url', '')}）\n"
                        f"  摘要：{r.get('snippet', '')}"
                    )

        return "\n".join(parts) if parts else "（無外部查核資料）"

    async def synthesize(
        self,
        content: str,
        rag_results: dict,
        fact_check_results: dict,
        web_search_results: dict = None,
        mode: str = "citizen",
        follow_up: Optional[str] = None,
        conversation_history: Optional[list] = None,
    ) -> dict:
        context = self._build_context(rag_results, fact_check_results, web_search_results)
        system_prompt = CITIZEN_PROMPT if mode == "citizen" else PROFESSIONAL_PROMPT

        if mode == "citizen":
            user_message = (
                f"【外部查核資料（用於決定 credibility_score 與 credibility_label，請勿在步驟中直接引用來源名稱）】\n"
                f"{context}\n\n"
                f"【分析任務】請針對以下訊息進行逐步分析。\n"
                f"重要規則：\n"
                f"1. 每個步驟都必須直接引用或提及訊息中的具體內容（例如特定詞彙、具體主張、人名、數字等），"
                f"不要只寫泛泛的判斷原則。格式參考：「這篇訊息中提到『XXX』，這樣的說法...」\n"
                f"2. 若外部查核資料中有新聞報導與訊息內容相符或矛盾，可在步驟中以「根據相關報導」方式引用，無需揭露來源名稱。\n"
                f"3. 分析內容（analysis）必須針對這則訊息的具體特徵作總結，不要只寫模板式的結語。\n"
                f"4. 不要提及 Cofacts 或 Google Fact Check。\n"
                f"5. 【語言規範，最高優先級】所有輸出欄位（steps、analysis、media_literacy_tip）必須使用正確的繁體中文。"
                f"若外部查核資料為英文，請理解其含義後以繁體中文表達，嚴禁逐字翻譯或輸出夾雜亂碼的文字。\n\n"
                f"【待查核訊息】\n{content}"
            )
        else:
            user_message = (
                f"【外部查核資料】\n{context}\n\n"
                f"請查核以下訊息。若網路搜尋結果中有相關新聞佐證或反駁，請在 key_findings 中具體引用（標明來源網站）。\n\n"
                f"【待查核訊息】\n{content}"
            )
        if follow_up:
            user_message += f"\n\n使用者追問：{follow_up}"

        # ── Follow-up 追問：獨立路徑，直接自然語言回答 ──────────────────────
        if follow_up:
            messages = [{"role": "system", "content": FOLLOW_UP_PROMPT}]
            # 加入對話歷史
            if conversation_history:
                for turn in conversation_history:
                    messages.append({"role": "user",      "content": turn.get("question", "")})
                    messages.append({"role": "assistant", "content": turn.get("answer", "")})
            # 組本次 user message：給 AI 足夠的背景
            messages.append({
                "role": "user",
                "content": (
                    f"【原始訊息】\n{content[:500]}\n\n"
                    f"【查核結論】\n{context[:800]}\n\n"
                    f"【使用者追問】\n{follow_up}"
                )
            })
            try:
                resp = self.client.chat.completions.create(
                    model=TEXT_MODEL,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=400,
                )
                answer = resp.choices[0].message.content.strip()
            except Exception as e:
                answer = f"回覆時發生錯誤：{e}"
            return {"analysis": answer}

        # ── 一般分析路徑 ────────────────────────────────────────────────────────
        try:
            response = self.client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            result = json.loads(response.choices[0].message.content)
            result["credibility_label"] = _normalize_label(result.get("credibility_label", "待查證"))
            return result
        except Exception as e:
            return {
                "credibility_score": 0.5,
                "credibility_label": "待查證",
                "analysis": f"分析時發生錯誤：{e}",
                "steps": [],
                "media_literacy_tip": "",
            }

    async def quick_check(self, content: str) -> dict:
        """快速查核：只回傳可信度標籤 + 2-3 句摘要，用於 RAG 卡片內嵌。"""
        prompt = (
            "你是事實查核助手。針對以下文章內容，給出可信度判斷與 2-3 句摘要說明（繁體中文）。\n"
            "只輸出 JSON，格式：{\"credibility_label\": \"假訊息\", \"credibility_score\": 0.0, \"summary\": \"...\"}\n"
            "credibility_label 只能是：假訊息 / 待查證 / 可信\n"
            "credibility_score 範圍 0.0（最不可信）~ 1.0（最可信）"
        )
        try:
            response = self.client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content[:2000]},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            result = json.loads(response.choices[0].message.content)
            result["credibility_label"] = _normalize_label(result.get("credibility_label", "待查證"))
            return result
        except Exception as e:
            return {"credibility_label": "待查證", "credibility_score": 0.5, "summary": f"分析失敗：{e}"}

    async def synthesize_image(self, vision_results: dict, mode: str = "citizen") -> dict:
        prob = vision_results.get("ai_probability", 0.5)
        label = vision_results.get("ai_label", "無法判斷")
        analysis = vision_results.get("analysis", "")
        media_literacy_tip = "辨識 AI 圖片時，請特別留意手指數量、文字是否扭曲、光影方向是否一致。"

        if mode != "professional":
            return {
                "credibility_label": label,
                "analysis": analysis,
                "media_literacy_tip": media_literacy_tip,
            }

        # ── Professional mode：呼叫 Groq 生成結構化鑑識報告 ──────────────────
        anomalies = vision_results.get("anomalies", [])
        visual_desc = vision_results.get("visual_description", "")
        confidence = vision_results.get("confidence", "低")
        source = vision_results.get("source", "")

        prompt = f"""你是一位資深數位鑑識分析師，正在撰寫專業圖像鑑識報告。請用繁體中文回覆。

以下是初步視覺分析結果：
- AI 生成概率：{round(prob * 100)}%
- 判斷標籤：{label}
- 信心等級：{confidence}
- 視覺描述：{visual_desc}
- 偵測到的異常：{json.dumps(anomalies, ensure_ascii=False)}
- 分析說明：{analysis}
- 偵測來源：{source}

請根據以上資料，以嚴謹的技術語言生成鑑識報告，輸出以下 JSON（禁止輸出其他文字）：
{{
  "executive_summary": "一段技術性總結，100字內，使用專業術語",
  "key_findings": ["具體技術發現1，需引用視覺觀察細節", "具體技術發現2", "具體技術發現3"],
  "technical_dimensions": [
    {{"name": "AI GENERATION PROBABILITY", "score": {round(prob, 2)}, "label": "{label}", "desc": "基於 AI or Not 偵測器的數值"}},
    {{"name": "PIXEL FORENSICS", "score": 0.0, "label": "待填", "desc": "像素層級特徵分析"}},
    {{"name": "SEMANTIC COHERENCE", "score": 0.0, "label": "待填", "desc": "圖像語義一致性評估"}},
    {{"name": "LIGHTING CONSISTENCY", "score": 0.0, "label": "待填", "desc": "光影方向與強度合理性"}}
  ],
  "uncertainties": ["鑑識過程中無法確認的項目1", "無法確認的項目2"]
}}

technical_dimensions 中後三項的 score 請根據視覺分析結果合理推估（0.0-1.0，越高代表越像真實照片），label 填寫一個 2-6 字的中文判斷詞。"""

        try:
            client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
            resp = client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=800,
            )
            pro_data = json.loads(resp.choices[0].message.content)
        except Exception as e:
            with open("synthesis_error.log", "a", encoding="utf-8") as f:
                f.write(f"[synthesize_image professional] {type(e).__name__}: {e}\n")
            pro_data = {
                "executive_summary": analysis,
                "key_findings": anomalies[:3],
                "technical_dimensions": [
                    {"name": "AI GENERATION PROBABILITY", "score": round(prob, 2), "label": label, "desc": "基於 AI or Not 偵測器"},
                    {"name": "ANALYSIS CONFIDENCE", "score": 0.85 if confidence == "高" else 0.55 if confidence == "中" else 0.3, "label": confidence, "desc": "模型把握程度"},
                ],
                "uncertainties": [],
            }

        return {
            "credibility_label": label,
            "analysis": pro_data.get("executive_summary", analysis),
            "media_literacy_tip": media_literacy_tip,
            "key_findings": pro_data.get("key_findings", []),
            "technical_dimensions": pro_data.get("technical_dimensions", []),
            "uncertainties": pro_data.get("uncertainties", []),
        }
