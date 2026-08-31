// DOM Elements
const statusEl = document.querySelector('#status');
const value = id => document.querySelector(id) ? document.querySelector(id).value : '';

// State
let state = {
  activeTab: 'lookback',
  lookbackDays: 1,
  lookbackData: [],
  searchQuery: '',
  isLoading: false,
};

function money(v) {
  return v == null ? '—' : '₹' + Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function rsiBadge(rsi) {
  if (rsi == null) return '<span class="rsi-cell">—</span>';
  const val = Number(rsi).toFixed(2);
  if (rsi < 30) {
    return `<span class="rsi-cell oversold">📉 ${val}</span>`;
  } else if (rsi > 70) {
    return `<span class="rsi-cell overbought">📈 ${val}</span>`;
  }
  return `<span class="rsi-cell">${val}</span>`;
}

function renderSignalBadge(primaryType) {
  switch ((primaryType || '').toLowerCase()) {
    case 'oversold':
    case 'buy':
      return '<span class="badge badge-buy">BUY</span>';
    case 'overbought':
    case 'sell':
      return '<span class="badge badge-sell">SELL</span>';
    default:
      return '<span class="badge badge-neutral">NEUTRAL</span>';
  }
}

function renderReasons(reasons) {
  if (!reasons || !reasons.length) return '—';
  return reasons.map(r => {
    let cls = 'strategy';
    if (r.category === 'RSI_Oversold' || r.type === 'buy') cls = 'oversold';
    if (r.category === 'RSI_Overbought' || r.type === 'sell') cls = 'overbought';
    if (r.category === 'MA200') {
      if (r.type === 'touch') cls = 'ma200-touch';
      else if (r.type === 'cross_up') cls = 'ma200-cross-up';
      else if (r.type === 'cross_down') cls = 'ma200-cross-down';
      else cls = 'ma200-touch';
    }
    return `<span class="reason-pill ${cls}">${r.text}</span>`;
  }).join(' ');
}

function updateMetrics(totalScanned, items) {
  document.querySelector('#metric-scanned').textContent = totalScanned || 0;
  document.querySelector('#metric-flagged').textContent = items.length;

  let oversold = 0;
  let overbought = 0;
  let knoxCount = 0;
  let ma200Count = 0;

  items.forEach(item => {
    const reasons = item.reasons || [];
    if (item.primary_type === 'oversold' || reasons.some(r => r.category === 'RSI_Oversold')) oversold++;
    if (item.primary_type === 'overbought' || reasons.some(r => r.category === 'RSI_Overbought')) overbought++;
    if (reasons.some(r => r.strategy === 'RB_KnoxDiv' || (r.text && r.text.toLowerCase().includes('knoxville')))) knoxCount++;
    if (reasons.some(r => r.category === 'MA200' || (r.text && r.text.includes('200 MA')))) ma200Count++;
  });

  document.querySelector('#metric-oversold').textContent = oversold;
  document.querySelector('#metric-overbought').textContent = overbought;
  document.querySelector('#metric-signals').textContent = knoxCount;
  document.querySelector('#metric-ma200').textContent = ma200Count;
}


// -------------------------------------------------------------
// Lookback Screener Logic
// -------------------------------------------------------------
async function fetchLookbackSignals(forceRefresh = false) {
  if (state.isLoading) return;
  state.isLoading = true;
  statusEl.textContent = `Screening ${state.lookbackDays}D lookback…`;

  const params = new URLSearchParams({
    lookback_days: state.lookbackDays,
    rsi_length: 14,
  });

  const indexVal = value('#lookback-index');
  if (indexVal) params.set('index', indexVal);

  const activeStratPill = document.querySelector('#strategy-filter-group .strat-pill.active');
  const filterVal = (activeStratPill && activeStratPill.dataset.filter) || state.strategyFilter || '';
  if (filterVal) params.set('signal_filter', filterVal);

  if (forceRefresh) params.set('refresh', 'true');


  try {
    const res = await fetch('/screener/lookback?' + params);
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();
    state.lookbackData = data.items || [];
    updateMetrics(data.total_scanned, state.lookbackData);
    renderLookbackTable();
    statusEl.textContent = `Scanned ${data.total_scanned} tickers · ${data.total_flagged} flagged (${data.lookback_days}D)`;
  } catch (err) {
    statusEl.textContent = 'Error: ' + err.message;
    document.querySelector('#lookback-rows').innerHTML = `<tr><td colspan="8" class="empty-cell">Failed to load screener: ${err.message}</td></tr>`;
  } finally {
    state.isLoading = false;
  }
}

function filterAndSortItems(items) {
  let list = [...items];

  // Enhanced Search filter (searches symbol, reason text, index tags)
  const query = state.searchQuery.trim().toUpperCase();
  if (query) {
    list = list.filter(item => {
      const symMatch = item.symbol.toUpperCase().includes(query);
      const reasonMatch = item.reason_summary && item.reason_summary.toUpperCase().includes(query);
      const indexMatch = item.index_membership && item.index_membership.toUpperCase().includes(query);
      const typeMatch = item.primary_type && item.primary_type.toUpperCase().includes(query);
      return symMatch || reasonMatch || indexMatch || typeMatch;
    });
  }

  // Sort
  const sortBy = value('#lookback-sort') || 'recency';
  switch (sortBy) {
    case 'rsi_asc':
      return list.sort((a, b) => (a.rsi == null ? 999 : a.rsi) - (b.rsi == null ? 999 : b.rsi));
    case 'rsi_desc':
      return list.sort((a, b) => (b.rsi == null ? -1 : b.rsi) - (a.rsi == null ? -1 : a.rsi));
    case 'symbol':
      return list.sort((a, b) => a.symbol.localeCompare(b.symbol));
    case 'recency':
    default:
      return list.sort((a, b) => (b.signal_date || '').localeCompare(a.signal_date || ''));
  }
}


function renderLookbackTable() {
  const tbody = document.querySelector('#lookback-rows');
  const filtered = filterAndSortItems(state.lookbackData);

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">No matching stocks found. Adjust filters or search.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(item => {
    const smaDisplay = item.sma_200 != null 
      ? `<span class="sma-cell">${money(item.sma_200)}</span>`
      : '<span class="sma-cell">—</span>';

    return `<tr>
      <td>
        <a class="ticker-link" target="_blank" rel="noopener" href="https://in.tradingview.com/chart/?symbol=NSE:${encodeURIComponent(item.symbol)}">
          ${item.symbol} ↗
        </a>
      </td>
      <td class="price-cell">${money(item.current_price)}</td>
      <td>${smaDisplay}</td>
      <td>${rsiBadge(item.rsi)}</td>
      <td>${renderSignalBadge(item.primary_type)}</td>
      <td>${renderReasons(item.reasons)}</td>
      <td class="date-cell">${item.signal_date || '—'}</td>
      <td class="universe-cell">${(item.index_membership || '').replace(/\|/g, ', ')}</td>
    </tr>`;
  }).join('');
}


// -------------------------------------------------------------
// TradingView Watchlist Manager Card Controller
// -------------------------------------------------------------
const wmCardEl = document.querySelector('#card-watchlist-manager');
const wmStatusEl = document.querySelector('#modal-status');
const customListsTagsEl = document.querySelector('#custom-lists-tags');

function toggleWatchlistManager() {
  if (wmCardEl.style.display === 'none' || !wmCardEl.style.display) {
    wmCardEl.style.display = 'block';
    wmStatusEl.style.display = 'none';
    document.querySelector('#input-tv-url').focus();
    loadCustomWatchlists();
  } else {
    wmCardEl.style.display = 'none';
  }
}

function hideWatchlistManager() {
  wmCardEl.style.display = 'none';
}

async function loadCustomWatchlists() {
  try {
    const res = await fetch('/watchlist/list');
    if (!res.ok) return;
    const watchlists = await res.json();
    
    // Update active tags
    const keys = Object.keys(watchlists);
    if (!keys.length) {
      customListsTagsEl.innerHTML = '<span class="empty-custom">None imported yet</span>';
    } else {
      customListsTagsEl.innerHTML = keys.map(k => {
        const count = watchlists[k].length;
        return `<span class="custom-tag">
          ⭐ ${k} (${count})
          <span class="custom-tag-del" data-name="${k}" title="Delete Watchlist">&times;</span>
        </span>`;
      }).join('');

      // Wire delete clicks
      customListsTagsEl.querySelectorAll('.custom-tag-del').forEach(btn => {
        btn.onclick = async (e) => {
          e.stopPropagation();
          const name = btn.dataset.name;
          if (confirm(`Remove custom watchlist "${name}"?`)) {
            await fetch(`/watchlist/${encodeURIComponent(name)}`, { method: 'DELETE' });
            loadCustomWatchlists();
            fetchLookbackSignals(true);
          }
        };
      });
    }

    // Update Dropdowns
    updateUniverseDropdowns(watchlists);
  } catch (err) {
    console.error('Failed to load watchlists', err);
  }
}

function updateUniverseDropdowns(customLists) {
  const lookbackSel = document.querySelector('#lookback-index');
  const newsSel = document.querySelector('#news-universe-filter');
  const currentLookbackVal = lookbackSel ? lookbackSel.value : '';
  const currentNewsVal = newsSel ? newsSel.value : '';

  const baseOptions = `
    <option value="">All Universes</option>
    <option value="FNO">📊 F&O List (178)</option>
    <option value="Watchlist">⭐ My Watchlist (108)</option>
    <option value="Nifty50">NIFTY 50</option>
    <option value="IT">NIFTY IT</option>
    <option value="Bank">NIFTY BANK</option>
    <option value="Smallcap">NIFTY SMALLCAP</option>
  `;

  let customOptions = '';
  for (const [name, syms] of Object.entries(customLists)) {
    customOptions += `<option value="${name}">⭐ ${name} (${syms.length})</option>`;
  }

  if (lookbackSel) {
    lookbackSel.innerHTML = baseOptions + customOptions;
    if (currentLookbackVal) lookbackSel.value = currentLookbackVal;
  }

  if (newsSel) {
    newsSel.innerHTML = `<option value="FNO">📊 F&O Universe (178)</option><option value="Watchlist">⭐ My Watchlist</option><option value="Nifty50">NIFTY 50</option><option value="IT">NIFTY IT</option><option value="Bank">NIFTY BANK</option><option value="">All Tickers</option>` + customOptions;
    if (currentNewsVal) newsSel.value = currentNewsVal;
  }
}


async function handleImportSubmit() {
  const urlInput = document.querySelector('#input-tv-url');
  const nameInput = document.querySelector('#input-tv-name');
  const url = (urlInput.value || '').trim();
  const customName = (nameInput.value || '').trim();

  if (!url) {
    wmStatusEl.className = 'wm-status-box error';
    wmStatusEl.textContent = 'Please enter a valid TradingView watchlist URL.';
    wmStatusEl.style.display = 'block';
    return;
  }

  wmStatusEl.className = 'wm-status-box';
  wmStatusEl.textContent = 'Fetching and extracting tickers from TradingView…';
  wmStatusEl.style.display = 'block';
  const submitBtn = document.querySelector('#btn-modal-submit');
  submitBtn.disabled = true;

  try {
    const res = await fetch('/watchlist/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, custom_name: customName }),
    });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'Import failed.');
    }

    wmStatusEl.className = 'wm-status-box success';
    wmStatusEl.textContent = `Successfully imported "${data.name}" (${data.count} stocks)!`;
    
    urlInput.value = '';
    nameInput.value = '';
    await loadCustomWatchlists();
    document.querySelector('#lookback-index').value = data.name;

    fetchLookbackSignals(true);
  } catch (err) {
    wmStatusEl.className = 'wm-status-box error';
    wmStatusEl.textContent = err.message;
  } finally {
    submitBtn.disabled = false;
  }
}



// -------------------------------------------------------------
// Navigation Tab Switching (Lookback Screener & AI News Analyzer)
// -------------------------------------------------------------
function switchTab(targetTab) {
  state.activeTab = targetTab;
  ['#tab-lookback', '#tab-news'].forEach(sel => {
    const el = document.querySelector(sel);
    if (el) el.classList.remove('active');
  });
  ['#section-lookback', '#section-news'].forEach(sel => {
    const el = document.querySelector(sel);
    if (el) el.style.display = 'none';
  });

  const tabBtn = document.querySelector(`#tab-${targetTab}`);
  const secEl = document.querySelector(`#section-${targetTab}`);
  if (tabBtn) tabBtn.classList.add('active');
  if (secEl) secEl.style.display = 'block';

  if (targetTab === 'lookback') fetchLookbackSignals();
}

document.querySelector('#tab-lookback').onclick = () => switchTab('lookback');
document.querySelector('#tab-news').onclick = () => switchTab('news');


// -------------------------------------------------------------
// AI News Analyzer Controller
// -------------------------------------------------------------
state.newsData = null;

// -------------------------------------------------------------
// Claude AI API Key Manager Controller
// -------------------------------------------------------------
const claudeCardEl = document.querySelector('#card-claude-key');
const claudeStatusEl = document.querySelector('#claude-key-status');
const claudeKeyInput = document.querySelector('#input-claude-key');
const claudeBtnText = document.querySelector('#claude-key-btn-text');

function updateClaudeKeyBadge() {
  const key = localStorage.getItem('claude_api_key') || '';
  if (key) {
    if (claudeBtnText) claudeBtnText.textContent = 'Claude AI (Active 🟢)';
    if (claudeKeyInput) claudeKeyInput.value = key;
  } else {
    if (claudeBtnText) claudeBtnText.textContent = 'Claude AI Key';
  }
}
updateClaudeKeyBadge();

function toggleClaudeKeyManager() {
  if (claudeCardEl.style.display === 'none' || !claudeCardEl.style.display) {
    claudeCardEl.style.display = 'block';
    claudeStatusEl.style.display = 'none';
    const saved = localStorage.getItem('claude_api_key') || '';
    claudeKeyInput.value = saved;
    claudeKeyInput.focus();
  } else {
    claudeCardEl.style.display = 'none';
  }
}

document.querySelector('#btn-claude-key-modal').onclick = toggleClaudeKeyManager;
document.querySelector('#btn-close-claude-key').onclick = () => { claudeCardEl.style.display = 'none'; };

document.querySelector('#btn-save-claude-key').onclick = () => {
  const key = (claudeKeyInput.value || '').trim();
  if (!key) {
    claudeStatusEl.className = 'wm-status-box error';
    claudeStatusEl.textContent = 'Please enter a valid Anthropic API key starting with sk-ant-...';
    claudeStatusEl.style.display = 'block';
    return;
  }
  localStorage.setItem('claude_api_key', key);
  updateClaudeKeyBadge();
  claudeStatusEl.className = 'wm-status-box success';
  claudeStatusEl.textContent = '✅ Claude API Key saved successfully! Live Claude 3.5 Sonnet analysis active.';
  claudeStatusEl.style.display = 'block';
  setTimeout(() => { claudeCardEl.style.display = 'none'; }, 1500);
};

document.querySelector('#btn-clear-claude-key').onclick = () => {
  localStorage.removeItem('claude_api_key');
  claudeKeyInput.value = '';
  updateClaudeKeyBadge();
  claudeStatusEl.className = 'wm-status-box';
  claudeStatusEl.textContent = 'Claude API Key removed. Institutional NLP fallback engine active.';
  claudeStatusEl.style.display = 'block';
};

// -------------------------------------------------------------
// AI News Analyzer Controller (Deep Multi-Step Synthesis)
// -------------------------------------------------------------
state.newsData = null;

// Populate News Stock Dropdown based on Universe
function populateNewsStockSelect() {
  const select = document.querySelector('#news-stock-select');
  if (!select) return;
  const uni = document.querySelector('#news-universe-filter').value;
  
  const defaultList = [
    { s: 'TVSMOTOR', n: 'TVS Motor Company' },
    { s: 'RELIANCE', n: 'Reliance Industries' },
    { s: 'TRENT', n: 'Trent Ltd' },
    { s: 'TATAMOTORS', n: 'Tata Motors' },
    { s: 'HDFCBANK', n: 'HDFC Bank' },
    { s: 'INFY', n: 'Infosys' },
    { s: 'IDFCFIRSTB', n: 'IDFC First Bank' },
    { s: 'KEI', n: 'KEI Industries' },
    { s: 'BAJAJ-AUTO', n: 'Bajaj Auto' },
    { s: 'BHARTIARTL', n: 'Bharti Airtel' },
    { s: 'IRCON', n: 'Ircon International' },
    { s: 'RVNL', n: 'Rail Vikas Nigam' },
    { s: 'COFORGE', n: 'Coforge Ltd' },
    { s: 'OFSS', n: 'Oracle Financial' },
    { s: 'SOLARINDS', n: 'Solar Industries' },
    { s: 'DIVISLAB', n: 'Divis Laboratories' },
  ];

  select.innerHTML = defaultList.map(item => `<option value="${item.s}">${item.s} (${item.n})</option>`).join('');
}
populateNewsStockSelect();

document.querySelector('#news-universe-filter').onchange = populateNewsStockSelect;

// News Quick Chips Listeners
document.querySelectorAll('#news-quick-chips .pill').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('#news-quick-chips .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const sym = btn.dataset.sym;
    document.querySelector('#news-custom-input').value = sym;
    document.querySelector('#news-stock-select').value = sym;
    analyzeStockNews(sym);
  };
});

document.querySelector('#news-stock-select').onchange = (e) => {
  const sym = e.target.value;
  document.querySelector('#news-custom-input').value = sym;
  document.querySelectorAll('#news-quick-chips .pill').forEach(b => b.classList.toggle('active', b.dataset.sym === sym));
};

document.querySelector('#btn-trigger-sample-news').onclick = () => {
  analyzeStockNews('TVSMOTOR');
};

document.querySelector('#btn-run-news').onclick = () => {
  const custom = (document.querySelector('#news-custom-input').value || '').trim().toUpperCase();
  const selected = document.querySelector('#news-stock-select').value;
  const sym = custom || selected || 'TVSMOTOR';
  analyzeStockNews(sym);
};

const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function analyzeStockNews(symbol) {
  const btn = document.querySelector('#btn-run-news');
  const placeholderEl = document.querySelector('#news-placeholder');
  const loadingCardEl = document.querySelector('#news-loading-card');
  const contentCardEl = document.querySelector('#news-content-card');

  btn.disabled = true;
  btn.innerHTML = '<span>⏳ Claude AI Analyzing…</span>';
  
  // Show Loading Progress State
  if (placeholderEl) placeholderEl.style.display = 'none';
  if (contentCardEl) contentCardEl.style.display = 'none';
  if (loadingCardEl) loadingCardEl.style.display = 'flex';

  const updateStep = (stepNum, title, sub) => {
    document.querySelector('#loading-stage-title').textContent = title;
    document.querySelector('#loading-stage-sub').textContent = sub;
    for (let i = 1; i <= 4; i++) {
      const stepEl = document.querySelector(`#step-${i}`);
      if (!stepEl) continue;
      if (i < stepNum) {
        stepEl.className = 'loading-step done';
      } else if (i === stepNum) {
        stepEl.className = 'loading-step active';
      } else {
        stepEl.className = 'loading-step';
      }
    }
  };

  updateStep(1, `Analyzing Live Information for ${symbol}…`, `Searching Google News & Yahoo Finance feeds for recent disclosures.`);
  statusEl.textContent = `[1/4] Scraping latest market news for ${symbol}…`;

  try {
    const apiKey = localStorage.getItem('claude_api_key') || null;

    // Trigger API request in parallel with progressive visual steps
    const fetchPromise = fetch('/news/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: symbol, days: 7, api_key: apiKey }),
    });

    await delay(700);
    updateStep(2, `Parsing Financial Catalysts & Filings…`, `Analyzing quarterly disclosures, institutional analyst notes & regulatory updates.`);
    statusEl.textContent = `[2/4] Extracting growth catalysts and downside risks for ${symbol}…`;

    await delay(800);
    updateStep(3, `Running Claude AI Sentiment Modeling…`, `Evaluating market trajectory, institutional flows & earnings commentary.`);
    statusEl.textContent = `[3/4] Running AI sentiment reasoning engine…`;

    await delay(700);
    updateStep(4, `Cross-Referencing Technical Momentum…`, `Synthesizing RSI momentum & 200 SMA support zones.`);
    statusEl.textContent = `[4/4] Finalizing equity research report…`;

    const res = await fetchPromise;
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail || `Server returned status ${res.status}`);
    }

    const data = await res.json();
    state.newsData = data;
    
    await delay(400);
    if (loadingCardEl) loadingCardEl.style.display = 'none';
    renderNewsAnalysis(data);
    statusEl.textContent = `AI analysis complete for ${data.symbol}: ${data.sentiment} (${data.sentiment_score}/100) via ${data.analysis_engine || 'Claude AI'}.`;
  } catch (err) {
    if (loadingCardEl) loadingCardEl.style.display = 'none';
    if (placeholderEl) placeholderEl.style.display = 'flex';
    statusEl.textContent = 'News analysis failed: ' + err.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>✨ Analyze News with AI</span>';
  }
}

function renderNewsAnalysis(data) {
  const placeholderEl = document.querySelector('#news-placeholder');
  const loadingCardEl = document.querySelector('#news-loading-card');
  const card = document.querySelector('#news-content-card');

  if (placeholderEl) placeholderEl.style.display = 'none';
  if (loadingCardEl) loadingCardEl.style.display = 'none';
  if (card) card.style.display = 'flex';


  // Hero section
  document.querySelector('#ai-stock-ticker').textContent = data.symbol;
  document.querySelector('#ai-company-name').textContent = data.company_name;
  document.querySelector('#ai-exec-summary').textContent = data.executive_summary;

  // Sentiment verdict
  const sentBadge = document.querySelector('#ai-sentiment-badge');
  const sentText = document.querySelector('#ai-sentiment-text');
  const sentLower = data.sentiment.toLowerCase();
  sentBadge.className = `sentiment-badge-pill ${sentLower}`;
  
  let icon = '🟢';
  if (sentLower === 'bearish') icon = '🔴';
  else if (sentLower === 'neutral') icon = '🟡';
  sentBadge.querySelector('.sentiment-icon').textContent = icon;
  sentText.textContent = data.sentiment;

  // Score
  document.querySelector('#ai-score-number').textContent = `${data.sentiment_score}%`;
  document.querySelector('#ai-score-fill').style.width = `${data.sentiment_score}%`;

  // Catalysts
  const catList = document.querySelector('#ai-catalysts-list');
  catList.innerHTML = (data.catalysts || []).map(c => `<li>${c}</li>`).join('');

  // Risks
  const riskList = document.querySelector('#ai-risks-list');
  riskList.innerHTML = (data.risks || []).map(r => `<li>${r}</li>`).join('');

  // Technical correlation
  document.querySelector('#ai-technical-correlation').textContent = data.technical_correlation;

  // Articles Feed
  const countBadge = document.querySelector('#ai-articles-count');
  countBadge.textContent = `${(data.articles || []).length} articles`;

  const articlesGrid = document.querySelector('#news-articles-grid');
  if (!data.articles || !data.articles.length) {
    articlesGrid.innerHTML = `<div class="empty-cell" style="grid-column: 1 / -1;">No breaking news articles found for ${data.symbol} in recent days.</div>`;
    return;
  }

  articlesGrid.innerHTML = data.articles.map(art => `
    <div class="news-article-card">
      <div class="article-top">
        <div class="article-meta-row">
          <span class="article-publisher">${art.publisher}</span>
          <span class="article-date">${art.published_at.split(' ').slice(0, 4).join(' ')}</span>
        </div>
        <h5 class="article-title">${art.title}</h5>
        <p class="article-snippet">${art.summary || 'Click below to read the complete financial coverage.'}</p>
      </div>
      <a href="${art.link}" target="_blank" rel="noopener noreferrer" class="article-link">
        <span>Read Full Story</span>
        <span>↗</span>
      </a>
    </div>
  `).join('');
}



// -------------------------------------------------------------
// Global Keyboard Shortcuts & Event Listeners
// -------------------------------------------------------------
// Lookback Period Buttons
document.querySelectorAll('#lookback-group .pill').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('#lookback-group .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.lookbackDays = parseInt(btn.dataset.days, 10) || 1;
    fetchLookbackSignals();
  };
});

// Strategy Filter Pills
document.querySelectorAll('#strategy-filter-group .strat-pill').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('#strategy-filter-group .strat-pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const filter = btn.dataset.filter || '';
    state.strategyFilter = filter;
    fetchLookbackSignals();
  };
});

// Global Keyboard Shortcuts
window.addEventListener('keydown', (e) => {
  const activeTag = (document.activeElement && document.activeElement.tagName) || '';
  const isInputActive = activeTag === 'INPUT' || activeTag === 'SELECT' || activeTag === 'TEXTAREA';

  // Press "/" to focus search
  if (e.key === '/' && !isInputActive) {
    e.preventDefault();
    const searchInput = state.activeTab === 'tester'
      ? document.querySelector('#tester-search')
      : document.querySelector('#symbol-search');
    if (searchInput) {
      searchInput.focus();
      searchInput.select();
    }
    return;
  }

  // Press Escape to blur or close modal
  if (e.key === 'Escape') {
    if (isInputActive) {
      document.activeElement.blur();
    }
    hideWatchlistManager();
    return;
  }

  // Numbers 1-4 for quick lookback switching
  if (!isInputActive && state.activeTab === 'lookback') {
    const keyMap = { '1': 1, '2': 3, '3': 7, '4': 14 };
    if (keyMap[e.key]) {
      const targetDays = keyMap[e.key];
      const targetBtn = document.querySelector(`#lookback-group .pill[data-days="${targetDays}"]`);
      if (targetBtn) targetBtn.click();
    }
  }
});

// -------------------------------------------------------------
// Watchlist-Scoped Auto-Complete & Modern Search Controller
// -------------------------------------------------------------
state.allSymbols = [];

function getFilteredSymbols(universeFilter) {
  if (!state.allSymbols || !state.allSymbols.length) return [];
  if (!universeFilter) return state.allSymbols;
  return state.allSymbols.filter(item => item.membership && item.membership.includes(universeFilter));
}

function updateLookbackSearchScope() {
  const uni = document.querySelector('#lookback-index').value;
  const filtered = getFilteredSymbols(uni);
  const badge = document.querySelector('#search-scope-badge');
  const input = document.querySelector('#symbol-search');
  if (badge) {
    badge.textContent = uni ? `${uni} · ${filtered.length}` : `All · ${filtered.length}`;
  }
  if (input) {
    input.placeholder = uni ? `Search ${uni} (${filtered.length} stocks)...` : `Search all stocks (${filtered.length})...`;
  }
}

function updateTesterSearchScope() {
  const uni = document.querySelector('#tester-universe').value;
  const filtered = getFilteredSymbols(uni);
  const input = document.querySelector('#tester-symbol-input');
  if (input) {
    input.placeholder = uni ? `Individual ${uni} stock (${filtered.length})...` : `Individual stock (e.g. TVSMOTOR)...`;
  }
}

function updateNewsSearchScope() {
  const uni = document.querySelector('#news-universe-filter').value;
  const filtered = getFilteredSymbols(uni);
  const select = document.querySelector('#news-stock-select');
  if (select && filtered.length) {
    select.innerHTML = filtered.map(item => `<option value="${item.symbol}">${item.symbol} (${item.membership.join(', ')})</option>`).join('');
  }

  const input = document.querySelector('#news-custom-input');
  if (input) {
    input.placeholder = uni ? `Enter ${uni} ticker (${filtered.length} stocks)...` : `Or enter ticker (e.g. TVSMOTOR)...`;
  }
}

// Universal Custom Floating Autocomplete Engine
function attachModernAutocomplete(inputEl, getUniverseFn, onSelectFn) {
  if (!inputEl) return;
  const wrapper = inputEl.closest('.search-wrapper') || inputEl.closest('.stock-input-wrapper') || inputEl.parentElement;
  
  let dropdown = wrapper.querySelector('.stock-search-dropdown');
  if (!dropdown) {
    dropdown = document.createElement('div');
    dropdown.className = 'stock-search-dropdown';
    dropdown.style.display = 'none';
    wrapper.appendChild(dropdown);
  }

  let activeIndex = -1;

  function renderList(query = '') {
    const cleanQuery = query.trim().toUpperCase();
    const universe = getUniverseFn();
    const filtered = getFilteredSymbols(universe);
    
    let matches = filtered;
    if (cleanQuery) {
      matches = filtered.filter(item => 
        item.symbol.toUpperCase().includes(cleanQuery) || 
        (item.membership && item.membership.some(m => m.toUpperCase().includes(cleanQuery)))
      );
    }

    const displayMatches = matches.slice(0, 10);
    if (!displayMatches.length) {
      dropdown.innerHTML = `<div class="ss-empty">No stocks found in ${universe || 'watchlist'}</div>`;
      dropdown.style.display = 'flex';
      return;
    }

    dropdown.innerHTML = displayMatches.map((item, idx) => `
      <div class="stock-search-item" data-sym="${item.symbol}" data-idx="${idx}">
        <div class="ss-left">
          <span class="ss-sym">${item.symbol}</span>
        </div>
        <div class="ss-right">
          ${item.membership.slice(0, 2).map(m => `<span class="ss-tag">${m}</span>`).join('')}
        </div>
      </div>
    `).join('');

    dropdown.style.display = 'flex';
    activeIndex = -1;

    dropdown.querySelectorAll('.stock-search-item').forEach(itemEl => {
      itemEl.onmousedown = (e) => {
        e.preventDefault();
        const sym = itemEl.dataset.sym;
        inputEl.value = sym;
        dropdown.style.display = 'none';
        onSelectFn(sym);
      };
    });
  }

  inputEl.addEventListener('focus', () => {
    renderList(inputEl.value);
  });

  inputEl.addEventListener('input', () => {
    renderList(inputEl.value);
  });

  inputEl.addEventListener('blur', () => {
    setTimeout(() => { dropdown.style.display = 'none'; }, 200);
  });

  inputEl.addEventListener('keydown', (e) => {
    const items = dropdown.querySelectorAll('.stock-search-item');
    if (!items.length || dropdown.style.display === 'none') return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
      items.forEach((it, i) => it.classList.toggle('active', i === activeIndex));
      if (items[activeIndex]) items[activeIndex].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      items.forEach((it, i) => it.classList.toggle('active', i === activeIndex));
      if (items[activeIndex]) items[activeIndex].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      const selectedSym = items[activeIndex].dataset.sym;
      inputEl.value = selectedSym;
      dropdown.style.display = 'none';
      onSelectFn(selectedSym);
    } else if (e.key === 'Escape') {
      dropdown.style.display = 'none';
    }
  });
}

async function loadUniverseSymbols() {
  try {
    const res = await fetch('/universe/symbols');
    if (!res.ok) return;
    const symbols = await res.json();
    state.allSymbols = symbols;

    updateLookbackSearchScope();
    updateTesterSearchScope();
    updateNewsSearchScope();

    // Attach modern floating autocomplete to all stock inputs
    attachModernAutocomplete(
      document.querySelector('#symbol-search'),
      () => document.querySelector('#lookback-index').value,
      async (sym) => {
        state.searchQuery = sym;
        const existing = state.lookbackData.find(item => item.symbol.toUpperCase() === sym.toUpperCase());
        if (!existing) {
          statusEl.textContent = `Searching live data for ${sym}…`;
          try {
            const res = await fetch(`/screener/lookback?symbol=${encodeURIComponent(sym)}&lookback_days=${state.lookbackDays}&rsi_length=14&include_neutral=true`);
            if (res.ok) {
              const data = await res.json();
              if (data.items && data.items.length) {
                state.lookbackData = [...data.items, ...state.lookbackData];
                renderLookbackTable();
                statusEl.textContent = `Loaded ${sym} status successfully.`;
              }
            }
          } catch (err) {
            console.error('Symbol search fetch error', err);
          }
        }
        renderLookbackTable();
      }
    );

    attachModernAutocomplete(
      document.querySelector('#news-custom-input'),
      () => document.querySelector('#news-universe-filter').value,
      (sym) => {
        analyzeStockNews(sym);
      }
    );

  } catch (err) {
    console.error('Failed to load universe symbols', err);
  }
}

// Search input for Lookback Screener
const symbolSearchEl = document.querySelector('#symbol-search');
const clearSearchBtn = document.querySelector('#btn-clear-search');

symbolSearchEl.oninput = (e) => {
  state.searchQuery = e.target.value;
  if (clearSearchBtn) {
    clearSearchBtn.style.display = state.searchQuery ? 'flex' : 'none';
  }
  renderLookbackTable();
};

if (clearSearchBtn) {
  clearSearchBtn.onclick = () => {
    symbolSearchEl.value = '';
    state.searchQuery = '';
    clearSearchBtn.style.display = 'none';
    symbolSearchEl.focus();
    renderLookbackTable();
  };
}

symbolSearchEl.onkeydown = async (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    const query = (symbolSearchEl.value || '').trim().toUpperCase();
    if (!query) return;

    const existing = state.lookbackData.find(item => item.symbol.toUpperCase() === query);
    if (!existing) {
      statusEl.textContent = `Searching live data for ${query}…`;
      try {
        const res = await fetch(`/screener/lookback?symbol=${encodeURIComponent(query)}&lookback_days=${state.lookbackDays}&rsi_length=14&include_neutral=true`);
        if (res.ok) {
          const data = await res.json();
          if (data.items && data.items.length) {
            state.lookbackData = [...data.items, ...state.lookbackData];
            renderLookbackTable();
            statusEl.textContent = `Loaded ${query} status successfully.`;
          }
        }
      } catch (err) {
        console.error('Direct symbol search error:', err);
      }
    }
  }
};

// AI News Analyzer Input on Enter
const newsInputEl = document.querySelector('#news-custom-input');
if (newsInputEl) {
  newsInputEl.onkeydown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const sym = (newsInputEl.value || '').trim().toUpperCase();
      if (sym) analyzeStockNews(sym);
    }
  };
}

// Universe Change Listeners
document.querySelector('#lookback-index').onchange = () => {
  updateLookbackSearchScope();
  fetchLookbackSignals();
};

document.querySelector('#news-universe-filter').onchange = () => {
  updateNewsSearchScope();
};

// Watchlist Manager Card Toggle & Submit Handlers
document.querySelector('#btn-import-modal').onclick = toggleWatchlistManager;
document.querySelector('#btn-close-wm').onclick = hideWatchlistManager;
document.querySelector('#btn-modal-submit').onclick = handleImportSubmit;

// Lookback Selectors & Buttons
document.querySelector('#lookback-sort').onchange = () => renderLookbackTable();
document.querySelector('#lookback-refresh').onclick = () => fetchLookbackSignals(false);
document.querySelector('#lookback-rescan').onclick = () => fetchLookbackSignals(true);

// Initial Load
loadUniverseSymbols();
loadCustomWatchlists();
fetchLookbackSignals();












