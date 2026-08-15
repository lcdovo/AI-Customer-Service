const API_BASE = '';
const WS_URL = `ws://${window.location.host}/api/v1/chat/stream`;

const state = {
  user: { id: 1, username: 'test_user', nickname: '测试用户', level: 'normal' },
  sessionId: null,
  ws: null,
  wsConnected: false,
  currentStreamMessage: null,
  messageCount: 0,
  knowledge: {
    selectedFiles: [],
  },
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function toast(message, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  $('#toastContainer').appendChild(el);
  setTimeout(() => {
    el.classList.add('fade-out');
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

async function api(method, path, data) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (data) opts.body = JSON.stringify(data);
  const res = await fetch(`${API_BASE}${path}`, opts);
  const json = await res.json();
  if (!res.ok || (json.code !== undefined && json.code !== 0)) {
    throw new Error(json.detail || json.message || `请求失败 (${res.status})`);
  }
  return json.data !== undefined ? json.data : json;
}

function initWebSocket() {
  if (state.ws && state.ws.readyState <= 1) return;

  state.ws = new WebSocket(WS_URL);

  state.ws.onopen = () => {
    state.wsConnected = true;
    updateWsStatus('connected', '已连接');
  };

  state.ws.onclose = () => {
    state.wsConnected = false;
    updateWsStatus('disconnected', '已断开');
    setTimeout(initWebSocket, 3000);
  };

  state.ws.onerror = () => {
    state.wsConnected = false;
    updateWsStatus('disconnected', '连接错误');
  };

  state.ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleWsMessage(data);
    } catch (e) {
      console.error('WS message parse error:', e);
    }
  };
}

function updateWsStatus(type, text) {
  const dot = $('#wsStatus');
  const txt = $('#wsStatusText');
  dot.className = 'status-dot';
  if (type === 'connected') dot.classList.add('connected');
  else if (type === 'disconnected') dot.classList.add('disconnected');
  txt.textContent = text;
}

function handleWsMessage(data) {
  switch (data.type) {
    case 'stream_start':
      state.sessionId = data.session_id;
      $('#sessionId').textContent = data.session_id.substring(0, 12) + '...';
      addBotMessage('', true);
      break;

    case 'token':
      if (state.currentStreamMessage) {
        state.currentStreamMessage.querySelector('.message-content').textContent += data.content;
        scrollChatToBottom();
      }
      break;

    case 'intent':
      $('#currentIntent').textContent = data.intent || '-';
      break;

    case 'tool_call_start':
      if (state.currentStreamMessage) {
        const content = state.currentStreamMessage.querySelector('.message-content');
        content.textContent += `\n\n🔧 调用工具: ${data.tool_name}...`;
        scrollChatToBottom();
      }
      break;

    case 'tool_call_complete':
      if (state.currentStreamMessage) {
        const content = state.currentStreamMessage.querySelector('.message-content');
        content.textContent += data.success ? ' ✅' : ' ❌';
        scrollChatToBottom();
      }
      break;

    case 'node_start':
    case 'node_complete':
    case 'rag_result':
    case 'validation':
      break;

    case 'stream_end':
      finalizeStreamMessage();
      break;

    case 'done':
      if (state.currentStreamMessage) {
        const content = state.currentStreamMessage.querySelector('.message-content');
        content.textContent = data.reply || content.textContent;
        $('#responseTime').textContent = (data.execution_time_ms || '-') + 'ms';
        $('#currentIntent').textContent = data.intent || '-';
      }
      finalizeStreamMessage();
      break;

    case 'error':
      if (state.currentStreamMessage) {
        const content = state.currentStreamMessage.querySelector('.message-content');
        content.textContent = '❌ ' + (data.message || '未知错误');
      }
      finalizeStreamMessage();
      break;
  }
}

function finalizeStreamMessage() {
  state.currentStreamMessage = null;
  $('#sendBtn').disabled = false;
  $('#chatInput').disabled = false;
}

function addBotMessage(text, isStreaming = false) {
  const msgDiv = document.createElement('div');
  msgDiv.className = 'message bot';
  msgDiv.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content"></div>
  `;
  if (text) msgDiv.querySelector('.message-content').textContent = text;
  $('#chatMessages').appendChild(msgDiv);
  state.currentStreamMessage = msgDiv;
  scrollChatToBottom();
}

function addUserMessage(text) {
  const msgDiv = document.createElement('div');
  msgDiv.className = 'message user';
  msgDiv.innerHTML = `
    <div class="message-avatar">我</div>
    <div class="message-content"></div>
  `;
  msgDiv.querySelector('.message-content').textContent = text;
  $('#chatMessages').appendChild(msgDiv);
  state.messageCount++;
  $('#messageCount').textContent = state.messageCount;
  scrollChatToBottom();
  return msgDiv;
}

function addBotMessageRest(text, intent, responseTime, sessionId) {
  const msgDiv = document.createElement('div');
  msgDiv.className = 'message bot';
  msgDiv.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div>
      <div class="message-content"></div>
      <div class="message-meta">
        <span>意图: ${intent || '未知'}</span>
        <span>⏱ ${responseTime || '-'}ms</span>
      </div>
      <div class="message-actions">
        <button class="msg-action-btn" title="点赞">👍</button>
        <button class="msg-action-btn" title="点踩">👎</button>
        <button class="msg-action-btn" title="复制">📋</button>
      </div>
    </div>
  `;
  msgDiv.querySelector('.message-content').textContent = text;
  $('#chatMessages').appendChild(msgDiv);
  state.messageCount++;
  $('#messageCount').textContent = state.messageCount;
  scrollChatToBottom();

  if (sessionId) state.sessionId = sessionId;
  if (intent) $('#currentIntent').textContent = intent;
  if (responseTime) $('#responseTime').textContent = responseTime + 'ms';

  const likeBtn = msgDiv.querySelectorAll('.msg-action-btn')[0];
  const dislikeBtn = msgDiv.querySelectorAll('.msg-action-btn')[1];
  const copyBtn = msgDiv.querySelectorAll('.msg-action-btn')[2];

  likeBtn.onclick = () => {
    submitFeedback('like', text);
    likeBtn.classList.toggle('active');
  };
  dislikeBtn.onclick = () => {
    submitFeedback('dislike', text);
    dislikeBtn.classList.toggle('active');
  };
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(text);
    toast('已复制到剪贴板', 'success');
  };
}

function scrollChatToBottom() {
  const container = $('#chatMessages');
  container.scrollTop = container.scrollHeight;
}

async function sendMessage(text) {
  if (!text.trim()) return;

  addUserMessage(text);

  $('#sendBtn').disabled = true;
  $('#chatInput').disabled = true;

  if (state.wsConnected) {
    state.ws.send(JSON.stringify({
      user_id: state.user.id,
      message: text,
      session_id: state.sessionId,
    }));
  } else {
    try {
      const data = await api('POST', '/api/v1/chat/send', {
        user_id: state.user.id,
        message: text,
        session_id: state.sessionId,
      });
      addBotMessageRest(data.reply, data.intent, data.response_time_ms, data.session_id);
    } catch (err) {
      toast(err.message, 'error');
      addBotMessage('❌ ' + err.message);
    } finally {
      $('#sendBtn').disabled = false;
      $('#chatInput').disabled = false;
    }
  }
}

async function submitFeedback(type, content) {
  try {
    await api('POST', '/api/v1/feedback/submit', {
      user_id: state.user.id,
      session_id: state.sessionId || 'unknown',
      feedback_type: type,
      content: content,
    });
    toast(type === 'like' ? '感谢您的好评！' : '我们会改进服务', 'success');
  } catch (e) {
    console.error('Feedback error:', e);
  }
}

async function loadTools() {
  try {
    const tools = await api('GET', '/api/v1/chat/tools');
    const list = $('#toolList');
    list.innerHTML = tools.map(t => `
      <div class="tool-item">
        <div class="tool-name">${t.name}</div>
        <div class="tool-desc">${t.description}</div>
      </div>
    `).join('');
  } catch (e) {
    $('#toolList').innerHTML = '<div class="empty">加载失败</div>';
  }
}

async function loadSessions() {
  try {
    const sessions = await api('GET', `/api/v1/chat/sessions/${state.user.id}`);
    const container = $('#sessionItems');
    container.innerHTML = '';

    if (!sessions || sessions.length === 0) {
      container.innerHTML = '<div class="empty-state" style="padding:20px;">暂无历史会话</div>';
      return;
    }

    sessions.forEach(s => {
      const item = document.createElement('div');
      item.className = 'session-item';
      item.dataset.session = s.id;
      item.innerHTML = `
        <div class="session-title">${s.last_intent || '通用对话'}</div>
        <div class="session-time">${new Date(s.updated_at).toLocaleString('zh-CN')}</div>
      `;
      item.onclick = () => switchSession(s.id);
      container.appendChild(item);
    });
  } catch (e) {
    console.error('Load sessions error:', e);
  }
}

async function switchSession(sessionId) {
  state.sessionId = sessionId;
  const items = $$('.session-item');
  items.forEach(i => i.classList.toggle('active', i.dataset.session === sessionId));

  try {
    const data = await api('GET', `/api/v1/chat/history/${sessionId}`);
    $('#chatMessages').innerHTML = '';
    data.messages.forEach(m => {
      if (m.role === 'user') {
        addUserMessage(m.content);
      } else if (m.role === 'assistant') {
        addBotMessageRest(m.content, null, m.response_time_ms, null);
      }
    });
    $('#sessionId').textContent = sessionId.substring(0, 12) + '...';
  } catch (e) {
    toast('加载历史失败', 'error');
  }
}

function newSession() {
  state.sessionId = null;
  state.messageCount = 0;
  $('#messageCount').textContent = '0';
  $('#sessionId').textContent = '-';
  $('#currentIntent').textContent = '-';
  $('#responseTime').textContent = '-';
  $('#chatMessages').innerHTML = `
    <div class="message system">
      <div class="message-content">
        <p>🆕 新会话已创建，请问有什么可以帮您？</p>
      </div>
    </div>
  `;
  const items = $$('.session-item');
  items.forEach(i => i.classList.toggle('active', i.dataset.session === 'current'));
}

async function loadTickets() {
  const status = $('#ticketStatusFilter').value;
  const priority = $('#ticketPriorityFilter').value;

  try {
    const data = await api('GET', `/api/v1/tickets?${new URLSearchParams({
      ...(status && { status }),
      ...(priority && { priority }),
    })}`);

    const tbody = $('#ticketsTableBody');
    const items = data.tickets || [];

    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">暂无工单</td></tr>';
    } else {
      tbody.innerHTML = items.map(t => `
        <tr>
          <td style="font-family:monospace;font-size:12px;">${(t.ticket_id || t.id || '').substring(0, 16)}</td>
          <td>${t.category}</td>
          <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${t.content}</td>
          <td><span class="badge badge-priority-${t.priority}">${priorityLabel(t.priority)}</span></td>
          <td><span class="badge badge-status-${t.status}">${statusLabel(t.status)}</span></td>
          <td style="font-size:12px;">${t.created_at ? new Date(t.created_at).toLocaleString('zh-CN') : '-'}</td>
          <td><button class="btn-danger" onclick="deleteTicket('${t.ticket_id || t.id}')">删除</button></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    $('#ticketsTableBody').innerHTML = '<tr><td colspan="7" class="empty">加载失败</td></tr>';
  }

  try {
    const stats = await api('GET', '/api/v1/tickets/stats');
    renderTicketStats(stats);
  } catch (e) {
    console.error('Stats error:', e);
  }
}

function renderTicketStats(stats) {
  const container = $('#ticketsStats');
  const sd = stats.status_distribution || {};
  const items = [
    { label: '总工单', value: stats.total_tickets || 0, color: '#4f46e5' },
    { label: '待处理', value: sd.pending || 0, color: '#3b82f6' },
    { label: '处理中', value: sd.processing || 0, color: '#f59e0b' },
    { label: '已解决', value: stats.resolved_count || 0, color: '#10b981' },
  ];
  container.innerHTML = items.map(i => `
    <div class="ticket-stat-card">
      <div class="ticket-stat-num" style="color:${i.color};">${i.value}</div>
      <div class="ticket-stat-label">${i.label}</div>
    </div>
  `).join('');
}

function priorityLabel(p) {
  return { low: '低', medium: '中', high: '高', urgent: '紧急' }[p] || p;
}

function statusLabel(s) {
  return { pending: '待处理', processing: '处理中', in_progress: '处理中', assigned: '已分配', resolved: '已解决', closed: '已关闭', online: '在线', offline: '离线', busy: '忙碌' }[s] || s;
}

async function deleteTicket(id) {
  if (!confirm('确定删除此工单？')) return;
  try {
    await api('DELETE', `/api/v1/tickets/${id}`);
    toast('删除成功', 'success');
    loadTickets();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function showTicketModal() {
  $('#ticketContent').value = '';
  $('#ticketCategory').value = 'complaint';
  $('#ticketPriority').value = 'medium';
  $('#ticketModal').classList.add('active');
}

function hideTicketModal() {
  $('#ticketModal').classList.remove('active');
}

async function submitTicket() {
  const category = $('#ticketCategory').value;
  const priority = $('#ticketPriority').value;
  const content = $('#ticketContent').value.trim();

  if (!content) {
    toast('请填写问题描述', 'warning');
    return;
  }

  try {
    await api('POST', '/api/v1/tickets', {
      user_id: state.user.id,
      category,
      priority,
      content,
      session_id: state.sessionId,
    });
    toast('工单创建成功', 'success');
    hideTicketModal();
    loadTickets();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function loadHandoffRequests() {
  try {
    const data = await api('GET', '/api/v1/handoff/requests');
    const list = $('#handoffList');
    const items = data.requests || [];
    if (items.length === 0) {
      list.innerHTML = '<div class="empty-state">暂无转人工请求</div>';
    } else {
      list.innerHTML = items.map(r => `
        <div class="handoff-card">
          <div class="handoff-card-header">
            <div class="handoff-reason">${r.reason || '-'}</div>
            <span class="badge badge-priority-${r.priority}">${priorityLabel(r.priority)}</span>
          </div>
          <div class="handoff-meta">
            会话: ${r.session_id?.substring(0, 12) || '-'}... · ${statusLabel(r.status)}
          </div>
        </div>
      `).join('');
    }
  } catch (e) {
    $('#handoffList').innerHTML = '<div class="empty-state">加载失败</div>';
  }
}

async function loadAgents() {
  try {
    const agents = await api('GET', '/api/v1/agents');
    const list = $('#agentsList');
    if (agents.length === 0) {
      list.innerHTML = '<div class="empty-state">暂无客服信息</div>';
    } else {
      list.innerHTML = agents.map(a => `
        <div class="agent-card">
          <div class="agent-card-header">
            <div class="agent-name">${a.name}</div>
            <span class="badge badge-status-${a.status}">${statusLabel(a.status)}</span>
          </div>
          <div class="agent-meta">ID: ${a.agent_id} · 技能: ${(a.skills || []).map(s => skillLabel(s)).join(', ') || '-'} · 负载: ${a.current_load}/${a.max_load}</div>
        </div>
      `).join('');
    }
  } catch (e) {
    $('#agentsList').innerHTML = '<div class="empty-state">加载失败</div>';
  }
}

async function requestHandoff() {
  if (!state.sessionId) {
    toast('请先发送一条消息开始会话', 'warning');
    return;
  }
  const reason = prompt('请说明转人工的原因：');
  if (!reason) return;

  try {
    const result = await api('POST', '/api/v1/handoff', {
      user_id: state.user.id,
      session_id: state.sessionId,
      reason,
      priority: 'normal',
    });
    toast('已请求转人工，客服将尽快与您联系', 'success');
    loadHandoffRequests();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function loadAnalytics() {
  try {
    const data = await api('GET', '/api/v1/analytics/metrics');
    renderAnalytics(data);
  } catch (e) {
    console.error('Analytics error:', e);
  }

  try {
    const summary = await api('GET', '/api/v1/analytics/metrics/summary?hours=24');
    renderAnalyticsSummary(summary);
  } catch (e) {
    console.error('Summary error:', e);
  }
}

function renderAnalytics(data) {
  const metrics = data.metrics || {};
  const counters = metrics.counters || {};

  const cards = [
    { label: '总请求数', value: counters['response.total'] || 0, color: '#4f46e5' },
    { label: '成功率', value: ((metrics.success_rate || 0) * 100).toFixed(1) + '%', color: '#10b981' },
    { label: '平均响应', value: metrics.response_time?.avg_ms || 0, suffix: 'ms', color: '#3b82f6' },
    { label: '会话数', value: metrics.session_count || 0, color: '#f59e0b' },
  ];

  $('#analyticsCards').innerHTML = cards.map(c => `
    <div class="analytics-card">
      <div class="analytics-card-label">${c.label}</div>
      <div class="analytics-card-value" style="color:${c.color};">${c.value}${c.suffix || ''}</div>
    </div>
  `).join('');

  const intentDist = metrics.intent_distribution || {};
  const maxIntent = Math.max(...Object.values(intentDist), 1);
  $('#intentChart').innerHTML = Object.keys(intentDist).length ? `
    <div class="bar-chart">
      ${Object.entries(intentDist).map(([k, v]) => `
        <div class="bar-item">
          <div class="bar-label">${intentName(k)}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${(v/maxIntent*100)}%"></div></div>
          <div class="bar-value">${v}</div>
        </div>
      `).join('')}
    </div>
  ` : '<div class="empty-state">暂无数据</div>';

  const toolStats = metrics.tool_statistics || {};
  const maxTool = Math.max(...Object.values(toolStats), 1);
  $('#toolChart').innerHTML = Object.keys(toolStats).length ? `
    <div class="bar-chart">
      ${Object.entries(toolStats).map(([k, v]) => `
        <div class="bar-item">
          <div class="bar-label">${k}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${(v/maxTool*100)}%"></div></div>
          <div class="bar-value">${v}</div>
        </div>
      `).join('')}
    </div>
  ` : '<div class="empty-state">暂无数据</div>';

  const alerts = data.alerts || [];
  $('#alertsList').innerHTML = alerts.length ? alerts.map(a => `
    <div class="alert-item alert-${a.level || 'info'}">
      <strong>${a.name}</strong>: ${a.message}
    </div>
  `).join('') : '<div class="empty-state">无告警</div>';
}

function renderAnalyticsSummary(summary) {
  if (!summary) return;
  const cards = [
    { label: '总请求', value: summary.total_requests || 0, color: '#4f46e5' },
    { label: '成功率', value: ((summary.success_rate || 0) * 100).toFixed(1) + '%', color: '#10b981' },
    { label: 'P95响应', value: summary.p95_response_time_ms || 0, suffix: 'ms', color: '#f59e0b' },
    { label: '会话数', value: summary.session_count || 0, color: '#3b82f6' },
  ];

  $('#analyticsCards').innerHTML = cards.map(c => `
    <div class="analytics-card">
      <div class="analytics-card-label">${c.label}</div>
      <div class="analytics-card-value" style="color:${c.color};">${c.value}${c.suffix || ''}</div>
    </div>
  `).join('');
}

function intentName(code) {
  const map = {
    query_order: '订单查询', refund: '退换货', complaint: '投诉',
    technical: '技术咨询', promotion: '活动咨询', human: '转人工', general: '通用',
  };
  return map[code] || code;
}

function skillLabel(code) {
  const map = {
    complaint: '投诉处理', escalation: '问题升级', general: '综合客服',
    order_query: '订单查询', refund: '退款处理', technical: '技术支持',
    product_support: '产品支持', return: '退货', exchange: '换货',
  };
  return map[code] || code;
}

function showUserModal() {
  $('#userIdInput').value = state.user.id;
  $('#usernameInput').value = state.user.username;
  $('#nicknameInput').value = state.user.nickname;
  $('#userLevelInput').value = state.user.level;
  $('#userModal').classList.add('active');
}

function hideUserModal() {
  $('#userModal').classList.remove('active');
}

function saveUser() {
  state.user.id = parseInt($('#userIdInput').value) || 1;
  state.user.username = $('#usernameInput').value;
  state.user.nickname = $('#nicknameInput').value;
  state.user.level = $('#userLevelInput').value;

  $('#username').textContent = state.user.username;
  $('#userLevel').textContent = { normal: '普通用户', vip: 'VIP用户', enterprise: '企业用户' }[state.user.level];
  $('#userAvatar').textContent = state.user.nickname.charAt(0).toUpperCase();

  localStorage.setItem('cs_user', JSON.stringify(state.user));
  hideUserModal();
  toast('用户信息已保存', 'success');
}

function switchPage(page) {
  $$('.page').forEach(p => p.classList.remove('active'));
  $$('.nav-item').forEach(n => n.classList.remove('active'));

  $(`.page-${page}`).classList.add('active');
  document.querySelector(`.nav-item[data-page="${page}"]`).classList.add('active');

  if (page === 'tickets') loadTickets();
  if (page === 'handoff') { loadHandoffRequests(); loadAgents(); }
  if (page === 'analytics') loadAnalytics();
  if (page === 'knowledge') loadKnowledgeStats();
}

function autoResize() {
  const input = $('#chatInput');
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
}

async function init() {
  // 检查登录状态
  const userRole = localStorage.getItem('cs_user_role');
  const userName = localStorage.getItem('cs_user_name');

  if (!userRole) {
    // 未登录，跳转到登录页
    window.location.href = '/login.html';
    return;
  }

  if (userRole !== 'admin') {
    // 非管理员，跳转到用户页
    window.location.href = '/user.html';
    return;
  }

  // 管理员初始化
  state.user = {
    id: 1,
    username: userName || 'admin',
    nickname: userName || '管理员',
    level: 'enterprise',
  };

  $('#username').textContent = state.user.username;
  $('#userLevel').textContent = '管理员';
  $('#userAvatar').textContent = 'A';

  initWebSocket();
  loadTools();
  loadSessions();

  $('#chatInput').addEventListener('input', autoResize);
  $('#chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(e.target.value);
      e.target.value = '';
      autoResize();
    }
  });

  $('#sendBtn').addEventListener('click', () => {
    const input = $('#chatInput');
    sendMessage(input.value);
    input.value = '';
    autoResize();
  });

  $$('.quick-action').forEach(btn => {
    btn.addEventListener('click', () => {
      sendMessage(btn.dataset.msg);
    });
  });

  $$('.nav-item').forEach(item => {
    item.addEventListener('click', () => switchPage(item.dataset.page));
  });

  $('#newSessionBtn').addEventListener('click', newSession);
  $('#newTicketBtn').addEventListener('click', showTicketModal);
  $('#createTicketBtn').addEventListener('click', showTicketModal);
  $('#submitTicketBtn').addEventListener('click', submitTicket);
  $('#cancelTicketBtn').addEventListener('click', hideTicketModal);
  $('#closeTicketModal').addEventListener('click', hideTicketModal);

  $('#handoffBtn').addEventListener('click', requestHandoff);
  $('#clearChatBtn').addEventListener('click', () => {
    if (confirm('确定清空当前对话？')) {
      $('#chatMessages').innerHTML = `
        <div class="message system">
          <div class="message-content">
            <p>🧹 对话已清空，请问有什么可以帮您？</p>
          </div>
        </div>
      `;
      state.messageCount = 0;
      $('#messageCount').textContent = '0';
    }
  });

  $('#refreshTicketsBtn').addEventListener('click', loadTickets);
  $('#ticketStatusFilter').addEventListener('change', loadTickets);
  $('#ticketPriorityFilter').addEventListener('change', loadTickets);

  $('#refreshAnalyticsBtn').addEventListener('click', loadAnalytics);

  $('#ticketModal').addEventListener('click', (e) => {
    if (e.target.id === 'ticketModal') hideTicketModal();
  });

  // 退出登录
  $('#logoutAdminBtn').addEventListener('click', () => {
    if (confirm('确定退出登录？')) {
      localStorage.removeItem('cs_user_role');
      localStorage.removeItem('cs_user_name');
      localStorage.removeItem('cs_user_id');
      window.location.href = '/login.html';
    }
  });

  // 知识库相关事件
  $('#uploadFileBtn').addEventListener('click', () => $('#fileInput').click());
  $('#fileInput').addEventListener('change', (e) => {
    state.knowledge.selectedFiles = Array.from(e.target.files);
    updateUploadFilename();
  });

  const uploadArea = $('#uploadArea');
  uploadArea.addEventListener('click', () => $('#fileInput').click());
  uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
  });
  uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
  uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    state.knowledge.selectedFiles = Array.from(e.dataTransfer.files);
    updateUploadFilename();
  });

  $('#confirmUploadBtn').addEventListener('click', uploadFiles);
  $('#addTextBtn').addEventListener('click', addTextDocument);
  $('#searchBtn').addEventListener('click', searchKnowledge);
  $('#seedDocsBtn').addEventListener('click', seedDefaultDocuments);
  $('#refreshKnowledgeBtn').addEventListener('click', loadKnowledgeStats);
}

// ===== 知识库管理 =====

function updateUploadFilename() {
  const files = state.knowledge.selectedFiles;
  const container = $('#uploadFilename');
  if (!files.length) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = `<strong>已选择 ${files.length} 个文件:</strong> ${files.map(f => f.name).join(', ')}`;
}

async function loadKnowledgeStats() {
  try {
    const data = await api('GET', '/api/v1/knowledge/documents');
    $('#totalDocs').textContent = data.total_documents || 0;
    $('#totalChunks').textContent = data.total_chunks || 0;
    $('#vectorBackend').textContent = data.backend === 'milvus' ? 'Milvus' : '内存';
    $('#vectorCount').textContent = data.vector_store_count || 0;
  } catch (e) {
    console.error('加载知识库统计失败:', e);
  }
}

async function uploadFiles() {
  const files = state.knowledge.selectedFiles;
  if (!files.length) {
    toast('请先选择文件', 'warning');
    return;
  }

  const category = $('#uploadCategory').value;
  const keywords = $('#uploadKeywords').value;

  if (files.length === 1) {
    const formData = new FormData();
    formData.append('file', files[0]);
    if (files[0].name) formData.append('title', files[0].name.replace(/\.[^.]+$/, ''));
    formData.append('category', category);
    formData.append('keywords', keywords);

    try {
      const res = await fetch(`${API_BASE}/api/v1/knowledge/documents/upload`, {
        method: 'POST',
        body: formData,
      });
      const json = await res.json();
      if (json.code === 0) {
        toast(`上传成功: ${json.data.title} (${json.data.chunks_count} 个分块)`, 'success');
      } else {
        toast(json.message || '上传失败', 'error');
      }
    } catch (e) {
      toast('上传失败: ' + e.message, 'error');
    }
  } else {
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    formData.append('category', category);
    formData.append('keywords', keywords);

    try {
      const res = await fetch(`${API_BASE}/api/v1/knowledge/documents/batch-upload`, {
        method: 'POST',
        body: formData,
      });
      const json = await res.json();
      if (json.code === 0) {
        toast(json.message, 'success');
      } else {
        toast(json.message || '上传失败', 'error');
      }
    } catch (e) {
      toast('批量上传失败: ' + e.message, 'error');
    }
  }

  state.knowledge.selectedFiles = [];
  updateUploadFilename();
  $('#fileInput').value = '';
  $('#uploadKeywords').value = '';
  loadKnowledgeStats();
}

async function addTextDocument() {
  const title = $('#textTitle').value.trim();
  const content = $('#textContent').value.trim();
  const category = $('#textCategory').value;
  const keywords = $('#textKeywords').value;

  if (!title || !content) {
    toast('标题和内容不能为空', 'warning');
    return;
  }

  try {
    const data = await api('POST', '/api/v1/knowledge/documents/text', {
      title,
      content,
      category,
      keywords: keywords ? keywords.split(',').map(k => k.trim()) : [],
      source: 'manual',
    });
    toast(`添加成功: ${title} (${data.chunks_count} 个分块)`, 'success');
    $('#textTitle').value = '';
    $('#textContent').value = '';
    $('#textKeywords').value = '';
    loadKnowledgeStats();
  } catch (e) {
    toast('添加失败: ' + e.message, 'error');
  }
}

async function searchKnowledge() {
  const query = $('#searchQuery').value.trim();
  const topK = parseInt($('#searchTopK').value);

  if (!query) {
    toast('请输入搜索内容', 'warning');
    return;
  }

  try {
    const data = await api('POST', '/api/v1/knowledge/search', {
      query,
      top_k: topK,
      similarity_threshold: 0.3,
    });

    const results = data.results || [];
    const container = $('#searchResults');

    if (!results.length) {
      container.innerHTML = '<div class="empty-state">未找到相关结果</div>';
      return;
    }

    container.innerHTML = results.map((r, i) => `
      <div class="search-result-item">
        <div class="search-result-title">#${i + 1} ${r.title || '无标题'}</div>
        <div class="search-result-content">${r.content || ''}</div>
        <div class="search-result-meta">
          <span>分类: ${r.category || '-'}</span>
          <span>来源: ${r.source || '-'}</span>
          <span class="search-result-score">相似度: ${(r.final_score * 100).toFixed(1)}%</span>
        </div>
      </div>
    `).join('');
  } catch (e) {
    toast('搜索失败: ' + e.message, 'error');
  }
}

async function seedDefaultDocuments() {
  if (!confirm('确定导入示例文档？这将添加 3 篇默认文档。')) return;

  try {
    const data = await api('POST', '/api/v1/knowledge/documents/seed');
    toast(data.message, 'success');
    loadKnowledgeStats();
  } catch (e) {
    toast('导入失败: ' + e.message, 'error');
  }
}

document.addEventListener('DOMContentLoaded', init);
