"""
轻量 RAG 性能测试 - 12个代表查询，4组参数
"""
import json, os, sys, time, statistics, requests
from collections import defaultdict
from datetime import datetime

BASE = "http://localhost:8000/api/v1/knowledge"
OUT = os.path.join(os.path.dirname(__file__), "..", "test_data")
REPORT = os.path.join(OUT, "rag_benchmark_report.json")

QUERIES = [
    ("退款政策是什么", "refund"),
    ("怎么申请退款", "refund"),
    ("订单状态有哪些", "order"),
    ("发什么快递几天能到", "order"),
    ("优惠券怎么用", "promotion"),
    ("PLUS会员有什么特权", "promotion"),
    ("忘记密码怎么办", "technical"),
    ("支持什么支付方式", "technical"),
    ("怎么投诉商家", "complaint"),
    ("产品参数是什么", "product"),
    ("怎么开发票", "technical"),
    ("如何联系客服", "complaint"),
]

def search(q, k=5, t=0.1):
    start = time.perf_counter()
    try:
        r = requests.post(f"{BASE}/search", json={"query": q, "top_k": k, "similarity_threshold": t}, timeout=30)
        ms = (time.perf_counter() - start) * 1000
        d = r.json().get("data", {})
        return {"ms": ms, "results": d.get("results", []), "total": d.get("total_candidates", 0),
                "strategy": d.get("search_strategy", ""), "cache": d.get("from_cache", False)}
    except Exception as e:
        return {"ms": (time.perf_counter() - start) * 1000, "error": str(e)}

def metrics(times, label=""):
    if not times: return {}
    s = sorted(times); n = len(s)
    return {f"{label}_n": n, f"{label}_avg": round(statistics.mean(s), 1),
            f"{label}_p95": round(s[min(int(n*.95),n-1)], 1),
            f"{label}_min": round(s[0], 1), f"{label}_max": round(s[-1], 1),
            f"{label}_qps": round(n/(sum(s)/1000), 1) if sum(s)>0 else 0}

def bench(k, t, label):
    times, strats, n_res = [], defaultdict(int), []
    for q, cat in QUERIES:
        r = search(q, k, t)
        times.append(r["ms"])
        strats[r.get("strategy", "?")] += 1
        n_res.append(len(r.get("results", [])))
    m = metrics(times, label)
    m[f"{label}_strats"] = dict(strats)
    m[f"{label}_avg_results"] = round(statistics.mean(n_res), 1)
    return m

def main():
    print("=" * 50, flush=True)
    print("RAG 性能测试 (轻量版)", flush=True)
    print(f"查询数: {len(QUERIES)} | 参数组: 4", flush=True)
    print("=" * 50, flush=True)

    sb = requests.get(f"{BASE}/stats", timeout=30).json().get("data", {})
    print(f"知识库: {sb.get('total_documents',0)} 文档, {sb.get('total_chunks',0)} 分块", flush=True)

    # Baseline
    print("\n--- 基准 (k=5, t=0.1) ---", flush=True)
    bl = bench(5, 0.1, "base")
    print(f"  avg={bl['base_avg']}ms  p95={bl['base_p95']}ms  qps={bl['base_qps']}  strats={bl['base_strats']}", flush=True)

    # Cache test
    print("\n--- 缓存测试 ---", flush=True)
    t1, t2, ch = [], [], 0
    for q, _ in QUERIES[:5]:
        r1 = search(q, 5, 0.1); t1.append(r1["ms"])
        r2 = search(q, 5, 0.1); t2.append(r2["ms"])
        if r2.get("cache"): ch += 1
    print(f"  首轮: {statistics.mean(t1):.0f}ms  缓存: {statistics.mean(t2):.0f}ms  命中: {ch}/5", flush=True)

    # Param combos
    combos = [(5, 0.1), (8, 0.1), (5, 0.05), (8, 0.15)]
    all_metrics = {"base": bl}
    for k, t in combos[1:]:
        lb = f"k{k}_t{t}"
        print(f"\n--- {lb} ---", end=" ", flush=True)
        m = bench(k, t, lb)
        all_metrics[lb] = m
        print(f"avg={m[f'{lb}_avg']}ms qps={m[f'{lb}_qps']} strats={m[f'{lb}_strats']}", flush=True)

    # Recall test
    print("\n--- 召回质量 ---", flush=True)
    hit, total = 0, 0
    cat_ok = defaultdict(lambda: [0, 0])
    for q, cat in QUERIES:
        r = search(q, 5, 0.1)
        total += 1
        cats = set(x.get("category", "") for x in r.get("results", []))
        cat_ok[cat][1] += 1
        if cat in cats: hit += 1; cat_ok[cat][0] += 1
    print(f"  总体: {hit}/{total} = {hit/total*100:.1f}%", flush=True)
    for c, (h, t) in cat_ok.items():
        print(f"  {c}: {h}/{t} = {h/t*100:.1f}%", flush=True)

    # Save
    report = {"timestamp": datetime.now().isoformat(), "kb": sb,
              "metrics": all_metrics, "recall": {"overall": f"{hit/total*100:.1f}%",
              "by_cat": {c: f"{h/t*100:.1f}%" for c,(h,t) in cat_ok.items()}}}
    os.makedirs(OUT, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n报告: {REPORT}", flush=True)
    print("=" * 50, flush=True)

if __name__ == "__main__":
    main()