const health = document.querySelector('#health');
const runButton = document.querySelector('#run-demo');
const empty = document.querySelector('#empty');
const report = document.querySelector('#report');
const card = document.querySelector('#symbol-card');
const disclaimer = document.querySelector('#disclaimer');

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
  const indicatorHtml = symbol.indicators.map((item) => `
    <div class="item"><h3>${escapeHtml(item.name)}</h3>
    <p>خانواده: ${escapeHtml(item.family)}</p><p>تایم‌فریم: ${escapeHtml(item.timeframe)}</p>
    <p>سیگنال: ${escapeHtml(item.direction)}</p></div>`).join('');
  const findings = symbol.quality.findings.map((item) => `
    <div class="finding ${escapeHtml(item.severity)}"><strong>${escapeHtml(item.code)}</strong> — ${escapeHtml(item.message)}</div>`).join('') || '<p>موردی ثبت نشده است.</p>';
  card.innerHTML = `<h2>نماد نمونه: ${escapeHtml(symbol.symbol)}</h2>
    <p>وضعیت داده: ${escapeHtml(symbol.data_status)}</p>
    <p>ناظر کیفیت: <strong>${escapeHtml(symbol.quality.status)}</strong> · نسخهٔ قانون: ${escapeHtml(symbol.quality.rule_version)}</p>
    <p>امتیاز پس از سقف‌دهی خانواده‌ها: ${escapeHtml(symbol.quality.score)}</p>
    <p class="decision">نتیجهٔ جک: ${escapeHtml(symbol.jack_decision)}</p>
    <p>${escapeHtml(symbol.reason)}</p><h3>اندیکاتورها</h3><div class="grid">${indicatorHtml}</div>
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

checkHealth();
