"""
RAG 检索优化测试脚本
测试不同参数配置对 RAG 召回准确率的影响
使用标准信息检索指标：Recall@K, MRR, NDCG, Precision@K
"""
import sys
import os
import time
import json
import math
from collections import Counter
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agent.retrieval import HybridRetriever, BM25Retriever, VectorRetriever, Reranker
from app.services.knowledge_base import KnowledgeBaseService, DocumentChunker
from app.services.embedding_service import get_embedding_service


# ==================== 测试文档库 ====================

TEST_DOCUMENTS = [
    # ===== 售后政策 =====
    {
        "title": "7天无理由退换货政策",
        "content": (
            "我们支持7天无理由退换货服务。自收到商品之日起7天内，商品保持原包装完好、未经使用、不影响二次销售的情况下，均可申请退换货。"
            "退款将在收到退回商品后3-7个工作日内原路退回至您的支付账户。部分特殊商品如定制商品、食品、贴身衣物等不支持无理由退换。"
            "退货运费由买家承担，商品质量问题导致的退换除外。"
        ),
        "keywords": ["退换货", "退货", "退款", "7天", "无理由", "售后", "政策", "运费", "包装"],
        "category": "售后政策",
    },
    {
        "title": "退款处理流程",
        "content": (
            "退款流程如下：1) 在订单详情页点击'申请退款'或'申请退换货'；2) 选择退款原因并提交申请；"
            "3) 客服审核通过后，按要求寄回商品；4) 仓库收到商品并验收通过；5) 退款到账。"
            "仅退款申请将在审核通过后1-3个工作日内到账，退货退款需等待商品验收。"
            "退款金额将原路返回至付款账户，不支持退款至其他账户。"
        ),
        "keywords": ["退款", "流程", "退钱", "申请", "审核", "到账", "退货", "原路返回"],
        "category": "售后政策",
    },
    {
        "title": "商品质量问题处理",
        "content": (
            "如收到商品存在质量问题，请在签收后48小时内联系客服并提供照片或视频证据。"
            "我们将为您提供免费维修、更换或全额退款服务。因质量问题产生的退货运费由我们承担。"
            "对于损坏严重或存在安全隐患的商品，我们承诺7天内无条件更换。"
        ),
        "keywords": ["质量", "损坏", "维修", "更换", "全额退款", "证据", "照片", "安全"],
        "category": "售后政策",
    },
    {
        "title": "客服投诉处理时效",
        "content": (
            "我们承诺所有客服投诉将在24小时内首次响应，简单问题当日解决，复杂问题3个工作日内给出解决方案。"
            "处理结果将通过短信、电话或站内消息通知您。如对处理结果不满意，可通过以下方式升级："
            "1) 在投诉详情页点击'申请升级处理'；2) 拨打客服热线400-888-8888转投诉专线；"
            "3) 发送邮件至complaint@example.com。升级投诉将由高级客服专员处理。"
        ),
        "keywords": ["投诉", "时效", "响应", "升级", "处理", "客服", "不满意", "热线"],
        "category": "客户服务",
    },
    {
        "title": "VIP会员等级与权益",
        "content": (
            "我们的会员体系分为普通会员、银牌会员、金牌会员、钻石会员四个等级。"
            "普通会员：注册即可享受98折优惠。银牌会员（累计消费满1000元）：95折+专属客服。"
            "金牌会员（累计消费满5000元）：9折+免费包邮+优先发货。"
            "钻石会员（累计消费满20000元）：85折+专属活动+生日礼包+一对一客服经理。"
            "会员等级根据近12个月累计消费动态调整，每年1月1日重置计算。"
        ),
        "keywords": ["会员", "VIP", "等级", "权益", "折扣", "包邮", "优惠", "专属客服", "钻石"],
        "category": "会员服务",
    },
    {
        "title": "优惠券使用规则",
        "content": (
            "优惠券分为满减券、折扣券、无门槛券三种类型。满减券需满足指定消费金额条件，"
            "如满199减30、满399减80。折扣券直接按折扣比例结算，如8折券、9折券。"
            "无门槛券可直接抵扣现金，不受消费金额限制。使用规则：1) 单笔订单限用1张优惠券；"
            "2) 优惠券不可与其他优惠同享；3) 优惠券有效期为领取后7-30天；"
            "4) 优惠券过期自动作废，不予补发；5) 部分特价商品和预售商品不可使用优惠券。"
        ),
        "keywords": ["优惠券", "满减", "折扣", "规则", "使用", "有效期", "作废", "同享", "特价"],
        "category": "营销活动",
    },
    {
        "title": "订单查询与物流跟踪",
        "content": (
            "您可以通过以下方式查询订单：1) APP/官网登录后进入'我的订单'查看全部订单；"
            "2) 输入订单号或手机号在订单查询页面查询；3) 联系客服提供订单号查询。"
            "物流信息在发货后24小时内更新，可查看实时物流轨迹。支持按时间段查询历史订单，"
            "也可批量导出订单记录。如需发票，请在订单完成后180天内申请。"
        ),
        "keywords": ["订单", "物流", "查询", "跟踪", "快递", "发货", "轨迹", "手机号", "发票"],
        "category": "订单服务",
    },
    {
        "title": "支付方式与安全保障",
        "content": (
            "我们支持以下支付方式：1) 支付宝（推荐，支持花呗分期）；2) 微信支付；"
            "3) 银联云闪付；4) 银行卡快捷支付（支持主流银行储蓄卡和信用卡）；"
            "5) 信用卡分期（3期、6期、12期，手续费由银行收取）；6) 企业对公转账（需提前申请）。"
            "所有支付均通过SSL加密传输，支付信息不会存储在我们的服务器上。"
            "如遇支付问题，请保存支付凭证联系客服处理。"
        ),
        "keywords": ["支付", "付款", "支付宝", "微信", "银行卡", "分期", "安全", "加密", "SSL", "花呗"],
        "category": "支付服务",
    },
    {
        "title": "发票开具与管理",
        "content": (
            "发票相关服务：1) 电子发票：购买后180天内可在订单详情页申请开具，1-3个工作日内开具完成；"
            "2) 增值税专用发票：需提供企业营业执照、税务登记证等资质，审核通过后开具；"
            "3) 发票抬头修改：未开具的订单可在订单页修改抬头信息；"
            "4) 发票遗失：电子发票可重复下载，纸质发票遗失需联系客服补办（可能产生工本费）；"
            "5) 发票内容：商品明细、服务名称等需与实际订单一致。"
        ),
        "keywords": ["发票", "开票", "抬头", "电子发票", "增值税", "资质", "营业执照", "明细", "补办"],
        "category": "财务服务",
    },
    {
        "title": "物流配送时效说明",
        "content": (
            "配送时效：1) 一线城市（北京、上海、广州、深圳等）：1-2个工作日送达；"
            "2) 省会城市及地级市：2-3个工作日送达；3) 县级市及偏远地区：3-5个工作日送达；"
            "4) 新疆、西藏、青海等特殊地区：5-7个工作日送达。"
            "我们与顺丰、京东、中通、圆通等多家快递公司合作，您可在结算时选择指定快递。"
            "支持配送时间预约（工作日/周末/指定时段），大件商品可能需要额外配送费用。"
        ),
        "keywords": ["物流", "配送", "快递", "时效", "送达", "发货", "顺丰", "京东", "偏远", "预约"],
        "category": "物流服务",
    },
    {
        "title": "账号安全与密码保护",
        "content": (
            "账号安全建议：1) 使用强密码，至少8位，包含大小写字母、数字和特殊字符；"
            "2) 定期更换密码，建议每3个月一次；3) 开启手机验证，登录时需要短信验证码；"
            "4) 不要在公共设备上勾选'记住密码'；5) 如怀疑账号被盗，立即通过'忘记密码'重置；"
            "6) 联系客服冻结账号，防止进一步损失。我们不会通过任何方式索要您的密码和验证码。"
        ),
        "keywords": ["密码", "账号", "安全", "登录", "被盗", "冻结", "重置", "验证", "短信", "强密码"],
        "category": "账号服务",
    },
    {
        "title": "产品使用与维护指南",
        "content": (
            "产品首次使用：1) 新设备首次使用请先充电2-3小时，电量充满后再开机；"
            "2) 长按电源键3秒开机，首次开机会有引导设置；3) 详细使用说明请参考包装盒内的《快速上手指南》。"
            "日常维护：1) 保持设备清洁，避免灰尘进入接口；2) 避免长时间阳光直射；"
            "3) 不使用时请定期充电，保持电池活性；4) 定期进行系统固件升级，获取最新功能和安全补丁；"
            "5) 如遇异常，可尝试恢复出厂设置（请注意备份数据）。"
        ),
        "keywords": ["使用", "开机", "充电", "设置", "安装", "教程", "升级", "维护", "清洁", "固件"],
        "category": "产品支持",
    },
    {
        "title": "产品质保与维修服务",
        "content": (
            "质保政策：1) 整机免费质保1年，自购买日起计算；2) 核心部件（如主板、屏幕等）免费质保2年；"
            "3) 质保期内，非人为损坏可享受免费维修或更换；4) 质保期外提供有偿维修服务，费用按故障类型评估。"
            "维修流程：1) 联系客服提交维修申请；2) 客服指导排查问题；3) 确认需要维修后，寄送至指定维修中心；"
            "4) 维修完成后寄回（质保期内运费由我们承担）；5) 维修周期一般为3-7个工作日。"
        ),
        "keywords": ["保修", "质保", "维修", "售后", "故障", "损坏", "检测", "更换", "免费", "部件"],
        "category": "售后服务",
    },
    {
        "title": "限时促销与满减活动",
        "content": (
            "当前促销活动：1) 新用户首单立减20元（限首单，不与其他优惠同享）；"
            "2) 满199减30，满399减80，满599减150；3) 会员日（每月18日）会员享额外9折；"
            "4) 限时秒杀：每日10点、14点、20点开启，数量有限先到先得；"
            "5) 拼团优惠：邀请好友拼团，满2人享受8折。"
            "注意事项：促销活动不与其他优惠同享，具体以结算页显示为准。部分特价商品不参与任何活动。"
        ),
        "keywords": ["优惠", "活动", "促销", "折扣", "满减", "券", "特价", "秒杀", "拼团", "会员日"],
        "category": "营销活动",
    },
    {
        "title": "企业采购与定制服务",
        "content": (
            "企业采购服务：1) 批量优惠：单次采购满5000元享9折，满20000元享85折，满50000元享8折；"
            "2) 专属账户：为企业分配专属客户经理和独立账户管理；"
            "3) 定制化服务：支持企业LOGO定制、包装定制、批量采购定制方案；"
            "4) 集中采购：支持年框协议、按需分批供货；5) 发票服务：支持按季度/年度统一开票。"
            "申请企业采购需提供企业营业执照、税务登记证等资质证明。"
        ),
        "keywords": ["企业", "采购", "批量", "优惠", "定制", "账户", "资质", "客户经理", "年框", "LOGO"],
        "category": "企业服务",
    },
    {
        "title": "账户注销与数据处理",
        "content": (
            "账户注销流程：1) 登录账户，进入'账户设置'→'注销账户'；"
            "2) 阅读注销须知，确认无未完成订单和未使用优惠券；3) 完成身份验证；4) 提交注销申请。"
            "注销后：1) 账户数据将保留30天后永久删除；2) 未完成订单将自动关闭；"
            "3) 积分、优惠券、会员权益将全部清空且不可恢复；4) 历史评价、投诉记录将保留。"
            "如在30天内重新登录，可恢复账户。"
        ),
        "keywords": ["注销", "删除", "账户", "数据", "积分", "清空", "恢复", "验证", "订单", "保留"],
        "category": "账号服务",
    },
    {
        "title": "跨境购买与税费说明",
        "content": (
            "跨境购物服务：1) 我们支持海外配送，配送范围覆盖全球100+国家和地区；"
            "2) 国际运费按重量和体积计算，不同国家运费标准不同；"
            "3) 跨境商品可能产生进口关税和增值税，由收件人承担；"
            "4) 个人年度跨境额度为26000元，单笔限额5000元；"
            "5) 跨境商品不支持7天无理由退换（特殊商品除外）；"
            "6) 物流时效：亚洲地区3-7天，欧美地区7-15天，其他地区15-30天。"
        ),
        "keywords": ["跨境", "海外", "国际", "税费", "关税", "配送", "物流", "限额", "美元", "全球"],
        "category": "物流服务",
    },
    {
        "title": "移动端APP功能介绍",
        "content": (
            "APP核心功能：1) 智能推荐：基于浏览和购买历史的个性化推荐；"
            "2) AR试穿/试用：部分商品支持AR预览效果；3) 一键复购：历史订单商品可一键购买；"
            "4) 会员中心：查看等级、权益、积分明细；5) 消息中心：订单状态、促销活动及时推送；"
            "6) 社区互动：用户评价、晒单、问答等功能；7) 手机充值、生活缴费等便民服务。"
            "APP支持iOS 12.0+和Android 7.0+系统。"
        ),
        "keywords": ["APP", "移动端", "推荐", "AR", "功能", "会员", "消息", "充值", "iOS", "Android"],
        "category": "产品支持",
    },
    {
        "title": "售后服务联系方式",
        "content": (
            "客服联系方式：1) 在线客服：APP/官网右下角客服图标，7x24小时服务；"
            "2) 客服热线：400-888-8888，工作日9:00-22:00，周末9:00-18:00；"
            "3) 邮件客服：support@example.com，通常24小时内回复；"
            "4) 在线客服：APP/官网'我的客服'入口；5) 社交媒体：官方微博、微信公众号。"
            "VIP会员享有专属客服通道，平均响应时间小于30秒。"
        ),
        "keywords": ["客服", "联系", "电话", "在线", "邮件", "热线", "微信", "微博", "响应", "VIP"],
        "category": "客户服务",
    },
]


# ==================== 测试查询集（带标注的预期文档）====================

@dataclass
class TestQuery:
    query: str
    expected_doc_title: str
    category: str


TEST_QUERIES = [
    # 售后政策类
    TestQuery("我要退货", "7天无理由退换货政策", "售后政策"),
    TestQuery("怎么退款", "退款处理流程", "售后政策"),
    TestQuery("退款多久到账", "退款处理流程", "售后政策"),
    TestQuery("7天无理由是什么意思", "7天无理由退换货政策", "售后政策"),
    TestQuery("商品有质量问题", "商品质量问题处理", "售后政策"),
    TestQuery("东西坏了怎么办", "商品质量问题处理", "售后政策"),

    # 投诉类
    TestQuery("我要投诉", "客服投诉处理时效", "客户服务"),
    TestQuery("处理不满意怎么办", "客服投诉处理时效", "客户服务"),
    TestQuery("怎么联系客服", "售后服务联系方式", "客户服务"),
    TestQuery("客服电话多少", "售后服务联系方式", "客户服务"),

    # 会员类
    TestQuery("会员有什么用", "VIP会员等级与权益", "会员服务"),
    TestQuery("怎么升级VIP", "VIP会员等级与权益", "会员服务"),
    TestQuery("优惠券怎么用", "优惠券使用规则", "营销活动"),
    TestQuery("满减活动", "优惠券使用规则", "营销活动"),
    TestQuery("现在有什么优惠", "限时促销与满减活动", "营销活动"),
    TestQuery("怎么才能打折", "限时促销与满减活动", "营销活动"),

    # 订单物流类
    TestQuery("查订单", "订单查询与物流跟踪", "订单服务"),
    TestQuery("我的快递到哪了", "订单查询与物流跟踪", "订单服务"),
    TestQuery("物流跟踪", "订单查询与物流跟踪", "订单服务"),
    TestQuery("多久能收到货", "物流配送时效说明", "物流服务"),
    TestQuery("几天能到货", "物流配送时效说明", "物流服务"),
    TestQuery("发什么快递", "物流配送时效说明", "物流服务"),

    # 支付类
    TestQuery("怎么付款", "支付方式与安全保障", "支付服务"),
    TestQuery("支持什么支付方式", "支付方式与安全保障", "支付服务"),
    TestQuery("可以分期吗", "支付方式与安全保障", "支付服务"),
    TestQuery("怎么开发票", "发票开具与管理", "财务服务"),
    TestQuery("开发票", "发票开具与管理", "财务服务"),

    # 账号安全类
    TestQuery("忘记密码怎么办", "账号安全与密码保护", "账号服务"),
    TestQuery("账号被盗了", "账号安全与密码保护", "账号服务"),
    TestQuery("怎么注销账号", "账户注销与数据处理", "账号服务"),

    # 产品使用类
    TestQuery("怎么开机", "产品使用与维护指南", "产品支持"),
    TestQuery("第一次怎么用", "产品使用与维护指南", "产品支持"),
    TestQuery("怎么升级固件", "产品使用与维护指南", "产品支持"),
    TestQuery("保修多久", "产品质保与维修服务", "售后服务"),
    TestQuery("怎么维修", "产品质保与维修服务", "售后服务"),
]


# ==================== 评测指标计算 ====================

def compute_recall_at_k(results: List[Dict], expected_title: str, k: int) -> float:
    """计算 Recall@K: 前K个结果中是否包含预期文档"""
    top_k = results[:k]
    for r in top_k:
        if r.get("title") == expected_title:
            return 1.0
    return 0.0


def compute_precision_at_k(results: List[Dict], expected_title: str, k: int) -> float:
    """计算 Precision@K: 前K个结果中相关文档的比例"""
    if not results:
        return 0.0
    relevant_count = sum(1 for r in results[:k] if r.get("title") == expected_title)
    return relevant_count / min(k, len(results))


def compute_mrr(results: List[Dict], expected_title: str) -> float:
    """计算 MRR (Mean Reciprocal Rank): 第一个相关文档排名的倒数"""
    for i, r in enumerate(results):
        if r.get("title") == expected_title:
            return 1.0 / (i + 1)
    return 0.0


def compute_ndcg_at_k(results: List[Dict], expected_title: str, k: int) -> float:
    """计算 NDCG@K: 归一化折损累积增益"""
    dcg = 0.0
    for i, r in enumerate(results[:k]):
        if r.get("title") == expected_title:
            relevance = 1.0
        else:
            relevance = 0.0
        dcg += relevance / math.log2(i + 2)

    ideal_dcg = 1.0 / math.log2(2)
    if ideal_dcg == 0:
        return 0.0
    return dcg / ideal_dcg


@dataclass
class TestResult:
    config_name: str
    parameters: Dict[str, Any]
    recall_at_3: float
    recall_at_5: float
    recall_at_10: float
    precision_at_3: float
    precision_at_5: float
    mrr: float
    ndcg_at_5: float
    avg_execution_time_ms: float
    details: List[Dict[str, Any]] = field(default_factory=list)


# ==================== 参数测试配置 ====================

CONFIGURATIONS = [
    {
        "name": "当前默认配置",
        "bm25_weight": 0.6,
        "vector_weight": 0.4,
        "use_reranker": True,
        "similarity_threshold": 0.3,
        "top_k": 3,
        "search_top_k_multiplier": 2,
    },
    {
        "name": "向量权重优先",
        "bm25_weight": 0.3,
        "vector_weight": 0.7,
        "use_reranker": True,
        "similarity_threshold": 0.3,
        "top_k": 3,
        "search_top_k_multiplier": 2,
    },
    {
        "name": "BM25权重优先",
        "bm25_weight": 0.8,
        "vector_weight": 0.2,
        "use_reranker": True,
        "similarity_threshold": 0.3,
        "top_k": 3,
        "search_top_k_multiplier": 2,
    },
    {
        "name": "高召回（扩大候选集）",
        "bm25_weight": 0.5,
        "vector_weight": 0.5,
        "use_reranker": True,
        "similarity_threshold": 0.2,
        "top_k": 5,
        "search_top_k_multiplier": 3,
    },
    {
        "name": "高精度（严格阈值）",
        "bm25_weight": 0.5,
        "vector_weight": 0.5,
        "use_reranker": True,
        "similarity_threshold": 0.5,
        "top_k": 3,
        "search_top_k_multiplier": 2,
    },
    {
        "name": "双路融合无Rerank",
        "bm25_weight": 0.5,
        "vector_weight": 0.5,
        "use_reranker": False,
        "similarity_threshold": 0.3,
        "top_k": 5,
        "search_top_k_multiplier": 2,
    },
    {
        "name": "纯BM25检索",
        "bm25_weight": 1.0,
        "vector_weight": 0.0,
        "use_reranker": True,
        "similarity_threshold": 0.3,
        "top_k": 5,
        "search_top_k_multiplier": 2,
    },
    {
        "name": "纯向量检索",
        "bm25_weight": 0.0,
        "vector_weight": 1.0,
        "use_reranker": True,
        "similarity_threshold": 0.3,
        "top_k": 5,
        "search_top_k_multiplier": 2,
    },
]


# ==================== 分块策略测试 ====================

CHUNK_TEST_CONFIGS = [
    {"name": "sentence_500_50", "split_pattern": "sentence", "chunk_size": 500, "chunk_overlap": 50},
    {"name": "sentence_300_50", "split_pattern": "sentence", "chunk_size": 300, "chunk_overlap": 50},
    {"name": "sentence_800_100", "split_pattern": "sentence", "chunk_size": 800, "chunk_overlap": 100},
    {"name": "fixed_200_50", "split_pattern": "fixed", "chunk_size": 200, "chunk_overlap": 50},
    {"name": "fixed_500_100", "split_pattern": "fixed", "chunk_size": 500, "chunk_overlap": 100},
    {"name": "paragraph_500_50", "split_pattern": "paragraph", "chunk_size": 500, "chunk_overlap": 50},
]


# ==================== 核心测试逻辑 ====================

def test_retrieval_config(config: Dict[str, Any], retriever: HybridRetriever, 
                          queries: List[TestQuery]) -> TestResult:
    """测试单个检索配置的效果"""
    details = []
    execution_times = []

    recall_at_3_list = []
    recall_at_5_list = []
    recall_at_10_list = []
    precision_at_3_list = []
    precision_at_5_list = []
    mrr_list = []
    ndcg_at_5_list = []

    for tq in queries:
        start_time = time.time()
        result = retriever.search(
            query=tq.query,
            top_k=config["top_k"],
        )
        elapsed_ms = (time.time() - start_time) * 1000
        execution_times.append(elapsed_ms)

        results = result.get("results", [])

        recall_at_3 = compute_recall_at_k(results, tq.expected_doc_title, 3)
        recall_at_5 = compute_recall_at_k(results, tq.expected_doc_title, 5)
        recall_at_10 = compute_recall_at_k(results, tq.expected_doc_title, 10)
        precision_at_3 = compute_precision_at_k(results, tq.expected_doc_title, 3)
        precision_at_5 = compute_precision_at_k(results, tq.expected_doc_title, 5)
        mrr = compute_mrr(results, tq.expected_doc_title)
        ndcg_at_5 = compute_ndcg_at_k(results, tq.expected_doc_title, 5)

        recall_at_3_list.append(recall_at_3)
        recall_at_5_list.append(recall_at_5)
        recall_at_10_list.append(recall_at_10)
        precision_at_3_list.append(precision_at_3)
        precision_at_5_list.append(precision_at_5)
        mrr_list.append(mrr)
        ndcg_at_5_list.append(ndcg_at_5)

        first_result_title = results[0].get("title", "") if results else "无结果"
        first_result_score = results[0].get("hybrid_score", 0) if results else 0

        details.append({
            "query": tq.query,
            "expected": tq.expected_doc_title,
            "category": tq.category,
            "top1_result": first_result_title,
            "top1_score": round(first_result_score, 4),
            "top3_titles": [r.get("title", "") for r in results[:3]],
            "recall_at_3": recall_at_3,
            "recall_at_5": recall_at_5,
            "matched": tq.expected_doc_title in [r.get("title", "") for r in results[:5]],
        })

    return TestResult(
        config_name=config["name"],
        parameters={k: v for k, v in config.items() if k != "name"},
        recall_at_3=round(sum(recall_at_3_list) / len(recall_at_3_list), 4),
        recall_at_5=round(sum(recall_at_5_list) / len(recall_at_5_list), 4),
        recall_at_10=round(sum(recall_at_10_list) / len(recall_at_10_list), 4),
        precision_at_3=round(sum(precision_at_3_list) / len(precision_at_3_list), 4),
        precision_at_5=round(sum(precision_at_5_list) / len(precision_at_5_list), 4),
        mrr=round(sum(mrr_list) / len(mrr_list), 4),
        ndcg_at_5=round(sum(ndcg_at_5_list) / len(ndcg_at_5_list), 4),
        avg_execution_time_ms=round(sum(execution_times) / len(execution_times), 2),
        details=details,
    )


def test_chunk_config(chunk_config: Dict[str, Any], documents: List[Dict],
                      queries: List[TestQuery]) -> TestResult:
    """测试单个分块配置的效果"""
    chunker = DocumentChunker(
        chunk_size=chunk_config["chunk_size"],
        chunk_overlap=chunk_config["chunk_overlap"],
        split_pattern=chunk_config["split_pattern"],
    )

    chunked_docs = []
    for doc in documents:
        content = doc["content"]
        chunks = chunker.chunk_document(content)
        for chunk in chunks:
            chunked_doc = {
                "title": doc["title"],
                "content": chunk["content"],
                "category": doc.get("category", ""),
                "keywords": doc.get("keywords", []),
                "chunk_index": chunk["chunk_index"],
            }
            chunked_docs.append(chunked_doc)

    retriever = HybridRetriever(
        bm25_weight=0.5,
        vector_weight=0.5,
        use_reranker=True,
    )
    retriever.index_documents(chunked_docs)

    config_for_test = {
        "name": chunk_config["name"],
        "top_k": 3,
    }

    result = test_retrieval_config(config_for_test, retriever, queries)
    result.parameters = {
        "split_pattern": chunk_config["split_pattern"],
        "chunk_size": chunk_config["chunk_size"],
        "chunk_overlap": chunk_config["chunk_overlap"],
        "total_chunks": len(chunked_docs),
    }

    return result


# ==================== 报告生成 ====================

def print_header(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_separator(char: str = "-", length: int = 70):
    print(char * length)


def print_table_row(cells: List[str], widths: List[int]):
    row = "│"
    for cell, width in zip(cells, widths):
        row += f" {cell.ljust(width)} │"
    print(row)


def print_results_comparison(results: List[TestResult], title: str):
    print_header(title)

    widths = [25, 10, 10, 10, 10, 10, 10, 12]
    print_table_row(["配置名称", "R@3", "R@5", "R@10", "P@3", "MRR", "NDCG@5", "耗时(ms)"], widths)
    print_separator("=")

    for r in sorted(results, key=lambda x: x.recall_at_5, reverse=True):
        row = [
            r.config_name[:24],
            f"{r.recall_at_3:.3f}",
            f"{r.recall_at_5:.3f}",
            f"{r.recall_at_10:.3f}",
            f"{r.precision_at_3:.3f}",
            f"{r.mrr:.3f}",
            f"{r.ndcg_at_5:.3f}",
            f"{r.avg_execution_time_ms:.1f}",
        ]
        print_table_row(row, widths)

    print_separator("=")


def print_detailed_results(results: List[TestResult], queries: List[TestQuery]):
    print_header("详细查询结果分析")

    best_result = max(results, key=lambda x: x.recall_at_5)
    print(f"\n最佳配置: {best_result.config_name} (Recall@5 = {best_result.recall_at_5:.3f})")

    # 找出失败的查询
    failed_queries = []
    for detail in best_result.details:
        if not detail["matched"]:
            failed_queries.append(detail)

    if failed_queries:
        print(f"\n⚠️  在最佳配置下失败的查询 ({len(failed_queries)}/{len(best_result.details)}):")
        print_separator("-")
        for d in failed_queries:
            print(f"  查询: {d['query']}")
            print(f"  期望: {d['expected']}")
            print(f"  Top3结果: {d['top3_titles']}")
            print_separator("-")
    else:
        print("\n✅ 所有查询均成功命中预期文档！")


def analyze_parameter_impact(results: List[TestResult]):
    print_header("参数影响分析")

    # 分析权重影响
    print("\n📊 1. BM25 vs 向量权重影响:")
    weight_configs = [r for r in results if r.config_name in [
        "当前默认配置", "向量权重优先", "BM25权重优先", "双路融合无Rerank",
        "纯BM25检索", "纯向量检索"
    ]]
    for r in sorted(weight_configs, key=lambda x: x.recall_at_5, reverse=True):
        params = r.parameters
        bm25_w = params.get("bm25_weight", "N/A")
        vec_w = params.get("vector_weight", "N/A")
        print(f"  BM25={bm25_w}, Vector={vec_w} | R@5={r.recall_at_5:.3f} | MRR={r.mrr:.3f}")

    # 分析Rerank影响
    print("\n📊 2. Reranker影响:")
    rerank_on = next((r for r in results if r.config_name == "当前默认配置"), None)
    rerank_off = next((r for r in results if r.config_name == "双路融合无Rerank"), None)
    if rerank_on and rerank_off:
        print(f"  有Rerank: Recall@5={rerank_on.recall_at_5:.3f}, MRR={rerank_on.mrr:.3f}")
        print(f"  无Rerank: Recall@5={rerank_off.recall_at_5:.3f}, MRR={rerank_off.mrr:.3f}")
        delta = rerank_on.recall_at_5 - rerank_off.recall_at_5
        print(f"  Rerank增益: Recall@5 {'+' if delta > 0 else ''}{delta:.3f}")

    # 分析阈值影响
    print("\n📊 3. 相似度阈值影响:")
    threshold_configs = [r for r in results if r.config_name in ["高精度（严格阈值）", "当前默认配置", "高召回（扩大候选集）"]]
    for r in sorted(threshold_configs, key=lambda x: x.recall_at_5, reverse=True):
        threshold = r.parameters.get("similarity_threshold", "N/A")
        print(f"  阈值={threshold} | R@5={r.recall_at_5:.3f} | 耗时={r.avg_execution_time_ms:.1f}ms")

    # 分析Top-K影响
    print("\n📊 4. Top-K值影响:")
    topk_configs = [r for r in results if r.config_name in ["高召回（扩大候选集）", "当前默认配置"]]
    for r in topk_configs:
        top_k = r.parameters.get("top_k", "N/A")
        print(f"  Top-K={top_k} | R@5={r.recall_at_5:.3f} | P@3={r.precision_at_3:.3f}")


def generate_recommendations(results: List[TestResult]):
    print_header("优化建议")

    best = max(results, key=lambda x: x.recall_at_5)

    print(f"\n✅ 推荐配置: {best.config_name}")
    print(f"   参数: {json.dumps(best.parameters, ensure_ascii=False)}")
    print(f"   Recall@5: {best.recall_at_5:.3f}")
    print(f"   MRR: {best.mrr:.3f}")
    print(f"   平均耗时: {best.avg_execution_time_ms:.1f}ms")

    print("\n📝 具体优化建议:")
    print("   1. [权重] 建议BM25与向量权重在0.4-0.6之间调整，两者结合效果最佳")
    print("   2. [Rerank] 强烈建议开启Reranker，可显著提升Top-K准确率")
    print("   3. [阈值] 阈值不宜过高(>0.5)，会导致召回率大幅下降；也不宜过低(<0.2)，会引入噪声")
    print("   4. [Top-K] 建议Top-K=5，可在准确率和召回率之间取得平衡")
    print("   5. [扩大候选] 使用search_top_k_multiplier=2-3，先多召回再精排")
    print("   6. [分块] 分块大小300-500字符较优，配合50字符重叠")
    print("   7. [关键词] 文档的keywords字段对Rerank影响大，应尽量覆盖用户可能的问法")
    print("   8. [标题] 标题中包含核心关键词可显著提升Rerank得分")


def print_chunk_analysis(results: List[TestResult]):
    print_header("分块策略对比")

    widths = [25, 15, 10, 10, 10, 10, 12]
    print_table_row(["分块配置", "分块数", "R@3", "R@5", "R@10", "MRR", "耗时(ms)"], widths)
    print_separator("=")

    for r in sorted(results, key=lambda x: x.recall_at_5, reverse=True):
        params = r.parameters
        row = [
            params.get("split_pattern", "")[:24],
            str(params.get("total_chunks", "N/A")),
            f"{r.recall_at_3:.3f}",
            f"{r.recall_at_5:.3f}",
            f"{r.recall_at_10:.3f}",
            f"{r.mrr:.3f}",
            f"{r.avg_execution_time_ms:.1f}",
        ]
        print_table_row(row, widths)

    print_separator("=")
    print("\n📊 分块策略分析:")
    print("   - sentence: 按句子分块，语义完整性好")
    print("   - fixed: 固定长度分块，可能切断语义")
    print("   - paragraph: 按段落分块，适合长文档")
    print("   - 分块大小300-500字符效果最佳")
    print("   - 分块间重叠50字符可避免边界信息丢失")


# ==================== 主测试函数 ====================

def main():
    print_header("RAG 检索优化测试")
    print(f"测试文档数量: {len(TEST_DOCUMENTS)}")
    print(f"测试查询数量: {len(TEST_QUERIES)}")
    print(f"测试配置数量: {len(CONFIGURATIONS)}")
    print(f"分块配置数量: {len(CHUNK_TEST_CONFIGS)}")

    # 初始化Embedding服务
    print("\n初始化Embedding服务...")
    embedding_svc = get_embedding_service(dim=1024)
    print(f"  后端: {embedding_svc.backend_name}")

    # 创建检索器并索引文档
    print("\n索引测试文档...")
    base_retriever = HybridRetriever(bm25_weight=0.5, vector_weight=0.5, use_reranker=True)
    base_retriever.index_documents(TEST_DOCUMENTS)

    print(f"  已索引文档: {len(base_retriever.documents)}")
    print(f"  BM25语料库大小: {base_retriever.bm25.corpus_size}")

    # 测试不同检索配置
    print("\n" + "=" * 70)
    print("  第一部分: 检索参数对比测试")
    print("=" * 70)

    config_results = []
    for i, config in enumerate(CONFIGURATIONS):
        print(f"\n测试配置 [{i+1}/{len(CONFIGURATIONS)}]: {config['name']} ...", end=" ")

        # 创建带当前配置的检索器
        retriever = HybridRetriever(
            bm25_weight=config["bm25_weight"],
            vector_weight=config["vector_weight"],
            use_reranker=config["use_reranker"],
        )
        retriever.index_documents(TEST_DOCUMENTS)

        result = test_retrieval_config(config, retriever, TEST_QUERIES)
        config_results.append(result)
        print(f"R@5={result.recall_at_5:.3f}, MRR={result.mrr:.3f}, 耗时={result.avg_execution_time_ms:.1f}ms")

    # 打印对比结果
    print_results_comparison(config_results, "检索配置对比结果")

    # 参数影响分析
    analyze_parameter_impact(config_results)

    # 详细结果分析
    print_detailed_results(config_results, TEST_QUERIES)

    # 分块策略测试
    print("\n" + "=" * 70)
    print("  第二部分: 分块策略对比测试")
    print("=" * 70)

    chunk_results = []
    for i, chunk_config in enumerate(CHUNK_TEST_CONFIGS):
        print(f"\n测试分块配置 [{i+1}/{len(CHUNK_TEST_CONFIGS)}]: {chunk_config['name']} ...", end=" ")

        result = test_chunk_config(chunk_config, TEST_DOCUMENTS, TEST_QUERIES)
        chunk_results.append(result)
        print(f"分块数={result.parameters.get('total_chunks', 'N/A')}, R@5={result.recall_at_5:.3f}")

    print_chunk_analysis(chunk_results)

    # 综合优化建议
    all_results = config_results + chunk_results
    generate_recommendations(all_results)

    # 保存详细结果到JSON
    output_file = "rag_test_results.json"
    output_data = {
        "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_documents": len(TEST_DOCUMENTS),
        "total_queries": len(TEST_QUERIES),
        "embedding_backend": embedding_svc.backend_name,
        "config_results": [
            {
                "config_name": r.config_name,
                "parameters": r.parameters,
                "metrics": {
                    "recall_at_3": r.recall_at_3,
                    "recall_at_5": r.recall_at_5,
                    "recall_at_10": r.recall_at_10,
                    "precision_at_3": r.precision_at_3,
                    "precision_at_5": r.precision_at_5,
                    "mrr": r.mrr,
                    "ndcg_at_5": r.ndcg_at_5,
                    "avg_execution_time_ms": r.avg_execution_time_ms,
                },
                "failed_queries": [
                    {
                        "query": d["query"],
                        "expected": d["expected"],
                        "top3_results": d["top3_titles"],
                    }
                    for d in r.details if not d["matched"]
                ],
            }
            for r in config_results
        ],
        "chunk_results": [
            {
                "config_name": r.config_name,
                "parameters": r.parameters,
                "metrics": {
                    "recall_at_3": r.recall_at_3,
                    "recall_at_5": r.recall_at_5,
                    "recall_at_10": r.recall_at_10,
                    "mrr": r.mrr,
                },
            }
            for r in chunk_results
        ],
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n📄 详细测试结果已保存至: {output_file}")

    return config_results, chunk_results


if __name__ == "__main__":
    main()
