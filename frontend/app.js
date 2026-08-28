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

  // Search filter
  const query = state.searchQuery.trim().toUpperCase();
  if (query) {
    list = list.filter(item => item.symbol.toUpperCase().includes(query));
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
document.querySelector('#tab-lookback').onclick = () => {
  state.activeTab = 'lookback';
  document.querySelector('#tab-lookback').classList.add('active');
  document.querySelector('#tab-scanner').classList.remove('active');
// Tab Navigation Handlers
document.querySelector('#tab-lookback').onclick = () => {
  state.activeTab = 'lookback';
  document.querySelector('#tab-lookback').classList.add('active');
  document.querySelector('#tab-scanner').classList.remove('active');
  document.querySelector('#tab-tester').classList.remove('active');
  document.querySelector('#section-lookback').style.display = 'block';
  document.querySelector('#section-scanner').style.display = 'none';
  document.querySelector('#section-tester').style.display = 'none';
  fetchLookbackSignals();
};

document.querySelector('#tab-scanner').onclick = () => {
  state.activeTab = 'scanner';
  document.querySelector('#tab-scanner').classList.add('active');
  document.querySelector('#tab-lookback').classList.remove('active');
  document.querySelector('#tab-tester').classList.remove('active');
  document.querySelector('#section-scanner').style.display = 'block';
  document.querySelector('#section-lookback').style.display = 'none';
  document.querySelector('#section-tester').style.display = 'none';
  refreshScanner();
};

document.querySelector('#tab-tester').onclick = () => {
  state.activeTab = 'tester';
  document.querySelector('#tab-tester').classList.add('active');
  document.querySelector('#tab-lookback').classList.remove('active');
  document.querySelector('#tab-scanner').classList.remove('active');
  document.querySelector('#section-tester').style.display = 'block';
  document.querySelector('#section-lookback').style.display = 'none';
  document.querySelector('#section-scanner').style.display = 'none';
};

// -------------------------------------------------------------
// Strategy Tester Controller
// -------------------------------------------------------------
state.testerData = { summary: null, trades: [] };
state.testerOutcomeFilter = 'ALL';
state.testerSearchQuery = '';

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

  const payload = {
    strategy,
    index,
    target_pct: targetPct,
    stop_loss_pct: slPct,
    max_holding_days: maxHoldDays,
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
    statusEl.textContent = `Simulation completed in ${data.execution_time_ms}ms · ${data.summary.total_trades} trades simulated.`;
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

// Search input
document.querySelector('#symbol-search').oninput = (e) => {
  state.searchQuery = e.target.value;
  renderLookbackTable();
};

// Watchlist Manager Card Toggle & Submit Handlers
document.querySelector('#btn-import-modal').onclick = toggleWatchlistManager;
document.querySelector('#btn-close-wm').onclick = hideWatchlistManager;
document.querySelector('#btn-modal-submit').onclick = handleImportSubmit;

// Lookback Selectors & Buttons
document.querySelector('#lookback-index').onchange = () => fetchLookbackSignals();
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
loadCustomWatchlists();
fetchLookbackSignals();








