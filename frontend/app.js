const health = document.querySelector('#health');
const runButton = document.querySelector('#run-demo');
const symbolForm = document.querySelector('#symbol-form');
const symbolInput = document.querySelector('#symbol');
const snapshotForm = document.querySelector('#snapshot-form');
const snapshotInput = document.querySelector('#snapshot');
const empty = document.querySelector('#empty');
const report = document.querySelector('#report');
const card = document.querySelector('#symbol-card');
const disclaimer = document.querySelector('#disclaimer');
const portfolioFileForm = document.querySelector('#portfolio-file-form');
const portfolioFileInput = document.querySelector('#portfolio-file');
const portfolioPriceUnit = document.querySelector('#portfolio-price-unit');
const portfolioImportButton = document.querySelector('#portfolio-import-button');
const portfolioImportStatus = document.querySelector('#portfolio-import-status');
const portfolioImportResult = document.querySelector('#portfolio-import-result');
const MAX_PORTFOLIO_FILE_BYTES = 5 * 1024 * 1024;

const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
}[character]));

async function checkHealth() {
  try {
    const response = await fetch('/api/health');
    if (!response.ok) throw new Error('health');
    health.textContent = 'محلی و آماده';
    health.className = 'badge ok';
  } catch {
    health.textContent = 'سرور در دسترس نیست';
    health.className = 'badge error';
  }
}

function renderReport(payload) {
  const symbol = payload.symbols[0];
  const indicatorHtml = (symbol.indicators || []).map((item) => `
    <div class="item"><h3>${escapeHtml(item.name)}</h3>
    <p>خانواده: ${escapeHtml(item.family)}</p><p>تایم‌فریم: ${escapeHtml(item.timeframe)}</p>
    <p>سیگنال: ${escapeHtml(item.direction)}</p></div>`).join('');
  const findings = (symbol.quality.findings || []).map((item) => `
    <div class="finding ${escapeHtml(item.severity)}"><strong>${escapeHtml(item.code)}</strong> — ${escapeHtml(item.message)}</div>`).join('') || '<p>موردی ثبت نشده است.</p>';
  const agents = payload.agents || (payload.agent ? [payload.agent] : []);
  const agentHtml = agents.map((agent) => `<p>ایجنت: <strong>${escapeHtml(agent.name)}</strong> · وضعیت: ${escapeHtml(agent.status)} · شناسه اجرا: ${escapeHtml(agent.run_id)}</p>`).join('');
  const technical = payload.technical ? `<h3>خروجی ایجنت تکنیکال</h3>
    <p>وضعیت: <strong>${escapeHtml(payload.technical.status)}</strong> · سیگنال فنی: ${escapeHtml(payload.technical.overall_signal)}</p>
    <p>${escapeHtml(payload.technical.summary || payload.technical.reason || '')}</p>
    ${payload.technical.trend ? `<p>روند: ${escapeHtml(payload.technical.trend.direction)} · مومنتوم: ${escapeHtml(payload.technical.momentum?.direction || 'NONE')} · RSI14: ${escapeHtml(payload.technical.momentum?.rsi14 ?? 'ندارد')}</p>` : ''}
    ${payload.technical.levels?.length ? `<p>سطوح مهم: ${payload.technical.levels.map((level) => `${escapeHtml(level.name)}=${escapeHtml(level.value)}`).join(' · ')}</p>` : ''}
    ${payload.technical.clear_signal ? `<p>سیگنال شفاف: ${escapeHtml(payload.technical.clear_signal.direction)} · محرک: ${escapeHtml(payload.technical.clear_signal.trigger || 'ندارد')} · ابطال: ${escapeHtml(payload.technical.clear_signal.invalidation || 'ندارد')}</p>` : ''}` : '';
  const chart = payload.chart_control ? `<h3>خروجی ایجنت کنترل نمودار</h3>
    <p>وضعیت: <strong>${escapeHtml(payload.chart_control.status)}</strong></p>
    <p>${escapeHtml(payload.chart_control.reason || '')}</p>` : '';
  const portfolio = payload.portfolio_capture ? `<h3>خروجی ایجنت مرورگر و پرتفوی</h3>
    <p>وضعیت: <strong>${escapeHtml(payload.portfolio_capture.status)}</strong> · تعداد دارایی: ${escapeHtml(payload.portfolio_capture.holdings_count)}</p>
    <p>${escapeHtml(payload.portfolio_capture.reason || '')}</p>` : '';
  const board = payload.market_board ? `<h3>خروجی ایجنت تابلو</h3>
    <p>وضعیت: <strong>${escapeHtml(payload.market_board.status)}</strong></p>
    <p>${escapeHtml(payload.market_board.reason || '')}</p>
    ${payload.market_board.metrics ? `<p>نسبت حجم به میانگین ۲۰روزه: ${escapeHtml(payload.market_board.metrics.volume_ratio_to_average_20)} · وضعیت صف: ${escapeHtml(payload.market_board.metrics.queue_state)}</p><p>قدرت خرید/فروش حقیقی: ${escapeHtml(payload.market_board.metrics.individual_buy_power ?? 'ندارد')} / ${escapeHtml(payload.market_board.metrics.individual_sell_power ?? 'ندارد')} · قدرت خرید/فروش حقوقی: ${escapeHtml(payload.market_board.metrics.legal_buy_power ?? 'ندارد')} / ${escapeHtml(payload.market_board.metrics.legal_sell_power ?? 'ندارد')}</p><p>تعداد معاملات: ${escapeHtml(payload.market_board.metrics.trade_count ?? 'ندارد')} · ارزش معاملات: ${escapeHtml(payload.market_board.metrics.turnover_value ?? 'ندارد')} · بهترین خرید/فروش: ${escapeHtml(payload.market_board.metrics.best_bid_price ?? 'ندارد')} / ${escapeHtml(payload.market_board.metrics.best_ask_price ?? 'ندارد')}</p>` : ''}` : '';
  const fundamental = payload.fundamental ? `<h3>خروجی ایجنت بنیادی</h3>
    <p>وضعیت: <strong>${escapeHtml(payload.fundamental.status)}</strong></p>
    <p>${escapeHtml(payload.fundamental.reason || '')}</p>
    ${payload.fundamental.metrics ? `<p>حاشیهٔ سود خالص: ${escapeHtml(payload.fundamental.metrics.net_margin_percent)}٪ · وضعیت سود: ${escapeHtml(payload.fundamental.metrics.earnings_state)} · وضعیت اهرم: ${escapeHtml(payload.fundamental.metrics.leverage_state)}</p>` : ''}` : '';
  const risk = payload.portfolio_risk ? `<h3>خروجی ایجنت ریسک پرتفوی</h3><p>وضعیت: <strong>${escapeHtml(payload.portfolio_risk.status)}</strong></p><p>${escapeHtml(payload.portfolio_risk.reason || '')}</p>${payload.portfolio_risk.metrics ? `<p>سقف یک پلهٔ آزمایشی: ${escapeHtml(payload.portfolio_risk.metrics.max_single_step_quantity)}</p>` : ''}` : '';
  const qa = payload.quality_supervisor ? `<h3>خروجی ناظر کیفیت</h3><p>وضعیت مستقل: <strong>${escapeHtml(payload.quality_supervisor.status)}</strong> · تعداد یافته: ${escapeHtml(payload.quality_supervisor.findings?.length || 0)}</p>` : '';
  card.innerHTML = `<h2>نماد: ${escapeHtml(symbol.symbol)}</h2>
    <p>وضعیت داده: ${escapeHtml(symbol.data_status)}</p>
    ${agentHtml}
    <p>ناظر کیفیت: <strong>${escapeHtml(symbol.quality.status)}</strong>${symbol.quality.rule_version ? ` · نسخهٔ قانون: ${escapeHtml(symbol.quality.rule_version)}` : ''}</p>
    ${symbol.quality.score !== undefined ? `<p>امتیاز پس از سقف‌دهی خانواده‌ها: ${escapeHtml(symbol.quality.score)}</p>` : ''}
    <p class="decision">نتیجهٔ جک: ${escapeHtml(symbol.jack_decision)}</p>
    <p>${escapeHtml(symbol.reason)}</p>${technical}${chart}${board}${fundamental}${risk}${qa}${portfolio}<h3>اندیکاتورها</h3><div class="grid">${indicatorHtml}</div>
    <h3>یافته‌های ناظر کیفیت</h3>${findings}`;
  disclaimer.textContent = payload.disclaimer;
  empty.hidden = true;
  report.hidden = false;
}

runButton.addEventListener('click', async () => {
  runButton.disabled = true;
  runButton.textContent = 'در حال اجرای نمونه…';
  try {
    const response = await fetch('/api/demo-report');
    if (!response.ok) throw new Error('report');
    renderReport(await response.json());
  } catch {
    alert('گزارش نمونه دریافت نشد. ابتدا سرور جک را اجرا کنید.');
  } finally {
    runButton.disabled = false;
    runButton.textContent = 'اجرای تحلیل نمونه';
  }
});

symbolForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const symbol = symbolInput.value.trim();
  try {
    const response = await fetch('/api/symbol-request', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({symbol})
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'request');
    renderReport(payload);
  } catch (error) {
    alert(error.message || 'ثبت نماد انجام نشد.');
  }
});

snapshotForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const snapshot = JSON.parse(snapshotInput.value);
    const response = await fetch('/api/market-snapshot', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(snapshot)
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'snapshot');
    renderReport(payload);
  } catch (error) {
    alert(error instanceof SyntaxError ? 'JSON دادهٔ بازار نامعتبر است.' : (error.message || 'تحلیل داده انجام نشد.'));
  }
});

function renderPortfolioImport(payload) {
  portfolioImportResult.replaceChildren();
  const capture = payload.portfolio_capture;
  const summary = payload.portfolio_summary;
  const heading = document.createElement('h3');
  heading.textContent = `پرتفوی اعتبارسنجی شد · ${capture.holdings_count} دارایی`;
  portfolioImportResult.append(heading);

  const metadata = document.createElement('p');
  metadata.textContent = `منبع: ${capture.source} · دریافت: ${capture.collected_at} · واحد قیمت: ${capture.price_unit}`;
  portfolioImportResult.append(metadata);

  if (summary) {
    const summaryPanel = document.createElement('section');
    summaryPanel.className = 'portfolio-summary';
    const summaryHeading = document.createElement('h4');
    summaryHeading.textContent = 'خلاصهٔ پرتفوی';
    summaryPanel.append(summaryHeading);

    const metrics = document.createElement('div');
    metrics.className = 'portfolio-summary-grid';
    const numberFormat = (value, fractionDigits = 2) => {
      if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
      return new Intl.NumberFormat('fa-IR', {maximumFractionDigits: fractionDigits}).format(Number(value));
    };
    const money = (value) => `${numberFormat(value)} ${capture.price_unit}`;
    const metricValues = [
      ['ارزش فعلی گزارش‌شده', money(summary.reported_total_market_value)],
      ['بهای خرید تخمینی', money(summary.estimated_total_cost_basis)],
      ['سود/زیان تحقق‌نیافتهٔ تخمینی', money(summary.estimated_unrealized_pnl)],
      ['بازده تخمینی', summary.estimated_return_percent === null ? '—' : `${numberFormat(summary.estimated_return_percent)}٪`],
      ['تمرکز ۵ دارایی بزرگ', summary.top_five_concentration_percent === null ? '—' : `${numberFormat(summary.top_five_concentration_percent)}٪`]
    ];
    for (const [label, value] of metricValues) {
      const metric = document.createElement('div');
      metric.className = 'portfolio-metric';
      const metricLabel = document.createElement('span');
      metricLabel.textContent = label;
      const metricValue = document.createElement('strong');
      metricValue.textContent = value;
      metric.append(metricLabel, metricValue);
      metrics.append(metric);
    }
    summaryPanel.append(metrics);
    const limitations = document.createElement('p');
    limitations.className = 'muted portfolio-limitations';
    limitations.textContent = (summary.limitations || []).join(' ');
    summaryPanel.append(limitations);
    portfolioImportResult.append(summaryPanel);
  }

  const table = document.createElement('table');
  table.className = 'portfolio-table';
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  for (const label of ['نماد', 'تعداد', 'میانگین قیمت خرید', 'آخرین قیمت', 'ارزش فعلی', 'سود/زیان تخمینی', 'وزن از کل']) {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = label;
    headerRow.append(cell);
  }
  thead.append(headerRow);
  table.append(thead);

  const tbody = document.createElement('tbody');
  const positions = new Map((summary?.positions || []).map((position) => [position.symbol, position]));
  const numberFormat = (value, fractionDigits = 2) => {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
    return new Intl.NumberFormat('fa-IR', {maximumFractionDigits: fractionDigits}).format(Number(value));
  };
  for (const holding of capture.holdings) {
    const row = document.createElement('tr');
    const position = positions.get(holding.symbol);
    const pnl = position?.estimated_unrealized_pnl;
    const weight = position?.market_value_weight_percent;
    const values = [
      holding.symbol,
      numberFormat(holding.quantity, 3),
      numberFormat(holding.average_price, 3),
      numberFormat(holding.last_price, 3),
      numberFormat(holding.market_value),
      numberFormat(pnl),
      weight === null || weight === undefined ? '—' : `${numberFormat(weight)}٪`
    ];
    for (const [index, value] of values.entries()) {
      const cell = document.createElement('td');
      cell.textContent = String(value);
      if (index === 5 && pnl !== null && pnl !== undefined) {
        cell.classList.add(Number(pnl) < 0 ? 'negative' : 'positive');
      }
      row.append(cell);
    }
    tbody.append(row);
  }
  table.append(tbody);
  portfolioImportResult.append(table);
  portfolioImportResult.hidden = false;
}

portfolioFileForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = portfolioFileInput.files?.[0];
  if (!file) return;
  if (!file.size || file.size > MAX_PORTFOLIO_FILE_BYTES) {
    portfolioImportStatus.textContent = 'حجم فایل باید کمتر از ۵ مگابایت باشد.';
    return;
  }
  if (!Number.isFinite(file.lastModified) || file.lastModified <= 0) {
    portfolioImportStatus.textContent = 'زمان فایل در دسترس نیست؛ فایل را دوباره از EasyTrader دریافت کن.';
    return;
  }
  const extension = file.name.toLowerCase().split('.').pop();
  if (!['csv', 'xlsx'].includes(extension)) {
    portfolioImportStatus.textContent = 'فقط فایل CSV یا XLSX پشتیبانی می‌شود.';
    return;
  }
  if (!portfolioPriceUnit.value) {
    portfolioImportStatus.textContent = 'واحد قیمت را انتخاب کن.';
    return;
  }

  portfolioImportButton.disabled = true;
  portfolioImportResult.hidden = true;
  portfolioImportStatus.textContent = 'در حال اعتبارسنجی فایل روی همین رایانه…';
  try {
    const response = await fetch('/api/portfolio-import', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-Jack-Import-Format': extension,
        'X-Jack-Price-Unit': portfolioPriceUnit.value,
        'X-Jack-File-Modified': new Date(file.lastModified).toISOString()
      },
      body: file,
      cache: 'no-store',
      credentials: 'same-origin'
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || payload.portfolio_capture?.reason || 'PORTFOLIO_FILE_IMPORT_FAILED');
    if (payload.portfolio_capture?.status !== 'PORTFOLIO_CAPTURED') {
      throw new Error(payload.portfolio_capture?.reason || payload.browser_portfolio_agent?.error_code || 'PORTFOLIO_FILE_IMPORT_FAILED');
    }
    renderPortfolioImport(payload);
    portfolioImportStatus.textContent = 'فایل پردازش شد؛ فقط نتیجه در حافظهٔ همین صفحه نمایش داده می‌شود.';
    portfolioFileInput.value = '';
  } catch (error) {
    portfolioImportStatus.textContent = `ورود فایل انجام نشد: ${error.message || 'PORTFOLIO_FILE_IMPORT_FAILED'}`;
  } finally {
    portfolioImportButton.disabled = false;
  }
});

checkHealth();
