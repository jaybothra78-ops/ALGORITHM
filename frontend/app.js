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
  const scannerSel = document.querySelector('#index');
  const currentLookbackVal = lookbackSel.value;
  const currentScannerVal = scannerSel.value;

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

  lookbackSel.innerHTML = baseOptions + customOptions;
  scannerSel.innerHTML = baseOptions + customOptions;

  if (currentLookbackVal) lookbackSel.value = currentLookbackVal;
  if (currentScannerVal) scannerSel.value = currentScannerVal;
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
// Daily Confirmed Scanner Logic
// -------------------------------------------------------------
function rsiDisplay(rsi, rsiMa, type) {
  if (rsi == null) return '—';
  const cls = type === 'buy' ? 'oversold' : (type === 'sell' ? 'overbought' : '');
  const rsiText = Number(rsi).toFixed(2);
  const maText = rsiMa != null ? Number(rsiMa).toFixed(2) : '—';
  return `<span class="rsi-cell ${cls}">RSI: ${rsiText} | MA: ${maText}</span>`;
}

async function refreshScanner() {
  const params = new URLSearchParams();
  if (value('#strategy')) params.set('strategy', value('#strategy'));
  if (value('#index')) params.set('index', value('#index'));
  if (value('#type')) params.set('signal_type', value('#type'));

  statusEl.textContent = 'Loading confirmed signals…';
  try {
    const response = await fetch('/signals/today?' + params);
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    const signals = await response.json();
    const tbody = document.querySelector('#rows');

    if (!signals.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="empty-cell">No confirmed signals found for today. Click "Run Daily Scan".</td></tr>`;
      statusEl.textContent = '0 confirmed signals today.';
      return;
    }

    tbody.innerHTML = signals.map(s => {
      const typeBadge = s.signal_type === 'buy' 
        ? '<span class="badge badge-buy">BUY</span>' 
        : '<span class="badge badge-sell">SELL</span>';

      return `<tr>
        <td>
          <a class="ticker-link" target="_blank" rel="noopener" href="https://in.tradingview.com/chart/?symbol=NSE:${encodeURIComponent(s.symbol)}">
            ${s.symbol} ↗
          </a>
        </td>
        <td><strong>${s.strategy || 'RSI'}</strong></td>
        <td>${typeBadge}</td>
        <td>${rsiDisplay(s.rsi_value, s.rsi_ma_value, s.signal_type)}</td>
        <td class="price-cell">${money(s.entry_price)}</td>
        <td class="price-cell">${money(s.signal_candle_low)}</td>
        <td class="price-cell">${money(s.stop_loss)}</td>
        <td class="date-cell">${s.signal_date}</td>
        <td class="universe-cell">${(s.index_membership || '').replace(/\|/g, ', ')}</td>
      </tr>`;
    }).join('');

    statusEl.textContent = `${signals.length} confirmed signal(s) active today.`;
  } catch (err) {
    statusEl.textContent = 'Error: ' + err.message;
  }
}

// -------------------------------------------------------------
// Navigation Tab Switching
// -------------------------------------------------------------
function switchTab(targetTab) {
  state.activeTab = targetTab;
  ['#tab-lookback', '#tab-scanner', '#tab-tester', '#tab-news'].forEach(sel => {
    const el = document.querySelector(sel);
    if (el) el.classList.remove('active');
  });
  ['#section-lookback', '#section-scanner', '#section-tester', '#section-news'].forEach(sel => {
    const el = document.querySelector(sel);
    if (el) el.style.display = 'none';
  });

  const tabBtn = document.querySelector(`#tab-${targetTab}`);
  const secEl = document.querySelector(`#section-${targetTab}`);
  if (tabBtn) tabBtn.classList.add('active');
  if (secEl) secEl.style.display = 'block';

  if (targetTab === 'lookback') fetchLookbackSignals();
  else if (targetTab === 'scanner') refreshScanner();
}

document.querySelector('#tab-lookback').onclick = () => switchTab('lookback');
document.querySelector('#tab-scanner').onclick = () => switchTab('scanner');
document.querySelector('#tab-tester').onclick = () => switchTab('tester');
document.querySelector('#tab-news').onclick = () => switchTab('news');

// -------------------------------------------------------------
// AI News Analyzer Controller
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

async function analyzeStockNews(symbol) {
  const btn = document.querySelector('#btn-run-news');
  btn.disabled = true;
  btn.innerHTML = '<span>⏳ Claude AI Analyzing…</span>';
  statusEl.textContent = `Fetching live news & analyzing market sentiment for ${symbol}…`;

  try {
    const res = await fetch('/news/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: symbol, days: 7 }),
    });

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail || `Server returned status ${res.status}`);
    }

    const data = await res.json();
    state.newsData = data;
    renderNewsAnalysis(data);
    statusEl.textContent = `AI analysis complete for ${data.symbol}: ${data.sentiment} (${data.sentiment_score}/100)`;
  } catch (err) {
    statusEl.textContent = 'News analysis failed: ' + err.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>✨ Analyze News with AI</span>';
  }
}

function renderNewsAnalysis(data) {
  document.querySelector('#news-placeholder').style.display = 'none';
  const card = document.querySelector('#news-content-card');
  card.style.display = 'flex';

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
// Strategy Tester Controller
// -------------------------------------------------------------
state.testerData = { summary: null, trades: [] };
state.testerOutcomeFilter = 'ALL';
state.testerSearchQuery = '';

// Date Range Calculation Helpers
function setTesterDateRange(months) {
  const toDate = new Date();
  const toStr = toDate.toISOString().split('T')[0];
  document.querySelector('#tester-to-date').value = toStr;

  if (months === 'all') {
    document.querySelector('#tester-from-date').value = '';
    return;
  }

  const fromDate = new Date();
  const m = parseInt(months, 10) || 3;
  fromDate.setMonth(fromDate.getMonth() - m);
  const fromStr = fromDate.toISOString().split('T')[0];
  document.querySelector('#tester-from-date').value = fromStr;
}

// Initialize default date range: 3 Months (Recent 2026)
setTesterDateRange(3);

// Date Range Pills Handler
document.querySelectorAll('#tester-range-group .pill').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('#tester-range-group .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const range = btn.dataset.range || '3m';
    if (range === '1m') setTesterDateRange(1);
    else if (range === '3m') setTesterDateRange(3);
    else if (range === '6m') setTesterDateRange(6);
    else if (range === '1y') setTesterDateRange(12);
    else if (range === 'all') setTesterDateRange('all');
  };
});

// Manual Date Picker Listeners
['#tester-from-date', '#tester-to-date'].forEach(sel => {
  document.querySelector(sel).onchange = () => {
    document.querySelectorAll('#tester-range-group .pill').forEach(b => b.classList.remove('active'));
  };
});

// Target % Pills & Custom Input
document.querySelectorAll('#target-pct-group .pill').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('#target-pct-group .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelector('#tester-target-input').value = btn.dataset.pct;
  };
});

document.querySelector('#tester-target-input').oninput = (e) => {
  const val = e.target.value;
  document.querySelectorAll('#target-pct-group .pill').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.pct === val);
  });
};

// Stop Loss % Pills & Custom Input
document.querySelectorAll('#sl-pct-group .pill').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('#sl-pct-group .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelector('#tester-sl-input').value = btn.dataset.pct;
  };
});

document.querySelector('#tester-sl-input').oninput = (e) => {
  const val = e.target.value;
  document.querySelectorAll('#sl-pct-group .pill').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.pct === val);
  });
};

// Holding Days Pills
document.querySelectorAll('#hold-days-group .pill').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('#hold-days-group .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  };
});

// Trade Outcome Filter Pills
document.querySelectorAll('#trade-outcome-filter .pill').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('#trade-outcome-filter .pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.testerOutcomeFilter = btn.dataset.outcome || 'ALL';
    renderTesterTradeTable();
  };
});

// Tester Search Input
document.querySelector('#tester-search').oninput = (e) => {
  state.testerSearchQuery = e.target.value.trim().toUpperCase();
  renderTesterTradeTable();
};

// Run Strategy Test Button Handler
document.querySelector('#btn-run-tester').onclick = async () => {
  const btn = document.querySelector('#btn-run-tester');
  btn.disabled = true;
  btn.innerHTML = '<span>⏳ Testing…</span>';
  statusEl.textContent = 'Simulating strategy performance across historical market data…';

  const activeHoldBtn = document.querySelector('#hold-days-group .pill.active');
  const maxHoldDays = activeHoldBtn ? parseInt(activeHoldBtn.dataset.days, 10) : 10;
  const targetPct = parseFloat(document.querySelector('#tester-target-input').value) || 5.0;
  const slPct = parseFloat(document.querySelector('#tester-sl-input').value) || 2.0;
  const strategy = value('#tester-strategy') || 'RSI';
  const index = value('#tester-universe') || null;
  const singleSymbol = (document.querySelector('#tester-symbol-input').value || '').trim().toUpperCase();
  const fromDate = document.querySelector('#tester-from-date').value || null;
  const toDate = document.querySelector('#tester-to-date').value || null;

  const payload = {
    strategy,
    index,
    symbol: singleSymbol || null,
    target_pct: targetPct,
    stop_loss_pct: slPct,
    max_holding_days: maxHoldDays,
    start_date: fromDate,
    end_date: toDate,
  };

  try {
    const res = await fetch('/backtest/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail || `Server returned status ${res.status}`);
    }

    const data = await res.json();
    state.testerData = data;
    renderTesterKPIs(data.summary, data.execution_time_ms);
    renderTesterTradeTable();
    const symLabel = singleSymbol ? `${singleSymbol} ` : '';
    statusEl.textContent = `Simulation completed in ${data.execution_time_ms}ms · ${symLabel}${data.summary.total_trades} trades simulated.`;
  } catch (err) {
    statusEl.textContent = 'Test failed: ' + err.message;
    document.querySelector('#tester-rows').innerHTML = `<tr><td colspan="12" class="empty-cell">Test failed: ${err.message}</td></tr>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>🚀 Run Test</span>';
  }
};


function renderTesterKPIs(summary, execMs) {
  if (!summary) return;

  // Win Rate
  document.querySelector('#kpi-win-rate').textContent = `${summary.win_rate_pct}%`;
  document.querySelector('#kpi-wins-losses').textContent = `${summary.winning_trades} wins / ${summary.losing_trades} losses`;

  // Net Return
  const netEl = document.querySelector('#kpi-net-return');
  const isNetPos = summary.net_return_pct >= 0;
  netEl.textContent = `${isNetPos ? '+' : ''}${summary.net_return_pct}%`;
  netEl.className = `kpi-val ${isNetPos ? 'text-green' : 'text-red'}`;
  document.querySelector('#kpi-total-trades').textContent = `${summary.total_trades} total trades`;

  // Profit Factor
  document.querySelector('#kpi-profit-factor').textContent = summary.profit_factor;

  // Max DD
  document.querySelector('#kpi-max-dd').textContent = `-${summary.max_drawdown_pct}%`;

  // Avg Win / Loss
  document.querySelector('#kpi-avg-win-loss').innerHTML = `<span class="text-green">+${summary.avg_win_pct}%</span> / <span class="text-red">${summary.avg_loss_pct}%</span>`;
  document.querySelector('#kpi-avg-pnl').textContent = `Avg trade: ${summary.avg_trade_pnl_pct >= 0 ? '+' : ''}${summary.avg_trade_pnl_pct}%`;

  // Avg Holding
  document.querySelector('#kpi-avg-hold').textContent = `${summary.avg_holding_days}D`;
  document.querySelector('#kpi-exec-time').textContent = `Executed in ${execMs}ms`;
}

function renderTesterTradeTable() {
  const tbody = document.querySelector('#tester-rows');
  const allTrades = (state.testerData && state.testerData.trades) || [];

  let filtered = [...allTrades];

  // Outcome filter
  if (state.testerOutcomeFilter !== 'ALL') {
    filtered = filtered.filter(t => t.outcome === state.testerOutcomeFilter);
  }

  // Search filter
  if (state.testerSearchQuery) {
    filtered = filtered.filter(t => t.symbol.toUpperCase().includes(state.testerSearchQuery));
  }

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="12" class="empty-cell">No trades match the current filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(t => {
    const isWin = t.outcome === 'WIN';
    const pnlCls = isWin ? 'win' : 'loss';
    const outcomeBadge = isWin ? `<span class="badge-win">🟢 WIN</span>` : `<span class="badge-loss">🔴 LOSS</span>`;

    let exitReasonCls = 'time';
    if (t.exit_reason === 'Target Hit') exitReasonCls = 'target';
    else if (t.exit_reason === 'Stop Loss Hit') exitReasonCls = 'stop';

    return `<tr>
      <td>
        <a class="ticker-link" target="_blank" rel="noopener" href="https://in.tradingview.com/chart/?symbol=NSE:${encodeURIComponent(t.symbol)}">
          ${t.symbol} ↗
        </a>
      </td>
      <td><span class="reason-pill strategy">${t.strategy}</span></td>
      <td>${renderSignalBadge(t.signal_type)}</td>
      <td class="date-cell">${t.entry_date}</td>
      <td class="price-cell">${money(t.entry_price)}</td>
      <td class="sma-cell">
        <span class="text-green" title="Target Price">${t.target_price ? '🎯 ' + money(t.target_price) : '—'}</span><br>
        <span class="text-red" title="Stop Loss Price">${t.stop_loss_price ? '🛑 ' + money(t.stop_loss_price) : '—'}</span>
      </td>
      <td class="date-cell">${t.exit_date}</td>
      <td class="price-cell">${money(t.exit_price)}</td>
      <td><span class="exit-tag ${exitReasonCls}">${t.exit_reason}</span></td>
      <td class="sma-cell">${t.holding_days}D</td>
      <td class="pnl-cell ${pnlCls}">${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct}%</td>
      <td>${outcomeBadge}</td>
    </tr>`;
  }).join('');
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
// Watchlist-Scoped Auto-Complete & Dropdown Search Logic
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
  const datalist = document.querySelector('#lookback-stocks-datalist');
  if (datalist) {
    datalist.innerHTML = filtered.map(item => 
      `<option value="${item.symbol}">${item.symbol} (${item.membership.join(', ')})</option>`
    ).join('');
  }

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
  const datalist = document.querySelector('#tester-stocks-datalist');
  if (datalist) {
    datalist.innerHTML = filtered.map(item => 
      `<option value="${item.symbol}">${item.symbol} (${item.membership.join(', ')})</option>`
    ).join('');
  }

  const input = document.querySelector('#tester-symbol-input');
  if (input) {
    input.placeholder = uni ? `Individual ${uni} stock (${filtered.length})...` : `Individual stock (e.g. TVSMOTOR)...`;
  }
}

function updateNewsSearchScope() {
  const uni = document.querySelector('#news-universe-filter').value;
  const filtered = getFilteredSymbols(uni);
  const datalist = document.querySelector('#news-stocks-datalist');
  if (datalist) {
    datalist.innerHTML = filtered.map(item => 
      `<option value="${item.symbol}">${item.symbol} (${item.membership.join(', ')})</option>`
    ).join('');
  }

  const select = document.querySelector('#news-stock-select');
  if (select && filtered.length) {
    select.innerHTML = filtered.map(item => `<option value="${item.symbol}">${item.symbol} (${item.membership.join(', ')})</option>`).join('');
  }

  const input = document.querySelector('#news-custom-input');
  if (input) {
    input.placeholder = uni ? `Enter ${uni} ticker (${filtered.length} stocks)...` : `Or enter ticker (e.g. TVSMOTOR)...`;
  }
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

    // Check if symbol already in table
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

// Strategy Tester Single Stock Input on Enter
const testerInputEl = document.querySelector('#tester-symbol-input');
if (testerInputEl) {
  testerInputEl.onkeydown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      runStrategyTester();
    }
  };
}

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

document.querySelector('#tester-universe').onchange = () => {
  updateTesterSearchScope();
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

// Daily Scanner Selectors & Buttons
document.querySelector('#refresh').onclick = refreshScanner;
document.querySelector('#strategy').onchange = refreshScanner;
document.querySelector('#index').onchange = refreshScanner;
document.querySelector('#type').onchange = refreshScanner;

document.querySelector('#scan').onclick = async () => {
  const strat = value('#strategy') || 'RSI';
  statusEl.textContent = `Scanning market for ${strat} signals…`;
  const scanBtn = document.querySelector('#scan');
  scanBtn.disabled = true;
  
  try {
    const response = await fetch('/scan/run?strategy=' + encodeURIComponent(strat), { method: 'POST' });
    const body = await response.json();
    if (response.ok) {
      statusEl.textContent = `Scan complete! Scanned ${body.stocks_scanned} stocks, inserted ${body.signals_inserted} signal(s).`;
      refreshScanner();
    } else {
      statusEl.textContent = 'Scan error: ' + (body.detail || 'Failed to scan');
    }
  } catch (err) {
    statusEl.textContent = 'Scan failed: ' + err.message;
  } finally {
    scanBtn.disabled = false;
  }
};

// Initial Load
loadUniverseSymbols();
loadCustomWatchlists();
fetchLookbackSignals();










