/**
 * SpendSense AI — Main Application JS (v2)
 * ==========================================
 * NEW in this version:
 *   1. Role Selector screen (User vs Admin)
 *   2. Separate User Login / Admin Login flows
 *   3. Forgot Password overlay (reset by username + new password)
 *   4. Admin Upload toggle + CSV analysis panel
 *
 * Architecture:
 *   app.js       → auth + routing + upload + admin tools  (this file)
 *   dashboard.js → renders all data panels
 *   charts.js    → Chart.js wrappers
 */

'use strict';

const BASE_API = '/api';

/* ─── State ───────────────────────────────────────────────────────────────────*/
let authToken   = localStorage.getItem('ss_token') || null;
let currentUser = null;
let selectedRole = null;   // 'user' or 'admin' — chosen on role screen
let adminUploadOpen = false;

try {
  const raw = localStorage.getItem('ss_user');
  if (raw) currentUser = JSON.parse(raw);
} catch (_) {}


/* ─── HTTP Helper ─────────────────────────────────────────────────────────────*/
async function authFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
  return fetch(url, { ...options, headers });
}


/* ─── Toast Notifications ─────────────────────────────────────────────────────*/
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast     = document.createElement('div');
  const icons     = {
    success: '<i data-lucide="check-circle-2"></i>',
    error:   '<i data-lucide="alert-circle"></i>',
    info:    '<i data-lucide="info"></i>',
    warning: '<i data-lucide="alert-triangle"></i>'
  };
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span class="toast-icon-wrap">${icons[type] || '<i data-lucide="info"></i>'}</span><span>${escHtml(message)}</span>`;
  container.appendChild(toast);
  if (window.lucide) lucide.createIcons();

  setTimeout(() => {
    toast.style.animation = 'toastIn 0.3s ease reverse both';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}


/* ─── Theme Management ────────────────────────────────────────────────────────*/
function initTheme() {
  const saved = localStorage.getItem('spendsense_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  updateThemeIcon(saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try {
    localStorage.setItem('spendsense_theme', next);
  } catch (e) {}
  updateThemeIcon(next);
  if (typeof updateChartsTheme === 'function') {
    updateChartsTheme(next);
  }
}

function updateThemeIcon(theme) {
  document.querySelectorAll('.theme-icon-sun').forEach(el => {
    el.style.display = theme === 'light' ? 'none' : 'inline-block';
  });
  document.querySelectorAll('.theme-icon-moon').forEach(el => {
    el.style.display = theme === 'light' ? 'inline-block' : 'none';
  });
}


/* ─── Mobile Sidebar Drawer ───────────────────────────────────────────────────*/
function toggleMobileSidebar() {
  const userSidebar = document.getElementById('user-sidebar');
  const adminSidebar = document.getElementById('admin-sidebar');
  const userOverlay = document.getElementById('user-mobile-overlay');
  const adminOverlay = document.getElementById('admin-mobile-overlay');

  const activeSidebar = (userSidebar && userSidebar.offsetParent !== null) ? userSidebar : adminSidebar;
  const activeOverlay = (userOverlay && userOverlay.offsetParent !== null) ? userOverlay : adminOverlay;

  if (activeSidebar) {
    const isOpen = activeSidebar.classList.toggle('open');
    if (activeOverlay) {
      activeOverlay.classList.toggle('active', isOpen);
    }
  }
}

function closeMobileSidebar() {
  document.querySelectorAll('.sidebar').forEach(s => s.classList.remove('open'));
  document.querySelectorAll('.mobile-overlay').forEach(o => o.classList.remove('active'));
}


/* ─── Loading ─────────────────────────────────────────────────────────────────*/
function showLoading(text = 'Processing...') {
  document.getElementById('loading-text').textContent = text;
  document.getElementById('loading-overlay').style.display = 'flex';
}
function hideLoading() {
  document.getElementById('loading-overlay').style.display = 'none';
}


/* ═══════════════════════════════════════════════════════════════════════════
   ROLE SELECTOR
════════════════════════════════════════════════════════════════════════════ */
function selectRole(role) {
  selectedRole = role;
  document.getElementById('role-screen').style.display = 'none';

  if (role === 'admin') {
    document.getElementById('admin-auth-screen').style.display = 'flex';
    document.getElementById('auth-screen').style.display = 'none';
  } else {
    document.getElementById('auth-screen').style.display = 'flex';
    document.getElementById('admin-auth-screen').style.display = 'none';
    switchAuthTab('login');
  }
  if (window.lucide) lucide.createIcons();
}

function goBackToRoleSelect() {
  document.getElementById('auth-screen').style.display = 'none';
  document.getElementById('admin-auth-screen').style.display = 'none';
  document.getElementById('role-screen').style.display = 'flex';
  if (window.lucide) lucide.createIcons();
}

function quickFillUser() {
  const u = document.getElementById('login-username');
  const p = document.getElementById('login-password');
  if (u && p) {
    u.value = 'dheer12';
    p.value = 'User@123';
    showToast('Demo account credentials populated.', 'info');
  }
}

function quickFillAdmin() {
  const u = document.getElementById('admin-login-username');
  const p = document.getElementById('admin-login-password');
  if (u && p) {
    u.value = 'admin';
    p.value = 'Admin@123';
    showToast('Admin credentials populated.', 'info');
  }
}
window.quickFillUser = quickFillUser;
window.quickFillAdmin = quickFillAdmin;


/* ═══════════════════════════════════════════════════════════════════════════
   AUTH — USER LOGIN
════════════════════════════════════════════════════════════════════════════ */
async function handleLogin(e) {
  e.preventDefault();
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value.trim();
  if (!username || !password) { showToast('Please enter username and password.', 'warning'); return; }

  const btn = document.getElementById('login-btn');
  btn.disabled = true; btn.textContent = 'Logging in...';

  try {
    const resp = await fetch(`${BASE_API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await resp.json();

    if (!resp.ok) { showToast(data.error || 'Login failed.', 'error'); return; }

    // User login must not be admin
    if (data.user.role === 'admin') {
      showToast('Please use Admin Login for administrator accounts.', 'warning');
      return;
    }

    _applyLogin(data);
  } catch (_) {
    showToast('Network error. Please try again.', 'error');
  } finally {
    btn.disabled = false; btn.innerHTML = '<i data-lucide="lock"></i> Login';
    if (window.lucide) lucide.createIcons();
  }
}


/* ═══════════════════════════════════════════════════════════════════════════
   AUTH — ADMIN LOGIN (separate form)
════════════════════════════════════════════════════════════════════════════ */
async function handleAdminLogin(e) {
  e.preventDefault();
  const username = document.getElementById('admin-login-username').value.trim();
  const password = document.getElementById('admin-login-password').value.trim();
  if (!username || !password) { showToast('Please enter admin credentials.', 'warning'); return; }

  const btn = document.getElementById('admin-login-btn');
  btn.disabled = true; btn.textContent = 'Logging in...';

  try {
    const resp = await fetch(`${BASE_API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await resp.json();

    if (!resp.ok) { showToast(data.error || 'Admin login failed.', 'error'); return; }

    // Must be admin role
    if (data.user.role !== 'admin') {
      showToast('This account does not have admin privileges. Use User Login.', 'error');
      return;
    }

    _applyLogin(data);
  } catch (_) {
    showToast('Network error. Please try again.', 'error');
  } finally {
    btn.disabled = false; btn.innerHTML = '<i data-lucide="shield-check"></i> Admin Login';
    if (window.lucide) lucide.createIcons();
  }
}


/* ─── Shared login state applier ──────────────────────────────────────────────*/
function _applyLogin(data) {
  authToken   = data.token;
  currentUser = data.user;
  localStorage.setItem('ss_token', authToken);
  localStorage.setItem('ss_user', JSON.stringify(currentUser));
  showToast(`Welcome, ${currentUser.username}!`, 'success');
  routeToRole(currentUser.role);
}


/* ═══════════════════════════════════════════════════════════════════════════
   AUTH — REGISTER
════════════════════════════════════════════════════════════════════════════ */
async function handleRegister(e) {
  e.preventDefault();
  const username = document.getElementById('reg-username').value.trim();
  const email    = document.getElementById('reg-email').value.trim();
  const password = document.getElementById('reg-password').value.trim();
  if (!username || !email || !password) { showToast('All fields are required.', 'warning'); return; }

  const btn = document.getElementById('register-btn');
  btn.disabled = true; btn.textContent = 'Creating account...';

  try {
    const resp = await fetch(`${BASE_API}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password })
    });
    const data = await resp.json();
    if (!resp.ok) { showToast(data.error || 'Registration failed.', 'error'); return; }
    showToast('Account created! Please log in.', 'success');
    switchAuthTab('login');
    document.getElementById('login-username').value = username;
  } catch (_) {
    showToast('Network error. Please try again.', 'error');
  } finally {
    btn.disabled = false; btn.innerHTML = '<i data-lucide="user-plus"></i> Create Account';
    if (window.lucide) lucide.createIcons();
  }
}


/* ═══════════════════════════════════════════════════════════════════════════
   FORGOT PASSWORD
════════════════════════════════════════════════════════════════════════════ */
function openForgotPassword() {
  const overlay = document.getElementById('forgot-overlay');
  overlay.classList.add('visible');
  // Reset to step 1
  document.getElementById('forgot-step-1').classList.add('active');
  document.getElementById('forgot-step-2').classList.remove('active');
  document.getElementById('forgot-username').value    = '';
  document.getElementById('forgot-new-pass').value    = '';
  document.getElementById('forgot-confirm-pass').value= '';
}

function closeForgotPassword() {
  document.getElementById('forgot-overlay').classList.remove('visible');
}

async function handleForgotPassword(e) {
  e.preventDefault();
  const username         = document.getElementById('forgot-username').value.trim();
  const new_password     = document.getElementById('forgot-new-pass').value.trim();
  const confirm_password = document.getElementById('forgot-confirm-pass').value.trim();

  if (!username || !new_password || !confirm_password) {
    showToast('All fields are required.', 'warning'); return;
  }
  if (new_password !== confirm_password) {
    showToast('Passwords do not match.', 'error'); return;
  }
  if (new_password.length < 6) {
    showToast('Password must be at least 6 characters.', 'warning'); return;
  }

  const btn = document.getElementById('forgot-submit-btn');
  btn.disabled = true; btn.textContent = 'Resetting...';

  try {
    const resp = await fetch(`${BASE_API}/auth/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, new_password, confirm_password })
    });
    const data = await resp.json();

    if (!resp.ok) { showToast(data.error || 'Reset failed.', 'error'); return; }

    // Show success step
    document.getElementById('forgot-step-1').classList.remove('active');
    document.getElementById('forgot-step-2').classList.add('active');
    showToast('Password reset successfully!', 'success');

  } catch (_) {
    showToast('Network error. Please try again.', 'error');
  } finally {
    btn.disabled = false; btn.innerHTML = '<i data-lucide="refresh-cw"></i> Reset Password';
    if (window.lucide) lucide.createIcons();
  }
}


/* ═══════════════════════════════════════════════════════════════════════════
   LOGOUT
════════════════════════════════════════════════════════════════════════════ */
function handleLogout() {
  authToken = null; currentUser = null;
  localStorage.removeItem('ss_token');
  localStorage.removeItem('ss_user');
  document.getElementById('user-dashboard').style.display   = 'none';
  document.getElementById('admin-dashboard').style.display  = 'none';
  document.getElementById('auth-screen').style.display      = 'none';
  document.getElementById('admin-auth-screen').style.display= 'none';
  document.getElementById('role-screen').style.display      = 'flex';

  // Hide AI chat completely on login / logout screen
  const floatChat = document.getElementById('floating-chat-container');
  if (floatChat) floatChat.style.display = 'none';
  const floatBox = document.getElementById('floating-chat-box');
  if (floatBox) floatBox.style.display = 'none';

  // Clear chat bubbles from DOM so next user doesn't see old history
  if (typeof resetChatUI === 'function') resetChatUI();

  showToast('Logged out successfully.', 'info');
}


/* ─── Auth Tab Switch (User login/register tabs) ──────────────────────────────*/
function switchAuthTab(tab) {
  document.getElementById('login-form').style.display    = tab === 'login'    ? 'block' : 'none';
  document.getElementById('register-form').style.display = tab === 'register' ? 'block' : 'none';
  document.querySelectorAll('.auth-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tab);
  });
}


/* ═══════════════════════════════════════════════════════════════════════════
   ROLE-BASED ROUTING
════════════════════════════════════════════════════════════════════════════ */
function routeToRole(role) {
  document.getElementById('role-screen').style.display       = 'none';
  document.getElementById('auth-screen').style.display       = 'none';
  document.getElementById('admin-auth-screen').style.display = 'none';

  const floatChat = document.getElementById('floating-chat-container');

  if (role === 'admin') {
    if (floatChat) floatChat.style.display = 'block'; // AI Chat available for Admin too!
    document.getElementById('admin-dashboard').style.display = 'flex';
    initAdminDashboard();
    if (typeof loadChatHistory === 'function') {
      loadChatHistory();
    }
  } else {
    // Show floating chat for regular user
    if (floatChat) floatChat.style.display = 'block';
    document.getElementById('user-dashboard').style.display  = 'flex';
    initUserDashboard();
  }
}


/* ═══════════════════════════════════════════════════════════════════════════
   USER DASHBOARD
════════════════════════════════════════════════════════════════════════════ */
async function initUserDashboard() {
  if (currentUser) {
    document.getElementById('user-name').textContent   = currentUser.username;
    document.getElementById('user-avatar').textContent = currentUser.username.charAt(0).toUpperCase();
    document.getElementById('user-role-badge').textContent = currentUser.role;
  }
  showPanel('panel-overview');
  await loadDashboard();
  await loadCharts();
  if (typeof loadChatHistory === 'function') {
    await loadChatHistory();
  }
}


/* ═══════════════════════════════════════════════════════════════════════════
   ADMIN DASHBOARD
════════════════════════════════════════════════════════════════════════════ */
async function initAdminDashboard() {
  if (currentUser) {
    document.getElementById('admin-user-name').textContent   = currentUser.username;
    document.getElementById('admin-user-avatar').textContent = currentUser.username.charAt(0).toUpperCase();
  }
  showAdminPanel('admin-panel-stats');
  await renderAdminStats();
}


/* ─── Panel Navigation ────────────────────────────────────────────────────────*/
const PANEL_CRUMBS = {
  'panel-overview':     { title: 'Overview', sub: 'Financial snapshot' },
  'panel-upload':       { title: 'Upload CSV', sub: 'Statement ingestion & ML processing' },
  'panel-transactions': { title: 'Transactions', sub: 'ML categorized records' },
  'panel-charts':       { title: 'Charts & Forecast', sub: 'Visual breakdown & predictive trends' },
  'panel-chat':         { title: 'Chat with AI', sub: 'Natural language financial assistant' },
  'panel-insight':      { title: 'Spending Insight', sub: 'Gemini plain-English narrative' },
  'panel-budget':       { title: 'Budget Tips', sub: 'Personalized recommendations' },
  'panel-alerts':       { title: 'Anomaly Alerts', sub: 'Statistical outlier flags' }
};

const ADMIN_PANEL_CRUMBS = {
  'admin-panel-stats':      { title: 'Platform Statistics', sub: 'Site-wide metrics across all users' },
  'admin-panel-workspace':  { title: 'Admin Workspace', sub: 'Platform governance, spend cap monitoring & runbooks' },
  'admin-panel-users':      { title: 'Manage Users', sub: 'Platform access and user directory' },
  'admin-panel-uploads':    { title: 'All Uploads', sub: 'Global statement uploads ledger' },
  'admin-panel-upload-csv': { title: 'Upload & Analyze', sub: 'Instant ML and multi-agent tester' },
  'admin-panel-retrain':    { title: 'Retrain Models', sub: 'Random Forest & Isolation Forest engine' },
  'admin-panel-logs':       { title: 'Audit Logs', sub: 'Administrative action history' }
};

function showPanel(panelId) {
  closeMobileSidebar();
  document.querySelectorAll('#user-dashboard .panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('#user-dashboard .nav-item').forEach(n => n.classList.remove('active'));
  const panel = document.getElementById(panelId);
  if (panel) panel.classList.add('active');
  const nav = document.querySelector(`[data-panel="${panelId}"]`);
  if (nav) nav.classList.add('active');

  const crumb = PANEL_CRUMBS[panelId];
  if (crumb) {
    const tEl = document.getElementById('user-crumb-title');
    const sEl = document.getElementById('user-crumb-sub');
    if (tEl) tEl.textContent = crumb.title;
    if (sEl) sEl.textContent = crumb.sub;
  }

  if (panelId === 'panel-transactions') renderTransactions(1);
  if (panelId === 'panel-charts')       loadCharts();
  if (panelId === 'panel-chat') {
    setTimeout(() => document.getElementById('chat-input')?.focus(), 150);
  }
  if (window.lucide) lucide.createIcons();
}

function showAdminPanel(panelId) {
  closeMobileSidebar();
  document.querySelectorAll('#admin-dashboard .panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('#admin-dashboard .nav-item').forEach(n => n.classList.remove('active'));
  const panel = document.getElementById(panelId);
  if (panel) panel.classList.add('active');
  const nav = document.querySelector(`[data-admin-panel="${panelId}"]`);
  if (nav) nav.classList.add('active');

  const crumb = ADMIN_PANEL_CRUMBS[panelId];
  if (crumb) {
    const tEl = document.getElementById('admin-crumb-title');
    const sEl = document.getElementById('admin-crumb-sub');
    if (tEl) tEl.textContent = crumb.title;
    if (sEl) sEl.textContent = crumb.sub;
  }

  if (panelId === 'admin-panel-workspace')  loadAdminWorkspaceData();
  if (panelId === 'admin-panel-users')      renderAdminUsers();
  if (panelId === 'admin-panel-uploads')    renderAdminUploads();
  if (panelId === 'admin-panel-logs')       renderAdminLogs();
  if (panelId === 'admin-panel-stats')      renderAdminStats();
  if (window.lucide) lucide.createIcons();
}


/* ═══════════════════════════════════════════════════════════════════════════
   USER FILE UPLOAD
════════════════════════════════════════════════════════════════════════════ */
function initUploadZone() {
  const zone      = document.getElementById('upload-zone');
  const fileInput = document.getElementById('file-input');
  if (!zone || !fileInput) return;

  zone.addEventListener('click', () => fileInput.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('dragover');
    if (e.dataTransfer.files[0]) handleFileUpload(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', e => {
    if (e.target.files[0]) handleFileUpload(e.target.files[0]);
  });
}

function updateUploadStepper(stepNum) {
  const steps = [
    { num: 1, id: 'step-cat' },
    { num: 2, id: 'step-anom' },
    { num: 3, id: 'step-insight' },
    { num: 4, id: 'step-tips' }
  ];

  steps.forEach(s => {
    const el = document.getElementById(s.id);
    if (!el) return;
    el.classList.remove('pending', 'active', 'completed');
    if (stepNum > s.num) {
      el.classList.add('completed');
    } else if (stepNum === s.num) {
      el.classList.add('active');
    } else {
      el.classList.add('pending');
    }
  });
}

async function handleFileUpload(file) {
  if (!file.name.toLowerCase().endsWith('.csv')) {
    showToast('Only CSV files are supported.', 'error');
    return;
  }

  const progressEl    = document.getElementById('upload-progress');
  const progressBar   = document.getElementById('progress-bar');
  const progressLabel = document.getElementById('progress-label');

  progressEl.style.display = 'block';
  progressBar.style.width   = '10%';
  progressLabel.textContent = 'Uploading CSV to server...';
  updateUploadStepper(1);

  try {
    const fd = new FormData();
    fd.append('file', file);
    const hdrs = {};
    if (authToken) hdrs['Authorization'] = `Bearer ${authToken}`;

    const resp = await fetch(`${BASE_API}/user/upload`, {
      method: 'POST',
      headers: hdrs,
      body: fd
    });
    const data = await resp.json();

    if (!resp.ok) {
      progressEl.style.display = 'none';
      showToast(data.error || 'Upload failed.', 'error');
      return;
    }

    const jobId = data.job_id;
    if (!jobId) {
      progressBar.style.width = '100%';
      progressLabel.textContent = 'Done!';
      updateUploadStepper(5);
      setTimeout(() => { progressEl.style.display = 'none'; }, 1200);
      await loadDashboard();
      await loadCharts();
      showPanel('panel-overview');
      return;
    }

    // Poll status endpoint every 350ms for snappy real-time feedback
    const pollTimer = setInterval(async () => {
      try {
        const sResp = await fetch(`${BASE_API}/user/upload/status/${jobId}`, { headers: hdrs });
        const sData = await sResp.json();
        if (!sResp.ok) return;

        progressBar.style.width   = `${sData.progress || 15}%`;
        progressLabel.textContent = sData.step_name || 'Processing...';
        updateUploadStepper(sData.step || 1);

        if (sData.status === 'completed') {
          clearInterval(pollTimer);
          progressBar.style.width = '100%';
          progressLabel.textContent = 'Analysis complete!';
          updateUploadStepper(5);

          showToast(
            `${sData.summary?.total_txns || 0} transactions analyzed! ${sData.summary?.anomaly_count || 0} anomalies flagged.`,
            'success',
            5000
          );

          setTimeout(async () => {
            progressEl.style.display = 'none';
            progressBar.style.width = '0%';
            await loadDashboard();
            await loadCharts();
            showPanel('panel-overview');
          }, 350);

        } else if (sData.status === 'failed') {
          clearInterval(pollTimer);
          progressEl.style.display = 'none';
          showToast(sData.error || 'Analysis failed. Please check CSV format.', 'error');
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 350);

  } catch (err) {
    progressEl.style.display = 'none';
    showToast('Network error during upload.', 'error');
  }
}

/* ─── One-Click Demo CSV Ingestion ───────────────────────────────────────────*/
async function loadDemoCsv() {
  showToast('Ingesting demo CSV statement...', 'info', 2000);
  try {
    const resp = await fetch('/api/sample-csv');
    if (!resp.ok) {
      showPanel('panel-upload');
      return;
    }
    const blob = await resp.blob();
    const demoFile = new File([blob], 'sample_upload.csv', { type: 'text/csv' });
    showPanel('panel-upload');
    handleFileUpload(demoFile);
  } catch (e) {
    showPanel('panel-upload');
  }
}


/* ═══════════════════════════════════════════════════════════════════════════
   ADMIN UPLOAD TOGGLE + UPLOAD
════════════════════════════════════════════════════════════════════════════ */
async function loadAdminDemoCsv() {
  showToast('Ingesting sample statement for admin diagnostics...', 'info', 2000);
  try {
    const resp = await fetch('/api/sample-csv');
    if (!resp.ok) {
      showToast('Sample CSV not found. Please browse a local file.', 'error');
      return;
    }
    const blob = await resp.blob();
    const demoFile = new File([blob], 'sample_upload.csv', { type: 'text/csv' });
    handleAdminFileUpload(demoFile);
  } catch (e) {
    showToast('Failed to load sample CSV.', 'error');
  }
}
window.loadAdminDemoCsv = loadAdminDemoCsv;

function toggleAdminUpload() {
  const section = document.getElementById('admin-upload-section');
  if (section) section.style.display = 'block';
}

function initAdminUploadZone() {
  const zone      = document.getElementById('admin-upload-zone');
  const fileInput = document.getElementById('admin-file-input');
  if (!zone || !fileInput) return;

  zone.addEventListener('click', () => fileInput.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('dragover');
    if (e.dataTransfer.files[0]) handleAdminFileUpload(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', e => {
    if (e.target.files[0]) handleAdminFileUpload(e.target.files[0]);
  });
}

async function handleAdminFileUpload(file) {
  if (!file.name.toLowerCase().endsWith('.csv')) {
    showToast('Only CSV files are supported.', 'error'); return;
  }

  const progressEl    = document.getElementById('admin-upload-progress');
  const progressBar   = document.getElementById('admin-progress-bar');
  const progressLabel = document.getElementById('admin-progress-label');
  progressEl.style.display = 'block';

  const steps = [
    { pct: 20, text: 'Reading CSV...' },
    { pct: 45, text: 'Running ML models...' },
    { pct: 70, text: 'Running AI agents...' },
    { pct: 90, text: 'Finalizing...' },
  ];
  let si = 0;
  const iv = setInterval(() => {
    if (si < steps.length) {
      progressBar.style.width   = steps[si].pct + '%';
      progressLabel.textContent = steps[si++].text;
    }
  }, 1500);

  try {
    const fd = new FormData();
    fd.append('file', file);
    const hdrs = {};
    if (authToken) hdrs['Authorization'] = `Bearer ${authToken}`;

    const resp = await fetch(`${BASE_API}/admin/upload`, { method: 'POST', headers: hdrs, body: fd });
    clearInterval(iv);
    progressBar.style.width = '100%'; progressLabel.textContent = 'Done!';
    const data = await resp.json();
    setTimeout(() => { progressEl.style.display = 'none'; progressBar.style.width = '0%'; }, 1500);

    if (!resp.ok) { showToast(data.error || 'Admin upload failed.', 'error'); return; }

    showToast(`Admin analysis complete! ${data.summary.total_txns} txns, ${data.summary.anomaly_count} anomalies.`, 'success', 5000);
    renderAdminUploadResult(data);

  } catch (_) {
    clearInterval(iv);
    progressEl.style.display = 'none';
    showToast('Upload failed. Check your connection.', 'error');
  }
}

function renderAdminUploadResult(data) {
  const resultEl = document.getElementById('admin-upload-result');
  resultEl.style.display = 'block';

  const s = data.summary || {};
  document.getElementById('admin-result-grid').innerHTML = `
    <div class="result-chip">
      <span class="chip-val">${(s.total_txns || 0).toLocaleString()}</span>
      <span class="chip-label">Transactions</span>
    </div>
    <div class="result-chip">
      <span class="chip-val" style="color:var(--color-danger)">${s.anomaly_count || 0}</span>
      <span class="chip-label">Anomalies</span>
    </div>
    <div class="result-chip">
      <span class="chip-val" style="color:var(--color-positive)">₹${parseFloat(s.total_amount || 0).toLocaleString('en-IN', {maximumFractionDigits:0})}</span>
      <span class="chip-label">Total Spend</span>
    </div>
    <div class="result-chip">
      <span class="chip-val">${Object.keys(s.category_totals || {}).length}</span>
      <span class="chip-label">Categories</span>
    </div>`;

  // Insight
  const insight = data.insight_text || 'No insight generated.';
  document.getElementById('admin-result-insight').innerHTML = `
    <div class="insight-text">${insight.split('\n').filter(p=>p.trim()).map(p=>`<p>${escHtml(p)}</p>`).join('')}</div>`;

  // Tips
  const tips = data.budget_tips || [];
  const tipIcons = ['lightbulb', 'target', 'trending-down', 'shield-check', 'piggy-bank'];
  document.getElementById('admin-result-tips').innerHTML = tips.length
    ? `<div class="tips-list">${tips.map((t,i)=>`
        <div class="tip-card">
          <div class="tip-icon-badge cat-amber"><i data-lucide="${tipIcons[i % tipIcons.length]}"></i></div>
          <div class="tip-text">${escHtml(t)}</div>
        </div>`).join('')}</div>`
    : `<p class="text-muted">No tips generated.</p>`;
  if (window.lucide) lucide.createIcons();

  // Alerts
  const alerts = data.alerts || [];
  document.getElementById('admin-result-alerts').innerHTML = alerts.length
    ? `<div class="alerts-list">${alerts.map(a=>`
        <div class="alert-item">
          <span class="alert-icon-pill"><i data-lucide="alert-triangle"></i></span>
          <span class="alert-text">${escHtml(a.replace(/[\u2600-\u27bf\uD800-\uDBFF\uDC00-\uDFFF]/g, '').trim())}</span>
        </div>`).join('')}</div>`
    : `<div class="no-alerts"><span class="big-icon"><i data-lucide="check-circle-2"></i></span><p>No anomalies detected.</p></div>`;

  if (window.lucide) lucide.createIcons();
}


/* ─── Transaction Filters ─────────────────────────────────────────────────────*/
function handleCategoryFilter(value) {
  currentCategory = value;
  renderTransactions(1);
}

function handleAnomalyFilter() {
  anomalyOnly = !anomalyOnly;
  const btn = document.getElementById('anomaly-filter-btn');
  btn.classList.toggle('active', anomalyOnly);
  btn.innerHTML = anomalyOnly ? '<i data-lucide="alert-triangle"></i> Anomalies Only' : 'Show Anomalies Only';
  if (window.lucide) lucide.createIcons();
  renderTransactions(1);
}


/* ─── Admin: Retrain Models ───────────────────────────────────────────────────*/
async function retrainModels() {
  const btn = document.getElementById('retrain-btn');
  btn.disabled = true; btn.textContent = 'Retraining...';
  showToast('Retraining started — this may take 1–2 minutes.', 'info');
  try {
    const resp = await authFetch(`${BASE_API}/admin/retrain`, { method: 'POST' });
    const data = await resp.json();
    if (resp.ok) { showToast('Models retrained successfully!', 'success', 6000); }
    else { showToast(data.error || 'Retraining failed.', 'error'); }
  } catch (_) {
    showToast('Retraining request failed.', 'error');
  } finally {
    btn.disabled = false; btn.innerHTML = '<i data-lucide="refresh-cw"></i> Retrain ML Models';
    if (window.lucide) lucide.createIcons();
  }
}


/* ─── Session Restore ─────────────────────────────────────────────────────────*/
async function checkExistingSession() {
  if (!authToken || !currentUser) return false;
  try {
    const resp = await authFetch(`${BASE_API}/auth/me`);
    if (!resp.ok) { handleLogout(); return false; }
    currentUser = await resp.json();
    return true;
  } catch (_) { return false; }
}


/* ─── Init ────────────────────────────────────────────────────────────────────*/
document.addEventListener('DOMContentLoaded', async () => {

  // Initialize theme from localStorage
  initTheme();

  // Auth tabs
  document.querySelectorAll('.auth-tab').forEach(tab => {
    tab.addEventListener('click', () => switchAuthTab(tab.dataset.tab));
  });

  // Forms
  document.getElementById('login-form')?.addEventListener('submit', handleLogin);
  document.getElementById('register-form')?.addEventListener('submit', handleRegister);
  document.getElementById('admin-login-form')?.addEventListener('submit', handleAdminLogin);
  document.getElementById('forgot-form')?.addEventListener('submit', handleForgotPassword);

  // Close forgot overlay on background click
  document.getElementById('forgot-overlay')?.addEventListener('click', e => {
    if (e.target === document.getElementById('forgot-overlay')) closeForgotPassword();
  });

  // Upload zones
  initUploadZone();
  initAdminUploadZone();

  // Voice recognition for Chat
  if (typeof initSpeechRecognition === 'function') {
    initSpeechRecognition();
  }

  // Render Lucide icons
  if (window.lucide) {
    lucide.createIcons();
  }

  // Check existing session
  const valid = await checkExistingSession();
  if (valid && currentUser) {
    document.getElementById('role-screen').style.display = 'none';
    routeToRole(currentUser.role);
  } else {
    document.getElementById('role-screen').style.display = 'flex';
  }

  if (window.lucide) {
    lucide.createIcons();
  }
});


/* ─── Utility ─────────────────────────────────────────────────────────────────*/
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
