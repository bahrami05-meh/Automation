/* پروزه اتوماسیون بورسی — خوانندهٔ Chrome فقط‌خواندنی. */
(function () {
  'use strict';
  const endpoint = 'http://127.0.0.1:8765/api/browser-observation';
  const blocked = /(password|passwd|otp|token|cookie|session|username|رمز|کد|نشست|کوکی)/i;
  const faDigits = '۰۱۲۳۴۵۶۷۸۹';
  const normalize = (value) => String(value || '').replace(/[۰-۹]/g, (d) => faDigits.indexOf(d)).replace(/[٬,]/g, '').trim();
  const number = (value) => {
    const input = normalize(value);
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(input)) return null;
    const n = Number(input);
    return Number.isFinite(n) ? n : null;
  };
  const visible = (node) => { const s = getComputedStyle(node); return s.display !== 'none' && s.visibility !== 'hidden' && node.getBoundingClientRect().width > 0; };
  const text = () => Array.from(document.querySelectorAll('body *')).filter(visible).map((n) => n.innerText || '').join('\n');
  const symbol = () => {
    const match = text().match(/(?:نماد|symbol)\s*[:：]?\s*([\u0600-\u06ffA-Za-z][\u0600-\u06ffA-Za-z0-9_-]{1,19})/i);
    return match ? match[1] : null;
  };
  const aliases = {
    date: ['date', 'تاریخ'], open: ['open', 'باز', 'قیمت باز'],
    high: ['high', 'بیشترین', 'بیشترین قیمت'], low: ['low', 'کمترین', 'کمترین قیمت'],
    close: ['close', 'قیمت بسته', 'بسته'], volume: ['volume', 'حجم']
  };
  const parseTable = (table, sym) => {
    // Metadata must be supplied explicitly by a verified source adapter.
    const meta = table.dataset;
    if (meta.jackSymbol !== sym || !['IRR', 'IRT'].includes(meta.jackPriceUnit) ||
        !['raw', 'adjusted'].includes(meta.jackPriceType) || meta.jackTimeframe !== 'daily' ||
        meta.jackDateFormat !== 'iso') return null;
    const trs = Array.from(table.querySelectorAll('tr')).filter(visible);
    if (!trs.length) return null;
    const headers = Array.from(trs[0].cells).map((c) => normalize(c.innerText).toLowerCase());
    const columns = {};
    for (const [key, names] of Object.entries(aliases)) {
      const matches = headers.map((h, i) => names.includes(h) ? i : -1).filter((i) => i >= 0);
      if (matches.length !== 1) return null;
      columns[key] = matches[0];
    }
    const dated = [];
    for (const tr of trs.slice(1)) {
      const cells = Array.from(tr.cells).map((c) => normalize(c.innerText));
      const date = cells[columns.date];
      if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
      const timestamp = Date.parse(date + 'T00:00:00Z');
      if (!Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== date) return null;
      const row = {};
      for (const key of ['open', 'high', 'low', 'close', 'volume']) row[key] = number(cells[columns[key]]);
      if (Object.values(row).some((v) => v === null || v < 0) ||
          Math.min(row.open, row.high, row.low, row.close) <= 0 ||
          row.high < Math.max(row.open, row.close) || row.low > Math.min(row.open, row.close)) return null;
      dated.push({date, ...row});
    }
    if (dated.length < 21) return null;
    const increasing = dated.every((r, i) => !i || r.date > dated[i - 1].date);
    const decreasing = dated.every((r, i) => !i || r.date < dated[i - 1].date);
    if (!increasing && !decreasing) return null;
    if (decreasing) dated.reverse();
    return {price_unit: meta.jackPriceUnit, price_type: meta.jackPriceType,
      timeframe: meta.jackTimeframe, ohlcv: dated.slice(-21)};
  };
  const read = () => {
    const all = text();
    if (blocked.test(all)) return { error: 'SENSITIVE_PAGE_CONTENT_BLOCKED' };
    const sym = symbol();
    if (!sym) return { error: 'MARKET_TABLE_NOT_READY', symbol: sym };
    const candidates = Array.from(document.querySelectorAll('table')).filter(visible).map((t) => parseTable(t, sym)).filter(Boolean);
    if (candidates.length !== 1) return { error: 'OHLCV_NOT_RECOGNIZED', symbol: sym };
    const now = new Date().toISOString();
    return { symbol: sym, market_snapshot: { symbol: sym, source: location.origin, collected_at: now, timezone: 'Asia/Tehran', ...candidates[0] } };
  };
  const send = async () => {
    const payload = read();
    if (payload.error) return { ok: false, ...payload };
    const nonceResponse = await fetch('http://127.0.0.1:8765/api/browser-nonce', { method: 'GET', credentials: 'omit' });
    if (!nonceResponse.ok) return { ok: false, error: 'BROWSER_NONCE_UNAVAILABLE' };
    const nonceBody = await nonceResponse.json();
    if (typeof nonceBody.nonce !== 'string' || !nonceBody.nonce.trim() || nonceBody.nonce.length > 128) return { ok: false, error: 'BROWSER_NONCE_INVALID' };
    payload.bridge_nonce = nonceBody.nonce;
    const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'omit', body: JSON.stringify(payload) });
    return { ok: response.ok, result: await response.json() };
  };
  window.JackReadOnly = Object.freeze({ read, send });
  window.addEventListener('message', (event) => {
    // Chrome isolated worlds may expose different Window proxies; rely on the
    // explicit message type and keep payload extraction read-only and filtered.
    if (event.origin !== location.origin || !event.data || event.data.type !== 'JACK_READ_MARKET') return;
    send().then((result) => window.postMessage({ type: 'JACK_READ_MARKET_RESULT', result }, location.origin)).catch((error) => window.postMessage({ type: 'JACK_READ_MARKET_RESULT', result: { ok: false, error: String(error) } }, location.origin));
  });
})();
