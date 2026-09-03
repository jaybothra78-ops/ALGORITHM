/**
 * ALGORYTHM Institutional Trading Platform - Modular Frontend Architecture
 * Namespaces: App.State, App.Utils, App.Screener, App.News, App.Paper, App.Zerodha, App.Init
 */
'use strict';

const App = window.App = window.App || {};

// Global Article Action Handlers
window.selectArticle = function(idx) {
  if (window.App && window.App.News) {
    window.App.News.selectArticle(idx);
  }
};
window.switchTerminalTab = function(tab) {
  if (window.App && window.App.News) {
    window.App.News.switchTerminalTab(tab);
  }
};
window.askTerminalQuestion = function(q) {
  if (window.App && window.App.News) {
    window.App.News.askTerminalQuestion(q);
  }
};
window.submitTerminalChat = function() {
  if (window.App && window.App.News) {
    window.App.News.submitTerminalChat();
  }
};




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
      'tab-backtest': 'section-backtest',
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
    } else if (tabName === 'backtest') {
      if (App.Backtester) App.Backtester.initOnce();
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
      const price = s.close_price != null ? s.close_price : (s.current_price != null ? s.current_price : 0);
      const sigType = (s.signal_type || s.primary_type || 'neutral').toLowerCase();
      const universe = s.universe || s.index_membership || 'NSE';
      const strat = s.strategy || (s.is_knox_divergence ? 'Knoxville' : 'RSI');
      const dateVal = s.scan_date || s.signal_date || 'Today';

      const rsiVal = s.rsi != null ? Number(s.rsi).toFixed(1) : '—';
      const rsiCls = s.rsi != null && s.rsi <= 30 ? 'oversold' : (s.rsi != null && s.rsi >= 70 ? 'overbought' : '');
      const knoxTag = s.is_knox_divergence ? '<span class="badge-knox">⚡ KNOXVILLE</span>' : '—';
      const ma200Tag = s.is_touching_200sma ? '<span class="badge-ma200">📈 200 SMA</span>' : '—';

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
        <td><span class="universe-cell">${universe}</span></td>
        <td><span class="badge badge-${sigType}">${sigType.toUpperCase()}</span></td>
        <td class="price-cell">${App.Utils.money(price)}</td>
        <td><span class="rsi-cell ${rsiCls}">${rsiVal}</span></td>
        <td>${knoxTag}</td>
        <td>${ma200Tag}</td>
        <td class="date-cell">${dateVal}</td>
        <td>
          <div class="row-action-btns">
            <button class="btn-table-action" onclick="App.Paper.prefillOrder('${s.symbol}', ${price}, '${strat}')" title="Place Paper Trade">
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
      App.State.customWatchlists = data.watchlists || [];
      const tagsContainer = document.querySelector('#custom-lists-tags');
      const lookbackSelect = document.querySelector('#lookback-index');
      const newsUniverseSelect = document.querySelector('#news-universe-filter');

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

      // Populate both Screener dropdown and News Analyzer universe dropdown
      [lookbackSelect, newsUniverseSelect].forEach(select => {
        if (!select || !data.watchlists) return;
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
      });
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
  _stepTimers: [],

  init() {
    const btnRun = document.querySelector('#btn-run-news');
    const btnSample = document.querySelector('#btn-trigger-sample-news');
    const stockSelect = document.querySelector('#news-stock-select');
    const customInput = document.querySelector('#news-custom-input');
    const universeFilter = document.querySelector('#news-universe-filter');

    // Stock dropdown sync with input
    if (stockSelect && customInput) {
      stockSelect.addEventListener('change', () => {
        customInput.value = stockSelect.value;
      });
    }

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

    // Custom input enter key
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

    // Enter key support for Terminal Chat
    const chatInput = document.querySelector('#terminal-chat-input');
    if (chatInput) {
      chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.submitTerminalChat();
        }
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
      const stockSelect = document.querySelector('#news-stock-select');
      const customInput = document.querySelector('#news-custom-input');
      if (!stockSelect) return;

      let symbols = [];

      // 1. Check if custom watchlist selected
      if (universe && universe.startsWith('custom:')) {
        const customName = universe.replace('custom:', '').trim();
        const found = (App.State.customWatchlists || []).find(w => w.name === customName);
        if (found && found.symbols && found.symbols.length) {
          symbols = found.symbols;
        }
      }

      // 2. Otherwise use universe symbols list or fetch from API
      if (!symbols.length) {
        if (App.State.universeSymbols && App.State.universeSymbols.length) {
          if (!universe) {
            symbols = App.State.universeSymbols.map(u => u.symbol);
          } else {
            symbols = App.State.universeSymbols
              .filter(u => (u.membership || []).includes(universe))
              .map(u => u.symbol);
          }
        } else {
          const res = await fetch('/universe/symbols');
          if (res.ok) {
            const allSymbols = await res.json();
            App.State.universeSymbols = allSymbols;
            if (!universe) {
              symbols = allSymbols.map(u => u.symbol);
            } else {
              symbols = allSymbols
                .filter(u => (u.membership || []).includes(universe))
                .map(u => u.symbol);
            }
          }
        }
      }

      // 3. Fallback to common F&O if still empty
      if (!symbols.length) {
        symbols = ['TVSMOTOR', 'RELIANCE', 'TRENT', 'TATAMOTORS', 'HDFCBANK', 'INFY', 'IDFCFIRSTB'];
      }

      stockSelect.innerHTML = symbols.map(s => `<option value="${s}">${s}</option>`).join('');
      if (customInput) customInput.value = symbols[0];
    } catch (err) {
      console.debug('Failed to populate news stocks:', err);
    }
  },


  clearLoadingSteps() {
    this._stepTimers.forEach(t => clearTimeout(t));
    this._stepTimers = [];
    ['#step-1', '#step-2', '#step-3', '#step-4'].forEach(id => {
      const el = document.querySelector(id);
      if (el) el.classList.remove('active', 'completed');
    });
  },

  animateLoadingSteps() {
    this.clearLoadingSteps();
    const steps = ['#step-1', '#step-2', '#step-3', '#step-4'];
    steps.forEach((id, idx) => {
      const timer = setTimeout(() => {
        const el = document.querySelector(id);
        if (el) {
          if (idx > 0) {
            const prev = document.querySelector(steps[idx - 1]);
            if (prev) {
              prev.classList.remove('active');
              prev.classList.add('completed');
            }
          }
          el.classList.add('active');
        }
      }, idx * 600);
      this._stepTimers.push(timer);
    });
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

    // Start progress animation
    this.animateLoadingSteps();

    try {
      const res = await fetch(`/news/analyze?symbol=${encodeURIComponent(symbol)}`);
      if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
      const data = await res.json();

      this.clearLoadingSteps();
      this.renderReport(data);

      if (loadingCard) loadingCard.style.display = 'none';
      if (contentCard) {
        contentCard.style.display = 'block';
        contentCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    } catch (err) {
      this.clearLoadingSteps();
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
      const iconEl = sentimentBadge.querySelector('.sentiment-icon');
      if (iconEl) {
        iconEl.textContent = sent === 'bullish' ? '🟢' : (sent === 'bearish' ? '🔴' : '🟡');
      }
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

    // Headlines Master List & Dedicated AI Terminal
    const articlesList = document.querySelector('#news-articles-list');
    const articlesCount = document.querySelector('#ai-articles-count');
    if (articlesCount) articlesCount.textContent = `${(data.articles || []).length} articles`;

    if (articlesList) {
      App.State.currentArticles = data.articles || [];
      App.News._articleCache = {}; // reset cache for new stock

      if (!data.articles || !data.articles.length) {
        articlesList.innerHTML = '<div class="empty-cell" style="padding: 30px 15px; text-align: center; color: #64748b;">No recent news articles found for this ticker.</div>';
        const emptyState = document.querySelector('#terminal-empty-state');
        const termContent = document.querySelector('#terminal-content');
        if (emptyState) emptyState.style.display = 'flex';
        if (termContent) termContent.style.display = 'none';
      } else {
        articlesList.innerHTML = data.articles.map((a, idx) => `
          <div class="article-list-item" id="art-item-${idx}" onclick="App.News.selectArticle(${idx})">
            <div class="item-meta">
              <span class="item-publisher">${a.publisher || 'Financial Media'}</span>
              <span class="item-date">${a.published_at || 'Recent'}</span>
            </div>
            <h5 class="item-title">${a.title}</h5>
            <div class="item-click-hint">
              <span class="item-ai-tag">⚡ Inspect AI Analysis</span>
              <span>→</span>
            </div>
          </div>
        `).join('');

        // Auto-select the first article so the user immediately gets a sleek, zero-clutter view!
        this.selectArticle(0);
      }
    }
  },

  _articleCache: {},

  async selectArticle(idx) {
    const articles = App.State.currentArticles || [];
    const article = articles[idx];
    if (!article) return;

    App.State.selectedArticleIndex = idx;

    // Highlight selected item in list
    document.querySelectorAll('.article-list-item').forEach(el => el.classList.remove('selected'));
    const selectedEl = document.querySelector(`#art-item-${idx}`);
    if (selectedEl) selectedEl.classList.add('selected');

    // Show terminal content
    const emptyState = document.querySelector('#terminal-empty-state');
    const termContent = document.querySelector('#terminal-content');
    if (emptyState) emptyState.style.display = 'none';
    if (termContent) termContent.style.display = 'flex';

    // Populate header info
    const titleEl = document.querySelector('#terminal-title');
    const pubEl = document.querySelector('#terminal-publisher');
    const dateEl = document.querySelector('#terminal-date');
    const linkEl = document.querySelector('#terminal-source-link');
    const sentEl = document.querySelector('#terminal-sentiment');

    if (titleEl) titleEl.textContent = article.title;
    if (pubEl) pubEl.textContent = article.publisher || 'Financial Media';
    if (dateEl) dateEl.textContent = article.published_at || 'Recent';
    if (linkEl) linkEl.href = article.link || '#';

    // Reset Chat messages thread with welcome msg
    const chatMessages = document.querySelector('#terminal-chat-messages');
    if (chatMessages) {
      chatMessages.innerHTML = `
        <div class="chat-msg ai-msg">
          <div class="msg-avatar">🤖</div>
          <div class="msg-bubble">Ask me anything about <strong>${article.title}</strong>, financial growth impacts, or immediate trading setups!</div>
        </div>
      `;
    }

    // Check cache or fetch
    let data = this._articleCache[article.title];
    if (!data) {
      const summaryText = document.querySelector('#terminal-summary-text');
      const bulletsList = document.querySelector('#terminal-bullets-list');
      if (summaryText) summaryText.innerHTML = `<em>⚡ Synthesizing 100-150 word institutional breakdown...</em>`;
      if (bulletsList) bulletsList.innerHTML = `<li>Loading key catalysts and impact metrics...</li>`;

      try {
        const symbol = App.State.activeNewsTicker || 'TVSMOTOR';
        const res = await fetch('/news/article-chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol: symbol,
            article_title: article.title,
            article_summary: article.summary,
            article_link: article.link,
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        data = await res.json();
        this._articleCache[article.title] = data;
      } catch (err) {
        if (summaryText) summaryText.innerHTML = `<span style="color: #f43f5e;">⚠️ Failed to load analysis: ${err.message}</span>`;
        return;
      }
    }

    // Populate loaded data
    if (sentEl) {
      const s = (data.sentiment || 'Bullish').toLowerCase();
      sentEl.className = `sentiment-badge-pill ${s}`;
      sentEl.textContent = `${data.sentiment || 'Bullish'} (${data.confidence_score || 80}%)`;
    }

    const summaryText = document.querySelector('#terminal-summary-text');
    if (summaryText) summaryText.textContent = data.short_analysis;

    const bulletsList = document.querySelector('#terminal-bullets-list');
    if (bulletsList) {
      bulletsList.innerHTML = (data.bullet_points || []).map(b => `<li>${b}</li>`).join('');
    }

    // Ensure currently selected tab view is displayed
    const currentTab = App.State.terminalActiveTab || 'summary';
    this.switchTerminalTab(currentTab);
  },

  switchTerminalTab(tabName) {
    App.State.terminalActiveTab = tabName;

    // Update nav pills
    ['summary', 'bullets', 'chat'].forEach(tab => {
      const pill = document.querySelector(`#term-pill-${tab}`);
      const view = document.querySelector(`#term-view-${tab}`);
      if (pill) pill.classList.toggle('active', tab === tabName);
      if (view) view.style.display = tab === tabName ? 'block' : 'none';
    });
  },

  askTerminalQuestion(question) {
    const input = document.querySelector('#terminal-chat-input');
    if (input) input.value = question;
    this.submitTerminalChat();
  },

  async submitTerminalChat() {
    const symbol = App.State.activeNewsTicker || 'TVSMOTOR';
    const idx = App.State.selectedArticleIndex || 0;
    const articles = App.State.currentArticles || [];
    const article = articles[idx] || {
      title: `${symbol} Corporate News & Momentum`,
      summary: `Recent market filings and sentiment developments for ${symbol}.`,
      link: ''
    };

    const input = document.querySelector('#terminal-chat-input');
    const thread = document.querySelector('#terminal-chat-messages');
    const q = input ? input.value.trim() : '';
    if (!q || !thread) return;

    input.value = '';

    thread.innerHTML += `
      <div class="chat-msg user-msg">
        <div class="msg-bubble">${this.escapeHtml(q)}</div>
      </div>
      <div class="chat-msg ai-msg term-typing">
        <div class="msg-avatar">🤖</div>
        <div class="msg-bubble thinking-bubble">
          <div class="thinking-header">
            <span class="pulse-dot"></span>
            <strong>Analyzing &amp; thinking...</strong>
          </div>
          <div class="thinking-subtext">Evaluating news facts, valuation multiples, and risk-reward profile for ${symbol}</div>
        </div>
      </div>
    `;
    thread.scrollTop = thread.scrollHeight;

    try {
      const res = await fetch('/news/article-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: symbol,
          article_title: article.title,
          article_summary: article.summary,
          article_link: article.link,
          user_question: q,
          api_key: localStorage.getItem('claude_api_key') || '',
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const typing = thread.querySelector('.term-typing');
      if (typing) typing.remove();

      // Render Thought Process if available
      let thoughtHtml = '';
      const thoughts = Array.isArray(data.thinking) ? data.thinking : [];
      if (thoughts.length) {
        thoughtHtml = `
          <details class="thought-box" open>
            <summary class="thought-summary">
              <span class="thought-icon">💭</span>
              <span>Thought Process (${thoughts.length} steps)</span>
            </summary>
            <ul class="thought-list">
              ${thoughts.map(t => `<li>${this.escapeHtml(t)}</li>`).join('')}
            </ul>
          </details>
        `;
      }

      const answerText = data.answer || data.short_analysis || 'Analysis complete.';
      const formattedAnswer = this.formatMarkdown(answerText);

      thread.innerHTML += `
        <div class="chat-msg ai-msg">
          <div class="msg-avatar">🤖</div>
          <div class="msg-bubble">
            ${thoughtHtml}
            <div class="ai-answer-body">${formattedAnswer}</div>
          </div>
        </div>
      `;
      thread.scrollTop = thread.scrollHeight;
    } catch (err) {
      const typing = thread.querySelector('.term-typing');
      if (typing) typing.remove();
      thread.innerHTML += `
        <div class="chat-msg ai-msg">
          <div class="msg-avatar">⚠️</div>
          <div class="msg-bubble" style="color: #f43f5e;">Error: ${this.escapeHtml(err.message)}</div>
        </div>
      `;
      thread.scrollTop = thread.scrollHeight;
    }
  },

  escapeHtml(text) {
    if (!text) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  },

  formatMarkdown(md) {
    if (!md) return '';
    let html = md
      .replace(/^### (.*$)/gim, '<h5 class="ai-ans-h5">$1</h5>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/^[•\-] (.*$)/gim, '<div class="ai-ans-bullet"><span class="bullet-dot">•</span><span>$1</span></div>')
      .replace(/\n\n/g, '<div class="ai-ans-gap"></div>');
    return html;
  },


  copyTerminalSummary() {
    const textEl = document.querySelector('#terminal-summary-text');
    const btn = document.querySelector('#btn-copy-terminal');
    if (!textEl) return;
    const text = textEl.textContent || '';
    navigator.clipboard.writeText(text).then(() => {
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = '<span>✅ Copied!</span>';
        setTimeout(() => { btn.innerHTML = orig; }, 2000);
      }
    }).catch(err => {
      console.warn('Copy failed:', err);
    });
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
          localStorage.setItem('claude_api_key', key);
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
        localStorage.removeItem('claude_api_key');
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
// 7. Strategy Tester & Quantitative Backtest Engine Module
// =====================================================================
App.Backtester = {
  _initialized: false,
  _currentTrades: [],
  _selectedTradeIndex: 0,
  _activeStrategy: 'RB_KnoxDiv',
  _activePeriod: '1y',

  init() {
    if (this._initialized) return;
    this._initialized = true;

    // Strategy selector pills
    document.querySelectorAll('#backtest-strategy-group .pill').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#backtest-strategy-group .pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this._activeStrategy = btn.dataset.strategy || 'RB_KnoxDiv';
        this.runBacktest();
      });
    });

    // Time Horizon period pills
    document.querySelectorAll('#backtest-period-group .pill').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#backtest-period-group .pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this._activePeriod = btn.dataset.period || '1y';

        // Clear custom date inputs so preset period is cleanly used
        const sInput = document.querySelector('#backtest-start-date');
        const eInput = document.querySelector('#backtest-end-date');
        if (sInput) sInput.value = '';
        if (eInput) eInput.value = '';

        this.runBacktest();
      });
    });

    // Custom Date Range inputs -> de-activate period pills & auto re-run
    const startDateInput = document.querySelector('#backtest-start-date');
    const endDateInput = document.querySelector('#backtest-end-date');
    if (startDateInput) {
      startDateInput.addEventListener('change', () => {
        document.querySelectorAll('#backtest-period-group .pill').forEach(b => b.classList.remove('active'));
        this.runBacktest();
      });
    }
    if (endDateInput) {
      endDateInput.addEventListener('change', () => {
        document.querySelectorAll('#backtest-period-group .pill').forEach(b => b.classList.remove('active'));
        this.runBacktest();
      });
    }

    // Universe/Watchlist dropdown change -> populate stock dropdown & reset specific stock
    const univSelect = document.querySelector('#backtest-universe-select');
    const stockSelect = document.querySelector('#backtest-stock-select');
    const customInput = document.querySelector('#backtest-custom-input');

    if (univSelect) {
      univSelect.addEventListener('change', () => {
        if (customInput) customInput.value = '';
        if (stockSelect) stockSelect.value = '';
        this.populateStockSelect(univSelect.value);
        this.runBacktest();
      });
    }

    // Specific stock dropdown change -> clear custom input & auto-run
    if (stockSelect) {
      stockSelect.addEventListener('change', () => {
        if (customInput) customInput.value = '';
        this.runBacktest();
      });
    }

    // Input on custom ticker -> clear stock select
    if (customInput) {
      customInput.addEventListener('input', () => {
        if (stockSelect) stockSelect.value = '';
      });
      customInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.runBacktest();
        }
      });
    }

    // Direction change -> auto re-run
    const directionSelect = document.querySelector('#backtest-direction-select');
    if (directionSelect) {
      directionSelect.addEventListener('change', () => {
        this.runBacktest();
      });
    }

    this.populateUniverseSelect();
    this.populateStockSelect('');
  },

  clearDateRange() {
    const startDateInput = document.querySelector('#backtest-start-date');
    const endDateInput = document.querySelector('#backtest-end-date');
    if (startDateInput) startDateInput.value = '';
    if (endDateInput) endDateInput.value = '';

    this._activePeriod = '1y';
    document.querySelectorAll('#backtest-period-group .pill').forEach(b => {
      b.classList.toggle('active', b.dataset.period === '1y');
    });
    this.runBacktest();
  },



  initOnce() {
    this.init();
    this.populateUniverseSelect();
  },

  populateUniverseSelect() {
    const select = document.querySelector('#backtest-universe-select');
    if (!select) return;

    let html = `
      <option value="">All Universes (Combined)</option>
      <option value="FNO">FNO (178 Stocks)</option>
      <option value="Watchlist">Default Watchlist (108 Stocks)</option>
      <option value="Nifty50">Nifty 50 Index</option>
    `;

    const customLists = App.State.customWatchlists || [];
    if (customLists.length) {
      html += `<optgroup label="⭐ Your Custom Watchlists">`;
      customLists.forEach(cw => {
        html += `<option value="custom:${cw.name}">⭐ ${cw.name} (${(cw.symbols || []).length} Stocks)</option>`;
      });
      html += `</optgroup>`;
    }

    select.innerHTML = html;
  },

  async populateStockSelect(universe) {
    const stockSelect = document.querySelector('#backtest-stock-select');
    if (!stockSelect) return;

    let symbols = [];

    if (universe && universe.startsWith('custom:')) {
      const customName = universe.replace('custom:', '').trim();
      const found = (App.State.customWatchlists || []).find(w => w.name === customName);
      if (found && found.symbols && found.symbols.length) {
        symbols = found.symbols;
      }
    } else if (universe) {
      symbols = (App.State.universeSymbols || [])
        .filter(s => Array.isArray(s.indices) && s.indices.includes(universe))
        .map(s => s.symbol);
    }

    if (!symbols.length) {
      symbols = (App.State.universeSymbols || []).map(s => s.symbol);
    }

    const uniqueSymbols = Array.from(new Set(symbols)).sort();

    stockSelect.innerHTML = `
      <option value="">-- All Stocks in Watchlist (${uniqueSymbols.length}) --</option>
      ${uniqueSymbols.map(s => `<option value="${s}">${s}</option>`).join('')}
    `;
  },

  quickPickStock(symbol) {
    const customInput = document.querySelector('#backtest-custom-input');
    const stockSelect = document.querySelector('#backtest-stock-select');
    if (stockSelect) stockSelect.value = '';
    if (customInput) customInput.value = symbol;
    this.runBacktest();
  },

  quickPickUniverse(univName) {
    const univSelect = document.querySelector('#backtest-universe-select');
    const stockSelect = document.querySelector('#backtest-stock-select');
    const customInput = document.querySelector('#backtest-custom-input');
    if (stockSelect) stockSelect.value = '';
    if (customInput) customInput.value = '';

    if (univSelect) {
      const match = Array.from(univSelect.options).find(o => o.value.includes(univName) || o.text.includes(univName));
      if (match) {
        univSelect.value = match.value;
        this.populateStockSelect(match.value);
      }
    }
    this.runBacktest();
  },


  async runBacktest() {
    const univSelect = document.querySelector('#backtest-universe-select');
    const stockSelect = document.querySelector('#backtest-stock-select');
    const customInput = document.querySelector('#backtest-custom-input');

    const targetInput = document.querySelector('#backtest-target-pct');
    const stopLossInput = document.querySelector('#backtest-stoploss-pct');
    const directionSelect = document.querySelector('#backtest-direction-select');

    const customTicker = customInput ? customInput.value.trim().toUpperCase() : '';
    const selectedStock = stockSelect ? stockSelect.value.trim().toUpperCase() : '';
    const symbolToTest = customTicker || selectedStock || null;

    const universe = (univSelect && !symbolToTest) ? univSelect.value : null;
    const strategy = this._activeStrategy || 'RB_KnoxDiv';

    const targetPct = targetInput ? parseFloat(targetInput.value) || 5.0 : 5.0;
    const stopLossPct = stopLossInput ? parseFloat(stopLossInput.value) || 3.0 : 3.0;
    const signalType = directionSelect ? directionSelect.value || null : null;

    const runBtn = document.querySelector('#btn-run-backtest');
    const tradesList = document.querySelector('#backtest-trades-list');
    const tradesCount = document.querySelector('#backtest-trades-count');
    const universeBadge = document.querySelector('#bt-universe-badge');

    if (runBtn) {
      runBtn.disabled = true;
      runBtn.innerHTML = `<span>⏳ Simulating Trades...</span>`;
    }

    if (tradesList) {
      tradesList.innerHTML = `
        <div class="empty-cell" style="padding: 40px 15px; text-align: center;">
          <div class="pulse-dot" style="margin: 0 auto 12px auto;"></div>
          <p style="color: #a5b4fc;">Simulating strategy across historical OHLC candles...</p>
        </div>
      `;
    }

    try {
      const startDateInput = document.querySelector('#backtest-start-date');
      const endDateInput = document.querySelector('#backtest-end-date');
      const startDate = startDateInput ? startDateInput.value.trim() || null : null;
      const endDate = endDateInput ? endDateInput.value.trim() || null : null;
      const period = this._activePeriod || '1y';

      const payload = {
        symbol: symbolToTest,
        index: universe,
        strategy: strategy,
        target_pct: targetPct,
        stop_loss_pct: stopLossPct,
        signal_type: signalType,
        period: period,
        start_date: startDate,
        end_date: endDate,
      };


      const res = await fetch('/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });


      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      this._currentTrades = data.trades || [];
      App.State.backtestSummary = data.summary;

      // Update KPI Banner
      const s = data.summary || {};
      const elTotal = document.querySelector('#bt-kpi-total-trades');
      const elWin = document.querySelector('#bt-kpi-win-rate');
      const elWinSub = document.querySelector('#bt-kpi-win-sub');
      const elPF = document.querySelector('#bt-kpi-profit-factor');
      const elNet = document.querySelector('#bt-kpi-net-return');
      const elDD = document.querySelector('#bt-kpi-max-drawdown');
      const elDays = document.querySelector('#bt-kpi-avg-days');

      if (elTotal) elTotal.textContent = s.total_trades || 0;
      if (elWin) {
        const wr = s.win_rate_pct !== undefined ? s.win_rate_pct : 0;
        elWin.textContent = `${wr.toFixed(1)}%`;
        elWin.style.color = wr >= 55 ? '#10b981' : (wr >= 45 ? '#f59e0b' : '#f43f5e');
      }
      if (elWinSub) elWinSub.textContent = `${s.winning_trades || 0}W / ${s.losing_trades || 0}L`;
      if (elPF) {
        const pf = s.profit_factor !== undefined ? s.profit_factor : 0;
        elPF.textContent = pf.toFixed(2);
        elPF.style.color = pf >= 1.5 ? '#10b981' : (pf >= 1.0 ? '#f59e0b' : '#f43f5e');
      }
      if (elNet) {
        const nr = s.net_return_pct !== undefined ? s.net_return_pct : 0;
        elNet.textContent = `${nr >= 0 ? '+' : ''}${nr.toFixed(1)}%`;
        elNet.style.color = nr >= 0 ? '#10b981' : '#f43f5e';
      }
      if (elDD) elDD.textContent = `${(s.max_drawdown_pct || 0).toFixed(1)}%`;
      if (elDays) elDays.textContent = `${(s.avg_holding_days || 0).toFixed(1)} days`;

      if (tradesCount) tradesCount.textContent = `${this._currentTrades.length} trades`;
      if (universeBadge) universeBadge.textContent = `${s.universe || 'Completed'} (${data.execution_time_ms}ms)`;

      // Render Trade Cards
      if (!this._currentTrades.length) {
        if (tradesList) {
          tradesList.innerHTML = `<div class="empty-cell" style="padding: 40px 15px; text-align: center; color: #64748b;">No trades triggered matching the selected strategy and filter parameters.</div>`;
        }
        this.renderEmptyDiagnostic();
      } else {
        if (tradesList) {
          tradesList.innerHTML = this._currentTrades.map((t, idx) => {
            const isWin = t.outcome === 'WIN';
            const isBuy = t.signal_type.toLowerCase() === 'buy';
            const pnlFormatted = `${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%`;
            return `
              <div class="article-list-item ${idx === 0 ? 'selected' : ''}" id="bt-trade-item-${idx}" onclick="App.Backtester.selectTrade(${idx})">
                <div class="item-meta">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <strong style="color: #fff; font-size: 0.92rem;">${t.symbol}</strong>
                    <span class="badge ${isBuy ? 'badge-bullish' : 'badge-bearish'}">${isBuy ? 'BUY' : 'SELL'}</span>
                  </div>
                  <span class="badge ${isWin ? 'badge-bullish' : 'badge-bearish'}" style="font-size: 0.82rem; font-weight: 800;">${pnlFormatted}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.76rem; color: #94a3b8; margin-top: 4px;">
                  <span>${t.strategy} • ${t.exit_reason}</span>
                  <span style="color: #64748b;">${t.entry_date}</span>
                </div>
              </div>
            `;
          }).join('');
        }

        // Auto-select first trade
        this.selectTrade(0);
      }

      // Also render Analytics Tab
      this.renderAnalyticsTab(s);

    } catch (err) {
      if (tradesList) {
        tradesList.innerHTML = `<div class="empty-cell" style="padding: 40px 15px; text-align: center; color: #f43f5e;">Backtest failed: ${err.message}</div>`;
      }
    } finally {
      if (runBtn) {
        runBtn.disabled = false;
        runBtn.innerHTML = `<span>🚀 Run Backtest</span>`;
      }
    }
  },

  selectTrade(idx) {
    this._selectedTradeIndex = idx;
    const trades = this._currentTrades || [];
    const t = trades[idx];
    if (!t) return;

    document.querySelectorAll('#backtest-trades-list .article-list-item').forEach(el => el.classList.remove('selected'));
    const selectedEl = document.querySelector(`#bt-trade-item-${idx}`);
    if (selectedEl) selectedEl.classList.add('selected');


    const diagView = document.querySelector('#bt-selected-trade-view');
    const titleEl = document.querySelector('#bt-inspect-title');
    const subEl = document.querySelector('#bt-inspect-sub');

    if (titleEl) titleEl.textContent = `${t.symbol} • ${t.strategy} (${t.signal_type.toUpperCase()})`;
    if (subEl) subEl.textContent = `Entry: ${t.entry_date} @ ₹${t.entry_price.toFixed(2)} → Exit: ${t.exit_date} @ ₹${t.exit_price.toFixed(2)}`;

    const isWin = t.outcome === 'WIN';
    const isBuy = t.signal_type.toLowerCase() === 'buy';

    if (diagView) {
      diagView.innerHTML = `
        <!-- Minimalist Visual Timeline -->
        <div class="inspect-timeline">
          <div class="timeline-step">
            <div class="step-circle done">✓</div>
            <div class="step-name">Signal</div>
            <div style="font-size: 0.65rem; color: #64748b;">${t.signal_date}</div>
          </div>
          <div class="timeline-connector"></div>
          <div class="timeline-step">
            <div class="step-circle done">✓</div>
            <div class="step-name">Confirmed</div>
            <div style="font-size: 0.65rem; color: #64748b;">Next Day</div>
          </div>
          <div class="timeline-connector"></div>
          <div class="timeline-step">
            <div class="step-circle done">₹</div>
            <div class="step-name">Open</div>
            <div style="font-size: 0.65rem; color: #64748b;">${t.entry_date}</div>
          </div>
          <div class="timeline-connector"></div>
          <div class="timeline-step">
            <div class="step-circle" style="border-color: ${isWin ? '#10b981' : '#f43f5e'}; color: ${isWin ? '#10b981' : '#f43f5e'};">
              ${isWin ? '🎯' : '🛑'}
            </div>
            <div class="step-name" style="color: ${isWin ? '#10b981' : '#f43f5e'};">${t.exit_reason}</div>
            <div style="font-size: 0.65rem; color: #64748b;">${t.exit_date}</div>
          </div>
        </div>

        <!-- 3 Performance Metric Cards -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px;">
          <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 12px; text-align: center;">
            <div style="font-size: 0.68rem; color: #94a3b8; text-transform: uppercase;">OUTCOME</div>
            <div style="font-size: 1.15rem; font-weight: 800; color: ${isWin ? '#10b981' : '#f43f5e'}; margin-top: 2px;">${t.outcome}</div>
            <div style="font-size: 0.72rem; color: #cbd5e1;">${t.exit_reason}</div>
          </div>
          <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 12px; text-align: center;">
            <div style="font-size: 0.68rem; color: #94a3b8; text-transform: uppercase;">NET RETURN</div>
            <div style="font-size: 1.15rem; font-weight: 800; color: ${isWin ? '#10b981' : '#f43f5e'}; margin-top: 2px;">${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%</div>
            <div style="font-size: 0.72rem; color: #cbd5e1;">₹${(t.pnl_amount >= 0 ? '+' : '')}${t.pnl_amount.toFixed(2)} / share</div>
          </div>
          <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 12px; text-align: center;">
            <div style="font-size: 0.68rem; color: #94a3b8; text-transform: uppercase;">HOLDING TIME</div>
            <div style="font-size: 1.15rem; font-weight: 800; color: #38bdf8; margin-top: 2px;">${t.holding_days} Days</div>
            <div style="font-size: 0.72rem; color: #cbd5e1;">${t.entry_date} to ${t.exit_date}</div>
          </div>
        </div>

        <!-- Execution Levels Table -->
        <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 14px; margin-bottom: 16px;">
          <h5 style="color: #cbd5e1; font-size: 0.82rem; margin-bottom: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;">Price Execution Levels</h5>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.82rem;">
            <div><span style="color: #94a3b8;">Entry Price:</span> <strong style="color: #fff;">₹${t.entry_price.toFixed(2)}</strong></div>
            <div><span style="color: #94a3b8;">Exit Price:</span> <strong style="color: #fff;">₹${t.exit_price.toFixed(2)}</strong></div>
            <div><span style="color: #94a3b8;">Target Level:</span> <strong style="color: #10b981;">₹${(t.target_price || 0).toFixed(2)}</strong></div>
            <div><span style="color: #94a3b8;">Stop Loss Level:</span> <strong style="color: #f43f5e;">₹${(t.stop_loss_price || 0).toFixed(2)}</strong></div>
            <div><span style="color: #94a3b8;">Signal Date:</span> <span style="color: #cbd5e1;">${t.signal_date}</span></div>
            <div><span style="color: #94a3b8;">Confirmation:</span> <span style="color: #10b981;">✅ Verified Next Day</span></div>
          </div>
        </div>

        <!-- 1-Click Bridge Actions -->
        <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px;">
          <button type="button" class="btn-subtle" style="background: rgba(99, 102, 241, 0.2); border-color: #6366f1; color: #a5b4fc; font-weight: 700;" onclick="App.Backtester.switchInspectorTab('chart')">
            🕯️ View Exact Candle Chart
          </button>
          <button type="button" class="btn-subtle" onclick="App.Backtester.openTradingViewWithDate()">
            📈 Open on TradingView (Alt+G Date Copied) ↗
          </button>
          <button type="button" class="btn-subtle" onclick="App.Backtester.sendToPaperTrading('${t.symbol}', '${t.signal_type}', ${t.entry_price}, ${t.target_price || 0}, ${t.stop_loss_price || 0})">
            💼 Place Paper Trade
          </button>
          <button type="button" class="btn-subtle" onclick="App.Backtester.sendToNewsAnalyzer('${t.symbol}')">
            📰 AI News Sentiment
          </button>
          <a href="https://www.screener.in/company/${t.symbol}/consolidated/" target="_blank" class="btn-subtle" style="text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">
            📊 Screener.in ↗
          </a>
        </div>
      `;
    }

    // If currently on chart tab, refresh chart to this trade
    if (this._activeInspectorTab === 'chart') {
      this.renderCandleChart();
    }
  },

  switchInspectorTab(tab) {
    this._activeInspectorTab = tab;
    document.querySelectorAll('.terminal-header-bar .term-pill').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.term-tab-pane').forEach(p => (p.style.display = 'none'));

    const btn = document.querySelector(`#btn-bt-tab-${tab}`);
    const pane = document.querySelector(`#bt-pane-${tab}`);
    if (btn) btn.classList.add('active');
    if (pane) pane.style.display = 'block';

    if (tab === 'chart') {
      this.renderCandleChart();
    }
  },

  async renderCandleChart() {
    const trades = this._currentTrades || [];
    const t = trades[this._selectedTradeIndex];
    if (!t) return;

    const titleEl = document.querySelector('#bt-chart-trade-title');
    const badgeEl = document.querySelector('#bt-chart-trade-badge');
    const loadingEl = document.querySelector('#bt-chart-loading');
    const container = document.querySelector('#bt-trade-chart-container');

    const isBuy = t.signal_type.toLowerCase() === 'buy';

    if (titleEl) {
      titleEl.innerHTML = `<strong>${t.symbol}</strong> • ${t.strategy} <span style="color: #94a3b8; font-weight: normal; font-size: 0.8rem;">(Entry: ${t.entry_date} @ ₹${t.entry_price.toFixed(2)})</span>`;
    }
    if (badgeEl) {
      badgeEl.className = `badge ${isBuy ? 'badge-bullish' : 'badge-bearish'}`;
      badgeEl.textContent = isBuy ? 'BUY' : 'SELL';
    }

    if (loadingEl) loadingEl.style.display = 'flex';

    try {
      if (!this._ohlcCache) this._ohlcCache = {};

      const period = this._activePeriod || '1y';
      const cacheKey = `${t.symbol}_${period}`;
      let candles = this._ohlcCache[cacheKey];
      if (!candles) {
        const res = await fetch(`/market/ohlc/${t.symbol}?period=${period}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        candles = await res.json();
        this._ohlcCache[cacheKey] = candles;
      }


      this._currentCandles = candles;

      if (!container || typeof LightweightCharts === 'undefined') {
        if (loadingEl) {
          loadingEl.innerHTML = `<span style="color: #f43f5e;">Chart library loading... please try again.</span>`;
        }
        return;
      }

      // Dispose previous chart instance
      if (this._chartInstance) {
        try {
          this._chartInstance.remove();
        } catch (e) {
          console.debug('Chart remove error:', e);
        }
        this._chartInstance = null;
        this._candlestickSeries = null;
      }

      // Initialize Lightweight Chart
      const chart = LightweightCharts.createChart(container, {
        width: container.clientWidth || 700,
        height: 420,
        layout: {
          background: { color: '#070a13' },
          textColor: '#94a3b8',
          fontSize: 11,
          fontFamily: 'system-ui, -apple-system, sans-serif',
        },
        grid: {
          vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
          horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
        },
        crosshair: {
          mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
          borderColor: 'rgba(255, 255, 255, 0.08)',
        },
        timeScale: {
          borderColor: 'rgba(255, 255, 255, 0.08)',
          timeVisible: true,
          secondsVisible: false,
        },
      });

      this._chartInstance = chart;

      // Add Candlestick Series
      const candleSeries = chart.addCandlestickSeries({
        upColor: '#10b981',
        downColor: '#f43f5e',
        borderVisible: false,
        wickUpColor: '#10b981',
        wickDownColor: '#f43f5e',
      });
      this._candlestickSeries = candleSeries;

      candleSeries.setData(candles);

      // Add Markers on Exact Trade Candles (ensuring unique timestamps per series)
      const markers = [];

      if (t.signal_date === t.entry_date) {
        if (t.entry_date) {
          markers.push({
            time: t.entry_date,
            position: isBuy ? 'belowBar' : 'aboveBar',
            color: '#10b981',
            shape: isBuy ? 'arrowUp' : 'arrowDown',
            text: `ENTRY ₹${t.entry_price.toFixed(2)} (${t.strategy})`,
          });
        }
      } else {
        if (t.signal_date) {
          markers.push({
            time: t.signal_date,
            position: isBuy ? 'belowBar' : 'aboveBar',
            color: '#818cf8',
            shape: isBuy ? 'arrowUp' : 'arrowDown',
            text: `SIGNAL (${t.strategy})`,
          });
        }
        if (t.entry_date) {
          markers.push({
            time: t.entry_date,
            position: isBuy ? 'belowBar' : 'aboveBar',
            color: '#10b981',
            shape: isBuy ? 'arrowUp' : 'arrowDown',
            text: `ENTRY ₹${t.entry_price.toFixed(2)}`,
          });
        }
      }

      // Exit Candle Marker
      if (t.exit_date && t.exit_date !== t.entry_date) {
        const isWin = t.outcome === 'WIN';
        markers.push({
          time: t.exit_date,
          position: isBuy ? 'aboveBar' : 'belowBar',
          color: isWin ? '#10b981' : '#f43f5e',
          shape: isBuy ? 'arrowDown' : 'arrowUp',
          text: `EXIT ₹${t.exit_price.toFixed(2)} (${t.exit_reason})`,
        });
      }

      // Sort markers chronologically (required by Lightweight Charts)
      markers.sort((a, b) => (a.time > b.time ? 1 : -1));
      candleSeries.setMarkers(markers);


      // Add Target Level Price Line
      if (t.target_price) {
        candleSeries.createPriceLine({
          price: t.target_price,
          color: '#10b981',
          lineWidth: 2,
          lineStyle: LightweightCharts.LineStyle.Dashed,
          axisLabelVisible: true,
          title: `TARGET Level (₹${t.target_price.toFixed(2)})`,
        });
      }

      // Add Stop Loss Price Line
      if (t.stop_loss_price) {
        candleSeries.createPriceLine({
          price: t.stop_loss_price,
          color: '#f43f5e',
          lineWidth: 2,
          lineStyle: LightweightCharts.LineStyle.Dashed,
          axisLabelVisible: true,
          title: `STOP LOSS (₹${t.stop_loss_price.toFixed(2)})`,
        });
      }

      // Add Entry Price Line
      if (t.entry_price) {
        candleSeries.createPriceLine({
          price: t.entry_price,
          color: '#38bdf8',
          lineWidth: 1,
          lineStyle: LightweightCharts.LineStyle.Dotted,
          axisLabelVisible: true,
          title: `ENTRY LEVEL (₹${t.entry_price.toFixed(2)})`,
        });
      }

      // Auto-focus around the trade candle
      this.centerChartOnTrade();

      // Window resize listener
      window.addEventListener('resize', () => {
        if (this._chartInstance && container) {
          this._chartInstance.applyOptions({ width: container.clientWidth });
        }
      });

      if (loadingEl) loadingEl.style.display = 'none';

    } catch (err) {
      if (loadingEl) {
        loadingEl.innerHTML = `<span style="color: #f43f5e;">Failed to load candle chart: ${err.message}</span>`;
      }
    }
  },

  centerChartOnTrade() {
    const trades = this._currentTrades || [];
    const t = trades[this._selectedTradeIndex];
    if (!t || !this._chartInstance || !this._currentCandles || !this._currentCandles.length) return;

    const candles = this._currentCandles;
    const entryIdx = candles.findIndex(c => c.time === t.entry_date);
    const exitIdx = candles.findIndex(c => c.time === t.exit_date);

    const refIdx = entryIdx >= 0 ? entryIdx : (exitIdx >= 0 ? exitIdx : candles.length - 1);
    const fromIdx = Math.max(0, refIdx - 20);
    const toIdx = Math.min(candles.length - 1, (exitIdx >= 0 ? exitIdx : refIdx) + 20);

    if (fromIdx < toIdx) {
      this._chartInstance.timeScale().setVisibleRange({
        from: candles[fromIdx].time,
        to: candles[toIdx].time,
      });
    }
  },

  fitChart() {
    if (this._chartInstance) {
      this._chartInstance.timeScale().fitContent();
    }
  },

  openTradingViewWithDate() {
    const trades = this._currentTrades || [];
    const t = trades[this._selectedTradeIndex];
    if (!t) return;

    // Copy exact entry date to clipboard
    if (navigator.clipboard && t.entry_date) {
      navigator.clipboard.writeText(t.entry_date).catch(() => {});
    }

    // Create a toast notification
    this.showToast(`📋 Trade Date (${t.entry_date}) copied! In TradingView, press Alt + G and Enter to jump directly to this exact candle.`);

    // Open TradingView chart
    const tvUrl = `https://in.tradingview.com/chart/?symbol=NSE:${t.symbol}&interval=D`;
    window.open(tvUrl, '_blank', 'noopener,noreferrer');
  },

  showToast(message) {
    let toast = document.querySelector('#bt-toast-notification');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'bt-toast-notification';
      toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
        border: 1px solid #6366f1;
        color: #f8fafc;
        padding: 14px 20px;
        border-radius: 10px;
        font-size: 0.85rem;
        font-weight: 600;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(99, 102, 241, 0.4);
        z-index: 99999;
        max-width: 420px;
        line-height: 1.5;
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        gap: 10px;
      `;
      document.body.appendChild(toast);
    }
    toast.innerHTML = `<span>⚡</span> <span>${message}</span>`;
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';

    setTimeout(() => {
      if (toast) {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
      }
    }, 6000);
  },

  renderAnalyticsTab(summary) {
    const pane = document.querySelector('#bt-analytics-view');
    if (!pane || !summary) return;

    pane.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 16px;">
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 12px;">
          <div style="font-size: 0.68rem; color: #94a3b8;">AVG WIN TRADE</div>
          <div style="font-size: 1.1rem; font-weight: 800; color: #10b981; margin-top: 2px;">+${(summary.avg_win_pct || 0).toFixed(2)}%</div>
        </div>
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 12px;">
          <div style="font-size: 0.68rem; color: #94a3b8;">AVG LOSS TRADE</div>
          <div style="font-size: 1.1rem; font-weight: 800; color: #f43f5e; margin-top: 2px;">${(summary.avg_loss_pct || 0).toFixed(2)}%</div>
        </div>
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 12px;">
          <div style="font-size: 0.68rem; color: #94a3b8;">PAYOFF RATIO</div>
          <div style="font-size: 1.1rem; font-weight: 800; color: #38bdf8; margin-top: 2px;">${(Math.abs((summary.avg_win_pct || 1) / (summary.avg_loss_pct || -1))).toFixed(2)}</div>
        </div>
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 12px;">
          <div style="font-size: 0.68rem; color: #94a3b8;">WIN/LOSS SPLIT</div>
          <div style="font-size: 1.1rem; font-weight: 800; color: #cbd5e1; margin-top: 2px;">${summary.winning_trades || 0} / ${summary.losing_trades || 0}</div>
        </div>
      </div>
      <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 14px; font-size: 0.82rem; color: #cbd5e1; line-height: 1.5;">
        <strong style="color: #fff;">Quantitative Strategy Summary:</strong><br>
        Over the backtested historical window, this strategy executed <strong>${summary.total_trades || 0}</strong> simulated trades with a <strong>${(summary.win_rate_pct || 0).toFixed(1)}% win rate</strong> and profit factor of <strong>${(summary.profit_factor || 0).toFixed(2)}</strong>. Cumulative return resulted in <strong>${(summary.net_return_pct || 0).toFixed(1)}%</strong> with maximum peak-to-trough drawdown of <strong>${(summary.max_drawdown_pct || 0).toFixed(1)}%</strong>.
      </div>
    `;
  },

  renderEmptyDiagnostic() {
    const diagView = document.querySelector('#bt-selected-trade-view');
    if (diagView) {
      diagView.innerHTML = `<div class="empty-cell" style="padding: 50px 20px; text-align: center; color: #64748b;">No trades available for inspection.</div>`;
    }
  },


  sendToPaperTrading(symbol, direction, price, target, stoploss) {
    App.Router.switchTab('paper');
    App.Paper.openModal(symbol, direction.toUpperCase() === 'BUY' ? 'BUY' : 'SELL');
    setTimeout(() => {
      const priceInput = document.querySelector('#order-entry-price');
      const targetInput = document.querySelector('#order-target-pct');
      const stopInput = document.querySelector('#order-stoploss-pct');
      if (priceInput && price) priceInput.value = price;
      if (targetInput && target) targetInput.value = target;
      if (stopInput && stoploss) stopInput.value = stoploss;
    }, 200);
  },

  sendToNewsAnalyzer(symbol) {
    App.Router.switchTab('news');
    const customInput = document.querySelector('#news-custom-input');
    if (customInput) customInput.value = symbol;
    App.News.analyzeStock();
  }
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
    App.Backtester.init();

    await App.Screener.loadCustomWatchlists();
    await this.populateDatalists();
    App.Screener.fetchSignals();
  },

  async populateDatalists() {
    try {
      const res = await fetch('/universe/symbols');
      if (!res.ok) return;
      const allData = await res.json();
      App.State.universeSymbols = allData;
      const symbols = allData.map(s => s.symbol).filter(Boolean);
      const uniqueSymbols = Array.from(new Set(symbols));

      const datalists = [
        '#lookback-stocks-datalist',
        '#paper-stocks-datalist',
        '#news-stocks-datalist',
        '#backtest-stocks-datalist',
      ];

      datalists.forEach(id => {
        const el = document.querySelector(id);
        if (el && uniqueSymbols.length) {
          el.innerHTML = uniqueSymbols.map(sym => `<option value="${sym}"></option>`).join('');
        }
      });

      // Populate initial news stock select with FNO or All
      App.News.populateStockSelect('FNO');
      App.Backtester.populateStockSelect('');
    } catch (err) {
      console.debug('Datalists load error:', err);
    }
  },
};


// Initialize on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  App.Init.bootstrap();
});
