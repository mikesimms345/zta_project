const csrf = document.querySelector('meta[name="csrf-token"]').content;
const message = document.querySelector('#message');
const startButton = document.querySelector('#start');
const stopButton = document.querySelector('#stop');
let captureId, events, running = false;


async function api(path, method, body) {
  const options = {method, headers: {'X-CSRF-Token': csrf}};
  if (body !== undefined) {
    options.body = body;
    options.headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(path, options);
  const data = response.status === 204 ? {} : await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

document.querySelector('#login')?.addEventListener('submit', async event => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api('/api/login', 'POST', JSON.stringify(Object.fromEntries(form)));
    location.reload();
  } catch (error) { message.textContent = error.message; }
});

function renderState(state) {
  const result = document.querySelector('#result');
  if (state.phase === 'starting') {
    result.textContent = 'Opening the local camera.';
    return;
  }
  if (state.phase === 'running' && state.sample_count === undefined) {
    result.textContent = 'RGB-D camera ready; starting inference and liveness.';
    return;
  }
  const summaries = [];
  if (state.sample_count !== undefined) {
    const text = {collecting: 'Collecting evidence', flagged: 'Synthetic-media threshold reached',
      below_threshold: 'Below synthetic-media threshold'};
    summaries.push(`${text[state.status]} - ${state.sample_count}/${state.window_size} frames, ${Math.round(state.fake_ratio * 100)}% flagged`);
  }
  if (state.liveness !== undefined) {
    const livenessText = {collecting: 'Liveness collecting', live: 'Liveness challenge complete',
      spoof_suspected: 'Possible presentation attack', unavailable: 'Liveness unavailable'};
    summaries.push(`${livenessText[state.liveness.status]} - ${state.liveness.instruction}`);
  }
  if (summaries.length) result.textContent = `${summaries.join(' | ')}.`;
  if (state.phase === 'failed') message.textContent = state.error;
  if (state.phase === 'stopped') message.textContent = 'Camera check stopped.';
  if (['failed', 'stopped'].includes(state.phase)) {
    running = false;
    events?.close();
    events = null;
    startButton.disabled = false;
    stopButton.disabled = true;
  }
}

function watchCapture(id) {
  events?.close();
  events = new EventSource(`/api/captures/${id}/events`);
  events.onmessage = event => renderState(JSON.parse(event.data));
  events.onerror = () => {
    if (!running) return;
    message.textContent = 'Lost the camera-status stream.';
    running = false;
    events?.close();
    startButton.disabled = false;
    stopButton.disabled = true;
  };
}

async function stop() {
  running = false;
  events?.close();
  events = null;
  const oldId = captureId;
  captureId = null;
  stopButton.disabled = true;
  if (oldId) {
    try { await api(`/api/captures/${oldId}`, 'DELETE'); }
    catch (error) { message.textContent = error.message; }
  }
  startButton.disabled = false;
}

startButton?.addEventListener('click', async () => {
  startButton.disabled = true;
  message.textContent = '';
  document.querySelector('#result').textContent = 'Starting camera check.';
  try {
    captureId = (await api('/api/captures', 'POST')).capture_id;
    running = true;
    stopButton.disabled = false;
    watchCapture(captureId);
  } catch (error) {
    message.textContent = error.message;
    startButton.disabled = false;
  }
});

stopButton?.addEventListener('click', () => { void stop(); });
document.querySelector('#logout')?.addEventListener('click', async () => {
  await stop();
  try { await api('/api/logout', 'POST'); location.reload(); }
  catch (error) { message.textContent = error.message; }
});
window.addEventListener('pagehide', () => {
  events?.close();
  if (captureId) {
    void fetch(`/api/captures/${captureId}`, {
      method: 'DELETE', keepalive: true, headers: {'X-CSRF-Token': csrf},
    });
  }
});
