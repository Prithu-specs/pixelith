/* SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
   Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
   stated allowance; beyond it, and for all commercial use, a paid licence
   is required. See LICENSE. */
/* ============================================================================
 * Pixelith web UI
 *
 * Sections
 *   1. Constants and element refs
 *   2. Small utilities
 *   3. Toasts and connectivity state
 *   4. API client
 *   5. Persisted settings
 *   6. Boot: health, models, presets
 *   7. File intake and media probing
 *   8. Estimation
 *   9. Submission
 *  10. Job rendering
 *  11. Live updates (SSE with polling fallback)
 *  12. Before/after compare slider
 *  13. Init
 * ========================================================================== */
'use strict';

/* -------------------------------------------------------------------------- *
 * 1. Constants and element refs
 * -------------------------------------------------------------------------- */

const API = '/api';
const STORE_KEY = 'pixelith.settings.v1';
const POLL_MS = 1500;
const ASSUMED_FPS = 30;               // API contract: assume 30 when fps is unknown
const TERMINAL = new Set(['done', 'error', 'cancelled']);

const IMAGE_EXT = ['png', 'jpg', 'jpeg', 'webp', 'heic', 'heif', 'bmp', 'tif', 'tiff'];
const VIDEO_EXT = ['mp4', 'mov', 'mkv', 'webm', 'avi'];

const $ = (sel, root = document) => root.querySelector(sel);

const el = {
  healthPill:   $('#health-pill'),
  healthText:   $('#health-text'),
  offlineBanner:$('#offline-banner'),
  allowance:$('#allowance'),
  allowanceTier:$('#allowance-tier'),
  allowanceMeters:$('#allowance-meters'),
  allowanceNote:$('#allowance-note'),
  allowanceUpgrade:$('#allowance-upgrade'),
  paywall:$('#paywall'),
  paywallDetail:$('#paywall-detail'),
  presetOut:$('#preset-out'),
  presetScale:$('#preset-scale'),
  presetDetail:$('#preset-detail'),
  presetTicks:$('#preset-ticks'),
  pricePersonal:$('#price-personal'),
  priceCommercial:$('#price-commercial'),
  paywallTax:$('#paywall-tax'),
  paywallContact:$('#paywall-contact'),
  paywallKey:$('#paywall-key'),
  paywallError:$('#paywall-error'),
  paywallActivate:$('#paywall-activate'),
  paywallClose:$('#paywall-close'),
  offlineDetail:$('#offline-detail'),
  retryHealth:  $('#retry-health'),

  form:         $('#compose-form'),
  dropzone:     $('#dropzone'),
  fileInput:    $('#file-input'),
  queueWrap:    $('#queue-wrap'),
  queue:        $('#queue'),
  queueCount:   $('#queue-count'),
  clearQueue:   $('#clear-queue'),

  models:       $('#models'),
  modelsNote:   $('#models-note'),
  preset:       $('#preset'),
  presetPane:   $('#preset-pane'),
  scalePane:    $('#scale-pane'),
  scale:        $('#scale'),
  scaleOut:     $('#scale-out'),
  denoise:      $('#denoise'),
  denoiseOut:   $('#denoise-out'),
  sharpen:      $('#sharpen'),
  sharpenOut:   $('#sharpen-out'),
  imageFormat:  $('#image-format'),
  videoFormat:  $('#video-format'),
  imageFmtWrap: $('#image-format-wrap'),
  videoFmtWrap: $('#video-format-wrap'),

  estimateCard: $('#estimate-card'),
  estimateBody: $('#estimate-body'),
  estimateWarn: $('#estimate-warnings'),

  submitBtn:    $('#submit-btn'),
  submitLabel:  $('#submit-label'),

  jobs:         $('#jobs'),
  jobsEmpty:    $('#jobs-empty'),
  refreshJobs:  $('#refresh-jobs'),
  announcer:    $('#job-announcer'),
  toasts:       $('#toasts'),
  jobTpl:       $('#tpl-job'),
};

/** Files staged for upload but not yet submitted. */
const staged = [];
/** id -> { job, el, source, poll, failures, announced } */
const jobViews = new Map();
/** Model list from /api/models, and whether any of them are installed. */
let models = [];
let presets = {};
let presetKeys = [];
let online = null;          // null = unknown, true/false once established
let failStreak = 0;         // consecutive transport failures; see setOnline()
let submitting = false;
let stagedSeq = 0;

/* -------------------------------------------------------------------------- *
 * 2. Small utilities
 * -------------------------------------------------------------------------- */

function extOf(name) {
  const i = String(name).lastIndexOf('.');
  return i < 0 ? '' : name.slice(i + 1).toLowerCase();
}

function kindOf(file) {
  const ext = extOf(file.name);
  if (VIDEO_EXT.includes(ext)) return 'video';
  if (IMAGE_EXT.includes(ext)) return 'image';
  // Extension missing or unfamiliar: fall back to the browser's MIME guess.
  if (file.type.startsWith('video/')) return 'video';
  if (file.type.startsWith('image/')) return 'image';
  return null;
}

function formatBytes(n) {
  if (!Number.isFinite(n)) return '';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n < 10 && i > 0 ? n.toFixed(1) : Math.round(n)} ${u[i]}`;
}

/** Compact duration, e.g. "1h 53m", "4m 12s", "8s". Used for ETAs. */
function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '';
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return s % 60 ? `${m}m ${s % 60}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
}

/** Longer phrasing for batch totals, matching the tone of the API's `human`. */
function formatDurationLong(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return 'less than a minute';
  const s = Math.round(seconds);
  if (s < 60) return `${s} seconds`;
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  const parts = [];
  if (h) parts.push(`${h} hour${h === 1 ? '' : 's'}`);
  if (m) parts.push(`${m} minute${m === 1 ? '' : 's'}`);
  return `about ${parts.join(' ') || 'a minute'}`;
}

function formatDims(w, h) {
  return Number.isFinite(w) && Number.isFinite(h) ? `${w} × ${h}` : '';
}

function clamp(n, lo, hi) { return Math.min(hi, Math.max(lo, n)); }

/** Replace an element's children with plain text (never innerHTML with data). */
function setText(node, text) { if (node) node.textContent = text == null ? '' : String(text); }

function svgIcon(id, cls = 'icon') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#${id}`);
  svg.appendChild(use);
  return svg;
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

/* -------------------------------------------------------------------------- *
 * 3. Toasts and connectivity state
 * -------------------------------------------------------------------------- */

function toast(message, variant = 'info', timeout = 6000) {
  const node = document.createElement('div');
  node.className = `toast toast--${variant}`;
  node.appendChild(svgIcon(variant === 'error' ? 'i-alert' : variant === 'success' ? 'i-check' : 'i-clock'));

  const body = document.createElement('div');
  body.className = 'toast__body';
  body.textContent = message;
  node.appendChild(body);

  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'toast__close';
  close.setAttribute('aria-label', 'Dismiss notification');
  close.appendChild(svgIcon('i-x'));
  node.appendChild(close);

  const dismiss = () => {
    node.classList.add('is-leaving');
    setTimeout(() => node.remove(), 200);
  };
  close.addEventListener('click', dismiss);
  el.toasts.appendChild(node);
  if (timeout) setTimeout(dismiss, timeout);
}

/**
 * Single source of truth for "can we talk to the backend".
 *
 * One dropped request is not an outage. A single failed thumbnail should not
 * raise a full-width alarm, so a failure only counts once it has happened
 * twice in a row; any success resets the streak immediately.
 */
function setOnline(state, detail) {
  if (state === false) {
    if (++failStreak < 2) return;
  } else {
    failStreak = 0;
  }
  if (online === state && !detail) return;
  online = state;
  el.offlineBanner.hidden = state !== false;
  if (state === false) {
    setText(el.offlineDetail, detail || 'Make sure the Pixelith server is running, then try again.');
    el.healthPill.className = 'pill pill--danger';
    setText(el.healthText, 'Offline');
  }
  updateSubmitState();
}

function setHealth(health) {
  el.healthPill.className = 'pill pill--ok';
  const bits = [`v${health.version || '?'}`];
  const active = health.active && Object.values(health.active)[0];
  if (active) bits.push(String(active).replace('ExecutionProvider', ''));
  if (health.ffmpeg === false) bits.push('no ffmpeg');
  setText(el.healthText, bits.join(' · '));
  el.healthPill.title = health.ffmpeg === false
    ? 'FFmpeg was not found — video jobs are unavailable.'
    : 'Server reachable';
  if (health.ffmpeg === false) el.healthPill.className = 'pill pill--warn';
}

/* -------------------------------------------------------------------------- *
 * 4. API client
 * -------------------------------------------------------------------------- */

class ApiError extends Error {
  constructor(message, status, detail = null) {
    super(message);
    this.status = status;
    this.detail = detail;      // structured bodies (e.g. the 402 paywall)
  }
}

function friendlyError(status, detail) {
  const tail = detail ? ` ${detail}` : '';
  switch (status) {
    case 413: return `That file is larger than the server accepts.${tail}`;
    case 415: return `That file type is not supported.${tail}`;
    case 404: return `That job no longer exists on the server.${tail}`;
    case 422: return `The server rejected these settings.${tail}`;
    default:
      if (status >= 500) return `The server hit an error (${status}).${tail}`;
      return detail || `Request failed (${status}).`;
  }
}

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(API + path, options);
  } catch (err) {
    // AbortError is a deliberate cancellation, not a connectivity problem.
    if (err && err.name === 'AbortError') throw err;
    setOnline(false);
    throw new ApiError('Cannot reach the Pixelith server.', 0);
  }
  setOnline(true);

  if (!res.ok) {
    let detail = '';
    let raw = null;
    try {
      const body = await res.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
      else if (body && body.detail) raw = body.detail;
    } catch { /* non-JSON error body */ }
    if (res.status === 402 && raw) {
      throw new ApiError(raw.message || 'Free limit reached.', 402, raw);
    }
    throw new ApiError(friendlyError(res.status, detail), res.status, raw);
  }
  if (res.status === 204) return null;
  try { return await res.json(); } catch { return null; }
}

/* -------------------------------------------------------------------------- *
 * 5. Persisted settings
 * -------------------------------------------------------------------------- */

function loadSettings() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }        // private mode, quota, or corrupt JSON
}

function saveSettings() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(readSettings()));
  } catch { /* storage unavailable — settings simply do not persist */ }
}

function readSettings() {
  const modeInput = $('input[name="target-mode"]:checked');
  return {
    model: currentModel(),
    targetMode: modeInput ? modeInput.value : 'preset',
    preset: currentPreset(),
    scale: parseFloat(el.scale.value),
    denoise: parseFloat(el.denoise.value),
    sharpen: parseFloat(el.sharpen.value),
    imageFormat: el.imageFormat.value,
    videoFormat: el.videoFormat.value,
  };
}

function currentModel() {
  const picked = $('input[name="model"]:checked', el.models);
  return picked ? picked.value : null;
}

function applySettings(s) {
  if (s.targetMode === 'scale') {
    const r = $('input[name="target-mode"][value="scale"]');
    if (r) r.checked = true;
  }
  if (Number.isFinite(s.scale)) el.scale.value = clamp(s.scale, 1.5, 8);
  if (Number.isFinite(s.denoise)) el.denoise.value = clamp(s.denoise, 0, 1);
  if (Number.isFinite(s.sharpen)) el.sharpen.value = clamp(s.sharpen, 0, 1);
  if (s.imageFormat) el.imageFormat.value = s.imageFormat;
  if (s.videoFormat) el.videoFormat.value = s.videoFormat;
  syncSliderOutputs();
  syncTargetMode();
}

function syncSliderOutputs() {
  setText(el.scaleOut, `${parseFloat(el.scale.value).toFixed(1)}×`);
  setText(el.denoiseOut, parseFloat(el.denoise.value).toFixed(2));
  setText(el.sharpenOut, parseFloat(el.sharpen.value).toFixed(2));
}

function syncTargetMode() {
  const mode = ($('input[name="target-mode"]:checked') || {}).value || 'preset';
  el.presetPane.hidden = mode !== 'preset';
  el.scalePane.hidden = mode !== 'scale';
}

/**
 * Returns { preset } or { scale } — never both, per the API's either/or rule.
 * Falls back to the scale slider if the preset list never loaded.
 */
function targetPayload() {
  const mode = ($('input[name="target-mode"]:checked') || {}).value || 'preset';
  if (mode === 'preset' && currentPreset()) return { preset: currentPreset() };
  return { scale: parseFloat(el.scale.value) };
}

/* -------------------------------------------------------------------------- *
 * 6. Boot: health, models, presets
 * -------------------------------------------------------------------------- */

async function checkHealth() {
  el.healthPill.className = 'pill pill--muted';
  setText(el.healthText, 'Connecting…');
  try {
    const health = await api('/health');
    setHealth(health || {});
    return true;
  } catch (err) {
    setOnline(false, err instanceof ApiError && err.status
      ? `The server answered with an error (${err.status}).`
      : undefined);
    return false;
  }
}

async function loadModels() {
  try {
    models = (await api('/models')) || [];
  } catch {
    el.models.textContent = '';
    const p = document.createElement('p');
    p.className = 'hint';
    p.textContent = 'Models could not be loaded.';
    el.models.appendChild(p);
    return;
  }
  renderModels();
}

function renderModels() {
  el.models.textContent = '';
  const saved = loadSettings().model;
  const anyInstalled = models.some((m) => m.installed);

  models.forEach((m, i) => {
    const label = document.createElement('label');
    label.className = 'choice';

    const input = document.createElement('input');
    input.type = 'radio';
    input.name = 'model';
    input.value = m.key;
    // Per the UI spec, an uninstalled model is not selectable. If nothing is
    // installed at all we unlock the list so the app is still usable.
    input.disabled = !m.installed && anyInstalled;
    label.appendChild(input);

    const body = document.createElement('div');
    body.className = 'choice__body';

    const row = document.createElement('div');
    row.className = 'choice__row';
    const name = document.createElement('span');
    name.className = 'choice__name';
    name.textContent = m.label || m.key;
    row.appendChild(name);

    const size = document.createElement('span');
    size.className = 'choice__size';
    size.textContent = Number.isFinite(m.size_mb) ? `${m.size_mb.toFixed(1)} MB` : '';
    row.appendChild(size);

    if (!m.installed) {
      const tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = `Will download ${Math.round(m.size_mb || 0)} MB`;
      row.appendChild(tag);
    }
    body.appendChild(row);

    if (m.notes) {
      const notes = document.createElement('p');
      notes.className = 'choice__notes';
      notes.textContent = m.notes;
      body.appendChild(notes);
    }
    label.appendChild(body);
    el.models.appendChild(label);

    const selectable = !input.disabled;
    if (selectable && (m.key === saved || (!saved && i === 0))) input.checked = true;
  });

  // Nothing chosen yet (saved model is uninstalled) — take the first selectable.
  if (!currentModel()) {
    const first = $('input[name="model"]:not(:disabled)', el.models);
    if (first) first.checked = true;
  }

  el.modelsNote.hidden = anyInstalled || models.length === 0;
  if (!el.modelsNote.hidden) {
    el.modelsNote.textContent =
      'No model weights are cached yet. The first job will download the one you pick.';
  }
  updateSubmitState();
}

async function loadPresets() {
  try {
    presets = (await api('/presets')) || {};
  } catch {
    presets = {};
  }
  presetKeys = Object.keys(presets);

  if (!presetKeys.length) {
    el.preset.disabled = true;
    setText(el.presetOut, 'unavailable');
    return;
  }

  el.preset.disabled = false;
  el.preset.min = '0';
  el.preset.max = String(presetKeys.length - 1);

  // Ticks under the track, one per stop.
  el.presetScale.textContent = '';
  el.presetTicks.textContent = '';
  presetKeys.forEach((key, i) => {
    const span = document.createElement('span');
    span.textContent = prettyPreset(key);
    el.presetScale.appendChild(span);
    const opt = document.createElement('option');
    opt.value = String(i);
    opt.label = prettyPreset(key);
    el.presetTicks.appendChild(opt);
  });

  const saved = loadSettings().preset;
  const idx = presetKeys.indexOf(saved);
  el.preset.value = String(idx >= 0 ? idx : Math.max(0, presetKeys.indexOf('4k')));
  renderPreset();
}

/** "1080p" stays as it is; "4k" becomes "4K". */
function prettyPreset(key) {
  return /^\d+k$/i.test(key) ? key.toUpperCase() : key;
}

function currentPreset() {
  return presetKeys[Number(el.preset.value)] || presetKeys[0] || '';
}

/**
 * Reflect the slider: the chosen name, the size it produces for the staged
 * file, and whether that is actually an upscale.
 */
function renderPreset() {
  if (!presetKeys.length) return;
  const key = currentPreset();
  const idx = presetKeys.indexOf(key);
  setText(el.presetOut, prettyPreset(key));

  const [boxW, boxH] = presets[key] || [];
  const probed = staged.find((it) => it.source && it.source.width);
  const src = probed ? probed.source : null;

  [...el.presetScale.children].forEach((span, i) => {
    span.classList.toggle('is-current', i === idx);
    if (src) {
      const [bw, bh] = presets[presetKeys[i]] || [];
      const r = Math.min(bw / src.width, bh / src.height);
      span.classList.toggle('is-down', r <= 1);
    } else {
      span.classList.remove('is-down');
    }
  });

  if (!src) {
    setText(el.presetDetail, `Fits inside ${boxW} \u00d7 ${boxH}.`);
    el.presetDetail.classList.remove('is-down');
    return;
  }

  const ratio = Math.min(boxW / src.width, boxH / src.height);
  const outW = Math.round(src.width * ratio);
  const outH = Math.round(src.height * ratio);
  const down = ratio <= 1;
  // Equal size is neither an upscale nor a downscale; say so rather than
  // claiming the target is smaller when it is identical.
  const same = Math.abs(ratio - 1) < 0.005;
  const note = same
    ? ' \u2014 the same size as the source, so nothing is added'
    : down
      ? ' \u2014 smaller than the source, so this only resamples down'
      : ` \u2014 ${ratio.toFixed(1)}\u00d7 larger`;
  setText(el.presetDetail,
    `${src.width} \u00d7 ${src.height} \u2192 ${outW} \u00d7 ${outH}${note}`);
  el.presetDetail.classList.toggle('is-down', down);
}

/* -------------------------------------------------------------------------- *
 * 7. File intake and media probing
 * -------------------------------------------------------------------------- */

function addFiles(fileList) {
  const rejected = [];
  for (const file of Array.from(fileList || [])) {
    const kind = kindOf(file);
    if (!kind) { rejected.push(file.name); continue; }
    if (staged.some((s) => s.file.name === file.name && s.file.size === file.size)) continue;

    const item = {
      id: `s${++stagedSeq}`,
      file,
      kind,
      source: null,
      probeError: null,
      estimate: null,
      estimateError: null,
      busy: true,
    };
    staged.push(item);
    probe(item);
  }
  if (rejected.length) {
    toast(`Skipped ${rejected.length} unsupported file${rejected.length === 1 ? '' : 's'}: ${rejected.join(', ')}`, 'error');
  }
  renderQueue();
  updateSubmitState();
}

async function probe(item) {
  try {
    item.source = item.kind === 'video'
      ? await probeVideo(item.file)
      : await probeImage(item.file);
  } catch (err) {
    item.probeError = err && err.message ? err.message : 'Could not read this file.';
  } finally {
    item.busy = false;
    renderQueue();
    scheduleEstimate();
  }
}

async function probeImage(file) {
  // createImageBitmap is the cheapest path but throws on formats the browser
  // cannot decode (HEIC on most desktops), so fall back to an <img> decode.
  if (typeof createImageBitmap === 'function') {
    try {
      const bmp = await createImageBitmap(file);
      const out = { width: bmp.width, height: bmp.height, frames: null, fps: null, duration: null };
      if (bmp.close) bmp.close();
      return out;
    } catch { /* fall through */ }
  }
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((resolve, reject) => {
      const node = new Image();
      node.onload = () => resolve(node);
      node.onerror = () => reject(new Error('This browser cannot read the dimensions of this image.'));
      node.src = url;
    });
    return { width: img.naturalWidth, height: img.naturalHeight, frames: null, fps: null, duration: null };
  } finally {
    URL.revokeObjectURL(url);
  }
}

function probeVideo(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement('video');
    video.preload = 'metadata';
    video.muted = true;
    video.playsInline = true;

    const done = (fn, arg) => {
      clearTimeout(timer);
      video.removeAttribute('src');
      video.load();
      URL.revokeObjectURL(url);
      fn(arg);
    };
    const timer = setTimeout(
      () => done(reject, new Error('Timed out reading the video metadata.')),
      15000,
    );

    video.addEventListener('loadedmetadata', () => {
      const duration = Number.isFinite(video.duration) ? video.duration : null;
      // The browser exposes no frame rate, so the contract's 30 fps assumption
      // is used to turn duration into a frame count.
      const fps = ASSUMED_FPS;
      done(resolve, {
        width: video.videoWidth,
        height: video.videoHeight,
        duration,
        fps,
        frames: duration ? Math.max(1, Math.round(duration * fps)) : null,
      });
    }, { once: true });

    video.addEventListener('error', () => {
      done(reject, new Error('This browser cannot read this video container.'));
    }, { once: true });

    video.src = url;
  });
}

function renderQueue() {
  // Source dimensions drive the size read-out and the downscale markers.
  if (typeof renderPreset === 'function' && presetKeys.length) renderPreset();
  el.queueWrap.hidden = staged.length === 0;
  setText(el.queueCount, staged.length ? String(staged.length) : '');
  el.queue.textContent = '';

  for (const item of staged) {
    const li = document.createElement('li');
    li.className = 'queue-item' + (item.probeError ? ' queue-item--bad' : '');

    const icon = document.createElement('span');
    icon.className = 'queue-item__icon';
    icon.appendChild(svgIcon(item.kind === 'video' ? 'i-video' : 'i-image'));
    li.appendChild(icon);

    const body = document.createElement('div');
    body.className = 'queue-item__body';

    const name = document.createElement('p');
    name.className = 'queue-item__name';
    name.textContent = item.file.name;
    name.title = item.file.name;
    body.appendChild(name);

    const meta = document.createElement('p');
    meta.className = 'queue-item__meta';
    if (item.busy) {
      meta.textContent = 'Reading…';
    } else if (item.probeError) {
      meta.textContent = `${item.probeError} It can still be uploaded.`;
    } else {
      const parts = [formatBytes(item.file.size)];
      if (item.source) {
        parts.push(formatDims(item.source.width, item.source.height));
        if (item.source.duration) parts.push(formatDuration(item.source.duration));
      }
      parts.filter(Boolean).forEach((text, i) => {
        if (i) {
          const sep = document.createElement('span');
          sep.className = 'sep';
          sep.textContent = '·';
          meta.appendChild(sep);
        }
        meta.appendChild(document.createTextNode(text));
      });
    }
    body.appendChild(meta);
    li.appendChild(body);

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'btn btn--quiet btn--icon';
    remove.setAttribute('aria-label', `Remove ${item.file.name}`);
    remove.appendChild(svgIcon('i-x'));
    remove.addEventListener('click', () => {
      const i = staged.indexOf(item);
      if (i >= 0) staged.splice(i, 1);
      renderQueue();
      scheduleEstimate();
      updateSubmitState();
    });
    li.appendChild(remove);

    el.queue.appendChild(li);
  }
  syncFormatVisibility();
}

/** Only offer the format selects that apply to what is actually queued. */
function syncFormatVisibility() {
  if (!staged.length) {
    el.imageFmtWrap.hidden = false;
    el.videoFmtWrap.hidden = false;
    return;
  }
  el.imageFmtWrap.hidden = !staged.some((s) => s.kind === 'image');
  el.videoFmtWrap.hidden = !staged.some((s) => s.kind === 'video');
}

/* -------------------------------------------------------------------------- *
 * 8. Estimation
 * -------------------------------------------------------------------------- */

let estimateAbort = null;
const scheduleEstimate = debounce(runEstimates, 280);

async function runEstimates() {
  if (estimateAbort) estimateAbort.abort();

  const usable = staged.filter((s) => s.source && s.source.width && s.source.height);
  if (!staged.length || !currentModel()) {
    el.estimateCard.hidden = true;
    return;
  }
  el.estimateCard.hidden = false;

  if (!usable.length) {
    el.estimateBody.setAttribute('aria-busy', 'false');
    el.estimateBody.textContent = '';
    el.estimateWarn.textContent = '';
    const p = document.createElement('p');
    p.className = 'hint';
    p.textContent =
      'Dimensions could not be read in this browser, so no time estimate is available. '
      + 'The server will size the job when it starts.';
    el.estimateBody.appendChild(p);
    return;
  }

  renderEstimateSkeleton(usable.length);
  const controller = new AbortController();
  estimateAbort = controller;

  const model = currentModel();
  const target = targetPayload();

  const results = await Promise.all(usable.map(async (item) => {
    const payload = {
      kind: item.kind,
      width: item.source.width,
      height: item.source.height,
      frames: item.source.frames,
      fps: item.source.fps,
      model,
      ...target,
    };
    try {
      const data = await api('/estimate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      item.estimate = data;
      item.estimateError = null;
      return { item, data };
    } catch (err) {
      if (err && err.name === 'AbortError') return null;
      item.estimate = null;
      item.estimateError = err.message || 'Estimate unavailable.';
      return { item, error: item.estimateError };
    }
  }));

  if (controller.signal.aborted) return;
  renderEstimates(results.filter(Boolean));
}

function renderEstimateSkeleton(count) {
  el.estimateBody.setAttribute('aria-busy', 'true');
  el.estimateBody.textContent = '';
  el.estimateWarn.textContent = '';
  for (let i = 0; i < Math.min(count, 3); i++) {
    const row = document.createElement('div');
    row.className = 'estimate__row';
    const a = document.createElement('div'); a.className = 'skeleton skeleton--sm';
    const b = document.createElement('div'); b.className = 'skeleton skeleton--lg';
    row.append(a, b);
    el.estimateBody.appendChild(row);
  }
}

function renderEstimates(results) {
  el.estimateBody.setAttribute('aria-busy', 'false');
  el.estimateBody.textContent = '';
  el.estimateWarn.textContent = '';

  let totalSeconds = 0;
  let haveTotal = true;
  const warnings = new Set();

  for (const res of results) {
    const row = document.createElement('div');
    row.className = 'estimate__row';

    if (results.length > 1) {
      const file = document.createElement('p');
      file.className = 'estimate__file';
      file.textContent = res.item.file.name;
      row.appendChild(file);
    }

    if (res.error) {
      haveTotal = false;
      const p = document.createElement('p');
      p.className = 'estimate__dims';
      p.textContent = res.error;
      row.appendChild(p);
    } else {
      const d = res.data || {};
      const time = document.createElement('p');
      time.className = 'estimate__time';
      time.textContent = d.human || formatDurationLong(d.seconds);
      row.appendChild(time);

      const dims = document.createElement('p');
      dims.className = 'estimate__dims';
      const bits = [];
      if (d.output_width && d.output_height) {
        bits.push(`${formatDims(res.item.source.width, res.item.source.height)} → ${formatDims(d.output_width, d.output_height)}`);
      }
      if (Number.isFinite(d.passes) && d.passes > 1) bits.push(`${d.passes} passes`);
      dims.textContent = bits.join('  ·  ');
      row.appendChild(dims);

      if (Number.isFinite(d.seconds)) totalSeconds += d.seconds; else haveTotal = false;
      if (d.warning) warnings.add(d.warning);
    }
    el.estimateBody.appendChild(row);
  }

  if (results.length > 1 && haveTotal) {
    const total = document.createElement('div');
    total.className = 'estimate__total';
    const label = document.createElement('span');
    label.className = 'muted';
    label.textContent = `${results.length} files, run one after another`;
    const value = document.createElement('strong');
    value.textContent = formatDurationLong(totalSeconds);
    total.append(label, value);
    el.estimateBody.appendChild(total);
  }

  for (const text of warnings) {
    const box = document.createElement('div');
    box.className = 'warning';
    box.appendChild(svgIcon('i-alert'));
    const span = document.createElement('span');
    span.textContent = text;
    box.appendChild(span);
    el.estimateWarn.appendChild(box);
  }
}

/* -------------------------------------------------------------------------- *
 * 9. Submission
 * -------------------------------------------------------------------------- */

function updateSubmitState() {
  const ready = staged.length > 0 && !!currentModel() && online !== false && !submitting;
  el.submitBtn.disabled = !ready;
  if (submitting) {
    setText(el.submitLabel, 'Uploading…');
  } else if (!staged.length) {
    setText(el.submitLabel, 'Add files to begin');
  } else if (online === false) {
    setText(el.submitLabel, 'Server unreachable');
  } else if (!currentModel()) {
    setText(el.submitLabel, 'Choose a model');
  } else {
    setText(el.submitLabel, `Upscale ${staged.length} file${staged.length === 1 ? '' : 's'}`);
  }
}

async function submitAll(event) {
  event.preventDefault();
  if (submitting || !staged.length) return;

  submitting = true;
  updateSubmitState();

  const target = targetPayload();
  const model = currentModel();
  const failures = [];
  let created = 0;

  // Sequential: the backend runs one job at a time anyway, and this keeps the
  // failure reporting attributable to a specific file.
  for (const item of staged.slice()) {
    const fd = new FormData();
    fd.append('file', item.file, item.file.name);
    fd.append('model', model);
    if (target.preset) fd.append('preset', target.preset);
    else fd.append('scale', String(target.scale));
    fd.append('denoise', el.denoise.value);
    fd.append('sharpen', el.sharpen.value);
    fd.append('format', item.kind === 'video' ? el.videoFormat.value : el.imageFormat.value);

    try {
      const job = await api('/jobs', { method: 'POST', body: fd });
      const i = staged.indexOf(item);
      if (i >= 0) staged.splice(i, 1);
      if (job && job.id) { upsertJob(job); watchJob(job); created++; }
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        openPaywall(err.detail);
        break;                 // one prompt is enough; stop queuing the rest
      }
      failures.push(`${item.file.name}: ${err.message}`);
    }
  }

  submitting = false;
  renderQueue();
  updateSubmitState();
  scheduleEstimate();
  if (!staged.length) el.estimateCard.hidden = true;

  if (created) toast(`Queued ${created} job${created === 1 ? '' : 's'}.`, 'success', 4000);
  failures.forEach((msg) => toast(msg, 'error', 12000));
}

/* -------------------------------------------------------------------------- *
 * 10. Job rendering
 * -------------------------------------------------------------------------- */

const STATUS_PILL = {
  queued:    'pill--muted',
  preparing: 'pill--run',
  running:   'pill--run',
  done:      'pill--ok',
  error:     'pill--danger',
  cancelled: 'pill--muted',
};

async function loadJobs() {
  let list;
  try {
    list = await api('/jobs');
  } catch (err) {
    if (err instanceof ApiError && err.status !== 0) toast(err.message, 'error');
    return;
  }
  const seen = new Set();
  (list || []).forEach((job) => { seen.add(job.id); upsertJob(job); });

  // Drop cards for jobs the server no longer knows about.
  for (const [id, view] of jobViews) {
    if (!seen.has(id)) { stopWatching(id); view.el.remove(); jobViews.delete(id); }
  }
  (list || []).filter((j) => !TERMINAL.has(j.status)).forEach(watchJob);
  syncJobsEmpty();
}

function syncJobsEmpty() {
  el.jobsEmpty.hidden = jobViews.size > 0;
}

/**
 * Place a new card in newest-first order without disturbing existing cards —
 * re-sorting the whole list would interrupt an in-progress compare-slider drag.
 */
function insertCard(node, job) {
  const created = Number(job.created_at) || 0;
  // Walk the list in DOM order and stop at the first older card.
  for (const child of Array.from(el.jobs.children)) {
    const other = jobViews.get(child.dataset.id);
    const otherCreated = other && other.job ? Number(other.job.created_at) || 0 : 0;
    if (otherCreated < created) {
      el.jobs.insertBefore(node, child);
      return;
    }
  }
  el.jobs.appendChild(node);
}

/** Create the card on first sight, then patch it in place on every update. */
function upsertJob(job) {
  // A finished job consumes allowance; keep the meters honest.
  if (job && TERMINAL.has(job.status)) loadAllowance();
  let view = jobViews.get(job.id);
  if (!view) {
    const node = el.jobTpl.content.firstElementChild.cloneNode(true);
    node.dataset.id = job.id;
    view = { job: null, el: node, poll: null, source: null, failures: 0 };
    jobViews.set(job.id, view);
    insertCard(node, job);
  }
  const previous = view.job;
  view.job = job;
  paintJob(view);
  syncJobsEmpty();

  if (previous && previous.status !== job.status) announceJob(job);
  if (TERMINAL.has(job.status)) stopWatching(job.id);
  return view;
}

function announceJob(job) {
  const name = job.filename || job.id;
  const phrase = {
    done: 'finished',
    error: 'failed',
    cancelled: 'was cancelled',
    running: 'started running',
    preparing: 'is preparing',
    queued: 'is queued',
  }[job.status] || job.status;
  setText(el.announcer, `${name} ${phrase}.`);
  if (job.status === 'done') toast(`${name} is ready to download.`, 'success');
  if (job.status === 'error') toast(`${name} failed: ${job.error || 'unknown error'}`, 'error', 12000);
}

function paintJob(view) {
  const job = view.job;
  const node = view.el;

  // Header
  const kindUse = $('.job__kind use', node);
  if (kindUse) kindUse.setAttribute('href', job.kind === 'video' ? '#i-video' : '#i-image');
  const nameEl = $('.job__name', node);
  setText(nameEl, job.filename || job.id);
  nameEl.title = job.filename || job.id;

  const metaParts = [];
  const src = job.source || {};
  const tgt = job.target || {};
  if (src.width && tgt.width) {
    metaParts.push(`${formatDims(src.width, src.height)} → ${formatDims(tgt.width, tgt.height)}`);
  } else if (tgt.width) {
    metaParts.push(formatDims(tgt.width, tgt.height));
  }
  if (job.model) metaParts.push(job.model);
  if (src.duration) metaParts.push(formatDuration(src.duration));
  const metaEl = $('.job__meta', node);
  metaEl.textContent = '';
  metaParts.forEach((text, i) => {
    if (i) {
      const sep = document.createElement('span');
      sep.className = 'sep';
      sep.textContent = '·';
      metaEl.appendChild(sep);
    }
    metaEl.appendChild(document.createTextNode(text));
  });

  // Status pill
  const pill = $('.job__pill', node);
  pill.className = `pill job__pill ${STATUS_PILL[job.status] || 'pill--muted'}`;
  setText($('.job__status', node), job.status);

  // Progress
  const active = !TERMINAL.has(job.status);
  const progWrap = $('.job__progress', node);
  progWrap.hidden = !active;
  if (active) {
    const pct = Number.isFinite(job.progress) ? clamp(job.progress * 100, 0, 100) : 0;
    const bar = $('.bar', node);
    const fill = $('.bar__fill', node);
    const indeterminate = !Number.isFinite(job.progress) || (pct === 0 && job.status !== 'running');
    node.classList.toggle('job--indeterminate', indeterminate);
    fill.style.width = `${pct}%`;
    bar.setAttribute('aria-valuenow', String(Math.round(pct)));
    bar.setAttribute('aria-valuetext', indeterminate ? 'Working' : `${Math.round(pct)} percent`);

    setText($('.job__stage', node), job.stage || job.status);
    const eta = Number.isFinite(job.eta_seconds) && job.eta_seconds > 0
      ? `${formatDuration(job.eta_seconds)} left`
      : (indeterminate ? '' : `${Math.round(pct)}%`);
    setText($('.job__eta', node), eta);
    setText($('.job__message', node), job.message || '');
  }

  // Error
  const errEl = $('.job__error', node);
  if (job.status === 'error') {
    errEl.hidden = false;
    setText(errEl, job.error || 'The job failed, but the server gave no reason.');
  } else {
    errEl.hidden = true;
  }

  // Before/after (images only)
  const compare = $('.compare', node);
  if (job.status === 'done' && job.kind === 'image') {
    if (compare.hidden) {
      compare.hidden = false;
      initCompare(compare, job.id);
    }
  } else {
    compare.hidden = true;
  }

  paintActions(view);
}

function paintActions(view) {
  const job = view.job;
  const box = $('.job__actions', view.el);
  box.textContent = '';

  if (!TERMINAL.has(job.status)) {
    const cancel = button('Cancel', 'i-x', 'btn btn--danger');
    cancel.addEventListener('click', async () => {
      cancel.disabled = true;
      try {
        const updated = await api(`/jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' });
        if (updated && updated.id) upsertJob(updated);
      } catch (err) {
        cancel.disabled = false;
        toast(err.message, 'error');
      }
    });
    box.appendChild(cancel);
  }

  if (job.status === 'done') {
    const link = document.createElement('a');
    link.className = 'btn btn--primary';
    link.href = `${API}/jobs/${encodeURIComponent(job.id)}/download`;
    link.setAttribute('download', job.output_name || '');
    link.appendChild(svgIcon('i-download'));
    link.appendChild(document.createTextNode('Download'));
    // Long output names would blow out the button, so they live in the tooltip.
    if (job.output_name) link.title = `Download ${job.output_name}`;
    box.appendChild(link);
  }

  if (TERMINAL.has(job.status)) {
    const del = button('Delete', 'i-trash', 'btn btn--quiet');
    let armed = false;
    let timer = null;

    const relabel = (text, danger) => {
      del.className = danger ? 'btn btn--danger' : 'btn btn--quiet';
      del.textContent = '';
      del.appendChild(svgIcon('i-trash'));
      del.appendChild(document.createTextNode(text));
    };

    del.addEventListener('click', async () => {
      if (!armed) {
        // Two-step confirm keeps a destructive action one deliberate tap away.
        armed = true;
        relabel('Confirm delete', true);
        timer = setTimeout(() => { armed = false; relabel('Delete', false); }, 4000);
        return;
      }
      clearTimeout(timer);
      del.disabled = true;
      try {
        await api(`/jobs/${encodeURIComponent(job.id)}`, { method: 'DELETE' });
        stopWatching(job.id);
        view.el.remove();
        jobViews.delete(job.id);
        syncJobsEmpty();
      } catch (err) {
        del.disabled = false;
        toast(err.message, 'error');
      }
    });
    box.appendChild(del);
  }
}

function button(text, icon, className) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = className;
  b.appendChild(svgIcon(icon));
  b.appendChild(document.createTextNode(text));
  return b;
}

/* -------------------------------------------------------------------------- *
 * 11. Live updates — EventSource, falling back to polling
 * -------------------------------------------------------------------------- */

function watchJob(job) {
  const id = job.id;
  const view = jobViews.get(id);
  if (!view || view.source || view.poll || TERMINAL.has(job.status)) return;

  if (typeof EventSource === 'undefined') { startPolling(id); return; }

  let source;
  try {
    source = new EventSource(`${API}/jobs/${encodeURIComponent(id)}/events`);
  } catch { startPolling(id); return; }
  view.source = source;

  source.addEventListener('message', (event) => {
    let payload;
    try { payload = JSON.parse(event.data); } catch { return; }
    if (!payload || !payload.id) return;
    view.failures = 0;
    setOnline(true);
    upsertJob(payload);
  });

  source.addEventListener('error', () => {
    // EventSource retries on its own; after a couple of failures we stop
    // trusting it (proxy buffering, connection drop) and poll instead.
    if (source.readyState === EventSource.CLOSED || ++view.failures >= 2) {
      closeSource(view);
      const current = view.job;
      if (current && !TERMINAL.has(current.status)) startPolling(id);
    }
  });
}

function closeSource(view) {
  if (view.source) {
    try { view.source.close(); } catch { /* already closed */ }
    view.source = null;
  }
}

function startPolling(id) {
  const view = jobViews.get(id);
  if (!view || view.poll) return;
  let misses = 0;

  view.poll = setInterval(async () => {
    try {
      const job = await api(`/jobs/${encodeURIComponent(id)}`);
      misses = 0;
      if (job && job.id) upsertJob(job);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) { stopWatching(id); return; }
      // Surface a stalled connection on the card itself rather than silently.
      if (++misses === 3) setText($('.job__message', view.el), 'Connection lost — retrying…');
    }
  }, POLL_MS);
}

function stopWatching(id) {
  const view = jobViews.get(id);
  if (!view) return;
  closeSource(view);
  if (view.poll) { clearInterval(view.poll); view.poll = null; }
}

/* -------------------------------------------------------------------------- *
 * 11b. Free-tier allowance and the paywall
 * -------------------------------------------------------------------------- */

let allowance = null;
let pricing = null;
let currency = null;

/** India gets rupee pricing; everyone else the international price. */
function guessCurrency() {
  try {
    const saved = localStorage.getItem('pixelith.currency');
    if (saved) return saved;
  } catch { /* private mode */ }
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    if (/Calcutta|Kolkata/i.test(tz)) return 'INR';
    if ((navigator.language || '').toLowerCase().endsWith('-in')) return 'INR';
  } catch { /* older browser */ }
  return 'USD';
}

function money(code, amount) {
  const sym = code === 'INR' ? '\u20b9' : '$';
  return sym + amount.toLocaleString(code === 'INR' ? 'en-IN' : 'en-US');
}

function applyCurrency(code) {
  if (!pricing || !pricing[code]) return;
  currency = code;
  try { localStorage.setItem('pixelith.currency', code); } catch { /* ignore */ }
  const p = pricing[code];
  setText(el.pricePersonal, money(code, p.personal));
  setText(el.priceCommercial, money(code, p.commercial));
  // Show the all-in total as well, so the checkout amount is never a surprise.
  const label = p.tax_included || p.personal_total === p.personal
    ? (p.tax_label || '')
    : `${p.tax_label} \u2014 ${money(code, p.personal_total)} and ` +
      `${money(code, p.commercial_total)} all in`;
  setText(el.paywallTax, label);
  document.querySelectorAll('.paywall__region-btn').forEach((b) => {
    b.setAttribute('aria-pressed', String(b.dataset.currency === code));
  });
  // Point the buy link at a checkout URL when one is configured.
  const url = p.commercial_url || p.personal_url;
  if (url) {
    el.paywallContact.textContent = 'Buy now';
    el.paywallContact.href = url;
  }
}

async function loadPricing() {
  try {
    const res = await api('/pricing');
    pricing = res.currencies;
    applyCurrency(guessCurrency() || res.default);
  } catch { /* offline */ }
}

function fmtBytes(n) {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n >= 1024 ** 2) return `${Math.round(n / 1024 ** 2)} MB`;
  return `${Math.round(n / 1024)} KB`;
}

/** A plain read-out with no bar, for when there is no limit to fill. */
function counted(label, value) {
  const row = document.createElement('div');
  row.className = 'meter';
  row.innerHTML =
    `<div class="meter__row"><span>${label}</span><span>${value} so far</span></div>`;
  return row;
}

function meter(label, used, limit, fmt) {
  const pct = limit ? Math.min(100, (used / limit) * 100) : 0;
  const cls = pct >= 100 ? 'meter meter--full' : pct >= 80 ? 'meter meter--warn' : 'meter';
  const el = document.createElement('div');
  el.className = cls;
  el.innerHTML =
    `<div class="meter__row"><span>${label}</span>` +
    `<span>${fmt(used)} of ${fmt(limit)}</span></div>` +
    `<div class="meter__track"><div class="meter__fill" style="width:${pct}%"></div></div>`;
  return el;
}

function renderAllowance() {
  if (!el.allowance || !allowance) return;
  el.allowance.hidden = false;
  const meters = el.allowanceMeters;
  meters.textContent = '';

  if (allowance.beta) {
    setText(el.allowanceTier, 'Public beta');
    el.allowanceUpgrade.hidden = true;
    meters.appendChild(counted('Images', `${allowance.images_used}`));
    meters.appendChild(counted('Video', fmtBytes(allowance.video_bytes_used)));
    setText(el.allowanceNote,
      `Free and unlimited until ${allowance.beta_ends} ` +
      `(${allowance.beta_days_left} days left). Nothing is charged, and there ` +
      'is no payment step yet \u2014 pricing starts when the beta ends. ' +
      (allowance.watermarked
        ? 'Output carries an invisible provenance mark.'
        : `Licensed to ${allowance.holder || allowance.tier}, so output ` +
          'carries no mark.'));
    return;
  }

  if (allowance.licensed) {
    setText(el.allowanceTier,
      `${allowance.tier === 'commercial' ? 'Commercial' : 'Personal'} licence`);
    el.allowanceUpgrade.hidden = true;
    setText(el.allowanceNote,
      (allowance.holder ? `Licensed to ${allowance.holder}. ` : '') +
      'Unlimited images and video. Output carries no mark.');
    return;
  }

  setText(el.allowanceTier, 'Free tier');
  el.allowanceUpgrade.hidden = false;
  meters.appendChild(meter('Images', allowance.images_used,
    allowance.images_limit, (n) => `${n}`));
  meters.appendChild(meter('Video', allowance.video_bytes_used,
    allowance.video_bytes_limit, fmtBytes));
  setText(el.allowanceNote,
    'Free output carries an invisible provenance mark. A licence removes ' +
    'the limits and the mark.');
}

async function loadAllowance() {
  try {
    allowance = await api('/allowance');
    renderAllowance();
  } catch { /* offline: the banner already says so */ }
}

function openPaywall(detail) {
  const dlg = el.paywall;
  if (!dlg) return;
  /* During the beta this dialog explains what pricing will be, rather than
     asking anyone to pay - there is nothing to buy yet. */
  if (allowance && allowance.beta) {
    setText(el.paywallDetail,
      'Pixelith is free and unlimited during the public beta, which runs to ' +
      `${allowance.beta_ends}. There is nothing to buy yet: a payment section ` +
      'will be added once the beta ends. The prices below are what it will ' +
      'cost then.');
  }
  if (detail) {
    if (detail.allowance) { allowance = detail.allowance; renderAllowance(); }
    setText(el.paywallDetail, detail.detail
      ? `${detail.detail}. ${detail.message || ''}`.trim()
      : (detail.message || ''));
    if (detail.contact) {
      el.paywallContact.textContent = detail.contact;
      el.paywallContact.href = `mailto:${detail.contact}` +
        '?subject=Pixelith%20licence';
    }
  }
  el.paywallError.hidden = true;
  el.paywallKey.value = '';
  if (typeof dlg.showModal === 'function' && !dlg.open) dlg.showModal();
}

async function activateKey() {
  const key = el.paywallKey.value.trim();
  if (!key) {
    setText(el.paywallError, 'Paste the key you were sent.');
    el.paywallError.hidden = false;
    return;
  }
  el.paywallActivate.disabled = true;
  try {
    const res = await api('/activate', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ key }),
    });
    allowance = res.allowance;
    renderAllowance();
    el.paywall.close();
    toast('Licence activated. Limits removed, and output is no longer marked.',
      'success', 6000);
  } catch (err) {
    setText(el.paywallError, err.message || 'That key was not accepted.');
    el.paywallError.hidden = false;
  } finally {
    el.paywallActivate.disabled = false;
  }
}

function wirePaywall() {
  if (!el.paywall) return;
  el.allowanceUpgrade?.addEventListener('click', () => openPaywall(null));
  document.querySelectorAll('.paywall__region-btn').forEach((b) => {
    b.addEventListener('click', () => applyCurrency(b.dataset.currency));
  });
  el.paywallActivate?.addEventListener('click', activateKey);
  el.paywallClose?.addEventListener('click', () => el.paywall.close());
  el.paywallKey?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); activateKey(); }
  });
}

/* -------------------------------------------------------------------------- *
 * 12. Before/after compare slider
 * -------------------------------------------------------------------------- */

function initCompare(root, jobId) {
  const frame = $('.compare__frame', root);
  const handle = $('.compare__handle', root);
  const before = $('.compare__img--before', root);
  const after = $('.compare__img--after', root);
  const base = `${API}/jobs/${encodeURIComponent(jobId)}/thumb`;

  let failed = false;
  const onThumbError = () => {
    if (failed) return;
    failed = true;
    root.textContent = '';
    const note = document.createElement('p');
    note.className = 'hint';
    note.textContent = 'The comparison preview could not be loaded.';
    root.appendChild(note);
  };
  before.addEventListener('error', onThumbError);
  after.addEventListener('error', onThumbError);

  // Match the frame to the real aspect ratio once the upscaled thumb is in.
  after.addEventListener('load', () => {
    const w = after.naturalWidth;
    const h = after.naturalHeight;
    if (!w || !h) return;
    frame.style.aspectRatio = `${w} / ${h}`;
    // Cap the height by capping the width instead, so a tall or square image
    // stays within the viewport without letterboxing inside the frame.
    frame.style.maxWidth = `calc(${(w / h).toFixed(4)} * 60vh)`;
  }, { once: true });

  before.src = `${base}?side=before`;
  after.src = `${base}?side=after`;

  const setSplit = (pct) => {
    const value = clamp(pct, 0, 100);
    frame.style.setProperty('--split', `${value}%`);
    handle.setAttribute('aria-valuenow', String(Math.round(value)));
    handle.setAttribute('aria-valuetext', `${Math.round(value)} percent`);
  };
  setSplit(50);

  const fromEvent = (clientX) => {
    const rect = frame.getBoundingClientRect();
    if (!rect.width) return;
    setSplit(((clientX - rect.left) / rect.width) * 100);
  };

  // Pointer events cover mouse, touch and pen with one code path.
  let dragging = false;
  frame.addEventListener('pointerdown', (e) => {
    if (e.button != null && e.button !== 0) return;
    dragging = true;
    frame.setPointerCapture(e.pointerId);
    fromEvent(e.clientX);
    e.preventDefault();
  });
  frame.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    fromEvent(e.clientX);
    e.preventDefault();
  });
  const end = (e) => {
    if (!dragging) return;
    dragging = false;
    try { frame.releasePointerCapture(e.pointerId); } catch { /* already released */ }
  };
  frame.addEventListener('pointerup', end);
  frame.addEventListener('pointercancel', end);

  handle.addEventListener('keydown', (e) => {
    // Note: `|| 50` would be wrong here — a valid position of 0 is falsy.
    const parsed = parseFloat(handle.getAttribute('aria-valuenow'));
    const now = Number.isFinite(parsed) ? parsed : 50;
    const step = e.shiftKey ? 10 : 2;
    let next = null;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') next = now - step;
    else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') next = now + step;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = 100;
    if (next === null) return;
    e.preventDefault();
    setSplit(next);
  });
}

/* -------------------------------------------------------------------------- *
 * 13. Init
 * -------------------------------------------------------------------------- */

function wireDropzone() {
  // The <label> already opens the picker natively; this only extends the hit
  // area to the whole zone, so clicks on the label or input must be ignored.
  el.dropzone.addEventListener('click', (e) => {
    if (e.target.closest('label, input')) return;
    el.fileInput.click();
  });

  el.fileInput.addEventListener('change', () => {
    addFiles(el.fileInput.files);
    el.fileInput.value = '';       // allow re-picking the same file
  });

  let depth = 0;
  const over = (on) => el.dropzone.classList.toggle('is-over', on);

  ['dragenter', 'dragover'].forEach((type) => {
    el.dropzone.addEventListener(type, (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      if (type === 'dragenter') depth++;
      over(true);
    });
  });
  el.dropzone.addEventListener('dragleave', (e) => {
    e.preventDefault();
    if (--depth <= 0) { depth = 0; over(false); }
  });
  el.dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    depth = 0;
    over(false);
    if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
  });

  // Dropping anywhere else must not navigate away from the app.
  ['dragover', 'drop'].forEach((type) => {
    window.addEventListener(type, (e) => {
      if (!el.dropzone.contains(e.target)) e.preventDefault();
    });
  });
}

function wireSettings() {
  el.models.addEventListener('change', () => {
    saveSettings(); scheduleEstimate(); updateSubmitState();
  });

  document.querySelectorAll('input[name="target-mode"]').forEach((radio) => {
    radio.addEventListener('change', () => { syncTargetMode(); saveSettings(); scheduleEstimate(); });
  });

  [el.scale, el.denoise, el.sharpen].forEach((input) => {
    input.addEventListener('input', syncSliderOutputs);
    input.addEventListener('change', () => { saveSettings(); scheduleEstimate(); });
  });

  // input fires while dragging so the readout tracks the thumb; change commits.
  el.preset.addEventListener('input', renderPreset);
  el.preset.addEventListener('change', () => {
    renderPreset(); saveSettings(); scheduleEstimate();
  });
  [el.imageFormat, el.videoFormat].forEach((sel) => sel.addEventListener('change', saveSettings));

  el.clearQueue.addEventListener('click', () => {
    staged.length = 0;
    renderQueue();
    el.estimateCard.hidden = true;
    updateSubmitState();
  });

  el.form.addEventListener('submit', submitAll);
  el.refreshJobs.addEventListener('click', () => { loadJobs(); });
  el.retryHealth.addEventListener('click', () => { boot(); });
}

/** Replace the loading placeholders with an honest "unavailable" state. */
function markSettingsUnavailable() {
  if (!models.length) {
    el.models.textContent = '';
    const p = document.createElement('p');
    p.className = 'hint';
    p.textContent = 'Models will load once the server is reachable.';
    el.models.appendChild(p);
  }
  if (!Object.keys(presets).length) {
    el.preset.disabled = true;
    el.presetScale.textContent = '';
    setText(el.presetOut, 'unavailable');
    setText(el.presetDetail, 'Resolutions load once the server is reachable.');
  }
}

async function boot() {
  const ok = await checkHealth();
  if (!ok) { markSettingsUnavailable(); updateSubmitState(); return; }

  await Promise.all([loadModels(), loadPresets(), loadAllowance(), loadPricing()]);
  applySettings(loadSettings());
  await loadJobs();
  scheduleEstimate();
  updateSubmitState();
}

function init() {
  wireDropzone();
  wirePaywall();
  wireSettings();
  syncSliderOutputs();
  syncTargetMode();
  syncJobsEmpty();
  updateSubmitState();
  boot();

  // While offline, keep probing quietly so the UI heals on its own.
  setInterval(() => { if (online === false) boot(); }, 8000);

  // Streams do not survive a backgrounded tab on mobile; resync on return.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && online !== false) loadJobs();
  });

  window.addEventListener('beforeunload', () => {
    for (const id of jobViews.keys()) stopWatching(id);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init, { once: true });
} else {
  init();
}
