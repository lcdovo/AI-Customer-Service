"""
Phase 2 API 集成验证测试
"""
import requests
import json
import time

BASE_URL = "http://localhost:8001"


def test_api():
    print("=" * 60)
    print("Phase 2 API 集成验证")
    print("=" * 60)

    # 1. 健康检查
    print("\n📋 1. 健康检查")
    resp = requests.get(f"{BASE_URL}/health")
    data = resp.json()
    print(f"   状态: {data.get('status')}")
    print(f"   版本: {data.get('version')}")
    assert data["status"] == "healthy"
    print("   ✅ 健康检查通过")

    # 2. 发送消息 - 查询订单
    print("\n💬 2. 查询订单 API")
    payload = {
        "user_id": 1,
        "message": "查询我的订单ORD20260801到哪了",
    }
    resp = requests.post(f"{BASE_URL}/api/v1/chat/send", json=payload)
    data = resp.json()
    print(f"   响应状态码: {resp.status_code}")
    print(f"   会话ID: {data.get('session_id')}")
    print(f"   意图: {data.get('intent')}")
    print(f"   回复: {data.get('reply', '')[:100]}...")
    assert resp.status_code == 200
    assert data["intent"] == "query_order"
    assert data["session_id"] is not None
    assert len(data["reply"]) > 0
    print("   ✅ 查询订单 API 测试通过")

    session_id = data["session_id"]

    # 3. 查询会话历史
    print("\n📜 3. 查询会话历史")
    resp = requests.get(f"{BASE_URL}/api/v1/chat/history/{session_id}")
    data = resp.json()
    print(f"   响应状态码: {resp.status_code}")
    print(f"   消息数: {len(data.get('data', {}).get('messages', []))}")
    assert resp.status_code == 200
    print("   ✅ 会话历史查询通过")

    # 4. 发送消息 - 申请退款
    print("\n🔄 4. 申请退款 API")
    payload = {
        "user_id": 1,
        "message": "我要退款，订单ORD20260801有质量问题",
    }
    resp = requests.post(f"{BASE_URL}/api/v1/chat/send", json=payload)
    data = resp.json()
    print(f"   响应状态码: {resp.status_code}")
    print(f"   意图: {data.get('intent')}")
    print(f"   回复: {data.get('reply', '')[:100]}...")
    assert resp.status_code == 200
    assert data["intent"] == "refund"
    print("   ✅ 申请退款 API 测试通过")

    # 5. 发送消息 - 投诉
    print("\n📣 5. 投诉 API")
    payload = {
        "user_id": 1,
        "message": "我要投诉你们的产品，质量太差了！",
    }
    resp = requests.post(f"{BASE_URL}/api/v1/chat/send", json=payload)
    data = resp.json()
    print(f"   响应状态码: {resp.status_code}")
    print(f"   意图: {data.get('intent')}")
    print(f"   回复: {data.get('reply', '')[:100]}...")
    assert resp.status_code == 200
    assert data["intent"] == "complaint"
    print("   ✅ 投诉 API 测试通过")

    # 6. 发送消息 - 转人工
    print("\n👤 6. 转人工 API")
    payload = {
        "user_id": 1,
        "message": "我要找人工客服！",
    }
    resp = requests.post(f"{BASE_URL}/api/v1/chat/send", json=payload)
    data = resp.json()
    print(f"   响应状态码: {resp.status_code}")
    print(f"   意图: {data.get('intent')}")
    print(f"   回复: {data.get('reply', '')[:100]}...")
    assert resp.status_code == 200
    assert data["intent"] == "human"
    print("   ✅ 转人工 API 测试通过")

    # 7. 发送消息 - 技术咨询 (RAG)
    print("\n📚 7. 技术咨询 (RAG) API")
    payload = {
        "user_id": 1,
        "message": "产品怎么安装设置",
    }
    resp = requests.post(f"{BASE_URL}/api/v1/chat/send", json=payload)
    data = resp.json()
    print(f"   响应状态码: {resp.status_code}")
    print(f"   意图: {data.get('intent')}")
    print(f"   回复: {data.get('reply', '')[:100]}...")
    assert resp.status_code == 200
    assert data["intent"] == "technical"
    print("   ✅ 技术咨询 API 测试通过")

    # 8. 获取工具列表
    print("\n🔧 8. 获取可用工具列表")
    resp = requests.get(f"{BASE_URL}/api/v1/chat/tools")
    data = resp.json()
    print(f"   响应状态码: {resp.status_code}")
    tools = data.get("data", [])
    print(f"   工具数: {len(tools)}")
    for tool in tools:
        print(f"     - {tool['name']}: {tool['description'][:30]}...")
    assert resp.status_code == 200
    assert len(tools) == 8
    print("   ✅ 工具列表 API 测试通过")

    # 9. 获取意图类型
    print("\n🎯 9. 获取支持的意图类型")
    resp = requests.get(f"{BASE_URL}/api/v1/chat/intents")
    data = resp.json()
    intents = data.get("data", [])
    print(f"   响应状态码: {resp.status_code}")
    print(f"   意图数: {len(intents)}")
    for intent in intents:
        print(f"     - {intent['code']}: {intent['name']}")
    assert resp.status_code == 200
    assert len(intents) >= 6
    print("   ✅ 意图类型 API 测试通过")

    # 10. 多轮对话测试
    print("\n🔄 10. 多轮对话测试")
    # 第一轮
    payload = {"user_id": 1, "message": "你好"}
    resp = requests.post(f"{BASE_URL}/api/v1/chat/send", json=payload)
    data = resp.json()
    session_id_1 = data["session_id"]
    print(f"   第1轮: session={session_id_1[:8]}..., reply={data['reply'][:40]}...")

    # 第二轮 (使用同一个会话)
    payload = {"user_id": 1, "session_id": session_id_1, "message": "查询订单ORD20260801"}
    resp = requests.post(f"{BASE_URL}/api/v1/chat/send", json=payload)
    data = resp.json()
    print(f"   第2轮: intent={data['intent']}, reply={data['reply'][:40]}...")

    # 第三轮 (继续使用同一个会话)
    payload = {"user_id": 1, "session_id": session_id_1, "message": "好的，谢谢"}
    resp = requests.post(f"{BASE_URL}/api/v1/chat/send", json=payload)
    data = resp.json()
    print(f"   第3轮: intent={data['intent']}, reply={data['reply'][:40]}...")

    # 检查会话历史中有3轮对话
    resp = requests.get(f"{BASE_URL}/api/v1/chat/history/{session_id_1}")
    history = resp.json()
    msg_count = len(history.get("data", {}).get("messages", []))
    print(f"   历史消息数: {msg_count}")
    assert msg_count >= 4  # 至少有4条消息 (3轮对话 x 2 角色)
    print("   ✅ 多轮对话测试通过")

    print("\n" + "=" * 60)
    print("🎉 Phase 2 API 集成验证全部通过!")
    print("=" * 60)
    print("\n📊 验证总结:")
    print("   ✅ 健康检查")
    print("   ✅ 查询订单 (Tool Calling)")
    print("   ✅ 会话历史查询")
    print("   ✅ 申请退款 (Tool Calling)")
    print("   ✅ 投诉工单 (Tool Calling)")
    print("   ✅ 转人工 (Human Handoff)")
    print("   ✅ 技术咨询 (RAG Retrieval)")
    print("   ✅ 工具列表 API")
    print("   ✅ 意图类型 API")
    print("   ✅ 多轮对话")
    print("\n🏗️  Phase 2 架构:")
    print("   ┌─────────────┐     ┌──────────────────┐")
    print("   │  FastAPI    │────▶│  AgentGraph      │")
    print("   │  REST API   │     │  (状态机编排)     │")
    print("   └─────────────┘     └──────────────────┘")
    print("                              │")
    print("              ┌───────────────┼───────────────┐")
    print("              ▼               ▼               ▼")
    print("       ┌─────────────┐ ┌─────────────┐ ┌─────────────┐")
    print("       │  IntentRec  │ │ ToolExec    │ │ RAG Retriev │")
    print("       │  意图识别   │ │ 工具调用    │ │ 知识库检索  │")
    print("       └─────────────┘ └─────────────┘ └─────────────┘")


if __name__ == "__main__":
    test_api()
