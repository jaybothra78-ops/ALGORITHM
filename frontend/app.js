/**
 * ALGORYTHM Institutional Trading Platform - Modular Frontend Architecture
 * Namespaces: App.State, App.Utils, App.Screener, App.News, App.Paper, App.Zerodha, App.Init
 */
'use strict';

window.App = window.App || {};

// =====================================================================
// 1. Central Reactive State Store
// =====================================================================
App.State = {
  activeTab: 'lookback',
  lookbackDays: 1,
  strategyFilter: '',
  indexFilter: '',
  selectedUniverse: '',
  
  // Paper Trading State
  paperInstrument: 'EQUITY', // 'EQUITY' | 'OPTION'
  paperSide: 'BUY',          // 'BUY' | 'SELL'
  paperOptionType: 'CE',     // 'CE' | 'PE'
  paperLotSize: 100,
  paperLots: 1,
  paperExpiry: null,
  paperStrike: null,
  
  // Zerodha Broker State
  zerodhaConnected: false,
  zerodhaUserId: null,
  zerodhaMethod: null,
  
  // Claude AI Key State
  hasClaudeKey: false,
  activeNewsTicker: null,
};

// =====================================================================
// 2. Utility Helpers & Formatters
// =====================================================================
App.Utils = {
  money(val) {
    if (val === null || val === undefined || isNaN(val)) return '—';
    return '₹' + Number(val).toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  },

  formatPct(val) {
    if (val === null || val === undefined || isNaN(val)) return '0.00%';
    const sign = Number(val) >= 0 ? '+' : '';
    return `${sign}${Number(val).toFixed(2)}%`;
  },

  showStatus(elementId, msg, type = 'success', timeoutMs = 4500) {
    const el = document.querySelector(elementId);
    if (!el) return;
    el.className = `wm-status-box ${type}`;
    el.textContent = msg;
    el.style.display = 'block';
    setTimeout(() => {
      el.style.display = 'none';
    }, timeoutMs);
  },

  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  },
};

// =====================================================================
// 3. Tab Navigation & View Router
// =====================================================================
App.Router = {
  init() {
    const tabs = {
      'tab-lookback': 'section-lookback',
      'tab-news': 'section-news',
      'tab-paper': 'section-paper',
    };

    Object.entries(tabs).forEach(([tabId, sectionId]) => {
      const btn = document.querySelector(`#${tabId}`);
      if (!btn) return;
      btn.addEventListener('click', () => {
        this.switchTab(tabId.replace('tab-', ''));
      });
    });
  },

  switchTab(tabName) {
    App.State.activeTab = tabName;
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.view-section').forEach(s => (s.style.display = 'none'));

    const activeBtn = document.querySelector(`#tab-${tabName}`);
    const activeSec = document.querySelector(`#section-${tabName}`);
    if (activeBtn) activeBtn.classList.add('active');
    if (activeSec) activeSec.style.display = 'block';

    if (tabName === 'paper') {
      App.Paper.loadData();
    } else if (tabName === 'news' && !App.State.activeNewsTicker) {
      App.News.loadTopMarketNews();
    }
  },
};

// =====================================================================
// 4. Lookback Screener & TradingView Module
// =====================================================================
App.Screener = {
  init() {
    // Lookback Range Pills
    document.querySelectorAll('#lookback-group .pill').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#lookback-group .pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        App.State.lookbackDays = parseInt(btn.dataset.days, 10);
        this.fetchSignals();
      });
    });

    // Strategy Filter Pills
    document.querySelectorAll('#strategy-filter-group .pill').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#strategy-filter-group .pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        App.State.strategyFilter = btn.dataset.filter || '';
        this.fetchSignals();
      });
    });

    // Universe Dropdown
    const idxSelect = document.querySelector('#lookback-index');
    if (idxSelect) {
      idxSelect.addEventListener('change', () => {
        App.State.indexFilter = idxSelect.value;
        this.fetchSignals();
      });
    }

    // Refresh & Rescan Buttons
    const btnRefresh = document.querySelector('#lookback-refresh');
    if (btnRefresh) btnRefresh.addEventListener('click', () => this.fetchSignals());

    const btnRescan = document.querySelector('#lookback-rescan');
    if (btnRescan) {
      btnRescan.addEventListener('click', async () => {
        btnRescan.disabled = true;
        btnRescan.innerHTML = '<span>⏳ Scanning…</span>';
        try {
          await fetch('/signals/scan', { method: 'POST' });
          await this.fetchSignals();
        } finally {
          btnRescan.disabled = false;
          btnRescan.innerHTML = '<span>⚡ Force Scan</span>';
        }
      });
    }

    this.initWatchlistImporter();
  },

  async fetchSignals() {
    const statusEl = document.querySelector('#header-status-badge');
    if (statusEl) statusEl.textContent = 'Refreshing market signals…';

    const params = new URLSearchParams({
      days: App.State.lookbackDays,
      filter: App.State.strategyFilter,
      index_name: App.State.indexFilter,
    });

    try {
      const res = await fetch(`/signals/lookback?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.renderTable(data.signals || []);
      this.updateMetricsRibbon(data);
      if (statusEl) statusEl.textContent = `Market Ready · ${data.total_signals || 0} Signals Found`;
    } catch (err) {
      console.error('Signals fetch error:', err);
      if (statusEl) statusEl.textContent = 'Failed to load signals';
    }
  },

  renderTable(signals) {
    const tbody = document.querySelector('#lookback-rows');
    if (!tbody) return;

    if (!signals.length) {
      tbody.innerHTML = `<tr><td colspan="10" class="empty-cell">No matching signals found for selected filters.</td></tr>`;
      return;
    }

    tbody.innerHTML = signals.map(s => {
      const rsiVal = s.rsi != null ? Number(s.rsi).toFixed(1) : '—';
      const rsiCls = s.rsi <= 30 ? 'oversold' : (s.rsi >= 70 ? 'overbought' : '');
      const knoxTag = s.is_knox_divergence ? '<span class="badge-knox">⚡ KNOXVILLE</span>' : '—';
      const ma200Tag = s.is_touching_200sma ? '<span class="badge-ma200">📈 200 SMA</span>' : '—';
      const signalCls = s.signal_type.toLowerCase();

      return `<tr>
        <td>
          <div class="ticker-cell-wrapper">
            <a class="ticker-link" target="_blank" rel="noopener noreferrer" href="https://in.tradingview.com/chart/?symbol=NSE:${encodeURIComponent(s.symbol)}">
              ${s.symbol} ↗
            </a>
            <div class="ticker-sub-links">
              <a class="sub-link-screener" target="_blank" rel="noopener noreferrer" href="https://www.screener.in/company/${encodeURIComponent(s.symbol)}/consolidated/">
                📊 Screener
              </a>
            </div>
          </div>
        </td>
        <td><span class="universe-cell">${s.universe || 'NSE'}</span></td>
        <td><span class="badge badge-${signalCls}">${s.signal_type.toUpperCase()}</span></td>
        <td class="price-cell">${App.Utils.money(s.close_price)}</td>
        <td><span class="rsi-cell ${rsiCls}">${rsiVal}</span></td>
        <td>${knoxTag}</td>
        <td>${ma200Tag}</td>
        <td class="date-cell">${s.scan_date}</td>
        <td>
          <div class="row-action-btns">
            <button class="btn-table-action" onclick="App.Paper.prefillOrder('${s.symbol}', ${s.close_price}, '${s.strategy}')" title="Place Paper Trade">
              ⚡ Paper Trade
            </button>
            <button class="btn-table-action subtle" onclick="App.News.analyzeTicker('${s.symbol}')" title="AI News Breakdown">
              📰 News
            </button>
          </div>
        </td>
      </tr>`;
    }).join('');
  },

  updateMetricsRibbon(data) {
    const totalEl = document.querySelector('#metric-total-signals');
    const oversoldEl = document.querySelector('#metric-oversold');
    const overboughtEl = document.querySelector('#metric-overbought');
    const knoxEl = document.querySelector('#metric-knoxville');

    if (totalEl) totalEl.textContent = data.total_signals || 0;
    if (oversoldEl) oversoldEl.textContent = data.oversold_count || 0;
    if (overboughtEl) overboughtEl.textContent = data.overbought_count || 0;
    if (knoxEl) knoxEl.textContent = data.knoxville_count || 0;
  },

  initWatchlistImporter() {
    const card = document.querySelector('#card-watchlist-manager');
    const btnOpen = document.querySelector('#btn-import-modal');
    const btnClose = document.querySelector('#btn-close-wm');
    const btnSubmit = document.querySelector('#btn-modal-submit');

    if (btnOpen && card) {
      btnOpen.addEventListener('click', () => {
        card.style.display = card.style.display === 'none' ? 'block' : 'none';
        if (card.style.display === 'block') card.scrollIntoView({ behavior: 'smooth' });
      });
    }

    if (btnClose && card) {
      btnClose.addEventListener('click', () => { card.style.display = 'none'; });
    }

    if (btnSubmit) {
      btnSubmit.addEventListener('click', async () => {
        const urlInput = document.querySelector('#input-tv-url');
        const nameInput = document.querySelector('#input-tv-name');
        const url = (urlInput ? urlInput.value : '').trim();
        const name = (nameInput ? nameInput.value : '').trim();

        if (!url) {
          App.Utils.showStatus('#modal-status', 'Please enter a valid TradingView watchlist URL', 'error');
          return;
        }

        btnSubmit.disabled = true;
        btnSubmit.innerHTML = '<span>⏳ Importing…</span>';

        try {
          const res = await fetch('/watchlist/import-tradingview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url, name: name || undefined }),
          });

          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
          }

          const resData = await res.json();
          App.Utils.showStatus('#modal-status', `✅ Successfully imported "${resData.watchlist_name}" with ${resData.symbols_count} tickers!`, 'success');
          this.loadCustomWatchlists();
        } catch (err) {
          App.Utils.showStatus('#modal-status', 'Import failed: ' + err.message, 'error');
        } finally {
          btnSubmit.disabled = false;
          btnSubmit.innerHTML = '<span>📥 Import &amp; Sync</span>';
        }
      });
    }

    this.loadCustomWatchlists();
  },

  async loadCustomWatchlists() {
    try {
      const res = await fetch('/watchlist/custom');
      if (!res.ok) return;
      const data = await res.json();
      const tagsContainer = document.querySelector('#custom-lists-tags');
      const select = document.querySelector('#lookback-index');

      if (tagsContainer && data.watchlists) {
        if (!data.watchlists.length) {
          tagsContainer.innerHTML = '<span class="empty-custom">None imported yet</span>';
        } else {
          tagsContainer.innerHTML = data.watchlists.map(w => `
            <span class="custom-tag-chip">
              ⭐ ${w.name} (${w.count})
              <button onclick="App.Screener.deleteWatchlist('${w.name}')" title="Remove">&times;</button>
            </span>
          `).join('');
        }
      }

      if (select && data.watchlists) {
        // Remove old custom options
        Array.from(select.options).forEach(opt => {
          if (opt.dataset.custom === 'true') opt.remove();
        });

        data.watchlists.forEach(w => {
          const opt = document.createElement('option');
          opt.value = `custom:${w.name}`;
          opt.textContent = `⭐ ${w.name} (${w.count})`;
          opt.dataset.custom = 'true';
          select.appendChild(opt);
        });
      }
    } catch (err) {
      console.debug('Custom watchlists load error:', err);
    }
  },

  async deleteWatchlist(name) {
    if (!confirm(`Delete custom watchlist "${name}"?`)) return;
    try {
      await fetch(`/watchlist/custom/${encodeURIComponent(name)}`, { method: 'DELETE' });
      this.loadCustomWatchlists();
      this.fetchSignals();
    } catch (err) {
      alert('Delete failed: ' + err.message);
    }
  },
};

// =====================================================================
// 5. AI News Analyzer & Claude 3.5 Sonnet Synthesis Module
// =====================================================================
App.News = {
  init() {
    const btnRun = document.querySelector('#btn-run-news');
    const btnSample = document.querySelector('#btn-trigger-sample-news');
    const stockSelect = document.querySelector('#news-stock-select');
    const customInput = document.querySelector('#news-custom-input');
    const universeFilter = document.querySelector('#news-universe-filter');

    // Analyze button click
    if (btnRun) {
      btnRun.addEventListener('click', () => {
        const sym = this.getSelectedSymbol();
        if (sym) this.analyzeTicker(sym);
      });
    }

    // Sample button click
    if (btnSample) {
      btnSample.addEventListener('click', () => {
        this.analyzeTicker('TVSMOTOR');
      });
    }

    // Custom input enter key or change
    if (customInput) {
      customInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
          const sym = customInput.value.trim().toUpperCase();
          if (sym) this.analyzeTicker(sym);
        }
      });
    }

    // Quick Chips click
    document.querySelectorAll('#news-quick-chips .pill').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#news-quick-chips .pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const sym = btn.dataset.sym;
        if (stockSelect) stockSelect.value = sym;
        if (customInput) customInput.value = sym;
        this.analyzeTicker(sym);
      });
    });

    // Universe filter to update stock dropdown
    if (universeFilter) {
      universeFilter.addEventListener('change', () => {
        this.populateStockSelect(universeFilter.value);
      });
    }

    this.initClaudeKeyModal();
  },

  getSelectedSymbol() {
    const customInput = document.querySelector('#news-custom-input');
    const stockSelect = document.querySelector('#news-stock-select');
    const customVal = customInput ? customInput.value.trim().toUpperCase() : '';
    if (customVal) return customVal;
    return stockSelect ? stockSelect.value : 'TVSMOTOR';
  },

  async populateStockSelect(universe) {
    try {
      const res = await fetch(`/signals/lookback?days=1&index_name=${encodeURIComponent(universe || '')}`);
      if (!res.ok) return;
      const data = await res.json();
      const stockSelect = document.querySelector('#news-stock-select');
      if (!stockSelect) return;

      const symbols = Array.from(new Set((data.signals || []).map(s => s.symbol).filter(Boolean)));
      if (symbols.length) {
        stockSelect.innerHTML = symbols.map(s => `<option value="${s}">${s}</option>`).join('');
      }
    } catch (err) {
      console.debug('Failed to filter news stocks:', err);
    }
  },

  async loadTopMarketNews() {
    this.analyzeTicker('TVSMOTOR');
  },

  async analyzeTicker(symbol) {
    App.Router.switchTab('news');
    App.State.activeNewsTicker = symbol;

    const customInput = document.querySelector('#news-custom-input');
    const stockSelect = document.querySelector('#news-stock-select');
    if (customInput) customInput.value = symbol;
    if (stockSelect) {
      const exists = Array.from(stockSelect.options).some(opt => opt.value === symbol);
      if (exists) stockSelect.value = symbol;
    }

    // Sync quick chip pills
    document.querySelectorAll('#news-quick-chips .pill').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.sym === symbol);
    });

    const placeholder = document.querySelector('#news-placeholder');
    const loadingCard = document.querySelector('#news-loading-card');
    const contentCard = document.querySelector('#news-content-card');

    if (placeholder) placeholder.style.display = 'none';
    if (contentCard) contentCard.style.display = 'none';
    if (loadingCard) loadingCard.style.display = 'block';

    // Animate loading step progression
    this.animateLoadingSteps();

    try {
      const res = await fetch(`/news/analyze?symbol=${encodeURIComponent(symbol)}`);
      if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
      const data = await res.json();

      this.renderReport(data);

      if (loadingCard) loadingCard.style.display = 'none';
      if (contentCard) {
        contentCard.style.display = 'block';
        contentCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    } catch (err) {
      if (loadingCard) loadingCard.style.display = 'none';
      if (placeholder) {
        placeholder.style.display = 'block';
        placeholder.innerHTML = `
          <div class="placeholder-icon">⚠️</div>
          <h3>Analysis Failed for ${symbol}</h3>
          <p style="color: #f43f5e;">${err.message || 'Unable to fetch news sentiment.'}</p>
          <button onclick="App.News.analyzeTicker('${symbol}')" class="btn-secondary">Retry Analysis</button>
        `;
      }
    }
  },

  animateLoadingSteps() {
    const steps = ['#step-1', '#step-2', '#step-3', '#step-4'];
    steps.forEach((id, idx) => {
      const el = document.querySelector(id);
      if (el) {
        el.classList.remove('active', 'completed');
        setTimeout(() => {
          if (idx > 0) {
            const prev = document.querySelector(steps[idx - 1]);
            if (prev) prev.classList.add('completed');
          }
          el.classList.add('active');
        }, idx * 650);
      }
    });
  },

  renderReport(data) {
    // Hero Elements
    const tickerEl = document.querySelector('#ai-stock-ticker');
    const companyEl = document.querySelector('#ai-company-name');
    const screenerLink = document.querySelector('#btn-open-screener');
    const tvLink = document.querySelector('#btn-open-tv');
    const execSummary = document.querySelector('#ai-exec-summary');
    const sentimentBadge = document.querySelector('#ai-sentiment-badge');
    const sentimentText = document.querySelector('#ai-sentiment-text');
    const scoreNum = document.querySelector('#ai-score-number');
    const scoreFill = document.querySelector('#ai-score-fill');

    if (tickerEl) tickerEl.textContent = data.symbol;
    if (companyEl) companyEl.textContent = `${data.company_name || data.symbol} (NSE)`;
    if (screenerLink) screenerLink.href = `https://www.screener.in/company/${encodeURIComponent(data.symbol)}/consolidated/`;
    if (tvLink) tvLink.href = `https://in.tradingview.com/chart/?symbol=NSE:${encodeURIComponent(data.symbol)}`;
    if (execSummary) execSummary.textContent = data.executive_summary;

    const sent = (data.sentiment || 'Neutral').toLowerCase();
    if (sentimentBadge) {
      sentimentBadge.className = `sentiment-badge-pill ${sent}`;
      const icon = sent === 'bullish' ? '🟢' : (sent === 'bearish' ? '🔴' : '🟡');
      sentimentBadge.querySelector('.sentiment-icon').textContent = icon;
    }
    if (sentimentText) sentimentText.textContent = data.sentiment || 'Neutral';
    if (scoreNum) scoreNum.textContent = `${data.sentiment_score || 50}%`;
    if (scoreFill) scoreFill.style.width = `${data.sentiment_score || 50}%`;

    // Catalysts List
    const catList = document.querySelector('#ai-catalysts-list');
    if (catList) {
      if (data.catalysts && data.catalysts.length) {
        catList.innerHTML = data.catalysts.map(c => `<li>${c}</li>`).join('');
      } else {
        catList.innerHTML = '<li>No prominent positive catalysts identified in current news cycle.</li>';
      }
    }

    // Risks List
    const riskList = document.querySelector('#ai-risks-list');
    if (riskList) {
      if (data.risks && data.risks.length) {
        riskList.innerHTML = data.risks.map(r => `<li>${r}</li>`).join('');
      } else {
        riskList.innerHTML = '<li>No acute headwinds or high-risk regulatory warnings reported.</li>';
      }
    }

    // Technical Correlation
    const tcEl = document.querySelector('#ai-technical-correlation');
    if (tcEl) {
      tcEl.textContent = data.technical_correlation || 'Technical and fundamental signals remain aligned with prevailing market direction.';
    }

    // Articles Grid
    const articlesGrid = document.querySelector('#news-articles-grid');
    const articlesCount = document.querySelector('#ai-articles-count');
    if (articlesCount) articlesCount.textContent = `${(data.articles || []).length} articles`;

    if (articlesGrid) {
      if (!data.articles || !data.articles.length) {
        articlesGrid.innerHTML = '<div class="empty-cell">No recent news articles found for this ticker.</div>';
      } else {
        articlesGrid.innerHTML = data.articles.map(a => `
          <div class="news-article-card">
            <div class="article-meta-row">
              <span class="article-publisher">${a.publisher || 'Financial Media'}</span>
              <span class="article-date">${a.published_at || 'Recent'}</span>
            </div>
            <h5 class="article-headline">
              <a href="${a.link}" target="_blank" rel="noopener noreferrer">${a.title}</a>
            </h5>
            <p class="article-summary">${a.summary || 'Click link to read full coverage on publisher site.'}</p>
            <a href="${a.link}" target="_blank" rel="noopener noreferrer" class="article-read-btn">Read Full Story ↗</a>
          </div>
        `).join('');
      }
    }
  },

  initClaudeKeyModal() {
    const card = document.querySelector('#card-claude-key');
    const btnOpen = document.querySelector('#btn-claude-key-modal');
    const btnClose = document.querySelector('#btn-close-claude-key');
    const btnSave = document.querySelector('#btn-save-claude-key');
    const btnClear = document.querySelector('#btn-clear-claude-key');
    const inputKey = document.querySelector('#input-claude-key');

    if (btnOpen && card) {
      btnOpen.addEventListener('click', () => {
        card.style.display = card.style.display === 'none' ? 'block' : 'none';
        if (card.style.display === 'block') card.scrollIntoView({ behavior: 'smooth' });
      });
    }

    if (btnClose && card) {
      btnClose.addEventListener('click', () => { card.style.display = 'none'; });
    }

    if (btnSave && inputKey) {
      btnSave.addEventListener('click', async () => {
        const key = inputKey.value.trim();
        if (!key) {
          App.Utils.showStatus('#claude-key-status', 'Please enter a valid Anthropic API key (sk-ant-...)', 'error');
          return;
        }

        try {
          const res = await fetch('/news/key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: key }),
          });

          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          App.Utils.showStatus('#claude-key-status', '✅ Claude API Key saved successfully!', 'success');
          this.checkKeyStatus();
          setTimeout(() => { if (card) card.style.display = 'none'; }, 1500);
        } catch (err) {
          App.Utils.showStatus('#claude-key-status', 'Failed to save key: ' + err.message, 'error');
        }
      });
    }

    if (btnClear) {
      btnClear.addEventListener('click', async () => {
        await fetch('/news/key', { method: 'DELETE' });
        if (inputKey) inputKey.value = '';
        App.Utils.showStatus('#claude-key-status', 'Claude API Key cleared', 'success');
        this.checkKeyStatus();
      });
    }

    this.checkKeyStatus();
  },

  async checkKeyStatus() {
    try {
      const res = await fetch('/news/status');
      if (!res.ok) return;
      const data = await res.json();
      const btnText = document.querySelector('#claude-key-btn-text');
      if (btnText) {
        btnText.textContent = data.has_api_key ? '🟢 Claude Active' : 'Claude AI Key';
      }
    } catch (err) {
      console.debug('Claude status error:', err);
    }
  },
};


// =====================================================================
// 6. Paper Trading & Institutional Options Derivatives Module
// =====================================================================
App.Paper = {
  init() {
    // Instrument Switches (Equity Cash vs Options F&O)
    const btnEq = document.querySelector('#btn-inst-equity');
    const btnOpt = document.querySelector('#btn-inst-option');

    if (btnEq) btnEq.addEventListener('click', () => this.switchInstrument('EQUITY'));
    if (btnOpt) btnOpt.addEventListener('click', () => this.switchInstrument('OPTION'));

    // Option Type Switches (CE vs PE)
    const btnCe = document.querySelector('#btn-opt-type-ce');
    const btnPe = document.querySelector('#btn-opt-type-pe');

    if (btnCe) btnCe.addEventListener('click', () => this.switchOptionType('CE'));
    if (btnPe) btnPe.addEventListener('click', () => this.switchOptionType('PE'));

    // Side Switches (BUY vs SELL)
    const btnBuy = document.querySelector('#btn-order-side-buy');
    const btnSell = document.querySelector('#btn-order-side-sell');

    if (btnBuy) {
      btnBuy.addEventListener('click', () => {
        App.State.paperSide = 'BUY';
        btnBuy.classList.add('active');
        if (btnSell) btnSell.classList.remove('active');
        this.updateEstimatedCapital();
      });
    }

    if (btnSell) {
      btnSell.addEventListener('click', () => {
        App.State.paperSide = 'SELL';
        btnSell.classList.add('active');
        if (btnBuy) btnBuy.classList.remove('active');
        this.updateEstimatedCapital();
      });
    }

    // Ticker Input Auto-Detect
    const stockInput = document.querySelector('#paper-stock-input');
    if (stockInput) {
      stockInput.addEventListener('change', () => {
        const sym = stockInput.value.trim().toUpperCase();
        if (sym) {
          if (App.State.paperInstrument === 'OPTION') {
            this.fetchOptionStrikes(sym);
          } else {
            this.fetchLivePriceOrPremium();
          }
        }
      });
    }

    // Expiry Dropdown & Strike Ladder
    const expSelect = document.querySelector('#paper-expiry-select');
    if (expSelect) {
      expSelect.addEventListener('change', () => {
        const sym = (document.querySelector('#paper-stock-input').value || '').trim().toUpperCase();
        if (sym) this.fetchOptionStrikes(sym, expSelect.value);
      });
    }

    const strikeInput = document.querySelector('#paper-strike-input');
    if (strikeInput) {
      strikeInput.addEventListener('change', () => this.fetchLivePriceOrPremium());
    }

    const btnAutoAtm = document.querySelector('#btn-auto-atm-strike');
    if (btnAutoAtm) {
      btnAutoAtm.addEventListener('click', () => {
        const sym = (document.querySelector('#paper-stock-input').value || '').trim().toUpperCase();
        if (sym) this.fetchOptionStrikes(sym);
      });
    }

    // Quantity / Contract Inputs
    const qtyInput = document.querySelector('#paper-qty-input');
    const lotsInput = document.querySelector('#paper-contracts-input');
    const priceInput = document.querySelector('#paper-price-input');

    if (qtyInput) qtyInput.addEventListener('input', () => this.updateEstimatedCapital());
    if (lotsInput) lotsInput.addEventListener('input', () => this.updateEstimatedCapital());
    if (priceInput) priceInput.addEventListener('input', () => this.updateEstimatedCapital());

    // Quick Chips Listeners
    this.initQuickChips();

    // Fetch LTP / Premium Button
    const btnFetch = document.querySelector('#btn-paper-fetch-ltp');
    if (btnFetch) btnFetch.addEventListener('click', () => this.fetchLivePriceOrPremium());

    // Execute Order Button
    const btnExecute = document.querySelector('#btn-paper-execute');
    if (btnExecute) btnExecute.addEventListener('click', () => this.executeOrder());

    // Reset Portfolio Button
    const btnReset = document.querySelector('#btn-paper-reset');
    if (btnReset) btnReset.addEventListener('click', () => this.resetPortfolio());

    // Subtabs Navigation
    this.initSubtabs();
  },

  switchInstrument(inst) {
    App.State.paperInstrument = inst;
    const isOpt = inst === 'OPTION';

    const btnEq = document.querySelector('#btn-inst-equity');
    const btnOpt = document.querySelector('#btn-inst-option');
    const optPanel = document.querySelector('#options-control-panel');
    const greeksRibbon = document.querySelector('#options-greeks-ribbon');
    const eqQtyGroup = document.querySelector('#form-group-equity-qty');
    const fetchBtn = document.querySelector('#btn-paper-fetch-ltp');
    const labelPrice = document.querySelector('#label-entry-price');

    if (isOpt) {
      if (btnOpt) btnOpt.classList.add('active');
      if (btnEq) btnEq.classList.remove('active');
      if (optPanel) optPanel.style.display = 'grid';
      if (greeksRibbon) greeksRibbon.style.display = 'flex';
      if (eqQtyGroup) eqQtyGroup.style.display = 'none';
      if (fetchBtn) fetchBtn.textContent = '⚡ Fetch Live Premium';
      if (labelPrice) labelPrice.textContent = 'Option Premium (₹)';
      this.updateQuickChips('OPTION');

      const sym = (document.querySelector('#paper-stock-input').value || '').trim().toUpperCase();
      if (sym) this.fetchOptionStrikes(sym);
    } else {
      if (btnEq) btnEq.classList.add('active');
      if (btnOpt) btnOpt.classList.remove('active');
      if (optPanel) optPanel.style.display = 'none';
      if (greeksRibbon) greeksRibbon.style.display = 'none';
      if (eqQtyGroup) eqQtyGroup.style.display = 'flex';
      if (fetchBtn) fetchBtn.textContent = '⚡ Fetch Live Price';
      if (labelPrice) labelPrice.textContent = 'Entry Price (₹)';
      this.updateQuickChips('EQUITY');
    }

    this.updateEstimatedCapital();
  },

  switchOptionType(type) {
    App.State.paperOptionType = type;
    const isCe = type === 'CE';
    const btnCe = document.querySelector('#btn-opt-type-ce');
    const btnPe = document.querySelector('#btn-opt-type-pe');

    if (btnCe) btnCe.classList.toggle('active', isCe);
    if (btnPe) btnPe.classList.toggle('active', !isCe);

    const sym = (document.querySelector('#paper-stock-input').value || '').trim().toUpperCase();
    if (sym) this.fetchLivePriceOrPremium();
  },

  initQuickChips() {
    // Equity Quantity Chips
    document.querySelectorAll('#equity-qty-quick-btns .btn-qty-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const qtyInput = document.querySelector('#paper-qty-input');
        const curr = parseInt(qtyInput ? qtyInput.value : 0, 10) || 0;
        const add = parseInt(btn.dataset.qty, 10);
        if (qtyInput) qtyInput.value = curr + add;
        this.updateEstimatedCapital();
      });
    });

    // Lots Quick Chips
    document.querySelectorAll('.btn-lot-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const lotInput = document.querySelector('#paper-contracts-input');
        if (lotInput) lotInput.value = btn.dataset.lots;
        this.updateEstimatedCapital();
      });
    });

    this.bindTargetAndSlChips();
  },

  updateQuickChips(mode) {
    const targetChips = document.querySelector('#quick-target-chips');
    const slChips = document.querySelector('#quick-sl-chips');

    if (mode === 'OPTION') {
      if (targetChips) {
        targetChips.innerHTML = `
          <button type="button" class="btn-pct-chip" data-pct="20">+20%</button>
          <button type="button" class="btn-pct-chip" data-pct="50">+50%</button>
          <button type="button" class="btn-pct-chip" data-pct="100">+100%</button>
        `;
      }
      if (slChips) {
        slChips.innerHTML = `
          <button type="button" class="btn-pct-chip" data-pct="-15">-15%</button>
          <button type="button" class="btn-pct-chip" data-pct="-30">-30%</button>
          <button type="button" class="btn-pct-chip" data-pct="-50">-50%</button>
        `;
      }
    } else {
      if (targetChips) {
        targetChips.innerHTML = `
          <button type="button" class="btn-pct-chip" data-pct="2">+2%</button>
          <button type="button" class="btn-pct-chip" data-pct="5">+5%</button>
          <button type="button" class="btn-pct-chip" data-pct="10">+10%</button>
        `;
      }
      if (slChips) {
        slChips.innerHTML = `
          <button type="button" class="btn-pct-chip" data-pct="-1">-1%</button>
          <button type="button" class="btn-pct-chip" data-pct="-2">-2%</button>
          <button type="button" class="btn-pct-chip" data-pct="-3">-3%</button>
        `;
      }
    }
    this.bindTargetAndSlChips();
  },

  bindTargetAndSlChips() {
    document.querySelectorAll('#quick-target-chips .btn-pct-chip').forEach(btn => {
      btn.onclick = () => {
        const entry = parseFloat(document.querySelector('#paper-price-input').value || 0);
        if (!entry) return;
        const pct = parseFloat(btn.dataset.pct) / 100.0;
        const target = App.State.paperSide === 'BUY' ? entry * (1 + pct) : entry * (1 - pct);
        document.querySelector('#paper-target-input').value = target.toFixed(2);
      };
    });

    document.querySelectorAll('#quick-sl-chips .btn-pct-chip').forEach(btn => {
      btn.onclick = () => {
        const entry = parseFloat(document.querySelector('#paper-price-input').value || 0);
        if (!entry) return;
        const pct = Math.abs(parseFloat(btn.dataset.pct)) / 100.0;
        const sl = App.State.paperSide === 'BUY' ? entry * (1 - pct) : entry * (1 + pct);
        document.querySelector('#paper-sl-input').value = sl.toFixed(2);
      };
    });
  },

  updateEstimatedCapital() {
    const isOpt = App.State.paperInstrument === 'OPTION';
    const price = parseFloat(document.querySelector('#paper-price-input').value || 0);
    const estEl = document.querySelector('#paper-est-capital');
    if (!estEl) return;

    if (isOpt) {
      const lots = parseInt(document.querySelector('#paper-contracts-input').value || 1, 10);
      const lotSize = App.State.paperLotSize || 100;
      const est = lots * lotSize * price;
      estEl.textContent = App.Utils.money(est);
    } else {
      const qty = parseInt(document.querySelector('#paper-qty-input').value || 0, 10);
      const est = qty * price;
      estEl.textContent = App.Utils.money(est);
    }
  },

  async fetchOptionStrikes(sym, selectedExpiry = null) {
    try {
      const url = selectedExpiry
        ? `/market/option-strikes?symbol=${encodeURIComponent(sym)}&expiry_date=${encodeURIComponent(selectedExpiry)}`
        : `/market/option-strikes?symbol=${encodeURIComponent(sym)}`;

      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();

      App.State.paperLotSize = data.lot_size;
      const lotBadge = document.querySelector('#paper-lot-size-badge');
      if (lotBadge) lotBadge.textContent = `Lot Size: ${data.lot_size}`;

      // Populate Expiry Select
      const expSelect = document.querySelector('#paper-expiry-select');
      if (expSelect && data.expiries && data.expiries.length) {
        const currentVal = selectedExpiry || expSelect.value;
        expSelect.innerHTML = data.expiries.map((exp, idx) => `
          <option value="${exp.date}" ${(currentVal === exp.date || (!selectedExpiry && idx === 0)) ? 'selected' : ''}>${exp.label}</option>
        `).join('');
      }

      // Populate Strike Ladder Quick Select
      const strikeSelect = document.querySelector('#paper-strike-quick-select');
      if (strikeSelect && data.strikes && data.strikes.length) {
        strikeSelect.innerHTML = `<option value="">⚡ Select Strike Ladder</option>` + data.strikes.map(s => {
          const isCe = App.State.paperOptionType === 'CE';
          const tag = isCe ? s.ce_tag : s.pe_tag;
          const prem = isCe ? s.ce_premium : s.pe_premium;
          return `<option value="${s.strike}" ${s.is_atm ? 'selected' : ''}>${s.strike} (${tag} · ₹${prem})</option>`;
        }).join('');

        strikeSelect.onchange = () => {
          if (strikeSelect.value) {
            document.querySelector('#paper-strike-input').value = strikeSelect.value;
            this.fetchLivePriceOrPremium();
          }
        };
      }

      // Set ATM Strike if blank
      const strikeInput = document.querySelector('#paper-strike-input');
      if (strikeInput && !strikeInput.value) {
        strikeInput.value = data.atm_strike;
      }

      this.fetchLivePriceOrPremium();
    } catch (err) {
      console.error('Option strikes error:', err);
    }
  },

  async fetchLivePriceOrPremium() {
    const sym = (document.querySelector('#paper-stock-input').value || '').trim().toUpperCase();
    if (!sym) return;

    const isOpt = App.State.paperInstrument === 'OPTION';
    const btn = document.querySelector('#btn-paper-fetch-ltp');
    if (btn) btn.textContent = '⏳ Fetching…';

    try {
      if (isOpt) {
        const optType = App.State.paperOptionType;
        const strike = parseFloat(document.querySelector('#paper-strike-input').value || 0);
        const expiry = document.querySelector('#paper-expiry-select').value;

        const res = await fetch(`/market/option-price?symbol=${encodeURIComponent(sym)}&option_type=${optType}&strike=${strike}&expiry_date=${encodeURIComponent(expiry)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        document.querySelector('#paper-price-input').value = data.premium.toFixed(2);
        this.updateDefaultTargetAndSl(data.premium);
        this.updateEstimatedCapital();

        // Populate Greeks Ribbon
        const spotEl = document.querySelector('#greek-spot');
        const premEl = document.querySelector('#greek-premium');
        const deltaEl = document.querySelector('#greek-delta');
        const thetaEl = document.querySelector('#greek-theta');
        const intrEl = document.querySelector('#greek-intrinsic');
        const timeEl = document.querySelector('#greek-time-val');

        if (spotEl) spotEl.textContent = App.Utils.money(data.spot_price);
        if (premEl) premEl.textContent = App.Utils.money(data.premium);
        if (deltaEl) deltaEl.textContent = data.delta;
        if (thetaEl) thetaEl.textContent = data.theta;
        if (intrEl) intrEl.textContent = App.Utils.money(data.intrinsic);
        if (timeEl) timeEl.textContent = App.Utils.money(data.time_value);

        App.Utils.showStatus('#paper-order-status', `⚡ Live ${data.display_symbol} Premium: ${App.Utils.money(data.premium)} (${data.source})`, 'success');
      } else {
        const res = await fetch(`/market/ltp?symbol=${encodeURIComponent(sym)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (data.ltp && data.ltp > 0) {
          document.querySelector('#paper-price-input').value = data.ltp.toFixed(2);
          this.updateDefaultTargetAndSl(data.ltp);
          this.updateEstimatedCapital();
          const changeSign = data.change >= 0 ? '+' : '';
          App.Utils.showStatus('#paper-order-status', `⚡ Live LTP for ${data.symbol}: ${App.Utils.money(data.ltp)} (${changeSign}${data.change_pct}% · ${data.source})`, 'success');
        }
      }
    } catch (err) {
      App.Utils.showStatus('#paper-order-status', 'Price fetch error: ' + err.message, 'error');
    } finally {
      if (btn) btn.textContent = isOpt ? '⚡ Fetch Live Premium' : '⚡ Fetch Live Price';
    }
  },

  updateDefaultTargetAndSl(entryPrice) {
    if (!entryPrice || entryPrice <= 0) return;
    const isBuy = App.State.paperSide === 'BUY';
    const isOpt = App.State.paperInstrument === 'OPTION';

    const targetPct = isOpt ? 0.50 : 0.05;
    const slPct = isOpt ? 0.30 : 0.02;

    const target = isBuy ? entryPrice * (1 + targetPct) : entryPrice * (1 - targetPct);
    const sl = isBuy ? entryPrice * (1 - slPct) : entryPrice * (1 + slPct);

    document.querySelector('#paper-target-input').value = target.toFixed(2);
    document.querySelector('#paper-sl-input').value = sl.toFixed(2);
  },

  async executeOrder() {
    const sym = (document.querySelector('#paper-stock-input').value || '').trim().toUpperCase();
    if (!sym) {
      App.Utils.showStatus('#paper-order-status', 'Please enter a valid stock or index symbol', 'error');
      return;
    }

    const isOpt = App.State.paperInstrument === 'OPTION';
    const price = parseFloat(document.querySelector('#paper-price-input').value || 0) || null;
    const target = parseFloat(document.querySelector('#paper-target-input').value || 0) || null;
    const sl = parseFloat(document.querySelector('#paper-sl-input').value || 0) || null;
    const strategy = document.querySelector('#paper-strategy-select').value;

    const payload = {
      symbol: sym,
      instrument_type: App.State.paperInstrument,
      side: App.State.paperSide,
      entry_price: price,
      target_price: target,
      stop_loss_price: sl,
      strategy: strategy,
    };

    if (isOpt) {
      const strike = parseFloat(document.querySelector('#paper-strike-input').value || 0);
      const expiry = document.querySelector('#paper-expiry-select').value;
      const lots = parseInt(document.querySelector('#paper-contracts-input').value || 1, 10);
      const lotSize = App.State.paperLotSize || 100;

      payload.option_type = App.State.paperOptionType;
      payload.strike_price = strike;
      payload.expiry_date = expiry;
      payload.contracts = lots;
      payload.lot_size = lotSize;
      payload.quantity = lots * lotSize;
    } else {
      payload.quantity = parseInt(document.querySelector('#paper-qty-input').value || 10, 10);
    }

    const btn = document.querySelector('#btn-paper-execute');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>⏳ Executing Order…</span>';
    }

    try {
      const res = await fetch('/paper/order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      App.Utils.showStatus('#paper-order-status', `✅ Order filled! ${App.State.paperSide} ${data.display_symbol || sym} (${data.quantity} units) @ ${App.Utils.money(data.entry_price)}.`, 'success');
      this.loadData();
    } catch (err) {
      App.Utils.showStatus('#paper-order-status', 'Order execution failed: ' + err.message, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span>⚡ Execute Paper Order</span>';
      }
    }
  },

  async closePosition(positionId) {
    if (!confirm(`Are you sure you want to square-off position #${positionId} at current live market quote?`)) return;

    try {
      const res = await fetch('/paper/close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position_id: positionId, exit_reason: 'Manual Exit' }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      App.Utils.showStatus('#paper-order-status', `Position closed! Realized P&L: ${App.Utils.money(data.pnl_amount)} (${App.Utils.formatPct(data.pnl_pct)})`, 'success');
      this.loadData();
    } catch (err) {
      alert('Failed to close position: ' + err.message);
    }
  },

  async resetPortfolio() {
    if (!confirm('⚠️ Reset virtual portfolio? This will clear all open & closed paper trades and restore balance to ₹10,00,000.')) return;

    try {
      const res = await fetch('/paper/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ capital: 1000000.0 }),
      });

      if (!res.ok) throw new Error('Reset failed');
      this.loadData();
      App.Utils.showStatus('#paper-order-status', 'Portfolio reset to ₹10,00,000.00 successfully!', 'success');
    } catch (err) {
      alert('Reset failed: ' + err.message);
    }
  },

  async loadData() {
    await Promise.all([
      this.loadSummary(),
      this.loadPositions(),
      this.loadHistory(),
    ]);
  },

  async loadSummary() {
    try {
      const res = await fetch('/paper/summary');
      if (!res.ok) return;
      const s = await res.json();

      const eqEl = document.querySelector('#paper-total-equity');
      const cashEl = document.querySelector('#paper-cash-balance');
      const marginEl = document.querySelector('#paper-invested-amount');
      const openCntEl = document.querySelector('#paper-open-count');
      const uPnlEl = document.querySelector('#paper-unrealized-pnl');
      const uPctEl = document.querySelector('#paper-unrealized-pct');
      const rPnlEl = document.querySelector('#paper-realized-pnl');
      const winRateEl = document.querySelector('#paper-win-rate');
      const totPnlEl = document.querySelector('#paper-total-pnl');

      if (eqEl) eqEl.textContent = App.Utils.money(s.total_equity);
      if (cashEl) cashEl.textContent = App.Utils.money(s.cash_balance);
      if (marginEl) marginEl.textContent = App.Utils.money(s.invested_margin);
      if (openCntEl) openCntEl.textContent = `${s.open_positions_count} active positions`;

      if (totPnlEl) {
        totPnlEl.textContent = `${App.Utils.money(s.total_pnl)} (${App.Utils.formatPct(s.total_pnl_pct)})`;
        totPnlEl.className = s.total_pnl > 0 ? 'kpi-pnl-pos' : (s.total_pnl < 0 ? 'kpi-pnl-neg' : 'kpi-pnl-neutral');
      }

      if (uPnlEl) {
        uPnlEl.textContent = App.Utils.money(s.unrealized_pnl);
        uPnlEl.className = `kpi-main-val ${s.unrealized_pnl > 0 ? 'kpi-pnl-pos' : (s.unrealized_pnl < 0 ? 'kpi-pnl-neg' : 'kpi-pnl-neutral')}`;
      }

      if (uPctEl) uPctEl.textContent = App.Utils.formatPct(s.unrealized_pnl_pct);

      if (rPnlEl) {
        rPnlEl.textContent = App.Utils.money(s.realized_pnl);
        rPnlEl.className = `kpi-main-val ${s.realized_pnl > 0 ? 'kpi-pnl-pos' : (s.realized_pnl < 0 ? 'kpi-pnl-neg' : 'kpi-pnl-neutral')}`;
      }

      if (winRateEl) {
        winRateEl.textContent = `Win Rate: ${s.win_rate_pct.toFixed(1)}% · ${s.winning_trades}W / ${s.losing_trades}L (${s.total_trades} Trades)`;
      }

      const badgeOpen = document.querySelector('#badge-open-positions');
      const badgeHist = document.querySelector('#badge-history-trades');
      if (badgeOpen) badgeOpen.textContent = s.open_positions_count;
      if (badgeHist) badgeHist.textContent = s.total_trades;
    } catch (err) {
      console.debug('Summary fetch error:', err);
    }
  },

  async loadPositions() {
    try {
      const res = await fetch('/paper/positions');
      if (!res.ok) return;
      const positions = await res.json();
      this.renderPositionsTable(positions);
    } catch (err) {
      console.debug('Positions fetch error:', err);
    }
  },

  renderPositionsTable(positions) {
    const tbody = document.querySelector('#paper-positions-rows');
    if (!tbody) return;

    if (!positions || !positions.length) {
      tbody.innerHTML = `<tr><td colspan="11" class="empty-cell">No open positions. Use the order form above or click "Paper Trade" from the Screener.</td></tr>`;
      return;
    }

    tbody.innerHTML = positions.map(pos => {
      const pnlCls = pos.unrealized_pnl > 0 ? 'positive' : (pos.unrealized_pnl < 0 ? 'negative' : '');
      const sideCls = pos.side.toLowerCase();
      const isOpt = pos.instrument_type === 'OPTION';
      const optTypeCls = pos.option_type ? (pos.option_type === 'CE' ? 'call' : 'put') : 'equity';

      return `<tr>
        <td>
          <div class="ticker-cell-wrapper">
            <a class="ticker-link" target="_blank" rel="noopener noreferrer" href="https://in.tradingview.com/chart/?symbol=NSE:${encodeURIComponent(pos.symbol)}">
              ${pos.display_symbol || pos.symbol} ↗
            </a>
            <div class="ticker-sub-links">
              <a class="sub-link-screener" target="_blank" rel="noopener noreferrer" href="https://www.screener.in/company/${encodeURIComponent(pos.symbol)}/consolidated/">
                📊 Screener
              </a>
            </div>
          </div>
        </td>
        <td>
          <span class="badge-inst-type ${optTypeCls}">
            ${isOpt ? (pos.option_type === 'CE' ? '🟢 CE' : '🔴 PE') : '📈 CASH'}
          </span>
          <div style="font-size: 0.68rem; color: var(--text-muted); margin-top: 2px;">${isOpt ? (pos.expiry_date || '') : ''}</div>
        </td>
        <td><span class="badge-side ${sideCls}">${pos.side}</span></td>
        <td>
          <div class="price-cell">
            <strong>${pos.quantity}</strong>
            ${isOpt ? `<div style="font-size: 0.7rem; color: var(--text-muted);">${pos.contracts || 1}L × ${pos.lot_size}</div>` : ''}
          </div>
        </td>
        <td class="price-cell">${App.Utils.money(pos.entry_price)}</td>
        <td class="price-cell"><strong>${App.Utils.money(pos.current_price)}</strong></td>
        <td class="price-cell">${App.Utils.money(pos.invested_amount)}</td>
        <td class="price-cell ${pnlCls}">
          <strong>${App.Utils.money(pos.unrealized_pnl)}</strong>
          <div style="font-size: 0.72rem;">${App.Utils.formatPct(pos.unrealized_pnl_pct)}</div>
        </td>
        <td>
          <div style="font-size: 0.76rem; font-family: var(--font-mono);">
            <span style="color: #10b981;">T: ${App.Utils.money(pos.target_price)}</span><br>
            <span style="color: #f43f5e;">SL: ${App.Utils.money(pos.stop_loss_price)}</span>
          </div>
        </td>
        <td><span class="strategy-tag">${pos.strategy}</span></td>
        <td>
          <button type="button" class="btn-close-pos" onclick="App.Paper.closePosition(${pos.id})" title="Square-off position">
            ✕ Close
          </button>
        </td>
      </tr>`;
    }).join('');
  },

  async loadHistory() {
    try {
      const res = await fetch('/paper/history');
      if (!res.ok) return;
      const history = await res.json();
      this.renderHistoryTable(history);
    } catch (err) {
      console.debug('History fetch error:', err);
    }
  },

  renderHistoryTable(history) {
    const tbody = document.querySelector('#paper-history-rows');
    if (!tbody) return;

    if (!history || !history.length) {
      tbody.innerHTML = `<tr><td colspan="12" class="empty-cell">No closed trades yet in your journal.</td></tr>`;
      return;
    }

    tbody.innerHTML = history.map(t => {
      const pnlCls = t.pnl_amount > 0 ? 'positive' : (t.pnl_amount < 0 ? 'negative' : '');
      const sideCls = t.side.toLowerCase();
      const isOpt = t.instrument_type === 'OPTION';
      const optTypeCls = t.option_type ? (t.option_type === 'CE' ? 'call' : 'put') : 'equity';

      return `<tr>
        <td>
          <a class="ticker-link" target="_blank" rel="noopener noreferrer" href="https://in.tradingview.com/chart/?symbol=NSE:${encodeURIComponent(t.symbol)}">
            ${t.display_symbol || t.symbol} ↗
          </a>
        </td>
        <td>
          <span class="badge-inst-type ${optTypeCls}">
            ${isOpt ? (t.option_type === 'CE' ? '🟢 CE' : '🔴 PE') : '📈 CASH'}
          </span>
        </td>
        <td><span class="badge-side ${sideCls}">${t.side}</span></td>
        <td>
          <div class="price-cell">
            <strong>${t.quantity}</strong>
            ${isOpt ? `<div style="font-size: 0.7rem; color: var(--text-muted);">${t.contracts || 1}L × ${t.lot_size}</div>` : ''}
          </div>
        </td>
        <td class="price-cell">${App.Utils.money(t.entry_price)}</td>
        <td class="price-cell">${App.Utils.money(t.exit_price)}</td>
        <td class="date-cell">${(t.exit_time || '').split(' ')[0]}</td>
        <td class="price-cell ${pnlCls}"><strong>${App.Utils.money(t.pnl_amount)}</strong></td>
        <td class="price-cell ${pnlCls}">${App.Utils.formatPct(t.pnl_pct)}</td>
        <td class="date-cell">${t.holding_duration}</td>
        <td><span class="reason-pill">${t.exit_reason}</span></td>
        <td><span class="strategy-tag">${t.strategy}</span></td>
      </tr>`;
    }).join('');
  },

  initSubtabs() {
    const tabPos = document.querySelector('#paper-tab-positions');
    const tabHist = document.querySelector('#paper-tab-history');
    const viewPos = document.querySelector('#paper-view-positions');
    const viewHist = document.querySelector('#paper-view-history');

    if (tabPos && tabHist && viewPos && viewHist) {
      tabPos.addEventListener('click', () => {
        tabPos.classList.add('active');
        tabHist.classList.remove('active');
        viewPos.style.display = 'block';
        viewHist.style.display = 'none';
      });

      tabHist.addEventListener('click', () => {
        tabHist.classList.add('active');
        tabPos.classList.remove('active');
        viewHist.style.display = 'block';
        viewPos.style.display = 'none';
      });
    }
  },

  prefillOrder(symbol, price, strategy) {
    App.Router.switchTab('paper');
    this.switchInstrument('EQUITY');

    const stockInput = document.querySelector('#paper-stock-input');
    const priceInput = document.querySelector('#paper-price-input');
    const stratSelect = document.querySelector('#paper-strategy-select');

    if (stockInput) stockInput.value = symbol;
    if (priceInput && price > 0) priceInput.value = Number(price).toFixed(2);
    if (stratSelect && strategy) {
      for (let opt of stratSelect.options) {
        if (opt.value.toLowerCase().includes(strategy.toLowerCase()) || strategy.toLowerCase().includes(opt.value.toLowerCase())) {
          stratSelect.value = opt.value;
          break;
        }
      }
    }

    this.updateDefaultTargetAndSl(price);
    this.updateEstimatedCapital();
    this.fetchLivePriceOrPremium();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  },
};

// =====================================================================
// 7. Zerodha Live Stream Connector Module
// =====================================================================
App.Zerodha = {
  init() {
    const card = document.querySelector('#card-zerodha');
    const btnOpen = document.querySelector('#btn-zerodha-modal');
    const btnClose = document.querySelector('#btn-close-zerodha');
    const btnQuick = document.querySelector('#btn-quick-zd-connect');

    const toggle = (show) => {
      if (!card) return;
      const isShown = show !== undefined ? show : card.style.display === 'none';
      card.style.display = isShown ? 'block' : 'none';
      if (isShown) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };

    if (btnOpen) btnOpen.addEventListener('click', () => toggle());
    if (btnQuick) btnQuick.addEventListener('click', () => toggle(true));
    if (btnClose) btnClose.addEventListener('click', () => toggle(false));

    // Tab Switcher
    const tabEnc = document.querySelector('#zd-tab-enctoken');
    const tabApi = document.querySelector('#zd-tab-apikey');
    const formEnc = document.querySelector('#zd-form-enctoken');
    const formApi = document.querySelector('#zd-form-apikey');

    if (tabEnc && tabApi) {
      tabEnc.addEventListener('click', () => {
        tabEnc.classList.add('active');
        tabApi.classList.remove('active');
        if (formEnc) formEnc.style.display = 'block';
        if (formApi) formApi.style.display = 'none';
      });

      tabApi.addEventListener('click', () => {
        tabApi.classList.add('active');
        tabEnc.classList.remove('active');
        if (formApi) formApi.style.display = 'block';
        if (formEnc) formEnc.style.display = 'none';
      });
    }

    // Connect via Enctoken
    const btnSaveEnc = document.querySelector('#btn-save-zd-enctoken');
    if (btnSaveEnc) {
      btnSaveEnc.addEventListener('click', async () => {
        const userId = (document.querySelector('#zd-input-userid').value || '').trim();
        const enctoken = (document.querySelector('#zd-input-enctoken').value || '').trim();

        if (!userId || !enctoken) {
          App.Utils.showStatus('#zerodha-status-box', 'Please provide both Zerodha Client ID and Enctoken value.', 'error');
          return;
        }

        btnSaveEnc.disabled = true;
        btnSaveEnc.innerHTML = '<span>⏳ Connecting to Zerodha…</span>';

        try {
          const res = await fetch('/zerodha/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, enctoken: enctoken }),
          });

          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP Error ${res.status}`);
          }

          App.Utils.showStatus('#zerodha-status-box', `✅ Connected to Zerodha Web Stream for ${userId}!`, 'success');
          this.checkStatus();
          setTimeout(() => toggle(false), 1500);
        } catch (err) {
          App.Utils.showStatus('#zerodha-status-box', 'Zerodha connection failed: ' + err.message, 'error');
        } finally {
          btnSaveEnc.disabled = false;
          btnSaveEnc.innerHTML = '<span>⚡ Connect Live Feed</span>';
        }
      });
    }

    // Connect via Kite Developer API
    const btnSaveApi = document.querySelector('#btn-save-zd-apikey');
    if (btnSaveApi) {
      btnSaveApi.addEventListener('click', async () => {
        const apiKey = (document.querySelector('#zd-input-apikey').value || '').trim();
        const accessToken = (document.querySelector('#zd-input-accesstoken').value || '').trim();

        if (!apiKey || !accessToken) {
          App.Utils.showStatus('#zerodha-status-box', 'Please provide both Kite API Key and Access Token.', 'error');
          return;
        }

        btnSaveApi.disabled = true;
        btnSaveApi.innerHTML = '<span>⏳ Connecting API…</span>';

        try {
          const res = await fetch('/zerodha/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey, access_token: accessToken }),
          });

          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP Error ${res.status}`);
          }

          App.Utils.showStatus('#zerodha-status-box', '✅ Connected to Zerodha KiteConnect Developer API!', 'success');
          this.checkStatus();
          setTimeout(() => toggle(false), 1500);
        } catch (err) {
          App.Utils.showStatus('#zerodha-status-box', 'KiteConnect connection failed: ' + err.message, 'error');
        } finally {
          btnSaveApi.disabled = false;
          btnSaveApi.innerHTML = '<span>⚡ Connect API</span>';
        }
      });
    }

    this.checkStatus();
  },

  async checkStatus() {
    try {
      const res = await fetch('/zerodha/status');
      if (!res.ok) return;
      const data = await res.json();

      App.State.zerodhaConnected = data.connected;
      App.State.zerodhaUserId = data.user_id;
      App.State.zerodhaMethod = data.method;

      const zdBtnText = document.querySelector('#zerodha-btn-text');
      const feedDot = document.querySelector('#feed-source-dot');
      const feedLabel = document.querySelector('#feed-source-label');
      const quickBtn = document.querySelector('#btn-quick-zd-connect');

      if (data.connected) {
        if (zdBtnText) zdBtnText.textContent = `🟢 Zerodha (${data.user_id || 'Active'})`;
        if (feedDot) feedDot.classList.add('connected');
        if (feedLabel) feedLabel.innerHTML = `Market Feed: <strong style="color:#10b981;">🟢 Zerodha Live Stream</strong> (${data.method}${data.user_id ? ' · ' + data.user_id : ''})`;
        if (quickBtn) {
          quickBtn.classList.add('connected');
          quickBtn.innerHTML = `<span>🟢 Zerodha Connected</span>`;
        }
      } else {
        if (zdBtnText) zdBtnText.textContent = 'Zerodha Live Feed';
        if (feedDot) feedDot.classList.remove('connected');
        if (feedLabel) feedLabel.textContent = 'Market Feed: Real-Time NSE Spot Engine';
        if (quickBtn) {
          quickBtn.classList.remove('connected');
          quickBtn.innerHTML = `<span>🪁 Connect Zerodha Live Ticks</span>`;
        }
      }
    } catch (err) {
      console.debug('Zerodha status check error:', err);
    }
  },
};

// =====================================================================
// 8. Application Auto-Complete Datalist Manager & Bootstrapping
// =====================================================================
App.Init = {
  async bootstrap() {
    App.Router.init();
    App.Screener.init();
    App.News.init();
    App.Paper.init();
    App.Zerodha.init();

    await this.populateDatalists();
    App.Screener.fetchSignals();
  },

  async populateDatalists() {
    try {
      const res = await fetch('/signals/today');
      if (!res.ok) return;
      const data = await res.json();
      const symbols = (data.signals || []).map(s => s.symbol).filter(Boolean);
      const uniqueSymbols = Array.from(new Set(symbols));

      const datalists = [
        '#lookback-stocks-datalist',
        '#paper-stocks-datalist',
        '#news-stocks-datalist',
      ];

      datalists.forEach(id => {
        const el = document.querySelector(id);
        if (el && uniqueSymbols.length) {
          el.innerHTML = uniqueSymbols.map(sym => `<option value="${sym}"></option>`).join('');
        }
      });
    } catch (err) {
      console.debug('Datalists load error:', err);
    }
  },
};

// Initialize on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  App.Init.bootstrap();
});
