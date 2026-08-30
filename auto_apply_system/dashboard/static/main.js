/**
 * main.js — Dashboard logic for AutoApply
 * Handles tab switching, data fetching, and real-time updates.
 */

// ────────────────────────────────────────────
// Tab navigation
// ────────────────────────────────────────────
const tabs = ['overview', 'jobs', 'applications', 'emails', 'logs', 'settings'];

function switchTab(tabName) {
  tabs.forEach(t => {
    document.getElementById(`tab-${t}`).classList.toggle('active', t === tabName);
    const nav = document.getElementById(`nav-${t}`);
    if (nav) nav.classList.toggle('active', t === tabName);
  });

  // Load data for the tab
  if (tabName === 'overview')      { refreshStats(); loadRecentApps(); }
  if (tabName === 'jobs')          { loadJobs(); }
  if (tabName === 'applications')  { loadApplications(); }
  if (tabName === 'emails')        { loadEmails(); }
  if (tabName === 'logs')          { loadLogs(); startLogPolling(); }
}

document.querySelectorAll('.nav-item').forEach(el => {
  el.addEventListener('click', e => {
    e.preventDefault();
    switchTab(el.dataset.tab);
  });
});

// ────────────────────────────────────────────
// API helpers
// ────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  try {
    const res = await fetch(path, options);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`API error [${path}]:`, err.message);
    return null;
  }
}

// ────────────────────────────────────────────
// Stats
// ────────────────────────────────────────────
async function refreshStats() {
  const stats = await apiFetch('/api/stats');
  if (!stats) return;

  document.getElementById('statScraped').textContent  = stats.total_scraped  || 0;
  document.getElementById('statMatched').textContent  = stats.total_matched  || 0;
  document.getElementById('statApplied').textContent  = stats.total_applied  || 0;
  document.getElementById('statToday').textContent    = stats.applied_today  || 0;
  document.getElementById('statInterviews').textContent = stats.interviews   || 0;
  document.getElementById('statResponses').textContent  = stats.responses    || 0;
  document.getElementById('lastUpdated').textContent  = new Date().toLocaleTimeString();

  renderPortalBars(stats.by_portal || {});
  renderStatusChart(stats.by_status || {});
}

function renderPortalBars(byPortal) {
  const container = document.getElementById('portalBars');
  const entries = Object.entries(byPortal).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {
    container.innerHTML = '<div class="empty-state">No data yet — run a scrape!</div>';
    return;
  }
  const max = entries[0][1] || 1;
  container.innerHTML = entries.map(([portal, count]) => `
    <div class="portal-bar">
      <span class="portal-bar-name">${capitalize(portal)}</span>
      <div class="portal-bar-track">
        <div class="portal-bar-fill" style="width:${(count/max*100).toFixed(0)}%"></div>
      </div>
      <span class="portal-bar-count">${count}</span>
    </div>
  `).join('');
}

const STATUS_COLORS = {
  applied: '#10b981', scraped: '#06b6d4', matched: '#6366f1',
  skipped: '#6b7280', failed: '#ef4444', interview: '#a855f7', rejected: '#f87171'
};
function renderStatusChart(byStatus) {
  const container = document.getElementById('statusChart');
  const entries = Object.entries(byStatus);
  if (entries.length === 0) {
    container.innerHTML = '<div class="empty-state">No applications yet</div>';
    return;
  }
  container.innerHTML = entries.map(([status, count]) => `
    <div class="status-row">
      <div class="status-dot-sm" style="background:${STATUS_COLORS[status]||'#6b7280'}"></div>
      <span class="status-row-name">${capitalize(status)}</span>
      <span class="status-row-count">${count}</span>
    </div>
  `).join('');
}

// ────────────────────────────────────────────
// Jobs
// ────────────────────────────────────────────
let allJobs = [];
let jobsPage = 1;
const JOBS_PER_PAGE = 25;

async function loadJobs() {
  const portal = document.getElementById('jobPortalFilter')?.value || '';
  const status = document.getElementById('jobStatusFilter')?.value || '';
  const minScore = document.getElementById('scoreFilter')?.value || 0;

  const params = new URLSearchParams({ limit: 500, min_score: minScore });
  if (portal) params.set('portal', portal);
  if (status) params.set('status', status);

  allJobs = await apiFetch(`/api/jobs?${params}`) || [];
  jobsPage = 1;
  renderJobsPage();
}

function filterJobs() { loadJobs(); }

function renderJobsPage() {
  const tbody = document.getElementById('jobsBody');
  const start = (jobsPage - 1) * JOBS_PER_PAGE;
  const slice = allJobs.slice(start, start + JOBS_PER_PAGE);

  if (slice.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No jobs found — try adjusting filters or run a scrape</td></tr>';
    document.getElementById('jobsPagination').innerHTML = '';
    return;
  }

  tbody.innerHTML = slice.map(job => `
    <tr style="cursor:pointer" onclick="openJobModal('${escapeAttr(job.id)}')">
      <td title="${escapeAttr(job.title)}">${escapeHtml(truncate(job.title, 45))}</td>
      <td title="${escapeAttr(job.company||'')}">${escapeHtml(truncate(job.company||'—', 25))}</td>
      <td>${escapeHtml(truncate(job.location||'—', 20))}</td>
      <td><span class="portal-chip portal-${job.portal}">${capitalize(job.portal)}</span></td>
      <td>${scoreBadge(job.score)}</td>
      <td>${statusBadge(job.status)}</td>
      <td><a href="${job.url}" target="_blank" onclick="event.stopPropagation()" class="btn btn-outline btn-sm">View ↗</a></td>
    </tr>
  `).join('');

  // Pagination
  const totalPages = Math.ceil(allJobs.length / JOBS_PER_PAGE);
  const pag = document.getElementById('jobsPagination');
  if (totalPages <= 1) { pag.innerHTML = ''; return; }

  let pages = '';
  for (let i = 1; i <= totalPages; i++) {
    pages += `<button class="page-btn ${i===jobsPage?'active':''}" onclick="goJobsPage(${i})">${i}</button>`;
  }
  pag.innerHTML = pages;
}

function goJobsPage(n) { jobsPage = n; renderJobsPage(); }

// ────────────────────────────────────────────
// Job modal
// ────────────────────────────────────────────
async function openJobModal(jobId) {
  const job = await apiFetch(`/api/jobs/${encodeURIComponent(jobId)}`);
  if (!job) return;

  document.getElementById('modalTitle').textContent = job.title || '(No title)';
  document.getElementById('modalCompany').textContent = job.company || '—';
  document.getElementById('modalLocation').textContent = job.location || '—';
  document.getElementById('modalApplyLink').href = job.url || '#';
  document.getElementById('modalDesc').textContent = job.description || 'No description available.';

  const scoreEl = document.getElementById('modalScore');
  scoreEl.textContent = `${(job.score||0).toFixed(0)}% match`;
  scoreEl.className = 'badge-score ' + scoreClass(job.score);

  document.getElementById('jobModal').style.display = 'flex';
}

function closeJobModal(event) {
  if (!event || event.target === document.getElementById('jobModal')) {
    document.getElementById('jobModal').style.display = 'none';
  }
}

// ────────────────────────────────────────────
// Applications
// ────────────────────────────────────────────
async function loadApplications() {
  const apps = await apiFetch('/api/applications?limit=200') || [];
  const tbody = document.getElementById('appsBody');
  document.getElementById('appCount').textContent = `${apps.length} total applications`;

  if (apps.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No applications yet — run the system to start applying!</td></tr>';
    return;
  }

  tbody.innerHTML = apps.map(app => `
    <tr>
      <td title="${escapeAttr(app.title||'')}">${escapeHtml(truncate(app.title||'—', 40))}</td>
      <td>${escapeHtml(truncate(app.company||'—', 25))}</td>
      <td><span class="portal-chip portal-${app.portal}">${capitalize(app.portal||'—')}</span></td>
      <td>${scoreBadge(app.score)}</td>
      <td>${statusBadge(app.status)}</td>
      <td>${formatDate(app.applied_at)}</td>
      <td>
        <a href="${app.job_url||app.application_url||'#'}" target="_blank" class="btn btn-outline btn-sm">View ↗</a>
      </td>
    </tr>
  `).join('');
}

async function loadRecentApps() {
  const apps = await apiFetch('/api/applications?limit=5') || [];
  const tbody = document.getElementById('recentAppsBody');
  if (apps.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No applications yet</td></tr>';
    return;
  }
  tbody.innerHTML = apps.map(app => `
    <tr>
      <td>${escapeHtml(truncate(app.title||'—', 40))}</td>
      <td>${escapeHtml(app.company||'—')}</td>
      <td><span class="portal-chip portal-${app.portal}">${capitalize(app.portal||'—')}</span></td>
      <td>${scoreBadge(app.score)}</td>
      <td>${statusBadge(app.status)}</td>
      <td>${formatDate(app.applied_at)}</td>
    </tr>
  `).join('');
}

// ────────────────────────────────────────────
// Emails
// ────────────────────────────────────────────
const EMAIL_ICONS = {
  application_received: '✅',
  otp: '🔐',
  interview: '🗣️',
  rejection: '❌',
  other: '📧',
};

let currentEmailType = '';
let currentEmailSearch = '';

async function loadEmails() {
  const params = new URLSearchParams({ limit: 150 });
  if (currentEmailType) params.set('type', currentEmailType);
  if (currentEmailSearch) params.set('search', currentEmailSearch);

  const [emails, stats] = await Promise.all([
    apiFetch(`/api/emails?${params}`),
    apiFetch('/api/emails/stats')
  ]);

  const list = emails || [];
  const container = document.getElementById('emailList');

  // Update badge and pill counters
  if (stats) {
    document.getElementById('cntAll').textContent = stats.total || 0;
    document.getElementById('cntApp').textContent = stats.by_type?.application_received || 0;
    document.getElementById('cntInt').textContent = stats.by_type?.interview || 0;
    document.getElementById('cntRej').textContent = stats.by_type?.rejection || 0;
    document.getElementById('cntOtp').textContent = stats.by_type?.otp || 0;

    const badge = document.getElementById('emailBadge');
    if (badge) {
      badge.textContent = stats.total || 0;
      badge.style.display = (stats.total > 0) ? '' : 'none';
    }
  }

  if (list.length === 0) {
    container.innerHTML = '<div class="empty-state">No matching emails found — click "Sync Inbox" to pull latest Gmail messages</div>';
    return;
  }

  container.innerHTML = list.map((em, idx) => `
    <div class="email-item-wrapper">
      <div class="email-item" onclick="toggleEmailBody('email-body-${idx}')">
        <div class="email-type-icon">${EMAIL_ICONS[em.email_type] || '📧'}</div>
        <div style="flex:1; min-width:0">
          <div class="email-subject">${escapeHtml(em.subject || '(no subject)')}</div>
          <div class="email-from">${escapeHtml(em.from_addr || '')} • <span class="status-badge status-${em.email_type}">${formatEmailTypeLabel(em.email_type)}</span></div>
        </div>
        <div class="email-time">${formatDate(em.received_at)}</div>
      </div>
      <div class="email-body-drawer" id="email-body-${idx}" style="display:none">
        <pre class="email-body-text">${escapeHtml(em.body || 'No body text content available.')}</pre>
      </div>
    </div>
  `).join('');
}

function formatEmailTypeLabel(t) {
  const map = {
    application_received: 'Application Confirmed',
    interview: 'Interview Invite',
    rejection: 'Rejection Notice',
    otp: 'OTP / Security Code',
    other: 'Other'
  };
  return map[t] || t;
}

function toggleEmailBody(drawerId) {
  const drawer = document.getElementById(drawerId);
  if (drawer) {
    drawer.style.display = drawer.style.display === 'none' ? 'block' : 'none';
  }
}

function filterEmailType(type, btnEl) {
  currentEmailType = type;
  document.querySelectorAll('#emailFilters .filter-pill').forEach(b => b.classList.remove('active'));
  if (btnEl) btnEl.classList.add('active');
  loadEmails();
}

let searchDebounce = null;
function searchEmails() {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    currentEmailSearch = document.getElementById('emailSearchInput').value.trim();
    loadEmails();
  }, 300);
}

async function syncEmails() {
  const btn = document.getElementById('btnSyncEmails');
  const spinner = document.getElementById('syncSpinner');
  if (btn) btn.disabled = true;
  if (spinner) spinner.classList.add('spin');

  toast('info', '🔄 Syncing Gmail Inbox...', 'Connecting to ranjankumar684118@gmail.com');
  const res = await apiFetch('/api/emails/sync', { method: 'POST' });

  if (spinner) spinner.classList.remove('spin');
  if (btn) btn.disabled = false;

  if (res?.ok) {
    toast('success', '✅ Inbox Synced!', `${res.count} email(s) processed from Gmail.`);
    loadEmails();
  } else {
    toast('error', 'Sync Failed', res?.error || 'Could not connect to Gmail IMAP');
  }
}

// ────────────────────────────────────────────
// Logs
// ────────────────────────────────────────────
let logPollInterval = null;

async function loadLogs() {
  const data = await apiFetch('/api/logs?n=200');
  if (!data) return;
  const pre = document.getElementById('logContent');
  pre.innerHTML = colorizeLog(data.lines.join('\n'));
  if (document.getElementById('autoScrollLogs')?.checked) {
    document.getElementById('logTerminal').scrollTop = 999999;
  }
}

function colorizeLog(text) {
  return escapeHtml(text)
    .replace(/\[ERROR\]/g, '<span class="log-error">[ERROR]</span>')
    .replace(/\[WARNING\]/g, '<span class="log-warn">[WARNING]</span>')
    .replace(/\[INFO\]/g, '<span class="log-info">[INFO]</span>')
    .replace(/✓/g, '<span class="log-ok">✓</span>')
    .replace(/Applied to:/g, '<span class="log-ok">Applied to:</span>');
}

function clearLogs() { document.getElementById('logContent').innerHTML = ''; }

function startLogPolling() {
  if (logPollInterval) return;
  logPollInterval = setInterval(loadLogs, 5000);
}

// ────────────────────────────────────────────
// System control
// ────────────────────────────────────────────
async function runNow() {
  const result = await apiFetch('/api/system/run-now', { method: 'POST' });
  if (result?.ok) toast('success', '▶ Run started!', 'Scraping and applying...');
  else toast('error', 'Failed to start', result?.error || 'Check logs');
  updateSystemStatus();
}

async function dryRun() {
  const result = await apiFetch('/api/system/dry-run', { method: 'POST' });
  if (result?.ok) toast('info', '🔬 Dry run started', 'Scraping only — no applications will be submitted');
  else toast('error', 'Failed', result?.error || '');
}

async function stopSystem() {
  const result = await apiFetch('/api/system/stop', { method: 'POST' });
  if (result?.ok) toast('info', '⏹ System stopped', '');
  updateSystemStatus();
}

async function updateSystemStatus() {
  const status = await apiFetch('/api/system/status');
  const dot = document.getElementById('systemStatusDot');
  if (!status) { dot.className = 'status-dot'; return; }
  dot.className = status.running ? 'status-dot running' : 'status-dot online';
  document.getElementById('btnStop').style.display = status.running ? '' : 'none';
  document.getElementById('btnRunNow').style.display = status.running ? 'none' : '';
}

// ────────────────────────────────────────────
// Toast notifications
// ────────────────────────────────────────────
function toast(type, title, msg) {
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `
    <span class="toast-icon">${icons[type]||'ℹ️'}</span>
    <div class="toast-msg"><strong>${escapeHtml(title)}</strong>${msg ? '<br><span style="opacity:.8">'+escapeHtml(msg)+'</span>' : ''}</div>
  `;
  document.getElementById('toastContainer').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────
function scoreBadge(score) {
  const s = (score || 0).toFixed(0);
  const cls = score >= 75 ? 'high' : score >= 50 ? 'medium' : 'low';
  return `<span class="score-badge score-${cls}">${s}%</span>`;
}

function scoreClass(score) {
  return score >= 75 ? 'score-high' : score >= 50 ? 'score-medium' : 'score-low';
}

function statusBadge(status) {
  const labels = {
    applied: '✓ Applied', scraped: 'Scraped', matched: 'Matched',
    skipped: 'Skipped', failed: '✗ Failed', interview: '🗣 Interview',
    rejected: 'Rejected', already_applied: 'Already Applied',
  };
  const label = labels[status] || capitalize(status || 'unknown');
  return `<span class="status-badge status-${status}">${label}</span>`;
}

function capitalize(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }
function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '…' : (s || ''); }
function escapeHtml(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function escapeAttr(s) { return (s||'').replace(/'/g,'&#39;').replace(/"/g,'&quot;'); }
function formatDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day:'numeric', month:'short' }) + ' ' +
           d.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' });
  } catch { return iso.slice(0, 16); }
}

// ────────────────────────────────────────────
// Auto-refresh
// ────────────────────────────────────────────
function startAutoRefresh() {
  // Refresh stats every 30 seconds
  setInterval(() => {
    const activeTab = tabs.find(t => document.getElementById(`tab-${t}`)?.classList.contains('active'));
    if (activeTab === 'overview') refreshStats();
    if (activeTab === 'emails') loadEmails();
  }, 30000);

  // System status every 10 seconds
  setInterval(updateSystemStatus, 10000);
}

// ────────────────────────────────────────────
// Init
// ────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  refreshStats();
  loadRecentApps();
  updateSystemStatus();
  startAutoRefresh();

  // Keyboard shortcuts
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeJobModal();
  });
});
