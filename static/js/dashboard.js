/**
 * SpendSense AI — Dashboard Renderer (v2)
 * ==========================================
 * Features:
 *   1. Animated KPI cards with Count-Up (requestAnimationFrame) + MoM change indicators
 *   2. Financial Health Score Half-Doughnut Gauge
 *   3. Monthly Trend with scikit-learn Forecast line
 *   4. Chat with Data (bilingual, aggregated summary, Web Speech voice input)
 *   5. Full transaction filtering, insights, tips, and alerts rendering
 */

const API = '/api';
let currentPage = 1;
let currentCategory = '';
let anomalyOnly = false;


/* ─── Format Helpers ──────────────────────────────────────────────────────────*/

function fmtAmount(n) {
  return '₹' + parseFloat(n || 0).toLocaleString('en-IN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  });
}

function fmtDate(d) {
  if (!d) return '—';
  const dt = new Date(d);
  return isNaN(dt) ? d : dt.toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric'
  });
}

function catClass(cat) {
  return 'cat-' + (cat || 'transfer').toLowerCase().replace(/\s+/g, '');
}

const CAT_ICONS = {
  Dining: 'utensils',
  Groceries: 'shopping-cart',
  Bills: 'file-text',
  Shopping: 'shopping-bag',
  Travel: 'plane',
  Health: 'activity',
  Entertainment: 'film',
  Transfer: 'arrow-left-right'
};

function catIcon(cat) {
  const icon = CAT_ICONS[cat] || 'credit-card';
  return `<i data-lucide="${icon}"></i>`;
}


/* ─── Count-Up Animation (requestAnimationFrame) ──────────────────────────────*/

function animateCountUp(el, target, prefix = '', suffix = '', isCurrency = false, duration = 1100) {
  if (!el) return;
  const targetVal = parseFloat(target) || 0;
  const startTime = performance.now();

  function step(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Smooth easeOutQuart
    const ease = 1 - Math.pow(1 - progress, 4);
    const current = targetVal * ease;

    if (isCurrency) {
      el.textContent = prefix + Math.round(current).toLocaleString('en-IN') + suffix;
    } else {
      el.textContent = prefix + Math.round(current).toLocaleString() + suffix;
    }

    if (progress < 1) {
      requestAnimationFrame(step);
    } else {
      if (isCurrency) {
        el.textContent = prefix + Math.round(targetVal).toLocaleString('en-IN') + suffix;
      } else {
        el.textContent = prefix + Math.round(targetVal).toLocaleString() + suffix;
      }
    }
  }
  requestAnimationFrame(step);
}


/* ─── Overview / Dashboard Loader ─────────────────────────────────────────────*/

async function loadDashboard() {
  try {
    // Always load user's financial workspace (budget target & cheat notes)
    await loadWorkspaceData();

    const resp = await authFetch(`${API}/user/dashboard`);
    const data = await resp.json();

    if (!data.has_data) {
      return;
    }

    renderStatsCards(data);
    renderInsight(data.insight_text);
    renderBudgetTips(data.budget_tips);
    renderAlerts(data.alerts);

    // Health Score
    if (data.health_score && typeof renderHealthScoreGauge === 'function') {
      renderHealthScoreGauge(data.health_score);
    }

    // Update alert badge count
    if (data.anomaly_count > 0) {
      const b = document.getElementById('alert-badge');
      if (b) {
        b.textContent = data.anomaly_count;
        b.style.display = 'inline';
      }
    }

  } catch (e) {
    console.error('Dashboard load error:', e);
  }
}


function renderStatsCards(data) {
  const totalSpend = data.total_amount || 0;
  const totalTxns  = data.total_txns || 0;
  const anomalies  = data.anomaly_count || 0;
  const numCats    = Object.keys(data.category_totals || {}).length;

  // Animate numbers
  animateCountUp(document.getElementById('stat-total-spend'), totalSpend, '₹', '', true);
  animateCountUp(document.getElementById('stat-total-txns'), totalTxns);
  animateCountUp(document.getElementById('stat-anomalies'), anomalies);
  animateCountUp(document.getElementById('stat-categories'), numCats);

  // Top category
  const cat = data.category_totals || {};
  const topCat = Object.keys(cat).reduce((a, b) => cat[a] > cat[b] ? a : b, '—');
  const topEl = document.getElementById('stat-top-category');
  if (topEl) topEl.textContent = topCat;

  // Month-over-Month Change Indicator (Feature 2a)
  if (data.kpis && data.kpis.monthly_change) {
    const mom = data.kpis.monthly_change;
    const momEl = document.getElementById('stat-mom-badge');
    if (momEl) {
      if (mom.has_comparison) {
        const isUp = mom.direction === 'up';
        // More spend = danger (red), less spend = savings (green)
        const badgeColor = isUp ? 'var(--accent-red)' : 'var(--accent-emerald)';
        const badgeBg    = isUp ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)';
        const arrow = isUp ? '▲' : '▼';
        momEl.style.color = badgeColor;
        momEl.style.background = badgeBg;
        momEl.style.border = `1px solid ${badgeColor}`;
        momEl.innerHTML = `${arrow} ${mom.label}`;
        momEl.style.display = 'inline-flex';
      } else {
        momEl.style.color = 'var(--text-muted)';
        momEl.style.background = 'rgba(255,255,255,0.05)';
        momEl.style.border = '1px solid var(--border-default)';
        momEl.textContent = mom.label || 'Initial period';
        momEl.style.display = 'inline-flex';
      }
    }
  }
}


/* ─── Financial Workspace (Budget Goals & Smart Cheat Notes) ──────────────── */

let currentWorkspaceBudget = 50000;

async function loadWorkspaceData() {
  try {
    const resp = await authFetch(`${API}/user/workspace`);
    const data = await resp.json();
    renderWorkspace(data);
  } catch (e) {
    console.error('Workspace load error:', e);
  }
}

function renderWorkspace(ws) {
  if (!ws) return;
  currentWorkspaceBudget = ws.monthly_budget || 50000;

  // 1. Budget Display & Pace
  const spendEl    = document.getElementById('ws-spend-display');
  const goalEl     = document.getElementById('ws-goal-display');
  const pctEl      = document.getElementById('ws-pct-label');
  const barEl      = document.getElementById('ws-progress-bar');
  const remainEl   = document.getElementById('ws-remaining-amt');
  const dailyEl    = document.getElementById('ws-daily-allowance');
  const paceBadge  = document.getElementById('workspace-pace-badge');

  if (spendEl) spendEl.textContent = fmtAmount(ws.current_spend || 0);
  if (goalEl)  goalEl.textContent  = `Target: ${fmtAmount(ws.monthly_budget)}`;
  if (remainEl) remainEl.textContent = fmtAmount(ws.remaining || 0);
  if (dailyEl)  dailyEl.textContent  = `${fmtAmount(ws.daily_allowance)} / day`;

  const pct = Math.min(ws.pct_used || 0, 100);
  if (barEl) {
    barEl.style.width = `${pct}%`;
    barEl.classList.toggle('overbudget', ws.is_overbudget);
  }
  if (pctEl) {
    pctEl.textContent = `${ws.pct_used || 0}% used (${ws.days_left}d left)`;
    pctEl.style.color = ws.is_overbudget ? 'var(--accent-red)' : 'var(--text-muted)';
  }

  if (paceBadge) {
    if (ws.is_overbudget) {
      paceBadge.textContent = 'Budget Exceeded';
      paceBadge.className   = 'category-badge cat-dining';
    } else if (ws.pct_used > 80) {
      paceBadge.textContent = 'Caution Pace';
      paceBadge.className   = 'category-badge cat-shopping';
    } else {
      paceBadge.textContent = 'On Track';
      paceBadge.className   = 'category-badge cat-groceries';
    }
  }

  // 2. Render Notes
  renderWorkspaceNotesList(ws.notes || []);
}

function renderWorkspaceNotesList(notes) {
  const container = document.getElementById('ws-notes-container');
  const countEl   = document.getElementById('ws-notes-count');
  if (countEl) countEl.textContent = `${notes.length} Note${notes.length === 1 ? '' : 's'}`;
  if (!container) return;

  if (notes.length === 0) {
    container.innerHTML = `
      <div class="ws-empty-notes">
        No notes yet. Add your personal financial rules or reminders (e.g. "Max ₹500 on Swiggy", "Cancel Prime on 24th") above!
      </div>`;
    return;
  }

  container.innerHTML = notes.map(n => `
    <div class="ws-note-item ${n.is_done ? 'done' : ''}">
      <div style="display:flex;align-items:center;flex:1;overflow:hidden">
        <input type="checkbox" class="ws-note-check" ${n.is_done ? 'checked' : ''} onclick="toggleWorkspaceNote(${n.id})">
        <span style="word-break:break-word;color:${n.is_done ? 'var(--text-muted)' : 'var(--text-primary)'}">${escHtml(n.note)}</span>
      </div>
      <button class="ws-note-del-btn" onclick="deleteWorkspaceNote(${n.id})" title="Delete note"><i data-lucide="trash-2"></i></button>
    </div>
  `).join('');

  if (window.lucide) lucide.createIcons();
}

function toggleBudgetEdit() {
  const row = document.getElementById('ws-budget-edit-row');
  const input = document.getElementById('ws-budget-input');
  if (!row) return;
  if (row.style.display === 'none' || row.style.display === '') {
    row.style.display = 'flex';
    if (input) {
      input.value = currentWorkspaceBudget;
      input.focus();
    }
  } else {
    row.style.display = 'none';
  }
}

async function saveWorkspaceBudget() {
  const input = document.getElementById('ws-budget-input');
  if (!input) return;
  const val = parseFloat(input.value);
  if (!val || val <= 0) {
    showToast('Kripya valid budget amount enter karein.', 'warning');
    return;
  }

  try {
    const resp = await authFetch(`${API}/user/workspace/goal`, {
      method: 'POST',
      body: JSON.stringify({ monthly_budget: val })
    });
    const data = await resp.json();
    if (resp.ok) {
      showToast('Monthly target updated!', 'success');
      toggleBudgetEdit();
      await loadWorkspaceData();
    } else {
      showToast(data.error || 'Failed to update budget', 'error');
    }
  } catch (e) {
    showToast('Network error while saving target.', 'error');
  }
}

async function quickSetBudget(amount) {
  try {
    const resp = await authFetch(`${API}/user/workspace/goal`, {
      method: 'POST',
      body: JSON.stringify({ monthly_budget: amount })
    });
    if (resp.ok) {
      showToast(`Target set to ${fmtAmount(amount)}!`, 'success');
      await loadWorkspaceData();
    }
  } catch (e) {
    console.error('Quick set error:', e);
  }
}

async function addWorkspaceNote() {
  const input = document.getElementById('ws-new-note-input');
  if (!input) return;
  const note = input.value.trim();
  if (!note) return;

  try {
    const resp = await authFetch(`${API}/user/workspace/notes`, {
      method: 'POST',
      body: JSON.stringify({ note })
    });
    if (resp.ok) {
      input.value = '';
      await loadWorkspaceData();
    } else {
      showToast('Failed to add note.', 'error');
    }
  } catch (e) {
    showToast('Network error.', 'error');
  }
}

async function toggleWorkspaceNote(id) {
  try {
    await authFetch(`${API}/user/workspace/notes/${id}/toggle`, { method: 'PATCH' });
    await loadWorkspaceData();
  } catch (e) {
    console.error('Note toggle error:', e);
  }
}

async function deleteWorkspaceNote(id) {
  try {
    await authFetch(`${API}/user/workspace/notes/${id}`, { method: 'DELETE' });
    await loadWorkspaceData();
  } catch (e) {
    console.error('Note delete error:', e);
  }
}


/* ─── Transactions Table ──────────────────────────────────────────────────────*/

async function renderTransactions(page = 1) {
  currentPage = page;
  const tableBody = document.getElementById('txn-tbody');
  const paginationEl = document.getElementById('txn-pagination');
  if (!tableBody) return;

  tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:32px">
    <div class="spinner"></div></td></tr>`;

  let url = `${API}/user/transactions?page=${page}&per_page=20`;
  if (currentCategory) url += `&category=${encodeURIComponent(currentCategory)}`;
  if (anomalyOnly)     url += `&anomaly_only=true`;

  try {
    const resp = await authFetch(url);
    const data = await resp.json();

    const cntEl = document.getElementById('txn-count');
    if (cntEl) cntEl.textContent = `${data.total?.toLocaleString() || 0} transactions`;

    if (!data.transactions || data.transactions.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:32px;color:var(--text-muted)">
        No transactions found.</td></tr>`;
      if (paginationEl) paginationEl.innerHTML = '';
      return;
    }

    tableBody.innerHTML = data.transactions.map(t => `
      <tr>
        <td>${fmtDate(t.date)}</td>
        <td style="font-weight:500">${escHtml(t.merchant)}</td>
        <td style="color:var(--text-muted);font-size:0.8rem">${escHtml(t.description || '—')}</td>
        <td style="font-weight:700;color:var(--text-primary)">${fmtAmount(t.amount)}</td>
        <td>
          <span class="category-badge ${catClass(t.final_category)}">
            ${catIcon(t.final_category)} ${escHtml(t.final_category || '—')}
          </span>
        </td>
        <td>
          <div class="confidence-bar" title="${(t.confidence * 100).toFixed(0)}% confidence">
            <div class="confidence-fill" style="width:${(t.confidence * 100).toFixed(0)}%"></div>
          </div>
          <span style="font-size:0.75rem;color:var(--text-muted);margin-left:6px">
            ${(t.confidence * 100).toFixed(0)}%
          </span>
        </td>
        <td>
          ${t.is_anomaly
            ? `<span class="anomaly-flag"><i data-lucide="alert-triangle"></i> Anomaly</span>`
            : `<span style="color:var(--color-positive);font-size:0.8rem"><i data-lucide="check"></i> Normal</span>`
          }
        </td>
        <td style="font-size:0.75rem;color:var(--text-muted)">
          ${t.anomaly_score?.toFixed(3) ?? '—'}
        </td>
      </tr>`).join('');

    if (paginationEl) renderPagination(paginationEl, data.page, data.pages);
    if (window.lucide) lucide.createIcons();

  } catch (e) {
    tableBody.innerHTML = `<tr><td colspan="8" style="color:var(--accent-red);padding:24px">
      Failed to load transactions.</td></tr>`;
  }
}


function renderPagination(container, current, total) {
  if (total <= 1) { container.innerHTML = ''; return; }

  let html = `<button class="page-btn" onclick="renderTransactions(${current - 1})"
    ${current === 1 ? 'disabled' : ''}>‹</button>`;

  const start = Math.max(1, current - 2);
  const end   = Math.min(total, current + 2);

  if (start > 1) html += `<button class="page-btn" onclick="renderTransactions(1)">1</button>
    ${start > 2 ? '<span style="color:var(--text-muted)">…</span>' : ''}`;

  for (let i = start; i <= end; i++) {
    html += `<button class="page-btn ${i === current ? 'active' : ''}"
      onclick="renderTransactions(${i})">${i}</button>`;
  }

  if (end < total) {
    html += `${end < total - 1 ? '<span style="color:var(--text-muted)">…</span>' : ''}
      <button class="page-btn" onclick="renderTransactions(${total})">${total}</button>`;
  }

  html += `<button class="page-btn" onclick="renderTransactions(${current + 1})"
    ${current === total ? 'disabled' : ''}>›</button>`;
  html += `<span class="page-info">Page ${current} of ${total}</span>`;
  container.innerHTML = html;
}


/* ─── Insight Panel ───────────────────────────────────────────────────────────*/

function renderInsight(text) {
  const el = document.getElementById('insight-content');
  const overviewEl = document.getElementById('overview-insight-content');

  if (!text) {
    const emptyHtml = `<div class="empty-state" style="padding:24px"><span class="empty-icon"><i data-lucide="bar-chart-3"></i></span><h3>No data yet</h3><p>Upload a CSV to see AI-powered insights.</p></div>`;
    if (el) el.innerHTML = emptyHtml;
    if (overviewEl) overviewEl.innerHTML = emptyHtml;
    if (window.lucide) lucide.createIcons();
    return;
  }

  const paragraphs = text.split('\n').filter(p => p.trim());
  const contentHtml = `<div class="insight-text">` +
    paragraphs.map(p => `<p>${escHtml(p)}</p>`).join('') +
    `</div>`;

  if (el) el.innerHTML = contentHtml;
  if (overviewEl) overviewEl.innerHTML = contentHtml;
}


/* ─── Budget Tips ─────────────────────────────────────────────────────────────*/

function renderBudgetTips(tips) {
  const el = document.getElementById('tips-content');
  if (!el) return;
  if (!tips || tips.length === 0) {
    el.innerHTML = `<p class="text-muted">No tips yet. Upload a CSV to get personalized advice.</p>`;
    return;
  }
  const tipIcons = ['lightbulb', 'target', 'trending-down', 'shield-check', 'piggy-bank'];
  el.innerHTML = `<div class="tips-list">` +
    tips.map((tip, i) => `
      <div class="tip-card">
        <div class="tip-icon-badge cat-amber"><i data-lucide="${tipIcons[i % tipIcons.length]}"></i></div>
        <div class="tip-text">${escHtml(tip)}</div>
      </div>`).join('') +
    `</div>`;
  if (window.lucide) lucide.createIcons();
}


/* ─── Alerts Panel ────────────────────────────────────────────────────────────*/

function renderAlerts(alerts) {
  const el = document.getElementById('alerts-content');
  const overviewEl = document.getElementById('overview-alerts-content');

  if (!alerts || alerts.length === 0) {
    const noAlertHtml = `
      <div class="no-alerts">
        <span class="big-icon"><i data-lucide="check-circle-2"></i></span>
        <p>No anomalies detected in your latest upload. Your spending looks normal!</p>
      </div>`;
    if (el) el.innerHTML = noAlertHtml;
    if (overviewEl) overviewEl.innerHTML = noAlertHtml;
    if (window.lucide) lucide.createIcons();
    return;
  }

  const alertListHtml = `<div class="alerts-list">` +
    alerts.map(a => `
      <div class="alert-item">
        <span class="alert-icon-pill"><i data-lucide="alert-triangle"></i></span>
        <span class="alert-text">${escHtml(a.replace(/[\u2600-\u27bf\uD800-\uDBFF\uDC00-\uDFFF]/g, '').trim())}</span>
      </div>`).join('') +
    `</div>`;

  if (el) el.innerHTML = alertListHtml;
  if (overviewEl) overviewEl.innerHTML = alertListHtml;
  if (window.lucide) lucide.createIcons();
}


/* ─── Charts Loading (with ML Forecast) ───────────────────────────────────────*/

async function loadCharts() {
  try {
    const resp = await authFetch(`${API}/user/summary`);
    const data = await resp.json();
    if (!data.has_data) return;

    if (data.category_totals && Object.keys(data.category_totals).length > 0) {
      renderCategoryChart(data.category_totals);
    }
    if (data.monthly_totals && Object.keys(data.monthly_totals).length > 0) {
      renderTrendChart(data.monthly_totals, data.forecast);
    }
  } catch (e) {
    console.error('Chart load error:', e);
  }
}


/* ═══════════════════════════════════════════════════════════════════════════
   CHAT WITH DATA (Feature 1) — Unified for Panel, Overview & Floating Widget
════════════════════════════════════════════════════════════════════════════ */

async function sendChatMessageCore(message) {
  if (!message || !message.trim()) return;
  const cleanMsg = message.trim();

  // Clear inputs across all 3 interfaces
  const panelInput = document.getElementById('chat-input');
  const overviewInput = document.getElementById('overview-chat-input');
  const floatingInput = document.getElementById('floating-chat-input');
  if (panelInput) panelInput.value = '';
  if (overviewInput) overviewInput.value = '';
  if (floatingInput) floatingInput.value = '';

  appendChatMessage('user', cleanMsg);
  showTypingIndicator();

  const isAdmin = (typeof currentUser !== 'undefined' && currentUser && currentUser.role === 'admin');
  const chatEndpoint = isAdmin ? `${API}/admin/chat` : `${API}/user/chat`;

  try {
    const resp = await authFetch(chatEndpoint, {
      method: 'POST',
      body: JSON.stringify({ message: cleanMsg })
    });
    const data = await resp.json();
    hideTypingIndicator();

    if (resp.ok && data.reply) {
      appendChatMessage('ai', data.reply);
    } else {
      appendChatMessage('ai', data.error || 'Maaf kijiye, abhi response generate nahi ho paya.');
    }
  } catch (e) {
    hideTypingIndicator();
    appendChatMessage('ai', 'Network issue. Kripya connection check karein aur dubara bhejein.');
  }
}

async function sendChatMessage() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  await sendChatMessageCore(input.value);
}

async function sendOverviewChatMessage() {
  const input = document.getElementById('overview-chat-input');
  if (!input) return;
  await sendChatMessageCore(input.value);
}

async function sendFloatingChatMessage() {
  const input = document.getElementById('floating-chat-input');
  if (!input) return;
  await sendChatMessageCore(input.value);
}

function sendQuickPrompt(promptText) {
  sendChatMessageCore(promptText);
}

function sendFloatingQuickPrompt(promptText) {
  sendChatMessageCore(promptText);
}

function toggleFloatingChat() {
  const box = document.getElementById('floating-chat-box');
  if (!box) return;
  if (box.style.display === 'none' || box.style.display === '') {
    box.style.display = 'flex';
    setTimeout(() => {
      document.getElementById('floating-chat-input')?.focus();
    }, 100);
  } else {
    box.style.display = 'none';
  }
}

function appendChatMessage(role, text) {
  const containerIds = ['chat-messages', 'overview-chat-messages', 'floating-chat-messages'];
  const avatar = role === 'ai' ? '<i data-lucide="bot"></i>' : '<i data-lucide="user"></i>';
  const author = role === 'ai' ? 'SpendSense AI' : 'You';

  // Format bold markdown and linebreaks
  const formatted = escHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');

  containerIds.forEach(id => {
    const container = document.getElementById(id);
    if (!container) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-bubble chat-bubble-${role}`;
    msgDiv.innerHTML = `
      <div class="chat-avatar">${avatar}</div>
      <div class="chat-bubble-content">
        <div class="chat-author">${author}</div>
        <div class="chat-text">${formatted}</div>
      </div>
    `;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
  });

  if (window.lucide) lucide.createIcons();
}

function showTypingIndicator() {
  const containerIds = ['chat-messages', 'overview-chat-messages', 'floating-chat-messages'];
  
  containerIds.forEach(id => {
    const container = document.getElementById(id);
    if (!container || container.querySelector('.typing-indicator-bubble')) return;

    const typingDiv = document.createElement('div');
    typingDiv.className = 'chat-bubble chat-bubble-ai typing-indicator-bubble';
    typingDiv.innerHTML = `
      <div class="chat-avatar"><i data-lucide="bot"></i></div>
      <div class="chat-bubble-content">
        <div class="typing-dots">
          <span></span><span></span><span></span>
        </div>
      </div>
    `;
    container.appendChild(typingDiv);
    container.scrollTop = container.scrollHeight;
  });

  if (window.lucide) lucide.createIcons();
}

function hideTypingIndicator() {
  document.querySelectorAll('.typing-indicator-bubble').forEach(el => el.remove());
}

function initSpeechRecognition() {
  const micBtns = [
    document.getElementById('chat-mic-btn'),
    document.getElementById('overview-chat-mic-btn')
  ].filter(Boolean);

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    micBtns.forEach(btn => btn.style.display = 'none');
    return;
  }

  micBtns.forEach(micBtn => {
    const recognition = new SpeechRecognition();
    recognition.lang = 'hi-IN';
    recognition.interimResults = false;

    micBtn.addEventListener('click', () => {
      try {
        micBtn.classList.add('recording');
        recognition.start();
        showToast('Listening... Speak now', 'info', 2500);
      } catch (_) {
        micBtn.classList.remove('recording');
      }
    });

    recognition.onresult = (e) => {
      micBtn.classList.remove('recording');
      const transcript = e.results[0][0].transcript;
      sendChatMessageCore(transcript);
    };

    recognition.onerror = () => {
      micBtn.classList.remove('recording');
    };

    recognition.onend = () => {
      micBtn.classList.remove('recording');
    };
  });
}

const DEFAULT_WELCOME_MSG = "Namaste! Main aapka SpendSense AI assistant hu. Aap mujhse kisi bhi merchant (jaise Zomato, Amazon, MakeMyTrip), category breakdown, total expenses ya ML anomaly transactions ke baare me poochh sakte hain.";

function resetChatUI() {
  const containerIds = ['chat-messages', 'overview-chat-messages', 'floating-chat-messages'];
  containerIds.forEach(id => {
    const container = document.getElementById(id);
    if (!container) return;
    container.innerHTML = '';
  });
}

function renderDefaultWelcome() {
  resetChatUI();
  const isAdmin = (typeof currentUser !== 'undefined' && currentUser && currentUser.role === 'admin');
  if (isAdmin) {
    appendChatMessage('ai', 'Namaste Admin! Main SpendSense AI Platform Assistant hu. Aap mujhse platform stats, total users, uploaded statements, ML models status ya security anomalies ke baare me poochh sakte hain.');
  } else {
    appendChatMessage('ai', DEFAULT_WELCOME_MSG);
  }

  const chipsEl = document.getElementById('floating-quick-chips');
  if (chipsEl) {
    if (isAdmin) {
      chipsEl.innerHTML = `
        <button onclick="sendFloatingQuickPrompt('Total users kitne hain?')"><i data-lucide="users"></i> Users</button>
        <button onclick="sendFloatingQuickPrompt('Platform stats kya hain?')"><i data-lucide="bar-chart-2"></i> Stats</button>
        <button onclick="sendFloatingQuickPrompt('Model status kya hai?')"><i data-lucide="cpu"></i> ML Models</button>
        <button onclick="sendFloatingQuickPrompt('Anomalies kitni hain?')"><i data-lucide="shield-alert"></i> Anomalies</button>
      `;
    } else {
      chipsEl.innerHTML = `
        <button onclick="sendFloatingQuickPrompt('Zomato pe kitna kharch hua?')"><i data-lucide="utensils"></i> Zomato</button>
        <button onclick="sendFloatingQuickPrompt('Mera total kharcha kitna hai?')"><i data-lucide="wallet"></i> Total spend</button>
        <button onclick="sendFloatingQuickPrompt('Anomalies kitni hain?')"><i data-lucide="alert-triangle"></i> Anomalies</button>
      `;
    }
    if (window.lucide) lucide.createIcons();
  }
}

async function loadChatHistory() {
  resetChatUI();
  const isAdmin = (typeof currentUser !== 'undefined' && currentUser && currentUser.role === 'admin');
  const endpoint = isAdmin ? `${API}/admin/chat/history` : `${API}/user/chat/history`;

  try {
    const resp = await authFetch(endpoint);
    const data = await resp.json();
    const messages = data.messages || [];

    if (messages.length === 0) {
      renderDefaultWelcome();
    } else {
      messages.forEach(m => {
        appendChatMessage(m.role || m.sender, m.message);
      });
    }
  } catch (e) {
    console.error('Failed to load chat history:', e);
    renderDefaultWelcome();
  }
}

async function clearUserChat() {
  if (!confirm('Kya aap apni chat history clear karna chahte hain?')) return;
  const isAdmin = (typeof currentUser !== 'undefined' && currentUser && currentUser.role === 'admin');
  const endpoint = isAdmin ? `${API}/admin/chat/history` : `${API}/user/chat/history`;

  try {
    const resp = await authFetch(endpoint, { method: 'DELETE' });
    if (resp.ok) {
      showToast('Chat history cleared.', 'info');
      renderDefaultWelcome();
    } else {
      showToast('Failed to clear chat history.', 'error');
    }
  } catch (e) {
    showToast('Network error while clearing chat.', 'error');
  }
}


/* ─── Admin Panels ────────────────────────────────────────────────────────────*/

async function renderAdminUsers() {
  const el = document.getElementById('admin-users-body');
  if (!el) return;
  el.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px"><div class="spinner"></div></td></tr>`;

  try {
    const resp  = await authFetch(`${API}/admin/users`);
    const data  = await resp.json();
    const users = data.users || [];

    const cntEl = document.getElementById('admin-user-count');
    if (cntEl) cntEl.textContent = users.length;

    el.innerHTML = users.map(u => `
      <tr class="admin-user-row">
        <td>${u.id}</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <div class="user-avatar" style="width:28px;height:28px;font-size:0.7rem">
              ${u.username.charAt(0).toUpperCase()}
            </div>
            ${escHtml(u.username)}
          </div>
        </td>
        <td style="color:var(--text-muted)">${escHtml(u.email)}</td>
        <td><span class="role-pill role-${u.role}">${u.role}</span></td>
        <td>${fmtDate(u.created_at)}</td>
        <td>
          ${u.role !== 'admin' ? `
            <button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id}, '${escHtml(u.username)}')">
              <i data-lucide="trash-2"></i> Delete
            </button>` : '<span style="color:var(--text-muted);font-size:0.8rem">Protected</span>'
          }
        </td>
      </tr>`).join('') || `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px">No users found.</td></tr>`;

  } catch (e) {
    el.innerHTML = `<tr><td colspan="6" style="color:var(--accent-red);padding:24px">Failed to load users.</td></tr>`;
  }
}

async function deleteUser(id, username) {
  if (!confirm(`Delete user "${username}" and all their data? This cannot be undone.`)) return;
  try {
    const resp = await authFetch(`${API}/admin/users/${id}`, { method: 'DELETE' });
    const data = await resp.json();
    if (resp.ok) {
      showToast(data.message, 'success');
      renderAdminUsers();
    } else {
      showToast(data.error, 'error');
    }
  } catch (e) {
    showToast('Failed to delete user.', 'error');
  }
}

let adminCategoryChartInstance = null;
let globalUploadsActive = true;

async function renderAdminStats() {
  try {
    const resp  = await authFetch(`${API}/admin/stats`);
    const stats = await resp.json();

    // Animated Count-Up Numbers
    animateCountUp(document.getElementById('admin-stat-users'), stats.total_users || 0);
    animateCountUp(document.getElementById('admin-stat-uploads'), stats.total_uploads || 0);
    animateCountUp(document.getElementById('admin-stat-txns'), stats.total_txns || 0);
    animateCountUp(document.getElementById('admin-stat-anomalies'), stats.total_anomalies || 0);
    animateCountUp(document.getElementById('admin-stat-amount'), stats.total_amount || 0, '₹', '', true);

    // Platform Category Breakdown Chart
    if (stats.category_breakdown && stats.category_breakdown.length > 0) {
      renderAdminCategoryChart(stats.category_breakdown);
    }

    // Sync master upload toggle
    await checkGlobalUploadToggle();

  } catch (e) {
    console.error('Admin stats error:', e);
  }
}

function renderAdminCategoryChart(breakdown) {
  const ctx = document.getElementById('admin-category-chart');
  if (!ctx) return;

  const labels = breakdown.map(b => b.final_category);
  const data   = breakdown.map(b => parseFloat(b.total));

  if (adminCategoryChartInstance) {
    adminCategoryChartInstance.destroy();
  }

  window.adminCategoryChartInstance = adminCategoryChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: labels.map((l, i) => (CATEGORY_COLORS[l] || {}).bg || FALLBACK_COLORS[i % FALLBACK_COLORS.length]),
        borderColor: labels.map((l, i) => (CATEGORY_COLORS[l] || {}).border || FALLBACK_COLORS[i % FALLBACK_COLORS.length]),
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: {
            boxWidth: 10,
            boxHeight: 10,
            usePointStyle: true,
            color: '#94a3b8',
            font: { size: 11 }
          }
        }
      }
    }
  });
}

async function checkGlobalUploadToggle() {
  try {
    const resp = await authFetch(`${API}/admin/settings/upload-toggle`);
    const data = await resp.json();
    globalUploadsActive = data.uploads_enabled;
    updateGlobalUploadUI(globalUploadsActive);
  } catch (e) {
    console.error('Upload toggle check error:', e);
  }
}

function updateGlobalUploadUI(enabled) {
  const toggle = document.getElementById('global-upload-toggle');
  const label  = document.getElementById('global-toggle-label');
  const badge  = document.getElementById('global-upload-badge');

  if (toggle) toggle.classList.toggle('on', enabled);
  if (label) {
    label.textContent = enabled ? 'ENABLED' : 'PAUSED';
    label.style.color = enabled ? 'var(--color-positive)' : 'var(--color-danger)';
  }
  if (badge) {
    badge.textContent = enabled ? 'Active' : 'Paused';
    badge.className = `category-badge ${enabled ? 'cat-groceries' : 'cat-dining'}`;
  }

  // Also sync with Admin Workspace elements
  const wsLabel = document.getElementById('admin-ws-ingest-label');
  const wsBtn   = document.getElementById('admin-ws-ingest-btn');
  if (wsLabel) {
    wsLabel.textContent = enabled ? 'ACTIVE' : 'PAUSED';
    wsLabel.style.color = enabled ? 'var(--color-positive)' : 'var(--color-danger)';
  }
  if (wsBtn) {
    wsBtn.innerHTML = enabled
      ? '<i data-lucide="pause-circle"></i> Pause Ingestions'
      : '<i data-lucide="play-circle"></i> Resume Ingestions';
    wsBtn.className = `btn btn-sm ${enabled ? 'btn-danger' : 'btn-primary'}`;
  }
  if (window.lucide) lucide.createIcons();
}

async function toggleGlobalUpload() {
  globalUploadsActive = !globalUploadsActive;
  updateGlobalUploadUI(globalUploadsActive);

  try {
    const resp = await authFetch(`${API}/admin/settings/upload-toggle`, {
      method: 'POST',
      body: JSON.stringify({ enabled: globalUploadsActive })
    });
    const data = await resp.json();
    if (resp.ok) {
      showToast(data.message, globalUploadsActive ? 'success' : 'warning');
    } else {
      showToast(data.error || 'Failed to update setting.', 'error');
      globalUploadsActive = !globalUploadsActive;
      updateGlobalUploadUI(globalUploadsActive);
    }
  } catch (e) {
    showToast('Failed to update upload status.', 'error');
    globalUploadsActive = !globalUploadsActive;
    updateGlobalUploadUI(globalUploadsActive);
  }
}

async function renderAdminUploads() {
  const el = document.getElementById('admin-uploads-body');
  if (!el) return;

  try {
    const resp    = await authFetch(`${API}/admin/uploads`);
    const data    = await resp.json();
    const uploads = data.uploads || [];

    const cnt = document.getElementById('admin-upload-count');
    if (cnt) cnt.textContent = uploads.length;

    el.innerHTML = uploads.map(u => `
      <tr>
        <td>${u.id}</td>
        <td style="font-weight:500">${escHtml(u.username)}</td>
        <td>${escHtml(u.filename)}</td>
        <td>${fmtDate(u.upload_date)}</td>
        <td>${u.total_txns?.toLocaleString()}</td>
        <td><span style="color:var(--accent-red)">${u.anomaly_count}</span></td>
        <td style="font-weight:600">${fmtAmount(u.total_amount)}</td>
      </tr>`).join('') || `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:24px">No uploads yet.</td></tr>`;

  } catch (e) {
    el.innerHTML = `<tr><td colspan="7" style="color:var(--accent-red);padding:24px">Failed to load uploads.</td></tr>`;
  }
}

async function renderAdminLogs() {
  const el = document.getElementById('admin-logs-body');
  if (!el) return;

  try {
    const resp = await authFetch(`${API}/admin/logs`);
    const data = await resp.json();

    el.innerHTML = (data.logs || []).map(l => `
      <tr>
        <td>${l.id}</td>
        <td style="font-weight:500">${escHtml(l.admin_name || '?')}</td>
        <td>${escHtml(l.action)}</td>
        <td style="color:var(--text-muted)">${fmtDate(l.timestamp)}</td>
      </tr>`).join('') || `<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:24px">No logs yet.</td></tr>`;

  } catch (e) {
    console.error('Logs error:', e);
  }
}


/* ─── Utility ─────────────────────────────────────────────────────────────────*/

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ─── Admin Workspace (Platform Governance, Spend Cap & Runbooks) ───────── */

let currentAdminPlatformCap = 5000000;

async function loadAdminWorkspaceData() {
  try {
    const resp = await authFetch(`${API}/admin/workspace`);
    const data = await resp.json();
    renderAdminWorkspace(data);
  } catch (e) {
    console.error('Admin workspace load error:', e);
  }
}

function renderAdminWorkspace(ws) {
  if (!ws) return;
  currentAdminPlatformCap = ws.platform_budget_cap || 5000000;

  // 1. Spend Cap Display & Pace
  const spendEl   = document.getElementById('admin-ws-spend-display');
  const capEl     = document.getElementById('admin-ws-cap-display');
  const pctEl     = document.getElementById('admin-ws-pct-label');
  const barEl     = document.getElementById('admin-ws-progress-bar');
  const ingestLbl = document.getElementById('admin-ws-ingest-label');
  const ingestBtn = document.getElementById('admin-ws-ingest-btn');

  if (spendEl) spendEl.textContent = fmtAmount(ws.total_spend || 0);
  if (capEl)   capEl.textContent   = `Cap: ${fmtAmount(ws.platform_budget_cap)}`;

  const pct = Math.min(ws.burn_pct || 0, 100);
  if (barEl) {
    barEl.style.width = `${pct}%`;
    barEl.classList.toggle('overbudget', ws.is_overcap);
  }
  if (pctEl) {
    pctEl.textContent = `${ws.burn_pct || 0}% of Cap`;
    pctEl.style.color = ws.is_overcap ? 'var(--color-danger)' : 'var(--text-muted)';
  }

  if (ingestLbl) {
    ingestLbl.textContent = ws.uploads_enabled ? 'ACTIVE' : 'PAUSED';
    ingestLbl.style.color = ws.uploads_enabled ? 'var(--color-positive)' : 'var(--color-danger)';
  }
  if (ingestBtn) {
    ingestBtn.innerHTML = ws.uploads_enabled
      ? '<i data-lucide="pause-circle"></i> Pause Ingestions'
      : '<i data-lucide="play-circle"></i> Resume Ingestions';
    ingestBtn.className = `btn btn-sm ${ws.uploads_enabled ? 'btn-danger' : 'btn-primary'}`;
  }

  // 2. Render Runbook Tasks
  renderAdminWorkspaceNotes(ws.notes || []);
  if (window.lucide) lucide.createIcons();
}

function renderAdminWorkspaceNotes(notes) {
  const container = document.getElementById('admin-ws-notes-container');
  const countEl   = document.getElementById('admin-ws-notes-count');
  if (countEl) countEl.textContent = `${notes.length} Task${notes.length === 1 ? '' : 's'}`;
  if (!container) return;

  if (notes.length === 0) {
    container.innerHTML = `<div class="ws-empty-notes">No runbook tasks yet. Add a maintenance or incident task above!</div>`;
    return;
  }

  const catBadgeMap = {
    maintenance: 'cat-groceries',
    security:    'cat-danger',
    audit:       'cat-amber',
    model:       'cat-dining'
  };

  container.innerHTML = notes.map(n => {
    const badgeClass = catBadgeMap[n.category] || 'cat-transfer';
    return `
      <div class="ws-note-item ${n.is_done ? 'done' : ''}">
        <div style="display:flex;align-items:center;flex:1;overflow:hidden;gap:10px">
          <input type="checkbox" class="ws-note-check" ${n.is_done ? 'checked' : ''} onclick="toggleAdminWorkspaceNote(${n.id})">
          <span class="category-badge ${badgeClass}" style="font-size:10px;text-transform:uppercase">${escHtml(n.category || 'task')}</span>
          <span style="word-break:break-word;color:${n.is_done ? 'var(--text-muted)' : 'var(--text-primary)'}">${escHtml(n.note)}</span>
        </div>
        <button class="ws-note-del-btn" onclick="deleteAdminWorkspaceNote(${n.id})" title="Delete task"><i data-lucide="trash-2"></i></button>
      </div>
    `;
  }).join('');

  if (window.lucide) lucide.createIcons();
}

function toggleAdminCapEdit() {
  const row = document.getElementById('admin-ws-cap-edit-row');
  const input = document.getElementById('admin-ws-cap-input');
  if (!row) return;
  if (row.style.display === 'none' || row.style.display === '') {
    row.style.display = 'flex';
    if (input) {
      input.value = currentAdminPlatformCap;
      input.focus();
    }
  } else {
    row.style.display = 'none';
  }
}

async function saveAdminPlatformCap() {
  const input = document.getElementById('admin-ws-cap-input');
  if (!input) return;
  const val = parseFloat(input.value);
  if (!val || val <= 0) {
    showToast('Please enter a valid platform cap amount.', 'warning');
    return;
  }

  try {
    const resp = await authFetch(`${API}/admin/workspace/cap`, {
      method: 'POST',
      body: JSON.stringify({ cap: val })
    });
    const data = await resp.json();
    if (resp.ok) {
      showToast('Platform spending cap updated!', 'success');
      toggleAdminCapEdit();
      await loadAdminWorkspaceData();
    } else {
      showToast(data.error || 'Failed to update cap', 'error');
    }
  } catch (e) {
    showToast('Network error while updating cap.', 'error');
  }
}

async function quickSetAdminCap(amount) {
  try {
    const resp = await authFetch(`${API}/admin/workspace/cap`, {
      method: 'POST',
      body: JSON.stringify({ cap: amount })
    });
    if (resp.ok) {
      showToast(`Platform cap set to ${fmtAmount(amount)}!`, 'success');
      await loadAdminWorkspaceData();
    }
  } catch (e) {
    console.error('Quick cap set error:', e);
  }
}

async function addAdminWorkspaceNote() {
  const input = document.getElementById('admin-ws-new-note-input');
  const catEl = document.getElementById('admin-ws-note-cat');
  if (!input) return;
  const note = input.value.trim();
  const category = catEl ? catEl.value : 'maintenance';
  if (!note) return;

  try {
    const resp = await authFetch(`${API}/admin/workspace/notes`, {
      method: 'POST',
      body: JSON.stringify({ note, category })
    });
    if (resp.ok) {
      input.value = '';
      await loadAdminWorkspaceData();
    } else {
      showToast('Failed to add runbook task.', 'error');
    }
  } catch (e) {
    showToast('Network error.', 'error');
  }
}

async function toggleAdminWorkspaceNote(id) {
  try {
    await authFetch(`${API}/admin/workspace/notes/${id}/toggle`, { method: 'PATCH' });
    await loadAdminWorkspaceData();
  } catch (e) {
    console.error('Task toggle error:', e);
  }
}

async function deleteAdminWorkspaceNote(id) {
  try {
    await authFetch(`${API}/admin/workspace/notes/${id}`, { method: 'DELETE' });
    await loadAdminWorkspaceData();
  } catch (e) {
    console.error('Task delete error:', e);
  }
}

async function refreshAdminWorkspace() {
  showToast('Refreshing Admin Workspace...', 'info');
  await loadAdminWorkspaceData();
}

/* ─── Global Window Exports for HTML Handlers ─── */
window.toggleBudgetEdit = toggleBudgetEdit;
window.saveWorkspaceBudget = saveWorkspaceBudget;
window.quickSetBudget = quickSetBudget;
window.addWorkspaceNote = addWorkspaceNote;
window.toggleWorkspaceNote = toggleWorkspaceNote;
window.deleteWorkspaceNote = deleteWorkspaceNote;
window.loadWorkspaceData = loadWorkspaceData;
window.toggleAdminCapEdit = toggleAdminCapEdit;
window.saveAdminPlatformCap = saveAdminPlatformCap;
window.quickSetAdminCap = quickSetAdminCap;
window.addAdminWorkspaceNote = addAdminWorkspaceNote;
window.toggleAdminWorkspaceNote = toggleAdminWorkspaceNote;
window.deleteAdminWorkspaceNote = deleteAdminWorkspaceNote;
window.refreshAdminWorkspace = refreshAdminWorkspace;
window.loadAdminWorkspaceData = loadAdminWorkspaceData;
window.toggleGlobalUpload = toggleGlobalUpload;
window.sendChatMessage = sendChatMessage;
window.sendOverviewChatMessage = sendOverviewChatMessage;
window.sendFloatingChatMessage = sendFloatingChatMessage;
window.sendQuickPrompt = sendQuickPrompt;
window.sendFloatingQuickPrompt = sendFloatingQuickPrompt;
window.toggleFloatingChat = toggleFloatingChat;
window.clearUserChat = clearUserChat;
window.loadDashboard = loadDashboard;
window.loadCharts = loadCharts;
window.loadChatHistory = loadChatHistory;
