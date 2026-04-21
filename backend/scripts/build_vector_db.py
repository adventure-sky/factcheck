#!/usr/bin/env python3
"""
建置 ChromaDB 向量資料庫
資料來源：backend/data/cofacts/ 目錄下的本地 CSV 檔案

使用方式：
    cd backend
    python scripts/build_vector_db.py
"""

import os
import sys
import csv
import json

script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
sys.path.insert(0, backend_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(backend_dir, ".env"))

import chromadb
from sentence_transformers import SentenceTransformer

DB_PATH = os.environ.get("CHROMA_DB_PATH", os.path.join(backend_dir, "chroma_db"))
DATA_DIR = os.path.join(backend_dir, "data", "cofacts")
COLLECTION_NAME = "fact_check_data"
BATCH_SIZE = 128


def clean(text) -> str:
    if not isinstance(text, str):
        return ""
    return text.strip().replace("\n", " ")


def read_csv(filepath: str) -> list[dict]:
    rows = []
    with open(filepath, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def main():
    print("=" * 55)
    print("  Cofacts 向量資料庫建置腳本")
    print("=" * 55)
    print(f"資料庫路徑：{DB_PATH}")
    print(f"資料來源：{DATA_DIR}\n")

    # ── 1. 讀取本地 CSV ────────────────────────────────────
    print("[1/4] 讀取本地 CSV 資料...")

    articles_path       = os.path.join(DATA_DIR, "articles.csv")
    replies_path        = os.path.join(DATA_DIR, "replies.csv")
    article_replies_path = os.path.join(DATA_DIR, "article_replies.csv")

    for p in [articles_path, replies_path, article_replies_path]:
        if not os.path.exists(p):
            print(f"      ✗ 找不到檔案：{p}")
            sys.exit(1)

    articles       = read_csv(articles_path)
    replies        = read_csv(replies_path)
    article_replies = read_csv(article_replies_path)
    print(f"      → articles：{len(articles):,} 筆")
    print(f"      → replies：{len(replies):,} 筆")
    print(f"      → article_replies：{len(article_replies):,} 筆")

    # 建立 reply 查找表 {replyId -> reply_text}
    reply_map = {}
    for r in replies:
        rid = r.get("id") or r.get("replyId") or r.get("reply_id", "")
        text = clean(r.get("text", ""))
        if rid and text:
            reply_map[rid] = text

    # 建立 articleId -> [replyId] 對照表
    article_to_replies: dict[str, list[str]] = {}
    for ar in article_replies:
        aid = ar.get("articleId") or ar.get("article_id", "")
        rid = ar.get("replyId") or ar.get("reply_id", "")
        if aid and rid:
            article_to_replies.setdefault(aid, []).append(rid)

    # ── 2. 資料清洗與合併 ──────────────────────────────────
    print("[2/4] 資料清洗與合併...")
    records = []
    for art in articles:
        aid      = art.get("id") or art.get("articleId") or art.get("article_id", "")
        text     = clean(art.get("text", ""))
        category = clean(art.get("articleType", "")) or "未分類"

        if not text or len(text) < 10:
            continue

        # 合併對應的查核回應
        reply_texts = []
        for rid in article_to_replies.get(aid, []):
            rt = reply_map.get(rid, "")
            if rt:
                reply_texts.append(rt)

        doc_text = f"訊息：{text}"
        if reply_texts:
            doc_text += f"\n查核回應：{reply_texts[0]}"  # 取第一筆回應

        records.append({
            "text": doc_text,
            "metadata": {
                "original_text": text[:300],
                "reply": reply_texts[0][:300] if reply_texts else "",
                "category": category,
                "article_id": aid,
            },
        })

    print(f"      → 清洗後保留 {len(records):,} 筆")

    # ── 3. 初始化 ChromaDB ─────────────────────────────────
    print("[3/4] 初始化向量資料庫...")
    db = chromadb.PersistentClient(path=DB_PATH)
    try:
        db.delete_collection(COLLECTION_NAME)
        print("      → 刪除既有 collection，重新建置")
    except Exception:
        pass
    collection = db.create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # ── 4. 向量化並寫入 ────────────────────────────────────
    print("[4/4] 向量化並寫入 ChromaDB（使用 paraphrase-multilingual-MiniLM-L12-v2）...")
    embed_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    total = len(records)

    for i in range(0, total, BATCH_SIZE):
        batch    = records[i : i + BATCH_SIZE]
        texts    = [r["text"] for r in batch]
        metas    = [r["metadata"] for r in batch]
        ids      = [f"cofacts_{i + j}" for j in range(len(batch))]
        embeddings = embed_model.encode(texts, show_progress_bar=False).tolist()

        collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metas,
            ids=ids,
        )

        done = min(i + BATCH_SIZE, total)
        pct  = done / total * 100
        print(f"      {done:,}/{total:,} ({pct:.1f}%)", end="\r")

    final_count = collection.count()
    print(f"\n      ✓ 寫入完成，共 {final_count:,} 筆")

    # ── 5. 寫入統計快取 ────────────────────────────────────
    print("[5/5] 計算並寫入統計快取...")
    categories: dict[str, int] = {}
    for r in records:
        cat = r["metadata"].get("category", "未分類")
        categories[cat] = categories.get(cat, 0) + 1

    stats = {"total": final_count, "categories": categories}
    stats_path = os.path.join(DB_PATH, "stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"      ✓ 統計快取已寫入：{stats_path}（{len(categories)} 個類別）")

    print("\n" + "=" * 55)
    print("  建置完成！請啟動後端後即可使用 RAG 功能。")
    print("=" * 55)


if __name__ == "__main__":
    main()
