import os
import json
import asyncio
import chromadb
from groq import AsyncGroq
from sentence_transformers import SentenceTransformer


class RAGAgent:
    """語義檢索 Agent：從 ChromaDB 找出最相近的 Cofacts 歷史查核記錄。"""

    def __init__(self):
        self.embed_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        db_path = os.environ.get("CHROMA_DB_PATH", "./chroma_db")
        self.db = chromadb.PersistentClient(path=db_path)
        self.collection = self.db.get_or_create_collection(
            "fact_check_data",
            metadata={"hnsw:space": "cosine"},
        )

    async def _rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """用 Groq 對候選結果打相關性分數（0-10），過濾低相關結果後回傳。"""
        if len(candidates) <= 1:
            return candidates

        numbered = "\n\n".join(
            f"[{i+1}] {c['document'][:200]}"
            for i, c in enumerate(candidates)
        )
        prompt = (
            f"查核主題：{query[:300]}\n\n"
            f"以下是從資料庫取出的候選記錄，請針對每筆記錄評估與查核主題的相關性（0=完全無關，10=高度相關）。\n"
            f"只輸出 JSON 陣列，格式：[{{\"index\":1,\"score\":8}}, ...]，不要其他文字。\n\n"
            f"{numbered}"
        )

        try:
            client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=200,
                ),
                timeout=10,
            )
            raw = resp.choices[0].message.content.strip()
            # 取出 JSON 陣列部分
            start, end = raw.find("["), raw.rfind("]")
            scores = json.loads(raw[start:end+1]) if start != -1 else []
            score_map = {item["index"]: item["score"] for item in scores}

            # 為每個候選加上 rerank_score，過濾分數 < 4 的
            ranked = []
            for i, c in enumerate(candidates):
                s = score_map.get(i + 1, 5)
                if s >= 4:
                    ranked.append({**c, "rerank_score": s})
            ranked.sort(key=lambda x: x["rerank_score"], reverse=True)
            return ranked if ranked else candidates  # fallback: 全部過濾時回傳原始結果
        except Exception:
            return candidates  # rerank 失敗時靜默降級，回傳原始順序

    async def retrieve(self, query: str, n_results: int = 3) -> dict:
        count = self.collection.count()
        if count == 0:
            return {
                "documents": [],
                "metadatas": [],
                "warning": "向量資料庫尚未建置，請先執行 python scripts/build_vector_db.py",
            }

        query_embedding = self.embed_model.encode(query).tolist()
        # 取多一倍候選給 reranker 選
        fetch_n = min(n_results * 2, count)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=fetch_n,
            include=["documents", "metadatas", "distances"],
        )

        docs      = results["documents"][0] if results["documents"] else []
        metas     = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        candidates = [
            {"document": docs[i], "metadata": metas[i], "distance": distances[i]}
            for i in range(len(docs))
        ]

        # Reranking
        reranked = await self._rerank(query, candidates)
        top = reranked[:n_results]

        return {
            "documents": [c["document"] for c in top],
            "metadatas": [c["metadata"] for c in top],
            "distances": [c["distance"] for c in top],
        }

    def get_dashboard_stats(self) -> dict:
        """回傳分類統計，供儀表板使用。優先讀取建置時產生的 stats.json 快取。"""
        db_path = os.environ.get("CHROMA_DB_PATH", "./chroma_db")
        stats_path = os.path.join(db_path, "stats.json")

        if os.path.exists(stats_path):
            with open(stats_path, encoding="utf-8") as f:
                return json.load(f)

        # 快取不存在時回退到全量掃描
        count = self.collection.count()
        if count == 0:
            return {"total": 0, "categories": {}}

        categories: dict[str, int] = {}
        offset = 0
        batch = 5000
        while offset < count:
            chunk = self.collection.get(
                limit=batch,
                offset=offset,
                include=["metadatas"],
            )
            for meta in chunk.get("metadatas", []):
                cat = (meta or {}).get("category", "未分類")
                categories[cat] = categories.get(cat, 0) + 1
            offset += batch

        return {"total": count, "categories": categories}
