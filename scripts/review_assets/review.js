const token = new URLSearchParams(window.location.search).get('token') || '';
let review = null;

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

async function renderFigures(entries) {
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
      const response = await fetch(entry.image_url, {headers: {'X-Review-Token': token}});
      if (response.ok) {
        const image = document.createElement('img');
        image.alt = entry.caption;
        image.src = URL.createObjectURL(await response.blob());
        article.append(image);
      }
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
  setText('object-title', `${review.current.path} · v${review.current.version}`);
  setText('identity', `对象 ${review.current.id}\n摘要 ${review.current.sha256}\n状态 revision ${review.revision}`);
  setText('current-label', `v${review.current.version} · ${review.current.status}`);
  setText('current-content', review.current.content || review.current.snapshot.message || '内容不可用');
  setText('previous-label', review.previous.version ? `v${review.previous.version}` : '无前版');
  setText('previous-content', review.previous.content || review.previous.message || '历史内容不可用');
  renderRetention(review.retain_chapters || []);
  renderFigures(review.figures || []).catch((error) => {
    setText('status', `配图读取失败：${error.message}`);
  });
  const pending = review.current.status === 'pending_review';
  document.getElementById('save-preference').disabled = !pending;
  document.getElementById('approve').disabled = !pending;
  document.getElementById('request-changes').disabled = !['pending_review', 'approved'].includes(review.current.status);
}

async function refresh(message = '') {
  review = await api('/api/review');
  render();
  setText('status', message || `已读取 ${review.current.id} v${review.current.version}`);
}

async function submitEvent(event) {
  const response = await api('/api/events', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({expected_revision: review.revision, event}),
  });
  await refresh(`已记录 ${event.object_id} v${event.version}；服务端 revision ${response.revision}`);
}

async function act(callback) {
  try {
    setText('status', '正在保存…');
    await callback();
  } catch (error) {
    setText('status', `未保存：${error.message}。请刷新后核对当前版本。`);
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

refresh().catch((error) => setText('status', `无法读取：${error.message}`));
