#!/usr/bin/env python3
"""
備份 ChromaDB 向量資料庫

使用方式：
    cd backend
    python scripts/backup_db.py

備份檔會存在 backend/backups/ 目錄下，格式：chroma_db_YYYYMMDD_HHMMSS.zip
還原方式：
    1. 刪除或移走現有 chroma_db/
    2. 解壓縮備份檔，資料夾名稱改回 chroma_db
"""

import os
import sys
import zipfile
import shutil
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)

DB_PATH     = os.path.join(backend_dir, "chroma_db")
BACKUP_DIR  = os.path.join(backend_dir, "backups")


def main():
    if not os.path.isdir(DB_PATH):
        print(f"找不到 chroma_db：{DB_PATH}")
        sys.exit(1)

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"chroma_db_{timestamp}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    print(f"開始備份 chroma_db -> {backup_path}")
    total_files = sum(len(files) for _, _, files in os.walk(DB_PATH))
    count = 0

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, _, files in os.walk(DB_PATH):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, backend_dir)
                zf.write(file_path, arcname)
                count += 1
                print(f"  {count}/{total_files} {arcname}", end="\r")

    size_mb = os.path.getsize(backup_path) / 1024 / 1024
    print(f"\n完成！備份檔：{backup_path} ({size_mb:.1f} MB)")

    # 只保留最新 3 份，自動清理舊備份
    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith("chroma_db_") and f.endswith(".zip")]
    )
    while len(backups) > 3:
        old = os.path.join(BACKUP_DIR, backups.pop(0))
        os.remove(old)
        print(f"已刪除舊備份：{old}")


if __name__ == "__main__":
    main()
