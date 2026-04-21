"""
從現有 ChromaDB 讀取 metadata 產生 stats.json 快取。
若 ChromaDB metadata 的 category 全為「未分類」（舊版 DB），
則改從 CSV 直接統計 articleType。

使用方式：
    cd backend
    python scripts/gen_stats.py
"""

import os
import json
import csv
import chromadb

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("CHROMA_DB_PATH", os.path.join(BACKEND_DIR, "chroma_db"))
DATA_DIR = os.path.join(BACKEND_DIR, "data", "cofacts")
STATS_PATH = os.path.join(DB_PATH, "stats.json")

db = chromadb.PersistentClient(path=DB_PATH)
col = db.get_collection("fact_check_data")
count = col.count()
print(f"總筆數：{count:,}")

# 先從 ChromaDB metadata 統計
cats = {}
offset, batch = 0, 5000
while offset < count:
    chunk = col.get(limit=batch, offset=offset, include=["metadatas"])
    for m in chunk.get("metadatas", []):
        cat = (m or {}).get("category", "未分類")
        cats[cat] = cats.get(cat, 0) + 1
    offset += batch
    print(f"  讀取中 {min(offset, count):,}/{count:,}", end="\r")
print()

# 若全為「未分類」，代表舊版 DB，改從 CSV 讀
if list(cats.keys()) == ["未分類"]:
    print("偵測到舊版 DB（category 全為未分類），改從 CSV 讀取 articleType...")
    cats = {}
    articles_path = os.path.join(DATA_DIR, "articles.csv")
    with open(articles_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            cat = (row.get("articleType") or "").strip() or "未分類"
            cats[cat] = cats.get(cat, 0) + 1

os.makedirs(DB_PATH, exist_ok=True)
with open(STATS_PATH, "w", encoding="utf-8") as f:
    json.dump({"total": count, "categories": cats}, f, ensure_ascii=False, indent=2)

print(f"完成，共 {len(cats)} 個類別，已寫入 {STATS_PATH}")
for k, v in sorted(cats.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v:,}")
