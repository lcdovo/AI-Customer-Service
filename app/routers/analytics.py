"""
统计分析与监控 API - Phase 4 实现
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta

from app.utils.tracking import get_tracer, alert_manager
from app.services.evaluation import get_answer_evaluator, get_low_score_pool, get_ab_test_framework

router = APIRouter(prefix="/api/v1/analytics", tags=["统计分析"])


@router.get("/metrics")
async def get_system_metrics():
    """获取系统指标"""
    tracer = get_tracer()
    metrics = tracer.get_metrics()

    alerts = alert_manager.check_alerts(metrics)
    active_alerts = alert_manager.get_active_alerts()

    return {
        "code": 0,
        "message": "获取成功",
        "data": {
            "metrics": metrics,
            "alerts": active_alerts,
            "alert_rules": alert_manager.get_alert_rules(),
        },
    }


@router.get("/metrics/summary")
async def get_metrics_summary(
    hours: int = Query(default=1, ge=1, le=168, description="统计小时数"),
):
    """获取指标摘要"""
    tracer = get_tracer()
    metrics = tracer.get_metrics()

    response_time = metrics.get("response_time", {})
    tool_stats = metrics.get("tool_statistics", {})

    summary = {
        "period_hours": hours,
        "total_requests": metrics.get("counters", {}).get("response.total", 0),
        "success_rate": metrics.get("success_rate", 0),
        "avg_response_time_ms": response_time.get("avg_ms", 0),
        "p95_response_time_ms": response_time.get("p95_ms", 0),
        "intent_distribution": metrics.get("intent_distribution", {}),
        "tool_statistics": tool_stats,
        "session_count": metrics.get("session_count", 0),
    }

    return {
        "code": 0,
        "message": "获取成功",
        "data": summary,
    }


@router.get("/evaluation/stats")
async def get_evaluation_stats():
    """获取评测统计"""
    evaluator = get_answer_evaluator()
    low_score_pool = get_low_score_pool()

    stats = evaluator.get_evaluation_stats()
    failure_patterns = low_score_pool.get_failure_patterns()

    return {
        "code": 0,
        "message": "获取成功",
        "data": {
            "evaluation_stats": stats,
            "failure_patterns": failure_patterns,
            "pending_low_score_samples": len(low_score_pool.get_pending_samples()),
        },
    }


@router.get("/evaluation/low-scores")
async def get_low_score_samples(
    limit: int = Query(default=50, ge=1, le=200),
    failure_type: Optional[str] = Query(default=None, description="失败类型过滤"),
):
    """获取低分样本"""
    low_score_pool = get_low_score_pool()

    if failure_type:
        samples = low_score_pool.get_samples_by_failure_type(failure_type)
    else:
        samples = low_score_pool.get_pending_samples(limit)

    return {
        "code": 0,
        "message": "获取成功",
        "data": {
            "total": len(samples),
            "samples": samples[:limit],
        },
    }


@router.post("/evaluation/low-scores/{sample_id}/resolve")
async def resolve_low_score_sample(
    sample_id: str,
    action: str = Query(..., description="处理动作: knowledge_update/prompt_optimization/tool_fix"),
    note: str = Query(default="", description="处理备注"),
):
    """处理低分样本"""
    low_score_pool = get_low_score_pool()
    success = low_score_pool.mark_processed(sample_id, action, note)

    if not success:
        raise HTTPException(status_code=404, detail="样本不存在")

    return {
        "code": 0,
        "message": "处理成功",
        "data": {"sample_id": sample_id, "action": action},
    }


@router.get("/ab-test/experiments")
async def get_ab_experiments():
    """获取A/B测试实验列表"""
    framework = get_ab_test_framework()
    experiments = framework.get_active_experiments()

    return {
        "code": 0,
        "message": "获取成功",
        "data": experiments,
    }


@router.post("/ab-test/experiments")
async def create_ab_experiment(
    experiment_id: str = Query(..., description="实验ID"),
    name: str = Query(..., description="实验名称"),
    description: str = Query(default="", description="实验描述"),
    variant_a: str = Query(..., description="变体A ID"),
    variant_b: str = Query(..., description="变体B ID"),
    traffic_split: float = Query(default=0.5, ge=0.1, le=0.9, description="流量分配比例"),
):
    """创建A/B测试实验"""
    framework = get_ab_test_framework()

    variants = [
        {"id": variant_a, "name": f"对照组-{variant_a}"},
        {"id": variant_b, "name": f"实验组-{variant_b}"},
    ]

    experiment = framework.create_experiment(
        experiment_id=experiment_id,
        name=name,
        description=description,
        variants=variants,
        traffic_split=traffic_split,
    )

    return {
        "code": 0,
        "message": "创建成功",
        "data": {
            "experiment_id": experiment_id,
            "name": name,
            "status": "active",
        },
    }


@router.get("/ab-test/experiments/{experiment_id}/results")
async def get_ab_experiment_results(experiment_id: str):
    """获取A/B测试结果"""
    framework = get_ab_test_framework()
    results = framework.get_experiment_results(experiment_id)

    if not results:
        raise HTTPException(status_code=404, detail="实验不存在")

    return {
        "code": 0,
        "message": "获取成功",
        "data": results,
    }