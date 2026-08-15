"""
Phase 4 API 集成测试
"""
import requests
import json

BASE_URL = "http://localhost:8080"

print("=" * 60)
print("Phase 4 API 集成测试")
print("=" * 60)

tests_passed = 0
tests_failed = 0

def test_api(name, method, url, data=None, expected_status=200):
    global tests_passed, tests_failed
    try:
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data)
        elif method == "PUT":
            response = requests.put(url, json=data)
        else:
            print(f"  ❌ {name}: 不支持的方法 {method}")
            tests_failed += 1
            return None

        if response.status_code == expected_status:
            print(f"  ✅ {name}: {response.status_code} OK")
            tests_passed += 1
            return response.json()
        else:
            print(f"  ❌ {name}: 期望 {expected_status}, 实际 {response.status_code}")
            print(f"     响应: {response.text[:100]}")
            tests_failed += 1
            return None
    except Exception as e:
        print(f"  ❌ {name}: 错误 - {str(e)}")
        tests_failed += 1
        return None


# 1. 基础接口测试
print("\n📡 1. 基础接口")
test_api("健康检查", "GET", f"{BASE_URL}/health")
test_api("根路由", "GET", f"{BASE_URL}/")

# 2. 统计分析接口
print("\n📊 2. 统计分析接口")
test_api("系统指标", "GET", f"{BASE_URL}/api/v1/analytics/metrics")
test_api("指标摘要", "GET", f"{BASE_URL}/api/v1/analytics/metrics/summary?hours=24")
test_api("评测统计", "GET", f"{BASE_URL}/api/v1/analytics/evaluation/stats")
test_api("低分样本", "GET", f"{BASE_URL}/api/v1/analytics/evaluation/low-scores?limit=10")
test_api("A/B实验列表", "GET", f"{BASE_URL}/api/v1/analytics/ab-test/experiments")

# 创建A/B测试实验
exp_url = f"{BASE_URL}/api/v1/analytics/ab-test/experiments?experiment_id=test-exp-001&name=测试实验&description=API测试创建的实验&variant_a=control&variant_b=treatment&traffic_split=0.5"
test_api("创建A/B实验", "POST", exp_url)
test_api("A/B实验结果", "GET", f"{BASE_URL}/api/v1/analytics/ab-test/experiments/test-exp-001/results")

# 3. 反馈接口
print("\n💬 3. 用户反馈接口")

# 提交点赞
test_api("提交点赞", "POST", f"{BASE_URL}/api/v1/feedback/submit", data={
    "user_id": 1,
    "session_id": "test-session-1",
    "feedback_type": "like",
    "content": "回答很准确",
})

# 提交点踩
test_api("提交点踩", "POST", f"{BASE_URL}/api/v1/feedback/submit", data={
    "user_id": 1,
    "session_id": "test-session-1",
    "feedback_type": "dislike",
    "content": "回答不准确，信息过时",
    "categories": ["inaccurate", "incomplete"],
})

# 提交CSAT评分
test_api("提交CSAT评分", "POST", f"{BASE_URL}/api/v1/feedback/submit", data={
    "user_id": 1,
    "session_id": "test-session-1",
    "feedback_type": "csat",
    "score": 5,
})

test_api("反馈历史", "GET", f"{BASE_URL}/api/v1/feedback/history/1?limit=10")
test_api("反馈统计", "GET", f"{BASE_URL}/api/v1/feedback/stats?days=7")

# 4. 工单管理接口
print("\n📋 4. 工单管理接口")

# 创建工单
ticket_data = {
    "user_id": 1,
    "category": "投诉",
    "content": "产品质量有问题，要求赔偿",
    "priority": "high",
    "session_id": "test-session-1",
}
ticket_result = test_api("创建工单", "POST", f"{BASE_URL}/api/v1/tickets", data=ticket_data)

if ticket_result and ticket_result.get("data", {}).get("ticket_id"):
    ticket_id = ticket_result["data"]["ticket_id"]
    test_api("查询工单", "GET", f"{BASE_URL}/api/v1/tickets/{ticket_id}")
    
    # 更新工单状态
    test_api("更新工单", "PUT", f"{BASE_URL}/api/v1/tickets/{ticket_id}", data={
        "status": "processing",
        "assigned_to": "客服主管",
    })

test_api("工单列表", "GET", f"{BASE_URL}/api/v1/tickets?page=1&page_size=10")
test_api("工单统计", "GET", f"{BASE_URL}/api/v1/tickets/stats")

# 5. 转人工接口
print("\n🤝 5. 人机协同接口")

handoff_data = {
    "user_id": 1,
    "session_id": "test-session-1",
    "reason": "用户主动要求人工客服",
    "priority": "normal",
}
handoff_result = test_api("请求转人工", "POST", f"{BASE_URL}/api/v1/handoff", data=handoff_data)

test_api("转人工请求列表", "GET", f"{BASE_URL}/api/v1/handoff/requests?limit=10")
test_api("客服列表", "GET", f"{BASE_URL}/api/v1/agents")
test_api("协同统计", "GET", f"{BASE_URL}/api/v1/collaboration/stats")

# 6. 聊天接口（保持兼容性测试）
print("\n💬 6. 聊天接口（兼容性）")

chat_data = {
    "user_id": 1,
    "message": "你好，我想查询一下订单",
}
chat_result = test_api("发送消息", "POST", f"{BASE_URL}/api/v1/chat/send", data=chat_data)

if chat_result and chat_result.get("session_id"):
    session_id = chat_result["session_id"]
    test_api("聊天历史", "GET", f"{BASE_URL}/api/v1/chat/history/{session_id}")

test_api("可用工具", "GET", f"{BASE_URL}/api/v1/chat/tools")
test_api("意图类型", "GET", f"{BASE_URL}/api/v1/chat/intents")

# 7. 会话接口
print("\n📁 7. 会话接口")
test_api("用户会话列表", "GET", f"{BASE_URL}/api/v1/chat/sessions/1")

# 总结
print("\n" + "=" * 60)
print(f"📊 测试结果: {tests_passed} 通过, {tests_failed} 失败")
print("=" * 60)

if tests_failed == 0:
    print("🎉 所有测试通过！")
else:
    print(f"⚠️ 有 {tests_failed} 个测试失败")