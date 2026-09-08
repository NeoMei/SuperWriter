const token = new URLSearchParams(window.location.search).get('token') || '';
let review = null;
let saving = false;
let reviewReady = false;
let renderGeneration = 0;
const imageUrls = new Set();

function setText(id, text) {
  document.getElementById(id).textContent = text;
}

function eventId(kind) {
  return `${kind}-${crypto.randomUUID()}`;
}

function currentEvent(kind, payload, text) {
  return {
    id: eventId(kind),
    kind,
    object_id: review.current.id,
    version: review.current.version,
    sha256: review.current.sha256,
    channel: 'web',
    evidence: {reference: `local-review:${window.location.pathname}`, text},
    payload,
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {...(options.headers || {}), 'X-Review-Token': token},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({error: response.statusText}));
    throw new Error(body.error || response.statusText);
  }
  return response.json();
}

function renderRetention(entries) {
  const fieldset = document.getElementById('retention');
  const options = document.getElementById('retention-options');
  options.replaceChildren();
  fieldset.hidden = entries.length === 0;
  for (const entry of entries) {
    const label = document.createElement('label');
    label.className = 'retention-option';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.dataset.entry = JSON.stringify({
      id: entry.id,
      version: entry.version,
      sha256: entry.sha256,
      previous_outline_version: entry.previous_outline_version,
    });
    const text = document.createElement('span');
    text.textContent = `${entry.label} · ${entry.id} · v${entry.version}`;
    label.append(input, text);
    options.append(label);
  }
}

async function imagePreview(url, caption) {
  try {
    const response = await fetch(url, {headers: {'X-Review-Token': token}});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const image = document.createElement('img');
    image.alt = caption;
    image.src = URL.createObjectURL(await response.blob());
    imageUrls.add(image.src);
    return image;
  } catch (error) {
    const warning = document.createElement('p');
    warning.textContent = `图片预览失败：${error.message}。请刷新后核对图片。`;
    return warning;
  }
}

function discardImage(image) {
  if (image.src) {
    URL.revokeObjectURL(image.src);
    imageUrls.delete(image.src);
  }
}

async function renderSnapshot(prefix, snapshot, generation) {
  const preview = document.getElementById(`${prefix}-preview`);
  preview.replaceChildren();
  preview.hidden = !snapshot.image_url;
  if (!snapshot.image_url) return;
  const image = await imagePreview(snapshot.image_url, `${snapshot.id} v${snapshot.version}`);
  if (generation !== renderGeneration) {discardImage(image); return;}
  preview.append(image);
}

async function renderFigures(entries, generation = renderGeneration) {
  const section = document.getElementById('figure-review');
  const container = document.getElementById('figure-items');
  container.replaceChildren();
  section.hidden = entries.length === 0;
  for (const entry of entries) {
    const article = document.createElement('article');
    article.className = 'figure-item';
    const heading = document.createElement('h3');
    heading.textContent = `${entry.caption} · ${entry.id} · v${entry.version}`;
    const path = document.createElement('p');
    path.textContent = `存储标签：${entry.storage_label} · 登记路径：${entry.path}`;
    const placement = document.createElement('p');
    placement.textContent = `插入位置：${entry.placement}`;
    article.append(heading, path, placement);
    if (entry.image_url) {
      const image = await imagePreview(entry.image_url, entry.caption);
      if (generation !== renderGeneration) {discardImage(image); return;}
      article.append(image);
    }
    for (const relatedChapter of entry.related_chapters) {
      const context = document.createElement('div');
      context.className = 'figure-context';
      const label = document.createElement('strong');
      label.textContent = `相关章节：${relatedChapter.label} · ${relatedChapter.id}`;
      const excerpt = document.createElement('pre');
      excerpt.textContent = relatedChapter.content;
      context.append(label, excerpt);
      article.append(context);
    }
    container.append(article);
  }
}

function render() {
  const generation = ++renderGeneration;
  for (const url of imageUrls) URL.revokeObjectURL(url);
  imageUrls.clear();
  setText('object-title', `${review.current.path} · v${review.current.version}`);
  setText('identity', `对象 ${review.current.id}\n摘要 ${review.current.sha256}\n状态 revision ${review.revision}`);
  setText('current-label', `v${review.current.version} · ${review.current.status}`);
  setText('current-content', review.current.content ?? review.current.message ?? '内容不可用');
  setText('previous-label', review.previous.version ? `v${review.previous.version}` : '无前版');
  setText('previous-content', review.previous.content ?? review.previous.message ?? '历史内容不可用');
  renderSnapshot('current', review.current, generation);
  renderSnapshot('previous', review.previous, generation);
  renderRetention(review.retain_chapters || []);
  renderFigures(review.figures || [], generation).catch((error) => {
    if (generation !== renderGeneration) return;
    setText('status', `配图读取失败：${error.message}`);
  });
  updateActions();
}

function updateActions() {
  const usable = reviewReady && !saving && review;
  const pending = usable && review.current.status === 'pending_review';
  document.getElementById('save-preference').disabled = !pending;
  document.getElementById('approve').disabled = !pending;
  document.getElementById('request-changes').disabled = !usable || !['pending_review', 'approved'].includes(review.current.status);
}

async function refresh(message = '') {
  review = await api('/api/review');
  reviewReady = true;
  render();
  setText('status', message || `已读取 ${review.current.id} v${review.current.version}`);
}

async function submitEvent(event) {
  let response;
  try {
    response = await api('/api/events', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({expected_revision: review.revision, event}),
    });
  } catch (error) {
    // A lost response (or a failed derived view write) can follow a durable commit.
    reviewReady = false;
    error.submissionFailed = true;
    throw error;
  }
  const message = `已记录 ${event.object_id} v${event.version}；服务端 revision ${response.revision}`;
  try {
    await refresh(message);
  } catch (error) {
    reviewReady = false;
    setText('status', `${message}。页面刷新失败：${error.message}。请刷新页面核对。`);
  }
}

async function act(callback) {
  if (saving || !reviewReady) return;
  saving = true;
  updateActions();
  try {
    setText('status', '正在保存…');
    await callback();
  } catch (error) {
    const outcome = error.submissionFailed ? '提交结果需核对' : '未保存';
    setText('status', `${outcome}：${error.message}。请刷新后核对当前版本。`);
  } finally {
    saving = false;
    updateActions();
  }
}

document.getElementById('save-preference').addEventListener('click', () => act(async () => {
  const input = document.getElementById('preference');
  const text = input.value.trim();
  if (!text) throw new Error('请先填写偏好');
  await submitEvent(currentEvent('record_preference', {scope: review.current.id, text}, text));
  input.value = '';
}));

document.getElementById('request-changes').addEventListener('click', () => act(async () => {
  const input = document.getElementById('changes');
  const comment = input.value.trim();
  if (!comment) throw new Error('请先填写修改意见');
  await submitEvent(currentEvent('request_changes', {comment}, comment));
  input.value = '';
}));

document.getElementById('approve').addEventListener('click', () => act(async () => {
  const retained = [...document.querySelectorAll('#retention-options input:checked')]
    .map((input) => JSON.parse(input.dataset.entry));
  const payload = review.current.kind === 'outline' ? {retain_chapters: retained} : {};
  const text = retained.length
    ? `确认当前版本，并明确保留章节：${retained.map((item) => item.id).join('、')}`
    : '确认当前版本';
  await submitEvent(currentEvent('approve', payload, text));
}));

updateActions();
refresh().catch((error) => setText('status', `无法读取：${error.message}`));
