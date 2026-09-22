'use strict';
const $ = (id) => document.getElementById(id);
const items = [];
let running = false;
let cancelled = false;
let activeWorker = null;
let rejectEncoding = null;
const limit = 200 * 1024 * 1024;
const durationLimit = 3 * 60 * 60;
const formatSize = (bytes) => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(2)} MB`;
const pending = () => items.filter(item => !['done','skipped'].includes(item.state));

function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
function updateRow(item) {
  item.row.querySelector('.file-name').textContent = item.file.name;
  item.row.querySelector('.file-meta').textContent = item.resultSize ? `${formatSize(item.file.size)} → ${formatSize(item.resultSize)} · ${Math.round((1 - item.resultSize / item.file.size) * 100)}% 감소` : formatSize(item.file.size);
  const status = item.row.querySelector('.file-status');
  status.textContent = item.message;
  status.classList.toggle('error', item.state === 'error');
  const link = item.row.querySelector('.download');
  link.hidden = !item.url;
  if (item.url) { link.href = item.url; link.download = item.outputName; link.setAttribute('aria-label', `${item.file.name} 압축 파일 다운로드`); }
}
function updateControls() {
  $('queue').hidden = !items.length;
  $('file-count').textContent = items.length;
  for (const id of ['choose','file-input','clear','bitrate','channels']) $(id).disabled = running;
  document.querySelectorAll('.remove').forEach(button => button.disabled = running);
  $('start').disabled = running || pending().length === 0;
  $('cancel').hidden = !running;
}
function addFiles(files) {
  if (running) return;
  const errors = [];
  for (const file of files) {
    if (!/\.mp3$/i.test(file.name)) { errors.push(`${file.name}: MP3 파일만 선택할 수 있습니다.`); continue; }
    if (!file.size || file.size > limit) { errors.push(`${file.name}: 0바이트 초과, 200MB 이하 파일을 선택해 주세요.`); continue; }
    if (items.some(item => item.file.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified)) continue;
    const row = $('file-template').content.firstElementChild.cloneNode(true);
    const item = {file, row, state:'ready', message:'대기 중', url:null};
    row.querySelector('.remove').setAttribute('aria-label', `${file.name} 목록에서 제거`);
    row.querySelector('.remove').addEventListener('click', () => {
      if (running) return;
      if (item.url) URL.revokeObjectURL(item.url);
      items.splice(items.indexOf(item), 1); row.remove(); updateControls();
    });
    items.push(item); $('files').append(row); updateRow(item);
  }
  notice(errors.join(' '));
  $('status').textContent = `${pending().length}개 파일을 압축할 준비가 되었습니다.`;
  $('progress').value = 0;
  updateControls();
}
// 부동소수점 샘플을 16비트로 미리 바꾼다. 워커에서 바꾸면 긴 파일의 메모리가 두 배로 든다.
const quantize = (value) => {
  const clamped = Math.max(-1, Math.min(1, value));
  return Math.round(clamped * (clamped < 0 ? 32768 : 32767));
};
function toPcm(source, mono) {
  const length = source[0].length;
  const downmix = mono && source.length > 1;
  const count = downmix ? 1 : source.length;
  const channels = Array.from({length:count}, () => new Int16Array(length));
  for (let i = 0; i < length; i++) {
    if (downmix) channels[0][i] = quantize((source[0][i] + source[1][i]) / 2);
    else for (let channel = 0; channel < count; channel++) channels[channel][i] = quantize(source[channel][i]);
  }
  return channels;
}
function encode(channels, bitrate, onProgress) {
  return new Promise((resolve, reject) => {
    const worker = new Worker('./encoder-worker.js');
    activeWorker = worker;
    rejectEncoding = reject;
    worker.onmessage = ({data}) => {
      if (data.type === 'progress') onProgress(data.progress);
      if (data.type === 'done') resolve(data.blob);
      if (data.type === 'error') reject(new Error(data.message));
    };
    worker.onerror = () => reject(new Error('압축기를 실행할 수 없습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.'));
    worker.postMessage({channels, sampleRate:24000, bitrate}, channels.map(channel => channel.buffer));
  }).finally(() => { activeWorker?.terminate(); activeWorker = null; rejectEncoding = null; });
}
function uniqueName(original, bitrate) {
  const base = original.replace(/\.mp3$/i, '') + `_${bitrate}kbps`;
  const used = new Set(items.map(item => item.outputName).filter(Boolean));
  let name = `${base}.mp3`, i = 1;
  while (used.has(name)) name = `${base}_${i++}.mp3`;
  return name;
}
async function start() {
  if (running || !pending().length) return;
  const OfflineContext = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  if (!OfflineContext || !window.Worker) { notice('이 브라우저는 압축 기능을 지원하지 않습니다. 최신 Chrome, Edge, Firefox 또는 Safari를 사용해 주세요.'); return; }
  running = true; cancelled = false; notice(); updateControls(); $('cancel').disabled = false;
  const batch = pending();
  const bitrate = Number($('bitrate').value);
  const mono = $('channels').value === '1';
  let saved = 0, done = 0, skipped = 0, failed = 0;
  try {
    for (let index = 0; index < batch.length; index++) {
      if (cancelled) break;
      const item = batch[index];
      item.state = 'working'; item.message = '오디오 읽는 중…'; updateRow(item);
      $('status').textContent = `${index + 1}/${batch.length} · ${item.file.name}`;
      $('progress').value = index / batch.length * 100;
      try {
        const decoder = new OfflineContext(2, 1, 24000);
        let decoded;
        try { decoded = await decoder.decodeAudioData(await item.file.arrayBuffer()); }
        catch { throw new Error('MP3를 읽을 수 없습니다. 손상되었거나 지원하지 않는 파일입니다.'); }
        if (cancelled) throw new Error('cancelled');
        if (decoded.duration > durationLimit) throw new Error('3시간 이하 파일을 선택해 주세요. 긴 파일은 PC 프로그램을 이용할 수 있습니다.');
        const channels = toPcm(Array.from({length:Math.min(2, decoded.numberOfChannels)}, (_, channel) => decoded.getChannelData(channel)), mono);
        decoded = null;
        const blob = await encode(channels, bitrate, value => {
          item.message = `압축 중 ${value}%`; updateRow(item);
          $('progress').value = (index + value / 100) / batch.length * 100;
        });
        if (cancelled) throw new Error('cancelled');
        if (blob.size >= item.file.size) { item.state = 'skipped'; item.message = '원본이 더 작아 저장을 생략했습니다.'; skipped++; }
        else {
          item.url = URL.createObjectURL(blob); item.resultSize = blob.size;
          item.outputName = uniqueName(item.file.name, bitrate);
          item.state = 'done'; item.message = `완료 · ${bitrate}kbps · ${mono ? '모노' : '스테레오 (원본이 모노면 모노)'}`;
          saved += item.file.size - blob.size; done++;
        }
      } catch (error) {
        if (cancelled) { item.state = 'cancelled'; item.message = '취소됨 · 다시 시작할 수 있습니다.'; }
        else { item.state = 'error'; item.message = error.message || '압축 중 오류가 발생했습니다.'; failed++; }
      }
      updateRow(item);
      if (cancelled) break;
      $('progress').value = (index + 1) / batch.length * 100;
    }
  } finally {
    running = false; updateControls();
    $('status').textContent = `${cancelled ? '취소됨' : '작업 완료'} · 성공 ${done}개 · 생략 ${skipped}개 · 오류 ${failed}개 · ${formatSize(saved)} 절약`;
  }
}
$('choose').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', (event) => { addFiles(event.target.files); event.target.value = ''; });
$('start').addEventListener('click', start);
$('cancel').addEventListener('click', () => {
  cancelled = true; activeWorker?.terminate(); rejectEncoding?.(new Error('cancelled'));
  $('cancel').disabled = true; $('status').textContent = '취소 중… 오디오를 읽는 중이면 잠시 기다려 주세요.';
});
$('clear').addEventListener('click', () => {
  if (running) return;
  items.forEach(item => item.url && URL.revokeObjectURL(item.url)); items.length = 0;
  $('files').replaceChildren(); notice(); updateControls();
});
$('bitrate').addEventListener('change', () => {
  const rate = Number($('bitrate').value);
  $('estimate').replaceChildren(document.createTextNode(`${rate}kbps 기준`), document.createElement('br'));
  const strong = document.createElement('strong'); strong.textContent = `1분 ≈ ${rate * 60 / 8}KB`; $('estimate').append(strong);
});
for (const event of ['dragenter','dragover']) $('drop-zone').addEventListener(event, e => { e.preventDefault(); if (!running) $('drop-zone').classList.add('dragover'); });
for (const event of ['dragleave','drop']) $('drop-zone').addEventListener(event, e => { e.preventDefault(); $('drop-zone').classList.remove('dragover'); });
$('drop-zone').addEventListener('drop', e => addFiles(e.dataTransfer.files));
// Prevent an accidentally dropped audio file from replacing the current page.
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => e.preventDefault());
window.addEventListener('beforeunload', event => { if (running) { event.preventDefault(); event.returnValue = ''; } });
updateControls();
