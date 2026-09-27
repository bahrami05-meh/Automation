/* پروزه اتوماسیون بورسی — خوانندهٔ Chrome فقط‌خواندنی. */
(function () {
  'use strict';
  const endpoint = 'http://127.0.0.1:8765/api/browser-observation';
  const blocked = /(password|passwd|otp|token|cookie|session|username|رمز|کد|نشست|کوکی)/i;
  const faDigits = '۰۱۲۳۴۵۶۷۸۹';
  const normalize = (value) => String(value || '').replace(/[۰-۹]/g, (d) => faDigits.indexOf(d)).replace(/[٬,]/g, '').trim();
  const number = (value) => { const n = Number(normalize(value).replace(/[^0-9.+-]/g, '')); return Number.isFinite(n) ? n : null; };
  const visible = (node) => { const s = getComputedStyle(node); return s.display !== 'none' && s.visibility !== 'hidden' && node.getBoundingClientRect().width > 0; };
  const text = () => Array.from(document.querySelectorAll('body *')).filter(visible).map((n) => n.innerText || '').join('\n');
  const symbol = () => {
    const match = text().match(/(?:نماد|symbol)\s*[:：]?\s*([\u0600-\u06ffA-Za-z][\u0600-\u06ffA-Za-z0-9_-]{1,19})/i);
    return match ? match[1] : null;
  };
  const rows = () => Array.from(document.querySelectorAll('table tr')).filter(visible).map((tr) => Array.from(tr.cells).map((c) => normalize(c.innerText))).filter((r) => r.length >= 5);
  const read = () => {
    const all = text();
    if (blocked.test(all)) return { error: 'SENSITIVE_PAGE_CONTENT_BLOCKED' };
    const rowsFound = rows();
    const sym = symbol();
    if (!sym || rowsFound.length < 21) return { error: 'MARKET_TABLE_NOT_READY', symbol: sym, rows: rowsFound.length };
    const ohlcv = rowsFound.slice(-21).map((r) => ({ open: number(r[0]), high: number(r[1]), low: number(r[2]), close: number(r[3]), volume: number(r[4]) }));
    if (ohlcv.some((r) => Object.values(r).some((v) => v === null)) || ohlcv.length < 21) return { error: 'OHLCV_NOT_RECOGNIZED', symbol: sym };
    const now = new Date().toISOString();
    return { symbol: sym, market_snapshot: { symbol: sym, source: location.origin, collected_at: now, timezone: 'Asia/Tehran', price_unit: 'IRR', price_type: 'raw', timeframe: 'daily', ohlcv } };
  };
  const send = async () => {
    const payload = read();
    if (payload.error) return { ok: false, ...payload };
    const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    return { ok: response.ok, result: await response.json() };
  };
  window.JackReadOnly = Object.freeze({ read, send });
  window.addEventListener('message', (event) => {
    if (event.source !== window || !event.data || event.data.type !== 'JACK_READ_MARKET') return;
    send().then((result) => window.postMessage({ type: 'JACK_READ_MARKET_RESULT', result }, '*')).catch((error) => window.postMessage({ type: 'JACK_READ_MARKET_RESULT', result: { ok: false, error: String(error) } }, '*'));
  });
})();
