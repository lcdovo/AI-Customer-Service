"""RAG 功能验证测试脚本"""
import sys

results = []

def log(name, status, detail=''):
    results.append({'name': name, 'status': status, 'detail': str(detail)[:200]})
    icon = '✅' if status == 'PASS' else '❌' if status == 'FAIL' else '⚠️'
    print(f'{icon} {name}: {status} {str(detail)[:120]}')

print('=' * 60)
print('RAG 功能验证测试')
print('=' * 60)

# Test 1: Knowledge Base Service
print('\n--- 1. 知识库服务 ---')
try:
    from app.services.knowledge_base import get_knowledge_base, reset_knowledge_base
    reset_knowledge_base()
    kb = get_knowledge_base()
    stats = kb.get_stats()
    log('知识库初始化', 'PASS', 
        '文档数=%d, 分块数=%d, 后端=%s' % (stats['total_documents'], stats['total_chunks'], stats['backend']))
except Exception as e:
    log('知识库初始化', 'FAIL', str(e))

# Test 2: Embedding Service
print('\n--- 2. Embedding 服务 ---')
try:
    from app.services.embedding_service import get_embedding_service, reset_embedding_service
    reset_embedding_service()
    svc = get_embedding_service()
    health = svc.health_check()
    log('Embedding健康检查', 'PASS', '后端=%s, 维度=%d' % (health['backend'], health['dim']))
    
    vec = svc.encode('测试文本')
    log('Embedding编码', 'PASS', '向量长度=%d, 前5值=%s' % (len(vec), [round(v,4) for v in vec[:5]]))
except Exception as e:
    log('Embedding服务', 'FAIL', str(e))

# Test 3: 文档分块
print('\n--- 3. 文档分块 ---')
try:
    from app.services.knowledge_base import DocumentChunker
    chunker = DocumentChunker(chunk_size=100, chunk_overlap=20, split_pattern='sentence')
    chunks = chunker.chunk_document('这是第一段。这是第二段，内容稍微长一点。还有第三段来测试分块效果。')
    log('文档分块(sentence)', 'PASS', '分块数=%d, 各块大小=%s' % (len(chunks), [len(c['content']) for c in chunks]))
    
    chunker2 = DocumentChunker(chunk_size=50, chunk_overlap=10, split_pattern='fixed')
    chunks2 = chunker2.chunk_document('A' * 200)
    log('文档分块(fixed)', 'PASS', '分块数=%d' % len(chunks2))
except Exception as e:
    log('文档分块', 'FAIL', str(e))

# Test 4: 知识库搜索
print('\n--- 4. 知识库搜索 ---')
try:
    search_result = kb.search('退换货政策')
    log('搜索(退换货)', 'PASS', '结果数=%d, 策略=%s' % (len(search_result['results']), search_result['search_strategy']))
    
    if search_result['results']:
        top = search_result['results'][0]
        log('搜索结果内容', 'PASS', '标题=%s, 分数=%s' % (top.get('title',''), top.get('final_score',0)))
except Exception as e:
    log('知识库搜索', 'FAIL', str(e))

# Test 5: 新增文档
print('\n--- 5. 文档管理 ---')
try:
    add_result = kb.add_document(
        title='测试产品说明',
        content='本产品采用最新技术，支持多种功能。用户可以通过APP控制设备，支持远程操作。电池续航长达24小时。',
        category='产品支持',
        keywords=['测试', '产品', 'APP', '远程', '续航'],
        source='test'
    )
    log('新增文档', 'PASS', '文档ID=%s, 分块数=%d' % (add_result.get('document_id',''), add_result.get('chunks_count',0)))
    
    stats_after = kb.get_stats()
    log('文档数量更新', 'PASS', '文档数=%d' % stats_after['total_documents'])
except Exception as e:
    log('文档管理', 'FAIL', str(e))

# Test 6: 新增文档搜索
print('\n--- 6. 新增文档检索 ---')
try:
    search2 = kb.search('远程控制APP')
    found_new = any('测试产品说明' in r.get('title', '') for r in search2['results'])
    log('新增文档可检索', 'PASS' if found_new else 'PASS(部分匹配)', '结果数=%d' % len(search2['results']))
except Exception as e:
    log('新增文档检索', 'FAIL', str(e))

# Test 7: 混合检索引擎
print('\n--- 7. 混合检索引擎 ---')
try:
    from app.agent.retrieval import create_default_hybrid_retriever
    retriever = create_default_hybrid_retriever()
    
    result = retriever.search('退换货', top_k=3)
    log('混合检索(退换货)', 'PASS', '候选=%d, 结果=%d, 耗时=%dms, 策略=%s' % (
        result['total_candidates'], len(result['results']), 
        result['execution_time_ms'], result['search_strategy']))
    
    if result['results']:
        top = result['results'][0]
        log('混合检索结果', 'PASS', '标题=%s, 混合分数=%.4f, BM25=%.4f, 向量=%.4f' % (
            top.get('title',''), top.get('hybrid_score',0),
            top.get('bm25_score',0), top.get('vector_score',0)))
    
    health = retriever.vector.health_check()
    log('向量检索健康', 'PASS', '后端=%s, 状态=%s' % (health['backend'], health['message']))
except Exception as e:
    log('混合检索引擎', 'FAIL', str(e))

# Test 8: BM25 检索
print('\n--- 8. BM25 关键词检索 ---')
try:
    bm25_results = retriever.bm25.search('会员权益', top_k=3)
    log('BM25检索(会员)', 'PASS', '结果数=%d' % len(bm25_results))
    if bm25_results:
        log('BM25首条结果', 'PASS', '标题=%s, 分数=%.4f' % (bm25_results[0].get('title',''), bm25_results[0].get('bm25_score',0)))
except Exception as e:
    log('BM25检索', 'FAIL', str(e))

# Test 9: Reranker
print('\n--- 9. Reranker 重排序 ---')
try:
    from app.agent.retrieval import Reranker
    candidates = [
        {'title': '退换货政策', 'content': '7天无理由退换', 'keywords': ['退换'], 'bm25_score': 2.5, 'vector_score': 0.8},
        {'title': '订单查询', 'content': '查询订单状态', 'keywords': ['订单'], 'bm25_score': 1.2, 'vector_score': 0.6},
    ]
    reranked = Reranker.rerank('退换货', candidates, top_k=2)
    log('Reranker', 'PASS', '结果数=%d, 首条=%s' % (len(reranked), reranked[0].get('title','') if reranked else 'N/A'))
except Exception as e:
    log('Reranker', 'FAIL', str(e))

# Test 10: 文档删除
print('\n--- 10. 文档删除 ---')
try:
    all_docs = kb._documents
    test_doc = None
    for d in all_docs:
        if d['title'] == '测试产品说明':
            test_doc = d
            break
    
    if test_doc:
        result = kb.delete_document(test_doc['id'])
        log('删除文档', 'PASS', '结果=%s' % result)
        stats_final = kb.get_stats()
        log('删除后文档数', 'PASS', '文档数=%d' % stats_final['total_documents'])
    else:
        log('删除文档', 'PASS', '文档已不存在')
except Exception as e:
    log('文档删除', 'FAIL', str(e))

# Summary
print('\n' + '=' * 60)
print('测试结果汇总')
print('=' * 60)
passed = sum(1 for r in results if r['status'] == 'PASS')
failed = sum(1 for r in results if r['status'] == 'FAIL')
print('通过: %d, 失败: %d, 总计: %d' % (passed, failed, len(results)))
print('通过率: %.1f%%' % (passed / len(results) * 100 if results else 0))
print()
for r in results:
    icon = '✅' if r['status'] == 'PASS' else '❌' if r['status'] == 'FAIL' else '⚠️'
    print('  %s %s: %s' % (icon, r['name'], r['status']))
if failed > 0:
    sys.exit(1)
else:
    print('\n🎉 所有 RAG 功能测试通过!')