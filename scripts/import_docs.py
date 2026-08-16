"""
导入测试文档到知识库
"""
import json
import os
import sys
import time
import requests

BASE_URL = "http://localhost:8000/api/v1/knowledge"
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "test_data", "test_documents.json")


def import_docs():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        docs = json.load(f)

    print(f"准备导入 {len(docs)} 篇文档...")

    success = 0
    failed = 0
    total_chunks = 0
    start = time.time()

    for i, doc in enumerate(docs):
        payload = {
            "title": doc["title"],
            "content": doc["content"],
            "category": doc.get("category", ""),
            "keywords": doc.get("keywords", []),
            "source": "test_data",
        }

        try:
            resp = requests.post(f"{BASE_URL}/documents/text", json=payload, timeout=60)
            data = resp.json()

            if data.get("code") == 0:
                chunks = data.get("data", {}).get("chunks_count", 0)
                total_chunks += chunks
                success += 1
                if (i + 1) % 10 == 0:
                    elapsed = time.time() - start
                    print(f"  进度: {i+1}/{len(docs)} | 成功: {success} | 分块: {total_chunks} | 耗时: {elapsed:.1f}s")
            else:
                failed += 1
                print(f"  失败 [{doc['title']}]: {data.get('message', 'unknown')}")

        except Exception as e:
            failed += 1
            print(f"  错误 [{doc['title']}]: {e}")

    elapsed = time.time() - start
    print(f"\n导入完成:")
    print(f"  成功: {success} | 失败: {failed}")
    print(f"  总分块: {total_chunks}")
    print(f"  总耗时: {elapsed:.1f}s")
    print(f"  平均每篇: {elapsed/max(success,1):.2f}s")

    # 验证
    stats = requests.get(f"{BASE_URL}/stats", timeout=10).json()
    print(f"\n知识库状态: {json.dumps(stats.get('data', {}), ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    if not os.path.exists(DATA_FILE):
        print(f"数据文件不存在: {DATA_FILE}")
        print("请先运行: python generate_test_docs.py")
        sys.exit(1)

    import_docs()