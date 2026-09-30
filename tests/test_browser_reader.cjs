'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../browser_reader/content.js'), 'utf8');
const metadata = {jackSymbol: 'TEST', jackPriceUnit: 'IRR', jackPriceType: 'raw', jackTimeframe: 'daily', jackDateFormat: 'iso'};
const element = (innerText = '') => ({innerText, getBoundingClientRect: () => ({width: 100})});
function fixture({headers = ['date', 'open', 'high', 'low', 'close', 'volume'], meta = metadata,
  change = () => {}, reverse = false, count = 21} = {}) {
  const rows = Array.from({length: count}, (_, i) => {
    const data = {date: `2026-09-${String(i + 1).padStart(2, '0')}`, open: '100', high: '102', low: '99', close: '101', volume: '1000'};
    change(data, i);
    return {...element(), cells: headers.map((key) => element(data[key]))};
  });
  if (reverse) rows.reverse();
  const table = {...element(), dataset: {...meta}, querySelectorAll: () => [{...element(), cells: headers.map((h) => element(h))}, ...rows]};
  return table;
}
function reader(tables, fetchResult) {
  let sent = 0;
  const requests = [];
  const messages = [];
  let listener;
  const window = {addEventListener(type, callback) {listener = callback;}, postMessage(message, origin) {messages.push({message, origin});}};
  vm.runInNewContext(source, {window, document: {querySelectorAll: (selector) => selector === 'table' ? tables : [element('symbol: TEST')]},
    location: {origin: 'https://www.tsetmc.com'}, getComputedStyle: () => ({display: 'table', visibility: 'visible'}),
    fetch: async (url, options) => {
      sent++;
      requests.push({url, options});
      if (fetchResult) return fetchResult(url, options);
      return {ok: true, json: async () => url.endsWith('/browser-nonce') ? {nonce: 'fixture_nonce'} : {accepted: true}};
    }});
  return {read: window.JackReadOnly.read, send: window.JackReadOnly.send, sent: () => sent,
    requests, messages, message: (event) => listener(event)};
}
test('header mapping works with reordered columns and explicit units', () => {
  const result = reader([fixture({headers: ['volume', 'date', 'close', 'low', 'open', 'high'], meta: {...metadata, jackPriceUnit: 'IRT', jackPriceType: 'adjusted'}})]).read();
  assert.equal(result.market_snapshot.ohlcv[0].close, 101);
  assert.equal(result.market_snapshot.price_unit, 'IRT');
  assert.equal(result.market_snapshot.price_type, 'adjusted');
});
test('descending dates normalize to chronological rows', () => {
  assert.equal(reader([fixture({reverse: true})]).read().market_snapshot.ohlcv[0].date, '2026-09-01');
});
test('missing, placeholder, infinite, malformed and zero prices block sending', async () => {
  for (const value of ['', 'N/A', '-', 'NaN', 'Infinity', '1e999', '100abc', '0', undefined]) {
    const r = reader([fixture({change: (data, i) => {if (i === 0) data.close = value;}})]);
    assert.equal(r.read().error, 'OHLCV_NOT_RECOGNIZED');
    assert.equal((await r.send()).ok, false);
    assert.equal(r.sent(), 0);
  }
});
test('unrelated headers, unknown metadata, short and ambiguous tables block', () => {
  for (const tables of [[fixture({headers: ['a','b','c','d','e']})], [fixture({meta: {}})],
    [fixture({meta: {...metadata, jackSymbol: 'OTHER'}})], [fixture({count: 20})],
    [fixture(), fixture()]]) assert.equal(reader(tables).read().error, 'OHLCV_NOT_RECOGNIZED');
});
test('duplicate dates and inconsistent candles block', () => {
  for (const change of [(data, i) => {if(i === 1) data.date = '2026-09-01';},
    (data) => {data.high = '90';}, (data) => {data.date = '2026-02-30';}]) {
    assert.equal(reader([fixture({change})]).read().error, 'OHLCV_NOT_RECOGNIZED');
  }
});
test('zero volume remains valid', () => {
  assert.equal(reader([fixture({change: (data) => {data.volume = '0';}})]).read().market_snapshot.ohlcv[0].volume, 0);
});

test('send obtains nonce before POST and uses fresh nonce per request', async () => {
  let issued = 0;
  const r = reader([fixture()], (url) => ({ok: true, json: async () => url.endsWith('/browser-nonce') ? {nonce: `fixture_${++issued}`} : {accepted: true}}));
  assert.equal(r.read().bridge_nonce, undefined);
  assert.equal((await r.send()).ok, true);
  assert.equal((await r.send()).ok, true);
  assert.deepEqual(r.requests.map((request) => request.options.method), ['GET', 'POST', 'GET', 'POST']);
  assert.equal(JSON.parse(r.requests[1].options.body).bridge_nonce, 'fixture_1');
  assert.equal(JSON.parse(r.requests[3].options.body).bridge_nonce, 'fixture_2');
  assert.ok(r.requests.every((request) => request.options.credentials === 'omit'));
});

test('nonce failure or invalid response prevents POST', async () => {
  for (const response of [{ok: false, json: async () => ({})}, {ok: true, json: async () => ({})}, {ok: true, json: async () => ({nonce: 1})}, {ok: true, json: async () => ({nonce: ' '})}, {ok: true, json: async () => ({nonce: 'x'.repeat(129)})}]) {
    const r = reader([fixture()], () => response);
    assert.equal((await r.send()).ok, false);
    assert.equal(r.requests.length, 1);
    assert.equal(r.requests[0].options.method, 'GET');
  }
});

test('foreign page message cannot trigger send and response targets own origin', async () => {
  const r = reader([fixture()]);
  r.message({origin: 'https://evil.example', data: {type: 'JACK_READ_MARKET'}});
  assert.equal(r.sent(), 0);
  r.message({origin: 'https://www.tsetmc.com', data: {type: 'JACK_READ_MARKET'}});
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(r.requests.length, 2);
  assert.equal(r.messages[0].origin, 'https://www.tsetmc.com');
  assert.equal(JSON.stringify(r.messages).includes('fixture_nonce'), false);
});
