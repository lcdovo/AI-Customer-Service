"""
RAG 综合性能基准测试
- 多参数组合对比
- 全分类召回率测试
- 延迟分析
- 缓存效果验证
"""
import json
import os
import time
import statistics
import requests
from collections import defaultdict
from datetime import datetime

BASE = "http://localhost:8000/api/v1/knowledge"
OUT = os.path.join(os.path.dirname(__file__), "..", "test_data")
REPORT = os.path.join(OUT, "rag_optimization_report.json")

TEST_QUERIES = [
    # 原有分类
    ("退款政策是什么", "refund", "退款"),
    ("怎么申请退款", "refund", "退款"),
    ("订单状态有哪些", "order", "订单"),
    ("发什么快递几天能到", "order", "订单_物流"),
    ("产品参数是什么", "product", "产品"),
    ("PLUS会员有什么特权", "promotion", "促销"),
    ("优惠券怎么用", "promotion", "促销"),
    ("支持什么支付方式", "payment", "支付"),
    ("怎么开发票", "payment", "发票"),
    ("忘记密码怎么办", "account", "账号"),
    ("怎么实名认证", "account", "账号"),
    ("怎么投诉商家", "complaint", "投诉"),
    ("如何联系客服", "complaint", "客服"),
    ("保修政策是什么", "warranty", "保修"),
    ("怎么维修产品", "warranty", "维修"),
    ("物流配送查询", "shipping", "物流"),
    ("运费怎么计算", "shipping", "运费"),
    ("如何签收验货", "shipping", "签收"),
    ("账号安全设置", "account", "账号_安全"),
    ("跨境购物说明", "product", "跨境"),
    ("预售订单说明", "order", "预售"),
    ("发票和税务问题", "payment", "发票"),
    ("退换货操作步骤", "refund", "退款"),
    ("商品保修延保", "warranty", "延保"),
]

def search(q, k=5, t=0.1):
    start = time.perf_counter()
    try:
        r = requests.post(f"{BASE}/search", json={"query": q, "top_k": k, "similarity_threshold": t}, timeout=30)
        ms = (time.perf_counter() - start) * 1000
        d = r.json().get("data", {})
        return {
            "ms": ms,
            "results": d.get("results", []),
            "total": d.get("total_candidates", 0),
            "strategy": d.get("search_strategy", ""),
            "cache": d.get("from_cache", False)
        }
    except Exception as e:
        return {"ms": (time.perf_counter() - start) * 1000, "error": str(e)}

def calc_metrics(times):
    if not times:
        return {}
    s = sorted(times)
    n = len(s)
    return {
        "n": n,
        "avg_ms": round(statistics.mean(s), 1),
        "p50_ms": round(s[n // 2], 1),
        "p95_ms": round(s[min(int(n * 0.95), n - 1)], 1),
        "min_ms": round(s[0], 1),
        "max_ms": round(s[-1], 1),
        "qps": round(n / (sum(s) / 1000), 1) if sum(s) > 0 else 0,
    }

def recall_test(k, t):
    hit = 0
    total = 0
    cat_stats = defaultdict(lambda: [0, 0])
    all_results = []

    for q, expected_cat, label in TEST_QUERIES:
        r = search(q, k, t)
        total += 1
        cats = set(x.get("category", "") for x in r.get("results", []))
        cat_stats[expected_cat][1] += 1
        if expected_cat in cats:
            hit += 1
            cat_stats[expected_cat][0] += 1

        all_results.append({
            "query": q,
            "expected": expected_cat,
            "hit": expected_cat in cats,
            "top_results": [{"title": x.get("title", ""), "score": x.get("final_score", 0), "cat": x.get("category", "")} for x in r.get("results", [])[:3]],
            "latency_ms": round(r.get("ms", 0), 1),
            "strategy": r.get("strategy", ""),
        })

    return {
        "overall": f"{hit}/{total} = {hit/total*100:.1f}%",
        "by_category": {c: f"{h}/{t} = {h/t*100:.1f}%" for c, (h, t) in cat_stats.items()},
        "details": all_results,
    }

def benchmark_param(k, t, label):
    times, strats = [], defaultdict(int)
    result_counts = []

    for q, cat, _ in TEST_QUERIES:
        r = search(q, k, t)
        times.append(r["ms"])
        strats[r.get("strategy", "?")] += 1
        result_counts.append(len(r.get("results", [])))

    m = calc_metrics(times)
    m.update({
        "label": label,
        "k": k,
        "threshold": t,
        "strategies": dict(strats),
        "avg_results": round(statistics.mean(result_counts), 1) if result_counts else 0,
    })
    return m

def main():
    print("=" * 60)
    print("RAG 综合性能基准测试 v2")
    print(f"测试查询: {len(TEST_QUERIES)} 条")
    print("=" * 60)

    # 获取知识库状态
    stats = requests.get(f"{BASE}/stats", timeout=10).json().get("data", {})
    print(f"\n知识库: {stats.get('total_documents', 0)} 文档, {stats.get('total_chunks', 0)} 分块")
    print(f"向量库: {stats.get('vector_store_count', 0)} 向量, 后端: {stats.get('backend', '')}")

    # ===== 1. 当前配置性能基线 =====
    print("\n" + "=" * 60)
    print("1. 当前配置性能基线")
    print("=" * 60)

    # 预热
    for q, _, _ in TEST_QUERIES[:3]:
        search(q, 10, 0.1)

    baseline = benchmark_param(10, 0.1, "current")
    print(f"  k=10, t=0.1: avg={baseline['avg_ms']}ms, p95={baseline['p95_ms']}ms, qps={baseline['qps']}")
    print(f"  策略分布: {baseline['strategies']}")
    print(f"  平均结果数: {baseline['avg_results']}")

    # ===== 2. 参数对比 =====
    print("\n" + "=" * 60)
    print("2. 参数组合对比")
    print("=" * 60)

    combos = [
        (5, 0.1, "k5_t0.1"),
        (5, 0.05, "k5_t0.05"),
        (10, 0.1, "k10_t0.1"),
        (10, 0.05, "k10_t0.05"),
        (15, 0.1, "k15_t0.1"),
        (15, 0.05, "k15_t0.05"),
    ]

    param_results = []
    for k, t, label in combos:
        m = benchmark_param(k, t, label)
        param_results.append(m)
        print(f"  {label}: avg={m['avg_ms']}ms, p95={m['p95_ms']}ms, qps={m['qps']}, results={m['avg_results']}")

    # ===== 3. 召回率测试 =====
    print("\n" + "=" * 60)
    print("3. 召回率测试 (k=10, t=0.1)")
    print("=" * 60)

    recall = recall_test(10, 0.1)
    print(f"  总体召回率: {recall['overall']}")
    print("\n  分类召回率:")
    for cat, rate in sorted(recall["by_category"].items(), key=lambda x: x[1]):
        print(f"    {cat}: {rate}")

    # ===== 4. 缓存测试 =====
    print("\n" + "=" * 60)
    print("4. 缓存效果测试")
    print("=" * 60)

    cache_t1, cache_t2, cache_hits = [], [], 0
    for q, _, _ in TEST_QUERIES[:8]:
        r1 = search(q, 10, 0.1)
        r2 = search(q, 10, 0.1)
        cache_t1.append(r1["ms"])
        cache_t2.append(r2["ms"])
        if r2.get("cache"):
            cache_hits += 1

    print(f"  首轮平均: {statistics.mean(cache_t1):.0f}ms")
    print(f"  缓存平均: {statistics.mean(cache_t2):.0f}ms")
    print(f"  命中率: {cache_hits}/8 = {cache_hits/8*100:.0f}%")
    print(f"  加速比: {statistics.mean(cache_t1)/max(statistics.mean(cache_t2), 1):.1f}x")

    # ===== 5. 生成报告 =====
    report = {
        "timestamp": datetime.now().isoformat(),
        "knowledge_base": stats,
        "baseline": baseline,
        "param_comparison": param_results,
        "recall": recall,
        "cache": {
            "first_pass_avg_ms": round(statistics.mean(cache_t1), 1),
            "cached_avg_ms": round(statistics.mean(cache_t2), 1),
            "hit_rate": f"{cache_hits}/8",
            "speedup": f"{statistics.mean(cache_t1)/max(statistics.mean(cache_t2), 1):.1f}x",
        },
        "optimization_summary": {
            "documents_count": stats.get("total_documents", 0),
            "chunks_count": stats.get("total_chunks", 0),
            "categories_covered": len(recall["by_category"]),
            "recall_rate": recall["overall"],
            "avg_latency_ms": baseline["avg_ms"],
            "qps": baseline["qps"],
            "hybrid_search": "enabled",
            "bm25_source": "milvus_loaded",
        },
    }

    os.makedirs(OUT, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"报告已保存: {REPORT}")
    print("=" * 60)

    # 打印优化总结
    print("\n" + "=" * 60)
    print("优化总结")
    print("=" * 60)
    print(f"  文档总数: {stats.get('total_documents', 0)} 篇")
    print(f"  分块总数: {stats.get('total_chunks', 0)} 个")
    print(f"  覆盖分类: {len(recall['by_category'])} 个")
    print(f"  召回率: {recall['overall']}")
    print(f"  平均延迟: {baseline['avg_ms']}ms")
    print(f"  QPS: {baseline['qps']}")
    print(f"  检索策略: {baseline['strategies']}")

if __name__ == "__main__":
    main()
