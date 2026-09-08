// Disposable DOM/network harness; actual browser acceptance remains separate.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const sample = () => ({revision: 2, current: {
  id: 'approach', path: '方案.md', kind: 'approach', version: 1,
  sha256: 'a'.repeat(64), status: 'pending_review', content: '待审方案', snapshot: {available: true},
}, previous: {available: false, message: '没有前版'}, figures: [], retain_chapters: []});
const tick = () => new Promise(resolve => setImmediate(resolve));
function element() {
  return {textContent: '', value: '', disabled: false, hidden: false, children: [], dataset: {},
    replaceChildren(...items) {this.children = items;}, append(...items) {this.children.push(...items);},
    addEventListener(name, callback) {this[name] = callback;}};
}
function harness(fetch) {
  const elements = new Map();
  const get = id => {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);};
  let sequence = 0;
  const context = {window: {location: {search: '?token=test', pathname: '/'}}, URLSearchParams,
    crypto: {randomUUID: () => `event-${++sequence}`},
    document: {getElementById: get, querySelectorAll: () => [], createElement: element}, fetch,
    URL: {createObjectURL: () => 'blob:synthetic', revokeObjectURL: () => {}}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);
  return {get, run: code => vm.runInContext(code, context)};
}
const ok = value => ({ok: true, json: async () => value});
async function savedButRefreshFails() {
  let gets = 0, persisted = false;
  const ui = harness(async (path, options) => {
    if (options.method === 'POST') {persisted = true; return ok({revision: 3});}
    if (++gets === 1) return ok(sample());
    return {ok: false, json: async () => ({error: 'temporary view sync error'})};
  });
  await tick(); await ui.get('approve').click();
  assert.equal(persisted, true);
  assert.match(ui.get('status').textContent, /已记录/);
  assert.doesNotMatch(ui.get('status').textContent, /未保存/);
  assert.equal(ui.get('approve').disabled, true);
}
async function onlyOneInflightAction() {
  let resolvePost, posts = 0;
  const ui = harness(async (path, options) => {
    if (options.method === 'POST') {posts++; return new Promise(resolve => {resolvePost = resolve;});}
    return ok(sample());
  });
  await tick(); const first = ui.get('approve').click();
  assert.equal(ui.get('approve').disabled, true);
  await ui.get('approve').click();
  assert.equal(posts, 1);
  resolvePost(ok({revision: 3})); await first;
}
async function obsoleteFigureRenderIsDiscarded() {
  let resolveOld;
  const ui = harness(async (path) => {
    if (path === '/old-image') return new Promise(resolve => {resolveOld = resolve;});
    return ok(sample());
  });
  await tick();
  ui.run(`review.figures = [{id:'old',caption:'old',storage_label:'old',path:'old.png',placement:'old',version:1,image_url:'/old-image',related_chapters:[]}]; render();`);
  ui.run(`review.figures = [{id:'new',caption:'new',storage_label:'new',path:'new.txt',placement:'new',version:2,image_url:null,related_chapters:[]}]; render();`);
  resolveOld({ok: true, blob: async () => ({})}); await tick();
  assert.equal(ui.get('figure-items').children.length, 1);
  assert.match(ui.get('figure-items').children[0].children[0].textContent, /new/);
}
async function missingImageIsVisibleError() {
  const ui = harness(async path => path === '/missing-image'
    ? {ok: false, status: 404} : ok(sample()));
  await tick();
  await ui.run(`renderFigures([{id:'missing',caption:'missing',storage_label:'missing',path:'missing.png',placement:'missing',version:1,image_url:'/missing-image',related_chapters:[]}])`);
  const texts = ui.get('figure-items').children[0].children.map(child => child.textContent).join(' ');
  assert.match(texts, /图片.*(失败|不可用)/);
}
async function lostPostResponseDoesNotClaimNothingWasSaved() {
  const ui = harness(async (path, options) => {
    if (options.method === 'POST') throw new TypeError('connection lost after commit');
    return ok(sample());
  });
  await tick(); await ui.get('approve').click();
  assert.doesNotMatch(ui.get('status').textContent, /未保存/);
  assert.match(ui.get('status').textContent, /核对/);
  assert.equal(ui.get('approve').disabled, true);
}
(async () => {
  let failures = 0;
  for (const test of [savedButRefreshFails, onlyOneInflightAction, obsoleteFigureRenderIsDiscarded, missingImageIsVisibleError, lostPostResponseDoesNotClaimNothingWasSaved]) {
    try {await test(); console.log(`PASS ${test.name}`);}
    catch (error) {failures++; console.error(`FAIL ${test.name}: ${error.message}`);}
  }
  assert.equal(failures, 0, `${failures} review UI regressions`);
})().catch(error => {console.error(error); process.exitCode = 1;});
