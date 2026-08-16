"""
知识库管理 API - 文件上传、文档管理、检索测试
支持多种格式：txt, markdown, json, csv
"""
import os
import json
import tempfile
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from app.services.knowledge_base import get_knowledge_base
from app.services.llm_service import LLMService

router = APIRouter(prefix="/api/v1/knowledge", tags=["知识库管理"])
logger = logging.getLogger(__name__)


class DocumentCreateRequest(BaseModel):
    title: str
    content: str
    category: str = ""
    keywords: Optional[List[str]] = None
    source: str = ""


class SearchRequest(BaseModel):
    query: str
    top_k: int = 3
    similarity_threshold: float = 0.3


def parse_file_content(file_path: str, file_type: str) -> str:
    """解析文件内容，支持多种格式"""
    content = ""

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        if file_type == "json":
            try:
                data = json.loads(raw_content)
                if isinstance(data, dict):
                    content = json.dumps(data, ensure_ascii=False, indent=2)
                elif isinstance(data, list):
                    content = "\n\n".join(
                        json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
                        for item in data
                    )
                else:
                    content = str(data)
            except json.JSONDecodeError:
                content = raw_content

        elif file_type == "csv":
            lines = raw_content.strip().split("\n")
            if len(lines) > 1:
                header = lines[0].split(",")
                rows = lines[1:]
                paragraphs = []
                for row in rows:
                    cols = row.split(",")
                    pairs = [f"{h.strip()}: {c.strip()}" for h, c in zip(header, cols) if h.strip() and c.strip()]
                    if pairs:
                        paragraphs.append("；".join(pairs))
                content = "\n".join(paragraphs)
            else:
                content = raw_content

        elif file_type == "md":
            lines = raw_content.split("\n")
            processed = []
            in_code_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block:
                    continue
                if line.startswith("#"):
                    processed.append(line.lstrip("#").strip())
                elif line.startswith("- ") or line.startswith("* "):
                    processed.append(line[2:].strip())
                elif line.strip():
                    processed.append(line.strip())
            content = "\n".join(processed)

        else:
            content = raw_content

    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="gbk") as f:
                content = f.read()
        except Exception:
            raise HTTPException(status_code=400, detail="文件编码不支持，请使用 UTF-8 编码")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件读取失败: {str(e)}")

    return content


def get_file_type(filename: str) -> str:
    """获取文件类型"""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    supported = {"txt", "md", "markdown", "json", "csv"}
    if ext not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: .{ext}，支持的类型: {', '.join(supported)}"
        )
    if ext == "markdown":
        return "md"
    return ext


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(..., description="上传的文件"),
    title: Optional[str] = Form(None, description="文档标题（默认使用文件名）"),
    category: str = Form("", description="文档分类"),
    keywords: Optional[str] = Form(None, description="关键词，逗号分隔"),
):
    """上传文件到知识库"""
    kb = get_knowledge_base()

    file_type = get_file_type(file.filename)

    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传文件")

    suffix = f".{file_type}"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        temp_path = tmp.name

    try:
        doc_content = parse_file_content(temp_path, file_type)

        if not doc_content.strip():
            raise HTTPException(status_code=400, detail="文件内容为空")

        doc_title = title or os.path.splitext(file.filename)[0]
        doc_keywords = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []

        result = kb.add_document(
            title=doc_title,
            content=doc_content,
            category=category,
            keywords=doc_keywords,
            source=f"upload:{file.filename}",
        )

        return {
            "code": 0,
            "message": "上传成功",
            "data": {
                "document_id": result["document_id"],
                "title": doc_title,
                "chunks_count": result["chunks_count"],
                "file_type": file_type,
                "file_size": len(content),
            },
        }

    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


@router.post("/documents/text")
async def add_text_document(request: DocumentCreateRequest):
    """直接添加文本内容到知识库"""
    kb = get_knowledge_base()

    if not request.content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")

    result = kb.add_document(
        title=request.title,
        content=request.content,
        category=request.category,
        keywords=request.keywords,
        source=request.source or "manual",
    )

    return {
        "code": 0,
        "message": "添加成功",
        "data": result,
    }


@router.post("/search")
async def search_knowledge(request: SearchRequest):
    """搜索知识库"""
    kb = get_knowledge_base()

    result = kb.search(
        query=request.query,
        top_k=request.top_k,
        similarity_threshold=request.similarity_threshold,
    )

    return {
        "code": 0,
        "message": "搜索成功",
        "data": result,
    }


@router.get("/documents")
async def list_documents():
    """获取文档列表"""
    kb = get_knowledge_base()
    stats = kb.get_stats()

    doc_list = []
    for doc in kb._documents:
        doc_list.append({
            "id": doc.get("id", ""),
            "title": doc.get("title", ""),
            "category": doc.get("category", ""),
            "source": doc.get("source", ""),
            "keywords": doc.get("keywords", []),
            "chunks_count": len(doc.get("chunks", [])),
            "created_at": doc.get("created_at", ""),
        })

    return {
        "code": 0,
        "message": "获取成功",
        "data": {
            **stats,
            "documents": doc_list,
        },
    }


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """删除文档"""
    kb = get_knowledge_base()

    success = kb.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")

    return {
        "code": 0,
        "message": "删除成功",
    }


@router.delete("/documents")
async def clear_all_documents():
    """清空所有文档"""
    kb = get_knowledge_base()
    result = kb.clear_all()

    return {
        "code": 0,
        "message": "清空成功",
        "data": result,
    }


@router.post("/documents/batch-upload")
async def batch_upload_documents(
    files: List[UploadFile] = File(..., description="多个文件上传"),
    category: str = Form("", description="文档分类"),
    keywords: Optional[str] = Form(None, description="关键词，逗号分隔"),
):
    """批量上传文件"""
    kb = get_knowledge_base()
    results = []

    for file in files:
        file_type = get_file_type(file.filename)

        suffix = f".{file_type}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            temp_path = tmp.name

        try:
            doc_content = parse_file_content(temp_path, file_type)

            if doc_content.strip():
                doc_title = os.path.splitext(file.filename)[0]
                doc_keywords = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []

                result = kb.add_document(
                    title=doc_title,
                    content=doc_content,
                    category=category,
                    keywords=doc_keywords,
                    source=f"batch_upload:{file.filename}",
                )

                results.append({
                    "filename": file.filename,
                    "document_id": result.get("document_id"),
                    "chunks_count": result.get("chunks_count", 0),
                    "success": True,
                })
            else:
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": "文件内容为空",
                })

        except Exception as e:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e),
            })
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    success_count = sum(1 for r in results if r["success"])
    return {
        "code": 0,
        "message": f"批量上传完成: {success_count}/{len(results)} 成功",
        "data": {
            "total": len(results),
            "success": success_count,
            "failed": len(results) - success_count,
            "results": results,
        },
    }


@router.post("/documents/seed")
async def seed_default_documents():
    """导入默认种子文档"""
    kb = get_knowledge_base()

    default_docs = [
        {
            "title": "退换货政策",
            "content": """退换货政策说明：

1. 退货政策：
   - 签收后7天内可无理由退货
   - 商品需保持完好状态，配件齐全
   - 退货运费由买家承担（商品质量问题除外）

2. 换货政策：
   - 商品存在质量问题时支持换货
   - 换货运费由卖家承担
   - 同款商品断货时可选择退款

3. 退款流程：
   - 提交退款申请后1-3个工作日审核
   - 审核通过后款项原路返回
   - 支付宝/微信退款即时到账
   - 银行卡退款需要3-7个工作日

4. 特殊商品：
   - 定制商品不支持退换货
   - 食品类商品不支持退换货
   - 贴身衣物如无质量问题不支持退换""",
            "category": "policy",
            "keywords": ["退换货", "退款", "政策"],
        },
        {
            "title": "订单查询说明",
            "content": """订单查询方式：

1. 订单状态说明：
   - 待付款：订单已创建，等待付款
   - 待发货：付款成功，等待商家发货
   - 待收货：商品已发货，等待收件
   - 已完成：订单已完成收货
   - 已取消：订单已取消

2. 查询订单方式：
   - 提供订单号即可查询
   - 可查询订单详情、物流信息
   - 可查询订单历史状态

3. 物流查询：
   - 发货后可查询物流轨迹
   - 支持多家快递公司查询
   - 物流更新时间约2-4小时""",
            "category": "help",
            "keywords": ["订单", "查询", "物流"],
        },
        {
            "title": "常见问题解答",
            "content": """常见问题解答：

Q1: 如何修改收货地址？
A: 订单未发货前可在订单详情中修改收货地址，发货后需联系客服处理。

Q2: 如何取消订单？
A: 待付款状态可直接取消，待发货状态需申请取消，已发货状态需办理退货。

Q3: 发票如何开具？
A: 结算时选择发票类型（电子普通发票/增值税专用发票），填写抬头信息后提交。

Q4: 积分如何使用？
A: 100积分=1元，结算时可抵扣现金，每笔订单最多抵扣50%。

Q5: 如何联系人工客服？
A: 在对话框输入"人工客服"或点击"转人工"按钮，工作日9:00-21:00为您服务。""",
            "category": "faq",
            "keywords": ["FAQ", "常见问题", "帮助"],
        },
    ]

    results = []
    for doc in default_docs:
        result = kb.add_document(
            title=doc["title"],
            content=doc["content"],
            category=doc.get("category", ""),
            keywords=doc.get("keywords", []),
            source="seed",
        )
        results.append(result)

    total_chunks = sum(r.get("chunks_count", 0) for r in results)
    return {
        "code": 0,
        "message": f"已导入 {len(results)} 篇默认文档，共 {total_chunks} 个分块",
        "data": {
            "documents_count": len(results),
            "total_chunks": total_chunks,
            "results": results,
        },
    }


@router.get("/stats")
async def get_knowledge_stats():
    """获取知识库统计信息"""
    kb = get_knowledge_base()
    stats = kb.get_stats()
    return {
        "code": 0,
        "message": "获取成功",
        "data": stats,
    }


class RagQueryRequest(BaseModel):
    query: str
    top_k: int = 3
    similarity_threshold: float = 0.3
    use_llm: bool = True


@router.post("/rag-query")
async def rag_query(request: RagQueryRequest):
    """RAG问答：检索+LLM生成回答"""
    kb = get_knowledge_base()
    search_result = kb.search(
        query=request.query,
        top_k=request.top_k,
        similarity_threshold=request.similarity_threshold,
    )

    if not search_result.get("results"):
        return {
            "code": 0,
            "message": "未找到相关文档",
            "data": {
                "query": request.query,
                "answer": "抱歉，知识库中没有找到与您问题相关的内容。",
                "sources": [],
                "search_result": search_result,
            },
        }

    context_chunks = []
    sources = []
    for r in search_result["results"]:
        context_chunks.append(f"【{r.get('title', '')}】{r.get('content', '')}")
        sources.append({
            "id": r.get("id", ""),
            "title": r.get("title", ""),
            "score": r.get("final_score", r.get("vector_score", 0)),
        })

    context_text = "\n\n".join(context_chunks)

    if request.use_llm:
        try:
            llm = LLMService()
            prompt = f"""基于以下参考资料回答用户的问题。如果资料中没有相关信息，请直接说明。

参考资料：
{context_text}

用户问题：{request.query}

请用中文给出简洁准确的回答。"""

            reply, _, _ = await llm.chat(
                user_id=0,
                session_id="rag_query",
                message=prompt,
            )
            answer = reply or f"根据知识库检索，找到 {len(sources)} 条相关内容，但AI生成回答失败。"
        except Exception as e:
            logger.error(f"LLM生成失败: {e}")
            answer = f"已检索到 {len(sources)} 条相关内容，但AI回答生成失败。以下是检索到的内容摘要。"
    else:
        if sources:
            top = search_result["results"][0]
            answer = f"根据知识库检索，找到相关内容：{top.get('content', '')}"
        else:
            answer = "未找到相关内容。"

    return {
        "code": 0,
        "message": "查询成功",
        "data": {
            "query": request.query,
            "answer": answer,
            "sources": sources,
            "chunks_count": len(search_result.get("results", [])),
            "search_strategy": search_result.get("search_strategy", ""),
            "search_result": search_result,
        },
    }
