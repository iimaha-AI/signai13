/* ═══════════════════════════════════════════════════════════════════
   SignAI — Recognition Page Logic  (BROWSER CAMERA EDITION)
   ───────────────────────────────────────────────────────────────────
   Camera: Browser-native getUserMedia → <video> → <canvas> → base64
   Predictions: Sequential loop → /api/predict (JSON body { image: b64 })
   Why browser-side?
     The cloud-hosted server has no physical webcam. The original
     server-side OpenCV camera only worked on local/RPi deployments.
     getUserMedia runs entirely in the user's browser and sends each
     captured frame to /api/predict as base64 — no server camera needed.
   Requires HTTPS — Hugging Face Spaces already serve over HTTPS, so
   camera permissions will work in all modern browsers.
   ═════════════════════════════════════════════════════════════════ */

'use strict';

document.addEventListener('DOMContentLoaded', () => {
  const { Toast, apiFetch, setButtonLoading } = window.SignAI;
  const { ConfidenceChart, updateRing } = window.SignAICharts;

  /* ── State ────────────────────────────────────────────────────── */
  let _isRunning        = false;
  let _autoSave         = true;
  let _soundEnabled     = true;
  let _showLandmarks    = true;
  let _confChart        = null;
  let _lastStableLetter = null;

  /* Anti-flicker: track what is currently displayed */
  let _displayedLetter    = null;
  let _displayedConf      = -1;
  let _displayedHandState = null;   // 'detected' | 'none'

  /* Browser camera state */
  let _stream         = null;   // MediaStream from getUserMedia
  let _videoEl        = null;   // hidden <video> element
  let _canvasEl       = null;   // hidden <canvas> for frame capture
  let _canvasCtx      = null;

  /* ── DOM refs ─────────────────────────────────────────────────── */
  const videoFeed         = document.getElementById('video-feed');   // <img> we repurpose as <video> holder
  const bigLetter         = document.getElementById('big-letter');
  const confPercent       = document.getElementById('conf-percent');
  const confBar           = document.getElementById('conf-bar');
  const top5Panel         = document.getElementById('top5-panel');
  const wordDisplay       = document.getElementById('word-display');
  const noHandOverlay     = document.getElementById('no-hand-overlay');
  const disconnectOverlay = document.getElementById('disconnect-overlay');
  const liveBadge         = document.getElementById('live-badge');
  const uncertaintyWarn   = document.getElementById('uncertainty-warning');
  const chartCanvas       = document.getElementById('conf-chart');
  const ringSvg           = document.getElementById('stability-ring');
  const bufferVotes       = document.getElementById('buffer-votes');
  const videoPredLetter   = document.getElementById('video-pred-letter');
  const videoPredConf     = document.getElementById('video-pred-conf');
  const cameraError       = document.getElementById('camera-error');
  const latencyDisplay    = document.getElementById('latency-display');
  const cameraPlaceholder = document.getElementById('camera-placeholder');

  /* Settings panel */
  const settingsBtn      = document.getElementById('settings-btn');
  const settingsSidebar  = document.getElementById('settings-sidebar');
  const sidebarOverlay   = document.getElementById('sidebar-overlay');
  const thresholdSlider  = document.getElementById('threshold-slider');
  const thresholdDisplay = document.getElementById('threshold-display');
  const toggleAutoSave   = document.getElementById('toggle-autosave');
  const toggleSound      = document.getElementById('toggle-sound');
  const toggleLandmarks  = document.getElementById('toggle-landmarks');
  const fpsSelect        = document.getElementById('fps-select');

  /* ── Init Charts ──────────────────────────────────────────────── */
  if (chartCanvas) _confChart = new ConfidenceChart(chartCanvas);

  /* ───────────────────────────────────────────────────────────────
     BROWSER CAMERA — getUserMedia
     ─────────────────────────────────────────────────────────────── */

  function _createCameraElements() {
    /* Hidden <video> for getUserMedia stream */
    if (!_videoEl) {
      _videoEl = document.createElement('video');
      _videoEl.setAttribute('playsinline', '');
      _videoEl.setAttribute('muted', '');
      _videoEl.muted = true;
      _videoEl.style.cssText =
        'width:100%;height:100%;object-fit:cover;display:block;transform:scaleX(-1)';
      _videoEl.autoplay = true;
    }
    /* Hidden canvas for frame capture */
    if (!_canvasEl) {
      _canvasEl = document.createElement('canvas');
      _canvasEl.width  = 640;
      _canvasEl.height = 480;
      _canvasCtx = _canvasEl.getContext('2d', { willReadFrequently: false });
    }
  }

  async function startCamera() {
    const btn = document.getElementById('btn-start-camera');
    setButtonLoading(btn, true);
    hideCameraError();

    /* Feature detection */
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showCameraError('Your browser does not support camera access. Please use a modern browser (Chrome, Firefox, Edge, Safari).');
      setButtonLoading(btn, false);
      return;
    }

    try {
      _createCameraElements();

      /* Request user's webcam — 640x480 is enough for the model */
      _stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width:  { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user',
        },
        audio: false,
      });
      _videoEl.srcObject = _stream;
      await _videoEl.play();

      /* Replace the placeholder with the live <video> element */
      const panel = document.getElementById('video-panel');
      if (cameraPlaceholder) cameraPlaceholder.style.display = 'none';
      if (videoFeed) videoFeed.style.display = 'none';  // hide the old <img>
      _videoEl.style.display = 'block';
      panel && panel.appendChild(_videoEl);

      _isRunning = true;
      liveBadge && (liveBadge.style.display = 'flex');
      disconnectOverlay && disconnectOverlay.classList.remove('show');
      if (btn) { btn.textContent = 'Camera On'; btn.disabled = true; }

      /* Begin sequential prediction loop */
      runPredictionLoop();

    } catch (err) {
      console.error('[SignAI] getUserMedia error:', err);
      let msg = 'Could not open camera.';
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        msg = 'Camera permission denied. Please allow camera access in your browser settings and try again.';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        msg = 'No camera found on this device.';
      } else if (err.name === 'NotReadableError') {
        msg = 'Camera is already in use by another application.';
      } else if (err.message) {
        msg = 'Could not open camera: ' + err.message;
      }
      showCameraError(msg);
    } finally {
      setButtonLoading(btn, false);
    }
  }

  async function stopCamera() {
    _isRunning = false;

    /* Stop all video tracks */
    if (_stream) {
      _stream.getTracks().forEach(t => t.stop());
      _stream = null;
    }

    /* Detach video element */
    if (_videoEl) {
      _videoEl.srcObject = null;
      _videoEl.style.display = 'none';
    }

    /* Restore placeholder */
    if (cameraPlaceholder) cameraPlaceholder.style.display = 'flex';

    liveBadge && (liveBadge.style.display = 'none');
    const btn = document.getElementById('btn-start-camera');
    if (btn) { btn.textContent = 'Start Camera'; btn.disabled = false; }
  }

  /* Capture a single frame as a base64 JPEG string (no data: prefix). */
  function _captureFrame() {
    if (!_videoEl || !_videoEl.videoWidth || !_canvasCtx) return null;
    /* Match canvas size to the actual video dimensions (just once is fine). */
    if (_canvasEl.width !== _videoEl.videoWidth) {
      _canvasEl.width  = _videoEl.videoWidth;
      _canvasEl.height = _videoEl.videoHeight;
    }
    /* Draw the frame WITHOUT mirroring — the server-side preprocess flips
       if needed. The <video> element is CSS-mirrored for the user's UX
       (selfie view), but we send the raw unmirrored pixels to the server
       so the trained model (which expects normal orientation) works. */
    _canvasCtx.drawImage(_videoEl, 0, 0, _canvasEl.width, _canvasEl.height);
    return _canvasEl.toDataURL('image/jpeg', 0.85).split(',')[1];  // strip "data:image/jpeg;base64,"
  }

  /* ── Camera error helpers ─────────────────────────────────────── */
  function showCameraError(msg) {
    if (cameraError) { cameraError.textContent = msg; cameraError.style.display = 'block'; }
    Toast.error(msg, 6000);
  }
  function hideCameraError() {
    if (cameraError) cameraError.style.display = 'none';
  }

  /* ══════════════════════════════════════════════════════════════
     PREDICTION LOOP — Sequential, not setInterval
     ══════════════════════════════════════════════════════════════ */

  async function runPredictionLoop() {
    const getFps = () => parseInt(fpsSelect?.value || '10');

    while (_isRunning) {
      const fps      = getFps();
      const targetMs = 1000 / fps;
      const t0       = performance.now();

      try {
        const b64 = _captureFrame();
        if (b64) {
          const res = await apiFetch('/api/predict', {
            method: 'POST',
            body:   JSON.stringify({ image: b64, auto_save: _autoSave }),
          });
          if (_isRunning && res.data.success) {
            renderPrediction(res.data.data);
          }
        }
      } catch (err) {
        /* Silent — network hiccups shouldn't crash the loop */
        console.warn('[SignAI] Prediction error:', err.message);
      }

      /* Sleep for remaining time in this frame window */
      const elapsed = performance.now() - t0;
      const sleep   = Math.max(0, targetMs - elapsed);
      if (sleep > 0) {
        await new Promise(r => setTimeout(r, sleep));
      }
    }
  }

  /* ══════════════════════════════════════════════════════════════
     RENDER — Anti-flicker: only update DOM when value changes
     ══════════════════════════════════════════════════════════════ */

  function renderPrediction(d) {
    /* ── No hand detected ───────────────────────────────────────── */
    if (!d.hand_detected) {
      if (_displayedHandState !== 'none') {
        _displayedHandState = 'none';
        _displayedLetter    = null;
        _displayedConf      = -1;
        noHandOverlay && noHandOverlay.classList.add('show');
        if (bigLetter) { bigLetter.textContent = '—'; bigLetter.className = 'big-letter'; }
        if (videoPredLetter) videoPredLetter.textContent = '—';
        if (videoPredConf)   videoPredConf.textContent   = '';
        top5Panel && (top5Panel.innerHTML = '');
        if (uncertaintyWarn) uncertaintyWarn.classList.remove('show');
      }
      if (ringSvg) updateRing(ringSvg, d.buffer_fill || 0, 10);
      return;
    }

    /* ── Hand detected ──────────────────────────────────────────── */
    noHandOverlay && noHandOverlay.classList.remove('show');
    _displayedHandState = 'detected';

    const conf   = d.confidence;
    const letter = d.letter;

    if (letter !== _displayedLetter) {
      _displayedLetter = letter;
      if (bigLetter) {
        bigLetter.textContent = letter;
        bigLetter.className   = 'big-letter '
          + (conf >= 70 ? 'high-conf' : conf >= 40 ? 'medium-conf' : 'low-conf');
      }
      if (videoPredLetter) videoPredLetter.textContent = letter;

      if (top5Panel && d.top5) {
        top5Panel.innerHTML = d.top5.map(t =>
          `<div class="top5-pill">
             <span class="letter">${t.letter}</span>
             <span class="pct">${t.confidence.toFixed(1)}%</span>
           </div>`
        ).join('');
      }
    }

    if (Math.abs(conf - _displayedConf) >= 1) {
      _displayedConf = conf;
      if (confPercent) confPercent.textContent = conf.toFixed(1) + '%';
      if (confBar)     confBar.style.width      = conf + '%';
      if (videoPredConf) videoPredConf.textContent = conf.toFixed(1) + '%';

      if (bigLetter) {
        const cls = conf >= 70 ? 'high-conf' : conf >= 40 ? 'medium-conf' : 'low-conf';
        if (!bigLetter.className.includes(cls)) {
          bigLetter.className = 'big-letter ' + cls;
        }
      }
    }

    if (latencyDisplay && d.latency_ms != null) {
      latencyDisplay.textContent = d.latency_ms.toFixed(0) + ' ms';
    }

    if (uncertaintyWarn) {
      uncertaintyWarn.classList.toggle('show', !!d.low_confidence_warning);
    }

    if (_confChart && d.letter_scores) _confChart.update(d.letter_scores);
    if (ringSvg) updateRing(ringSvg, d.buffer_fill || 0, 10);

    if (bufferVotes && d.buffer_votes) {
      bufferVotes.innerHTML = Object.entries(d.buffer_votes)
        .sort(([, a], [, b]) => b - a)
        .map(([l, v]) => `<span class="badge badge-violet">${l}:${v}</span>`)
        .join(' ');
    }

    if (d.stable && d.stable_letter && d.stable_letter !== _lastStableLetter) {
      _lastStableLetter = d.stable_letter;
      appendLetter(d.stable_letter);
    }
  }

  /* ── Word Builder ──────────────────────────────────────────────── */
  async function loadCurrentWord() {
    const res = await apiFetch('/api/word/current').catch(() => null);
    if (res?.data?.success) updateWordDisplay(res.data.data.sentence);
  }

  function updateWordDisplay(sentence) {
    if (!wordDisplay) return;
    wordDisplay.innerHTML = '';
    for (const ch of sentence) {
      const span = document.createElement('span');
      span.className   = 'word-char';
      span.textContent = ch === ' ' ? '\u00A0' : ch;
      wordDisplay.appendChild(span);
    }
  }

  async function appendLetter(letter) {
    const res = await apiFetch('/api/word/append', {
      method: 'POST',
      body:   JSON.stringify({ letter }),
    }).catch(() => null);
    if (res?.data?.success) updateWordDisplay(res.data.data.sentence);
  }

  async function wordAction(endpoint) {
    const res = await apiFetch(endpoint, { method: 'POST' }).catch(() => null);
    if (res?.data?.success) {
      updateWordDisplay(res.data.data.sentence);
      if (endpoint === '/api/word/space' && _soundEnabled) {
        const s = res.data.data.sentence.trim();
        if (s) speakText(s);
      }
    }
  }

  /* ── TTS ──────────────────────────────────────────────────────── */
  async function speakText(text) {
    if (!_soundEnabled || !text.trim()) return;
    try {
      const res = await apiFetch('/api/tts/speak', {
        method: 'POST',
        body:   JSON.stringify({ text }),
      });
      if (!res.data.success) return;
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const raw = atob(res.data.data.audio_base64);
      const buf = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
      const decoded = await audioCtx.decodeAudioData(buf.buffer);
      const source  = audioCtx.createBufferSource();
      source.buffer = decoded;
      source.connect(audioCtx.destination);
      source.start();
    } catch (err) {
      console.warn('TTS error:', err.message);
    }
  }

  /* ── Settings Panel ────────────────────────────────────────────── */
  if (settingsBtn) {
    settingsBtn.addEventListener('click', () => {
      settingsSidebar && settingsSidebar.classList.toggle('open');
      sidebarOverlay  && sidebarOverlay.classList.toggle('open');
    });
  }
  if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', () => {
      settingsSidebar && settingsSidebar.classList.remove('open');
      sidebarOverlay.classList.remove('open');
    });
  }

  if (thresholdSlider) {
    thresholdSlider.addEventListener('input', () => {
      if (thresholdDisplay)
        thresholdDisplay.textContent = (thresholdSlider.value * 100).toFixed(0) + '%';
    });
    thresholdSlider.addEventListener('change', async () => {
      const val = parseFloat(thresholdSlider.value);
      const res = await apiFetch('/api/profile/threshold', {
        method: 'POST',
        body:   JSON.stringify({ confidence_threshold: val }),
      }).catch(() => null);
      if (res?.data?.success) Toast.success('Threshold updated.');
      else Toast.error('Failed to update threshold.');
    });
  }

  if (toggleAutoSave) toggleAutoSave.addEventListener('change', () => {
    _autoSave = toggleAutoSave.checked;
    Toast.info('Auto-save ' + (_autoSave ? 'on' : 'off'));
  });
  if (toggleSound) toggleSound.addEventListener('change', () => {
    _soundEnabled = toggleSound.checked;
    Toast.info('Sound ' + (_soundEnabled ? 'on' : 'off'));
  });
  if (toggleLandmarks) toggleLandmarks.addEventListener('change', () => {
    _showLandmarks = toggleLandmarks.checked;
    Toast.info('Landmarks ' + (_showLandmarks ? 'on' : 'off'));
  });

  /* ── Keyboard Shortcuts ────────────────────────────────────────── */
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    switch (e.key) {
      case ' ':         e.preventDefault(); wordAction('/api/word/space');     break;
      case 'Backspace': wordAction('/api/word/backspace');                      break;
      case 'Delete':    wordAction('/api/word/clear');                          break;
      case 'Enter': {
        const s = wordDisplay?.textContent.trim();
        if (s) speakText(s);
        break;
      }
    }
  });

  /* ── Button Bindings ───────────────────────────────────────────── */
  document.getElementById('btn-start-camera')?.addEventListener('click', startCamera);
  document.getElementById('btn-stop-camera')?.addEventListener('click',  stopCamera);

  document.getElementById('btn-space')    ?.addEventListener('click', () => wordAction('/api/word/space'));
  document.getElementById('btn-backspace')?.addEventListener('click', () => wordAction('/api/word/backspace'));
  document.getElementById('btn-clear')    ?.addEventListener('click', () => wordAction('/api/word/clear'));

  document.getElementById('btn-speak')?.addEventListener('click', () => {
    const s = wordDisplay?.textContent.trim();
    if (s) speakText(s);
    else Toast.info('Nothing to speak yet.');
  });

  document.getElementById('btn-reset-session')?.addEventListener('click', async () => {
    await apiFetch('/api/session/reset', { method: 'POST' }).catch(() => null);
    _lastStableLetter = null;
    Toast.info('Session reset.');
  });

  /* ── Load initial state ────────────────────────────────────────── */
  loadCurrentWord();

  /* ── Cleanup on page leave ─────────────────────────────────────── */
  window.addEventListener('beforeunload', () => {
    stopCamera();
    if (_confChart) _confChart.destroy();
  });
});
