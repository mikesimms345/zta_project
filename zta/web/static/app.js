const csrf = document.querySelector('meta[name="csrf-token"]').content;
const message = document.querySelector('#message');
let stream, captureId, timer, running = false, generation = 0;
const video = document.querySelector('#preview');
const startButton = document.querySelector('#start');
const stopButton = document.querySelector('#stop');


async function api(path, method, body, type = 'application/json') {
  const response = await fetch(path, {method, body, headers: {'X-CSRF-Token': csrf, 'Content-Type': type}});
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

async function stop() {
  running = false;
  generation++;
  clearTimeout(timer);
  stream?.getTracks().forEach(track => track.stop());
  stream = null;
  if (video) video.srcObject = null;
  const oldId = captureId;
  captureId = null;
  if (stopButton) stopButton.disabled = true;
  if (oldId) {
    try { await api(`/api/captures/${oldId}`, 'DELETE'); }
    catch (error) { message.textContent = error.message; }
  }
  if (startButton) startButton.disabled = false;
}

async function sendFrame(token) {
  if (!running || token !== generation) return;
  try {
    if (video.readyState >= 2) {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext('2d').drawImage(video, 0, 0);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.8));
      if (!running || token !== generation) return;
      if (!blob) throw new Error('Could not capture a frame');
      const data = await api(`/api/captures/${captureId}/frames`, 'POST', blob, 'image/jpeg');
      if (!running || token !== generation) return;
      const text = {collecting: 'Collecting evidence', flagged: 'Synthetic-media threshold reached',
        below_threshold: 'Below synthetic-media threshold'};
      document.querySelector('#result').textContent = `${text[data.status]} — ${data.sample_count}/${data.window_size} frames, ${Math.round(data.fake_ratio * 100)}% flagged.`;
    }
    // Backpressure: wait for inference before scheduling the next sample.
    if (running && token === generation) timer = setTimeout(() => sendFrame(token), 200);
  } catch (error) {
    if (!running || token !== generation) return;
    message.textContent = error.message;
    document.querySelector('#result').textContent = 'Check interrupted; current result unavailable.';
    await stop();
  }
}

startButton?.addEventListener('click', async () => {
  startButton.disabled = true;
  message.textContent = '';
  document.querySelector('#result').textContent = 'No evidence collected.';
  try {
    stream = await navigator.mediaDevices.getUserMedia({video: {width: {ideal: 640}, height: {ideal: 480}}, audio: false});
    video.srcObject = stream;
    await video.play();
    captureId = (await api('/api/captures', 'POST')).capture_id;
    running = true;
    stopButton.disabled = false;
    const token = ++generation;
    stream.getVideoTracks()[0].addEventListener('ended', () => { void stop(); });
    void sendFrame(token);
  } catch (error) { message.textContent = error.message; await stop(); }
});
stopButton?.addEventListener('click', () => { void stop(); });
document.querySelector('#logout')?.addEventListener('click', async () => {
  await stop();
  try { await api('/api/logout', 'POST'); location.reload(); }
  catch (error) { message.textContent = error.message; }
});
window.addEventListener('pagehide', () => {
  running = false;
  stream?.getTracks().forEach(track => track.stop());
});
