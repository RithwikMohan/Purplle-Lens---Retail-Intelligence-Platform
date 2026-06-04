/* ===================================
   STORE INTELLIGENCE — DASHBOARD JS
   Real-time polling every 5 seconds
   =================================== */

const API_BASE = 'http://127.0.0.1:8000';
let currentStore = 'ST1008';
let metricsChart = null;
let metricsHistory = { labels: [], visitors: [], queueDepth: [] };
let refreshInterval = null;
let eventStreamQueue = [];

// ─── Color palettes for funnel stages ───
const FUNNEL_COLORS = [
  { bg: 'linear-gradient(90deg,#7c3aed,#a855f7)', bar: '#a855f7' },
  { bg: 'linear-gradient(90deg,#0891b2,#06b6d4)', bar: '#06b6d4' },
  { bg: 'linear-gradient(90deg,#d97706,#f59e0b)', bar: '#f59e0b' },
  { bg: 'linear-gradient(90deg,#059669,#10b981)', bar: '#10b981' },
];

const HEATMAP_COLORS = [
  { bg: 'rgba(30,41,59,0.8)',   border: '#1e293b', bar: '#334155' },
  { bg: 'rgba(76,29,149,0.25)', border: 'rgba(109,40,217,0.4)',  bar: '#6d28d9' },
  { bg: 'rgba(109,40,217,0.3)', border: 'rgba(139,92,246,0.5)',  bar: '#8b5cf6' },
  { bg: 'rgba(168,85,247,0.3)', border: 'rgba(168,85,247,0.6)',  bar: '#a855f7' },
  { bg: 'rgba(192,132,252,0.3)',border: 'rgba(192,132,252,0.7)', bar: '#c084fc' },
];

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
  initParticles();
  initClock();
  initChart();
  loadAll();
  startAutoRefresh();
});

// ─── Particle Network Background ───
function initParticles() {
  const canvas = document.getElementById('particleCanvas');
  if(!canvas) return;
  const ctx = canvas.getContext('2d');
  
  let w = canvas.width = window.innerWidth;
  let h = canvas.height = window.innerHeight;
  let particles = [];
  
  window.addEventListener('resize', () => {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  });
  
  class Particle {
    constructor() {
      this.x = Math.random() * w;
      this.y = Math.random() * h;
      this.vx = (Math.random() - 0.5) * 0.5;
      this.vy = (Math.random() - 0.5) * 0.5;
      this.size = Math.random() * 2;
    }
    update() {
      this.x += this.vx;
      this.y += this.vy;
      if(this.x < 0 || this.x > w) this.vx *= -1;
      if(this.y < 0 || this.y > h) this.vy *= -1;
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(168,85,247,0.5)';
      ctx.fill();
    }
  }
  
  for(let i=0; i<60; i++) particles.push(new Particle());
  
  function animate() {
    ctx.clearRect(0, 0, w, h);
    for(let i=0; i<particles.length; i++) {
      particles[i].update();
      particles[i].draw();
      for(let j=i+1; j<particles.length; j++) {
        let dx = particles[i].x - particles[j].x;
        let dy = particles[i].y - particles[j].y;
        let dist = Math.sqrt(dx*dx + dy*dy);
        if(dist < 150) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(168,85,247,${0.15 * (1 - dist/150)})`;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(animate);
  }
  animate();
}

// ─── Clock ───
function initClock() {
  setInterval(() => {
    const now = new Date();
    document.getElementById('headerTime').textContent =
      now.toLocaleTimeString('en-IN', { hour12: false });
  }, 1000);
}

// ─── Store Switch ───
function switchStore(storeId) {
  currentStore = storeId;
  document.getElementById('btn-store1').classList.toggle('active', storeId === 'ST1008');
  document.getElementById('btn-store2').classList.toggle('active', storeId === 'ST1076');
  // Reset history
  metricsHistory = { labels: [], visitors: [], queueDepth: [] };
  clearEventStream();
  loadAll();
}

// ─── Auto Refresh ───
function startAutoRefresh() {
  if (refreshInterval) clearInterval(refreshInterval);
  refreshInterval = setInterval(() => {
    loadAll();
  }, 5000);
}

// ─── Load All Data ───
async function loadAll() {
  await Promise.allSettled([
    loadMetrics(),
    loadFunnel(),
    loadHeatmap(),
    loadAnomalies(),
    loadEvents(),
  ]);
}

// ─── API Call Helper ───
async function apiFetch(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Accept': 'application/json' }
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ─── Update API Status Dot ───
function setApiStatus(status, label) {
  const dot = document.getElementById('statusDot');
  const lbl = document.getElementById('statusLabel');
  dot.className = `status-dot ${status}`;
  lbl.textContent = label;
}

// ─── METRICS ───
async function loadMetrics() {
  try {
    const data = await apiFetch(`/stores/${currentStore}/metrics`);
    setApiStatus('ok', 'Connected');
    updateKPIs(data);
    pushMetricsHistory(data);
    updateChart();
  } catch (e) {
    setApiStatus('error', 'API Offline');
    // Load demo data so dashboard looks great even without backend
    loadDemoData();
  }
}

function updateKPIs(data) {
  animateValue('val-visitors', data.unique_visitors, '');
  animateValue('val-conversion', (data.conversion_rate * 100).toFixed(1), '%');
  animateValue('val-queue', data.queue_depth, '');
  animateValue('val-abandon', (data.abandonment_rate * 100).toFixed(1), '%');
}

function animateValue(id, value, suffix) {
  const el = document.getElementById(id);
  if (!el) return;
  const prev = el.textContent;
  const next = `${value}${suffix}`;
  if (prev !== next && prev !== '—') {
    el.classList.remove('bump');
    void el.offsetWidth;
    el.classList.add('bump');
  }
  el.textContent = next;
}

function pushMetricsHistory(data) {
  const now = new Date().toLocaleTimeString('en-IN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  metricsHistory.labels.push(now);
  metricsHistory.visitors.push(data.unique_visitors);
  metricsHistory.queueDepth.push(data.queue_depth);
  // Keep last 20 points
  if (metricsHistory.labels.length > 20) {
    metricsHistory.labels.shift();
    metricsHistory.visitors.shift();
    metricsHistory.queueDepth.shift();
  }
}

// ─── CHART ───
function initChart() {
  const ctx = document.getElementById('metricsChart').getContext('2d');
  metricsChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'Unique Visitors',
          data: [],
          borderColor: '#a855f7',
          backgroundColor: 'rgba(168,85,247,0.1)',
          borderWidth: 2.5,
          fill: true,
          tension: 0.45,
          pointRadius: 3,
          pointBackgroundColor: '#a855f7',
        },
        {
          label: 'Queue Depth',
          data: [],
          borderColor: '#f59e0b',
          backgroundColor: 'rgba(245,158,11,0.07)',
          borderWidth: 2,
          fill: true,
          tension: 0.45,
          pointRadius: 3,
          pointBackgroundColor: '#f59e0b',
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 600 },
      plugins: {
        legend: {
          position: 'top',
          labels: { color: '#8da0bb', font: { size: 11, family: 'Inter' }, boxWidth: 12, padding: 16 }
        },
        tooltip: {
          backgroundColor: '#0f1623',
          borderColor: '#1e2d45',
          borderWidth: 1,
          titleColor: '#f0f4ff',
          bodyColor: '#8da0bb',
          padding: 10,
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { color: '#4a6080', font: { size: 10 }, maxRotation: 0, maxTicksLimit: 8 }
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { color: '#4a6080', font: { size: 10 } },
          beginAtZero: true,
        }
      }
    }
  });
}

function updateChart() {
  if (!metricsChart) return;
  metricsChart.data.labels = [...metricsHistory.labels];
  metricsChart.data.datasets[0].data = [...metricsHistory.visitors];
  metricsChart.data.datasets[1].data = [...metricsHistory.queueDepth];
  metricsChart.update('active');
}

// ─── FUNNEL ───
async function loadFunnel() {
  try {
    const data = await apiFetch(`/stores/${currentStore}/funnel`);
    renderFunnel(data);
  } catch (e) {
    renderDemoFunnel();
  }
}

function renderFunnel(data) {
  const container = document.getElementById('funnelContainer');
  const dateEl = document.getElementById('funnelDate');
  if (data.date) dateEl.textContent = formatDate(data.date);

  const stages = data.stages || [];
  const maxCount = stages[0]?.count || 1;

  container.innerHTML = stages.map((stage, i) => {
    const pct = maxCount > 0 ? (stage.count / maxCount * 100).toFixed(1) : 0;
    const color = FUNNEL_COLORS[i] || FUNNEL_COLORS[0];
    const dropHtml = stage.drop_off_pct > 0
      ? `<div class="funnel-drop">▼ ${stage.drop_off_pct.toFixed(1)}% dropped off</div>`
      : i === 0 ? '' : `<div class="funnel-drop good">✓ No drop-off</div>`;

    return `
      <div class="funnel-stage" style="animation-delay:${i * 80}ms">
        <div class="funnel-stage-header">
          <span class="funnel-stage-name">${stage.stage}</span>
          <span class="funnel-stage-count">${stage.count.toLocaleString()}</span>
        </div>
        <div class="funnel-bar-track">
          <div class="funnel-bar-fill" style="width:0%;background:${color.bar}" data-target="${pct}"></div>
        </div>
        ${dropHtml}
      </div>
    `;
  }).join('');

  // Animate bars after render
  requestAnimationFrame(() => {
    container.querySelectorAll('.funnel-bar-fill').forEach(bar => {
      setTimeout(() => { bar.style.width = bar.dataset.target + '%'; }, 50);
    });
  });
}

// ─── HEATMAP ───
async function loadHeatmap() {
  try {
    const data = await apiFetch(`/stores/${currentStore}/heatmap`);
    renderHeatmap(data);
  } catch (e) {
    renderDemoHeatmap();
  }
}

const SVG_MAP = `
<svg viewBox="0 0 800 500" class="svg-store-map" xmlns="http://www.w3.org/2000/svg">
  <rect x="10" y="10" width="780" height="480" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="2" rx="10"/>
  <path id="svg-SKINCARE" class="svg-zone" d="M 20 20 L 250 20 L 250 150 L 20 150 Z" data-zone="SKINCARE" />
  <text x="135" y="90" class="svg-zone-text">SKINCARE</text>
  <path id="svg-MOISTURISER" class="svg-zone" d="M 270 20 L 780 20 L 780 150 L 270 150 Z" data-zone="MOISTURISER" />
  <text x="525" y="90" class="svg-zone-text">MOISTURISER</text>
  <path id="svg-LIPSTICK" class="svg-zone" d="M 20 170 L 250 170 L 250 300 L 20 300 Z" data-zone="LIPSTICK" />
  <text x="135" y="240" class="svg-zone-text">LIPSTICK</text>
  <path id="svg-FRAGRANCES" class="svg-zone" d="M 270 170 L 500 170 L 500 300 L 270 300 Z" data-zone="FRAGRANCES" />
  <text x="385" y="240" class="svg-zone-text">FRAGRANCES</text>
  <path id="svg-HAIRCARE" class="svg-zone" d="M 20 320 L 250 320 L 250 470 L 20 470 Z" data-zone="HAIRCARE" />
  <text x="135" y="400" class="svg-zone-text">HAIRCARE</text>
  <path id="svg-NAIL_ART" class="svg-zone" d="M 270 320 L 500 320 L 500 470 L 270 470 Z" data-zone="NAIL_ART" />
  <text x="385" y="400" class="svg-zone-text">NAIL ART</text>
  <path id="svg-BILLING_ZONE" class="svg-zone" d="M 520 170 L 780 170 L 780 470 L 520 470 Z" data-zone="BILLING_ZONE" />
  <text x="650" y="325" class="svg-zone-text">BILLING ZONE</text>
  <rect x="350" y="480" width="100" height="8" fill="#10b981" />
  <text x="400" y="475" fill="#10b981" font-size="12" text-anchor="middle" font-family="Inter" font-weight="700">ENTRANCE</text>
</svg>
`;

function renderHeatmap(data) {
  const grid = document.getElementById('heatmapGrid');
  const zones = data.zones || {};
  const entries = Object.entries(zones);

  if (entries.length === 0) {
    grid.innerHTML = '<div class="heatmap-loading">No zone data available yet.<br>Run the pipeline to populate.</div>';
    return;
  }

  // Inject SVG map if not present
  if (!grid.querySelector('.svg-store-map')) {
    grid.innerHTML = SVG_MAP;
    setupSvgInteractions(zones);
  }
  
  // Colorize SVG paths based on frequency
  entries.forEach(([zoneId, info]) => {
    const freq = info.normalized_frequency || 0;
    const colorIdx = Math.min(Math.floor(freq / 25), HEATMAP_COLORS.length - 1);
    const color = HEATMAP_COLORS[colorIdx];
    
    const path = grid.querySelector(`#svg-${zoneId}`);
    if (path) {
      path.style.fill = color.bg;
      path.dataset.visits = info.visit_frequency;
      path.dataset.dwell = info.avg_dwell_seconds.toFixed(0);
      path.dataset.name = formatZoneName(zoneId);
    }
  });
}

function setupSvgInteractions(zones) {
  const paths = document.querySelectorAll('.svg-zone');
  const tooltip = document.getElementById('heatmapTooltip');
  
  paths.forEach(path => {
    path.addEventListener('mouseenter', (e) => {
      path.classList.add('active-zone');
      tooltip.style.opacity = '1';
      tooltip.innerHTML = `
        <div style="font-weight:700;margin-bottom:4px">${path.dataset.name}</div>
        <div>Visits: <strong style="color:var(--cyan)">${path.dataset.visits || 0}</strong></div>
        <div>Avg Dwell: <strong style="color:var(--amber)">${path.dataset.dwell || 0}s</strong></div>
      `;
    });
    path.addEventListener('mousemove', (e) => {
      tooltip.style.left = (e.pageX + 15) + 'px';
      tooltip.style.top = (e.pageY + 15) + 'px';
    });
    path.addEventListener('mouseleave', () => {
      path.classList.remove('active-zone');
      tooltip.style.opacity = '0';
    });
  });
}

// ─── ANOMALIES ───
async function loadAnomalies() {
  try {
    const data = await apiFetch(`/stores/${currentStore}/anomalies`);
    renderAnomalies(data);
  } catch (e) {
    renderDemoAnomalies();
  }
}

function renderAnomalies(anomalies) {
  const list = document.getElementById('anomalyList');
  const countEl = document.getElementById('anomalyCount');

  countEl.textContent = anomalies.length;
  countEl.className = `anomaly-count ${anomalies.length === 0 ? 'zero' : ''}`;

  if (anomalies.length === 0) {
    list.innerHTML = `
      <div class="anomaly-empty">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#334155" stroke-width="1.5">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
        <p>All systems normal</p>
      </div>`;
    return;
  }

  list.innerHTML = anomalies.map((a, i) => `
    <div class="anomaly-item ${a.severity}" style="animation-delay:${i * 60}ms">
      <div class="anomaly-top">
        <span class="anomaly-type">${a.type.replace(/_/g,' ')}</span>
        <span class="anomaly-sev">${a.severity}</span>
      </div>
      <div class="anomaly-msg" data-text="> ${a.message.replace(/"/g, '&quot;')}"></div>
      <div class="anomaly-action">${a.suggested_action}</div>
    </div>
  `).join('');

  requestAnimationFrame(() => {
    list.querySelectorAll('.anomaly-msg').forEach((el) => {
      const fullText = el.dataset.text;
      el.textContent = '';
      let charIdx = 0;
      // Add a slight delay before typing starts based on the item animation delay
      setTimeout(() => {
        const typeInterval = setInterval(() => {
          if(charIdx < fullText.length) {
            el.textContent += fullText[charIdx];
            charIdx++;
          } else {
            clearInterval(typeInterval);
          }
        }, 15);
      }, 400); // Start after the fade-in animation
    });
  });
}

// ─── EVENT STREAM ───
async function loadEvents() {
  try {
    const events = await apiFetch(`/stores/${currentStore}/events?limit=50`);
    renderEvents(events);
  } catch (e) {
    // Keep showing demo event simulation if API fails/offline
  }
}

function renderEvents(events) {
  const stream = document.getElementById('eventStream');
  if (events.length === 0) {
    stream.innerHTML = '<div class="stream-placeholder">Waiting for events…</div>';
    return;
  }

  stream.innerHTML = events.map(e => {
    const time = formatDateToTime(e.timestamp);
    const dotColor = {
      ENTRY:'#10b981', EXIT:'#ef4444', ZONE_ENTER:'#06b6d4',
      ZONE_EXIT:'#64748b', ZONE_DWELL:'#f59e0b',
      BILLING_QUEUE_JOIN:'#f97316', BILLING_QUEUE_ABANDON:'#ef4444', REENTRY:'#a78bfa'
    }[e.event_type] || '#64748b';

    const avatarHtml = `<img class="visitor-avatar" src="${API_BASE}/images/${e.store_id}_${e.visitor_id}.jpg" onerror="this.onerror=null; this.src='${API_BASE}/images/default.jpg';" onclick="openImageModal(this.src)" />`;

    return `
      <div class="stream-event">
        <div class="se-dot" style="background:${dotColor}"></div>
        <span class="se-time">${time}</span>
        <span class="se-type ${e.event_type}">${e.event_type.replace(/_/g,' ')}</span>
        ${e.zone_id ? `<span class="se-visitor">@ ${formatZoneName(e.zone_id)}</span>` : ''}
        ${avatarHtml}
        <span class="se-visitor" style="margin-left:auto">${(e.visitor_id || '').slice(0,10)}</span>
      </div>
    `;
  }).join('');
}

function formatDateToTime(isoStr) {
  if (!isoStr) return '--:--:--';
  try {
    const date = new Date(isoStr);
    return date.toLocaleTimeString('en-IN', { hour12: false });
  } catch {
    return isoStr;
  }
}

function pushStreamEvent(type, visitorId, zoneId, ts) {
  const stream = document.getElementById('eventStream');
  const placeholder = stream.querySelector('.stream-placeholder');
  if (placeholder) placeholder.remove();

  const time = new Date(ts || Date.now()).toLocaleTimeString('en-IN', { hour12: false });
  const el = document.createElement('div');
  el.className = 'stream-event';

  const dotColor = {
    ENTRY:'#10b981', EXIT:'#ef4444', ZONE_ENTER:'#06b6d4',
    ZONE_EXIT:'#64748b', ZONE_DWELL:'#f59e0b',
    BILLING_QUEUE_JOIN:'#f97316', BILLING_QUEUE_ABANDON:'#ef4444', REENTRY:'#a78bfa'
  }[type] || '#64748b';

  const avatarHtml = `<img class="visitor-avatar" src="${API_BASE}/images/${currentStore}_${visitorId}.jpg" onerror="this.onerror=null; this.src='${API_BASE}/images/default.jpg';" onclick="openImageModal(this.src)" />`;

  el.innerHTML = `
    <div class="se-dot" style="background:${dotColor}"></div>
    <span class="se-time">${time}</span>
    <span class="se-type ${type}">${type.replace(/_/g,' ')}</span>
    ${zoneId ? `<span class="se-visitor">@ ${formatZoneName(zoneId)}</span>` : ''}
    ${avatarHtml}
    <span class="se-visitor" style="margin-left:auto">${(visitorId||'').slice(0,10)}</span>
  `;

  stream.insertBefore(el, stream.firstChild);

  // Keep max 50 items
  while (stream.children.length > 50) stream.removeChild(stream.lastChild);
}

function clearEventStream() {
  const stream = document.getElementById('eventStream');
  stream.innerHTML = '<div class="stream-placeholder">Switching store…</div>';
}

// ─── DEMO DATA (shown when API is offline) ───
function loadDemoData() {
  const demoMetrics = {
    unique_visitors: 87 + Math.floor(Math.random() * 10),
    conversion_rate: 0.23 + Math.random() * 0.05,
    queue_depth: Math.floor(Math.random() * 8),
    abandonment_rate: 0.08 + Math.random() * 0.04,
  };
  updateKPIs(demoMetrics);
  pushMetricsHistory(demoMetrics);
  updateChart();

  // Simulate event stream
  const types = ['ENTRY','ZONE_ENTER','ZONE_DWELL','BILLING_QUEUE_JOIN','EXIT','ZONE_EXIT','REENTRY'];
  const zones = ['SKINCARE','LIPSTICK','MOISTURISER','BILLING_ZONE','FOH'];
  const randomType = types[Math.floor(Math.random() * types.length)];
  const randomZone = zones[Math.floor(Math.random() * zones.length)];
  pushStreamEvent(randomType, `VIS_${Math.floor(Math.random()*999).toString().padStart(3,'0')}`, randomZone, new Date().toISOString());

  setApiStatus('warn', 'Demo Mode');
}

function renderDemoFunnel() {
  const demoData = {
    date: new Date().toISOString().split('T')[0],
    stages: [
      { stage: 'Entry',         count: 87,  drop_off_pct: 0.0  },
      { stage: 'Zone Visit',    count: 64,  drop_off_pct: 26.4 },
      { stage: 'Billing Queue', count: 38,  drop_off_pct: 40.6 },
      { stage: 'Purchase',      count: 20,  drop_off_pct: 47.4 },
    ]
  };
  renderFunnel(demoData);
}

function renderDemoHeatmap() {
  const demoData = {
    zones: {
      'SKINCARE':    { visit_frequency: 64, avg_dwell_seconds: 95,  normalized_frequency: 100, normalized_dwell: 100 },
      'LIPSTICK':    { visit_frequency: 55, avg_dwell_seconds: 72,  normalized_frequency: 86,  normalized_dwell: 76  },
      'MOISTURISER': { visit_frequency: 47, avg_dwell_seconds: 81,  normalized_frequency: 73,  normalized_dwell: 85  },
      'FRAGRANCES':  { visit_frequency: 31, avg_dwell_seconds: 108, normalized_frequency: 48,  normalized_dwell: 100 },
      'HAIRCARE':    { visit_frequency: 22, avg_dwell_seconds: 54,  normalized_frequency: 34,  normalized_dwell: 57  },
      'NAIL_ART':    { visit_frequency: 12, avg_dwell_seconds: 38,  normalized_frequency: 19,  normalized_dwell: 40  },
      'BILLING_ZONE':{ visit_frequency: 38, avg_dwell_seconds: 240, normalized_frequency: 59,  normalized_dwell: 100 },
    }
  };
  renderHeatmap(demoData);
}

function renderDemoAnomalies() {
  const demoAnomalies = [
    {
      type: 'BILLING_QUEUE_SPIKE',
      severity: 'WARN',
      message: 'Billing queue is building up (6 people in line).',
      suggested_action: 'Open another billing counter to disperse the queue.'
    },
    {
      type: 'DEAD_ZONE',
      severity: 'INFO',
      message: "Zone 'NAIL_ART' has had zero visits in the last 45 minutes.",
      suggested_action: 'Ensure items in this zone are properly stocked and visible to traffic.'
    }
  ];
  renderAnomalies(demoAnomalies);
}

// ─── HELPERS ───
function formatZoneName(id) {
  return (id || '').replace(/_/g,' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

function formatDate(dateStr) {
  try {
    return new Date(dateStr).toLocaleDateString('en-IN', { weekday:'short', day:'numeric', month:'short', year:'numeric' });
  } catch { return dateStr; }
}

// ─── Initial demo render while connecting ───
window.addEventListener('load', () => {
  // Immediately show demo data on first render for wow factor
  renderDemoFunnel();
  renderDemoHeatmap();
  renderDemoAnomalies();
  loadDemoData();

  // Simulate some initial events
  const demoEvents = [
    ['ENTRY', 'VIS_042', null],
    ['ZONE_ENTER', 'VIS_042', 'SKINCARE'],
    ['ZONE_DWELL', 'VIS_039', 'LIPSTICK'],
    ['BILLING_QUEUE_JOIN', 'VIS_037', null],
    ['ZONE_EXIT', 'VIS_036', 'MOISTURISER'],
    ['EXIT', 'VIS_033', null],
  ];
  demoEvents.forEach(([type, vis, zone], i) => {
    setTimeout(() => pushStreamEvent(type, vis, zone, new Date(Date.now() - (demoEvents.length - i) * 8000).toISOString()), i * 200);
  });
});

// ─── MODAL CONTROLS ───
function openImageModal(src) {
  const modal = document.getElementById('imageModal');
  const modalImg = document.getElementById('modalImage');
  modalImg.src = src;
  modal.classList.add('show');
}

function closeImageModal(event) {
  // If event is not provided or target is modal background or close button
  if (!event || event.target.id === 'imageModal' || event.target.className === 'image-modal-close') {
    const modal = document.getElementById('imageModal');
    modal.classList.remove('show');
  }
}

