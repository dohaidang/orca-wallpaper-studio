// Wallpaper Studio panel: crop and adjust an image in the browser, then hand the original file and the
// chosen settings to the plugin's worker, which renders the final wallpaper at full resolution.
// The crop is kept in "oriented" source pixels (after rotate, then flip), matching wallpaper_core.py.
'use strict'

const MAX_INPUT_BYTES = 50 * 1024 * 1024
const MIN_W = 640, MIN_H = 360, MAX_SIDE = 4096
const EDITOR_MAX_SIDE = 1600 // the editor works on a reduced copy; the worker always uses the original
const $ = (id) => document.getElementById(id)

const screenW = Math.round(screen.width * (devicePixelRatio || 1))
const screenH = Math.round(screen.height * (devicePixelRatio || 1))
// Labels follow Orca's language (see i18n.js); the numbers behind them never change.
const ASPECTS = [
  [() => tr('aspect_screen', { w: screenW, h: screenH }), screenW / screenH],
  [() => '16:9', 16 / 9], [() => '16:10', 1.6], [() => '21:9', 21 / 9], [() => '4:3', 4 / 3],
  [() => '1:1', 1], [() => '3:4', 3 / 4], [() => '10:16', 10 / 16], [() => '9:16', 9 / 16],
  [() => tr('aspect_full'), null]
]
const WIDTHS = [[() => tr('width_screen', { px: Math.min(MAX_SIDE, screenW) }), Math.min(MAX_SIDE, screenW)], [() => '1280 px', 1280], [() => '1920 px', 1920], [() => '2560 px', 2560], [() => '3840 px', 3840]]

const state = {
  file: null, image: null, natW: 0, natH: 0,
  rotate: 0, flipH: false, flipV: false, crop: [0, 0, 0, 0],
  oriented: document.createElement('canvas'), orientedScale: 1,
  terminalOpacity: 0.6, busy: false, job: null, drag: null
}

/** (Re)fills the two dropdowns in the current language, keeping the chosen entries. */
function fillSelects() {
  for (const [id, list] of [['aspect', ASPECTS], ['width', WIDTHS]]) {
    const select = $(id), chosen = select.selectedIndex
    select.length = 0
    for (const [label] of list) select.add(new Option(label()))
    select.selectedIndex = Math.max(0, chosen)
  }
}
fillSelects()

// ---------- geometry ----------
function orientedSize() {
  return state.rotate % 180 === 0 ? [state.natW, state.natH] : [state.natH, state.natW]
}
function aspect() { return ASPECTS[$('aspect').selectedIndex][1] }
function centeredCrop() {
  const [ow, oh] = orientedSize()
  const a = aspect()
  if (!a) return [0, 0, ow, oh]
  let cw = ow, ch = Math.round(ow / a)
  if (ch > oh) { ch = oh; cw = Math.round(oh * a) }
  const left = Math.floor((ow - cw) / 2), top = Math.floor((oh - ch) / 2)
  return [left, top, left + cw, top + ch]
}
function clampCrop(crop) {
  const [ow, oh] = orientedSize()
  let [l, t, r, b] = crop
  const w = Math.min(ow, r - l), h = Math.min(oh, b - t)
  l = Math.min(Math.max(0, l), ow - w)
  t = Math.min(Math.max(0, t), oh - h)
  return [Math.round(l), Math.round(t), Math.round(l + w), Math.round(t + h)]
}
function outputSize() {
  const [l, t, r, b] = state.crop
  const w = WIDTHS[$('width').selectedIndex][1]
  const h = Math.round(w * (b - t) / Math.max(1, r - l))
  let s = Math.min(1, MAX_SIDE / Math.max(w, h))
  s = Math.max(s, MIN_W / w, MIN_H / h)
  return [Math.min(MAX_SIDE, Math.max(MIN_W, Math.round(w * s))), Math.min(MAX_SIDE, Math.max(MIN_H, Math.round(h * s)))]
}

// ---------- drawing ----------
function rebuildOriented() {
  const [ow, oh] = orientedSize()
  const s = Math.min(1, EDITOR_MAX_SIDE / Math.max(ow, oh))
  const c = state.oriented
  c.width = Math.max(1, Math.round(ow * s))
  c.height = Math.max(1, Math.round(oh * s))
  const ctx = c.getContext('2d')
  ctx.save()
  ctx.translate(c.width / 2, c.height / 2)
  ctx.scale(state.flipH ? -1 : 1, state.flipV ? -1 : 1) // applied after the rotation, like the Python side
  ctx.rotate(state.rotate * Math.PI / 180)
  ctx.drawImage(state.image, -state.natW * s / 2, -state.natH * s / 2, state.natW * s, state.natH * s)
  ctx.restore()
  state.orientedScale = s
}

function editorView() {
  const canvas = $('editor')
  const cw = canvas.clientWidth || 320
  const ch = Math.round(cw * 9 / 16)
  if (canvas.width !== cw || canvas.height !== ch) { canvas.width = cw; canvas.height = ch }
  const o = state.oriented
  const fit = Math.min(cw / o.width, ch / o.height)
  return { canvas, fit, ox: (cw - o.width * fit) / 2, oy: (ch - o.height * fit) / 2 }
}

function drawEditor() {
  const { canvas, fit, ox, oy } = editorView()
  const ctx = canvas.getContext('2d')
  const o = state.oriented
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(o, ox, oy, o.width * fit, o.height * fit)
  ctx.fillStyle = 'rgba(0,0,0,0.6)'
  ctx.fillRect(ox, oy, o.width * fit, o.height * fit)
  const s = state.orientedScale * fit
  const [l, t, r, b] = state.crop
  ctx.drawImage(o, l * state.orientedScale, t * state.orientedScale, (r - l) * state.orientedScale, (b - t) * state.orientedScale,
    ox + l * s, oy + t * s, (r - l) * s, (b - t) * s)
  ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue('--primary').trim() || '#8ab4ff'
  ctx.lineWidth = 2
  ctx.strokeRect(ox + l * s + 1, oy + t * s + 1, (r - l) * s - 2, (b - t) * s - 2)
}

function drawPreview() {
  const canvas = $('preview')
  const W = canvas.width, H = canvas.height
  const ctx = canvas.getContext('2d')
  const [l, t, r, b] = state.crop
  const sc = state.orientedScale
  const [outW, outH] = outputSize()
  const brightness = +$('brightness').value, darken = +$('darken').value, blur = +$('blur').value, opacity = +$('opacity').value
  ctx.save()
  ctx.fillStyle = '#111214'
  ctx.fillRect(0, 0, W, H)
  // the exported picture, fitted the way Orca will paint it
  const tmp = document.createElement('canvas')
  tmp.width = W
  tmp.height = Math.max(1, Math.round(W * outH / outW))
  const tctx = tmp.getContext('2d')
  tctx.filter = `brightness(${brightness}) blur(${blur * W / outW}px)`
  tctx.drawImage(state.oriented, l * sc, t * sc, (r - l) * sc, (b - t) * sc, 0, 0, tmp.width, tmp.height)
  tctx.filter = 'none'
  tctx.fillStyle = `rgba(0,0,0,${darken})`
  tctx.fillRect(0, 0, tmp.width, tmp.height)
  ctx.globalAlpha = opacity
  const size = $('size').value, position = $('position').value
  if (size === 'tile') {
    const tw = Math.round(W / 3), th = Math.round(tw * tmp.height / tmp.width)
    for (let x = 0; x < W; x += tw) for (let y = 0; y < H; y += th) ctx.drawImage(tmp, x, y, tw, th)
  } else {
    const k = (size === 'contain' ? Math.min : Math.max)(W / tmp.width, H / tmp.height)
    const dw = tmp.width * k, dh = tmp.height * k
    const dx = position === 'left' ? 0 : position === 'right' ? W - dw : (W - dw) / 2
    const dy = position === 'top' ? 0 : position === 'bottom' ? H - dh : (H - dh) / 2
    ctx.drawImage(tmp, dx, dy, dw, dh)
  }
  ctx.globalAlpha = 1
  // Orca's translucent terminal over the wallpaper
  ctx.fillStyle = `rgba(17,18,20,${Math.min(1, Math.max(0, state.terminalOpacity))})`
  ctx.fillRect(0, 0, W, H)
  ctx.fillStyle = '#ececef'
  ctx.font = '11px Consolas, monospace'
  ;['$ orca --version', '1.4.246', '$ git status', 'On branch main', 'nothing to commit'].forEach((line, i) => ctx.fillText(line, 10, 18 + i * 15))
  ctx.restore()
  $('size-note').textContent = tr('size_note', { w: outW, h: outH, minw: MIN_W, minh: MIN_H, max: MAX_SIDE })
}

let pending = 0
function redraw() {
  if (!state.image) return
  cancelAnimationFrame(pending)
  pending = requestAnimationFrame(() => { drawEditor(); drawPreview() })
}

// ---------- opening ----------
$('file').addEventListener('change', () => {
  const file = $('file').files[0]
  if (!file) return
  if (file.size > MAX_INPUT_BYTES) return setStatus(tr('too_big', { mb: MAX_INPUT_BYTES / 1048576 }), true)
  const url = URL.createObjectURL(file)
  const isVideo = file.type.startsWith('video/') || /\.(mp4|m4v|mov|webm|mkv|avi)$/i.test(file.name)
  const opened = (image, width, height, extra = '') => {
    Object.assign(state, { file, library: null, image, natW: width, natH: height, rotate: 0, flipH: false, flipV: false })
    $('source').textContent = `${file.name}: ${width}×${height}${extra}, ${(file.size / 1048576).toFixed(2)} MB`
    $('editor-box').hidden = false
    $('editor-box').classList.remove('no-image')
    $('video-range').hidden = !isVideo
    $('scrub-box').hidden = !isVideo
    state.video = isVideo ? image.__video : null
    $('start-s').value = 0
    $('end-s').value = -1
    // A video can only be a video wallpaper.
    if (isVideo) document.querySelector('input[name=mode][value=video]').checked = true
    else if (document.querySelector('input[name=mode]:checked').value === 'video') document.querySelector('input[name=mode][value=stock]').checked = true
    rebuildOriented()
    state.crop = centeredCrop()
    setStatus('')
    redraw()
  }
  if (isVideo) {
    // The editor works on one picture: the first frame of the video, drawn onto a canvas.
    const video = document.createElement('video')
    video.muted = true
    video.preload = 'auto'
    video.onloadeddata = () => {
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      canvas.getContext('2d').drawImage(video, 0, 0)
      const seconds = Number.isFinite(video.duration) ? `, ${Math.round(video.duration)} s` : ''
      canvas.__video = video // kept (with its object URL) so the time slider can show other frames
      opened(canvas, video.videoWidth, video.videoHeight, seconds)
      const total = Number.isFinite(video.duration) ? video.duration : 1
      for (const id of ['scrub', 'trim-start', 'trim-end']) $(id).max = total
      $('scrub').value = 0
      $('trim-start').value = 0
      $('trim-end').value = total
      $('scrub-time').textContent = '0.0'
      showTrim()
    }
    video.onerror = () => { URL.revokeObjectURL(url); setStatus(tr('cannot_open'), true) }
    video.src = url
    return
  }
  const image = new Image()
  image.onload = () => opened(image, image.naturalWidth, image.naturalHeight)
  image.onerror = () => { URL.revokeObjectURL(url); setStatus(tr('cannot_open'), true) }
  image.src = url
})

// ---------- crop interaction ----------
$('editor').addEventListener('pointerdown', (event) => {
  if (!state.image || !aspect()) return
  state.drag = { x: event.clientX, y: event.clientY }
  $('editor').setPointerCapture(event.pointerId)
  $('editor').classList.add('dragging')
})
$('editor').addEventListener('pointermove', (event) => {
  if (!state.drag) return
  const { fit } = editorView()
  const ratio = $('editor').width / ($('editor').clientWidth || $('editor').width)
  const k = ratio / (fit * state.orientedScale)
  const dx = (event.clientX - state.drag.x) * k, dy = (event.clientY - state.drag.y) * k
  state.drag = { x: event.clientX, y: event.clientY }
  const [l, t, r, b] = state.crop
  state.crop = clampCrop([l + dx, t + dy, r + dx, b + dy])
  redraw()
})
for (const type of ['pointerup', 'pointercancel']) {
  $('editor').addEventListener(type, () => { state.drag = null; $('editor').classList.remove('dragging') })
}
$('editor').addEventListener('wheel', (event) => {
  if (!state.image || !aspect()) return
  event.preventDefault()
  const [ow, oh] = orientedSize()
  const [l, t, r, b] = state.crop
  const a = aspect()
  const factor = event.deltaY < 0 ? 0.9 : 1.1
  let w = Math.min(ow, Math.max(64, (r - l) * factor)), h = w / a
  if (h > oh) { h = oh; w = h * a }
  const cx = (l + r) / 2, cy = (t + b) / 2
  state.crop = clampCrop([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
  redraw()
}, { passive: false })

document.addEventListener('click', (event) => {
  const action = event.target.closest('[data-action]')?.dataset.action
  if (!action || !state.image) return
  if (action === 'rotate-left') state.rotate = (state.rotate + 270) % 360
  if (action === 'rotate-right') state.rotate = (state.rotate + 90) % 360
  if (action === 'flip-h') state.flipH = !state.flipH
  if (action === 'flip-v') state.flipV = !state.flipV
  rebuildOriented()
  state.crop = centeredCrop()
  redraw()
})
// ---------- video time slider ----------
// Seeks the hidden <video> and paints that frame into the editor's picture, so the crop and the preview show it.
$('scrub').addEventListener('input', () => {
  const video = state.video
  if (!video) return
  $('scrub-time').textContent = (+$('scrub').value).toFixed(1)
  video.currentTime = +$('scrub').value
})
document.addEventListener('seeked', (event) => {
  const video = state.video
  if (!video || event.target !== video) return
  state.image.getContext('2d').drawImage(video, 0, 0)
  rebuildOriented()
  redraw()
}, true)
// Start / end of the part to use: two handles on one track, kept in step with the two number boxes.
function showTrim() {
  const total = +$('trim-end').max
  const start = +$('trim-start').value, end = +$('trim-end').value
  $('start-s').value = start.toFixed(1)
  $('end-s').value = end >= total - 0.05 ? -1 : end.toFixed(1)
  $('trim-label').textContent = `${start.toFixed(1)} – ${end.toFixed(1)}  (${(end - start).toFixed(1)} s)`
  const pct = (v) => `${(v / Math.max(0.1, total)) * 100}%`
  $('trim-start').parentElement.style.setProperty('--a', pct(start))
  $('trim-start').parentElement.style.setProperty('--b', pct(end))
}
for (const id of ['trim-start', 'trim-end']) {
  $(id).addEventListener('input', () => {
    const a = $('trim-start'), b = $('trim-end')
    if (+a.value > +b.value - 0.2) { if (id === 'trim-start') a.value = +b.value - 0.2; else b.value = +a.value + 0.2 }
    if (+a.value < 0) a.value = 0
    showTrim()
    if (state.video) { stopPlay(); state.video.currentTime = +$(id).value; $('scrub').value = $(id).value; $('scrub-time').textContent = (+$(id).value).toFixed(1) }
  })
}
for (const id of ['start-s', 'end-s']) {
  $(id).addEventListener('change', () => {
    const total = +$('trim-end').max
    $('trim-start').value = Math.max(0, +$('start-s').value || 0)
    $('trim-end').value = +$('end-s').value < 0 ? total : Math.min(total, +$('end-s').value)
    showTrim()
  })
}
$('set-start').addEventListener('click', () => {
  $('trim-start').value = Math.min(+$('scrub').value, +$('trim-end').value - 0.2)
  showTrim()
})
$('set-end').addEventListener('click', () => {
  $('trim-end').value = Math.max(+$('scrub').value, +$('trim-start').value + 0.2)
  showTrim()
})

// Preview: plays the chosen part in the editor, looping, at the chosen speed.
let playing = false
function stopPlay() {
  playing = false
  if (state.video) state.video.pause()
  $('play').textContent = tr('play')
}
function playLoop() {
  const video = state.video
  if (!playing || !video) return
  const start = +$('trim-start').value, end = +$('trim-end').value
  if (video.currentTime >= end - 0.03 || video.currentTime < start - 0.05) video.currentTime = start
  state.image.getContext('2d').drawImage(video, 0, 0)
  rebuildOriented()
  redraw()
  $('scrub').value = video.currentTime
  $('scrub-time').textContent = video.currentTime.toFixed(1)
  requestAnimationFrame(playLoop)
}
$('play').addEventListener('click', () => {
  const video = state.video
  if (!video) return
  if (playing) return stopPlay()
  playing = true
  video.playbackRate = Math.min(4, Math.max(0.25, +$('speed').value || 1))
  const start = +$('trim-start').value
  if (video.currentTime < start || video.currentTime >= +$('trim-end').value - 0.05) video.currentTime = start
  $('play').textContent = tr('pause')
  video.play().then(() => requestAnimationFrame(playLoop)).catch(() => stopPlay())
})
$('scrub').addEventListener('input', stopPlay)
$('aspect').addEventListener('change', () => { if (state.image) { state.crop = centeredCrop(); redraw() } })
for (const id of ['width', 'brightness', 'darken', 'blur', 'opacity', 'size', 'position', 'speed']) {
  $(id).addEventListener('input', () => { showValue(id); redraw() })
}
function showValue(id) {
  const out = document.querySelector(`output[for="${id}"]`)
  if (out) out.textContent = (+$(id).value).toFixed(2)
}
;['brightness', 'darken', 'blur', 'opacity', 'speed'].forEach(showValue)
new ResizeObserver(redraw).observe(document.body)

// ---------- applying ----------
function setStatus(text, error = false) {
  $('status').textContent = text
  $('status').classList.toggle('error', error)
}
function setProgress(fraction) {
  $('progress').hidden = fraction === null
  $('bar').style.width = `${Math.round((fraction ?? 0) * 100)}%`
}
function base64(bytes) {
  let binary = ''
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000))
  return btoa(binary)
}
// Orca lets a panel send at most 120 messages per 10 s (PANEL_MESSAGE_RATE_LIMIT). Upload chunks are
// spaced to about 10 per second, leaving room for status polls, and a refused message waits out
// Orca's retry-after hint and is sent again instead of failing the whole upload.
const MIN_GAP_MS = 100
let lastRequestAt = 0
async function requestPaced(name, input) {
  for (let attempt = 0; ; attempt++) {
    const wait = lastRequestAt + MIN_GAP_MS - Date.now()
    if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait))
    lastRequestAt = Date.now()
    try {
      return await orca.plugin.request(name, input)
    } catch (error) {
      if (error?.code !== 'rate_limited' || attempt >= 30) throw error
      const retryMs = typeof error.retryAfterMs === 'number' ? error.retryAfterMs : 1000
      setStatus(tr('rate_limited', { s: Math.ceil(retryMs / 1000) }))
      await new Promise((resolve) => setTimeout(resolve, retryMs + 100))
    }
  }
}

function currentEdit() {
  const [outW, outH] = outputSize()
  return {
    rotate: state.rotate, flip_h: state.flipH, flip_v: state.flipV, crop: state.crop,
    out_w: outW, out_h: outH,
    brightness: +$('brightness').value, darken: +$('darken').value, blur: +$('blur').value,
    opacity: +$('opacity').value, size: $('size').value, position: $('position').value,
    mode: document.querySelector('input[name=mode]:checked').value,
    speed: +$('speed').value, start_s: Math.max(0, +$('start-s').value || 0), end_s: Math.max(-1, +$('end-s').value || 0),
    first_frame: Math.max(0, Math.round(+$('first').value || 0)),
    last_frame: Math.max(-1, Math.round(+$('last').value)), frame_step: Math.min(4, Math.max(1, Math.round(+$('step').value || 1)))
  }
}

$('apply').addEventListener('click', async () => {
  stopPlay()
  if ((!state.file && !state.library) || state.busy) return
  state.busy = true
  state.cancelled = false
  state.uploadId = null
  $('apply').disabled = true
  $('cancel').hidden = false
  $('cancel').disabled = false
  const slot = +document.querySelector('input[name=slot]:checked').value
  try {
    let id
    if (state.file) {
      setStatus(tr('sending'))
      setProgress(0)
      const bytes = new Uint8Array(await state.file.arrayBuffer())
      const begun = await orca.plugin.request('upload.begin', { name: state.file.name, size: bytes.length, lang: language })
      id = begun.id
      state.uploadId = id
      const chunks = Math.ceil(bytes.length / begun.chunkBytes)
      for (let i = 0; i < chunks; i++) {
        if (state.cancelled) return
        await requestPaced('upload.chunk', { id, index: i, data: base64(bytes.subarray(i * begun.chunkBytes, (i + 1) * begun.chunkBytes)) })
        setProgress((i + 1) / chunks * 0.3)
        setStatus(tr('sending_n', { i: i + 1, n: chunks }))
      }
    }
    if (state.cancelled) return
    setStatus(tr('processing'))
    // Without a file in the panel the worker uses the picture saved for the slot that was reopened.
    // Only fields that have a value: Orca rejects a request that carries undefined.
    const payload = { slot, edit: currentEdit(), lang: language }
    if (state.file) payload.id = id
    else payload.library = state.library
    const { job } = await orca.plugin.request('wallpaper.apply', payload)
    state.uploadId = null
    state.job = job
    if (state.cancelled) return void orca.plugin.request('wallpaper.cancel', { job, lang: language }).catch(() => {})
    void pollJob(job, slot)
  } catch (error) {
    if (!state.cancelled) finish(false, tr('failed', { e: error?.message || String(error) }))
  }
})

// Stops whichever stage is running: the upload (the worker drops what arrived) or the encode (the worker
// stops Python). The slot keeps its current wallpaper.
$('cancel').addEventListener('click', () => {
  if (!state.busy) return
  state.cancelled = true
  $('cancel').disabled = true
  const job = state.job, uploadId = state.uploadId
  if (job) orca.plugin.request('wallpaper.cancel', { job, lang: language }).catch(() => {})
  else if (uploadId) orca.plugin.request('upload.cancel', { id: uploadId }).catch(() => {})
  finish(false, tr('cancelled'))
})

// Why poll as well as listen: a posted result can miss the panel, and these requests keep the worker
// counted as active so Orca never stops it in the middle of a long encode.
async function pollJob(job, slot) {
  const started = Date.now()
  while (state.job === job) {
    if (Date.now() - started > 15 * 60 * 1000) return finish(false, tr('timeout'))
    await new Promise((resolve) => setTimeout(resolve, 1000))
    if (state.job !== job) return
    try {
      const status = await requestPaced('wallpaper.status', { job })
      if (status.state === 'done') return showResult(job, slot, status.result || {})
      if (status.state === 'unknown') return finish(false, tr('worker_restarted'))
      setStatus(status.text || tr('processing'))
      $('bar').style.width = `${Math.min(95, (parseFloat($('bar').style.width) || 30) + 2)}%`
    } catch (error) {
      setStatus(tr('waiting_worker', { e: error?.message || error }))
    }
  }
}

function showResult(job, slot, answer) {
  if (!job || state.job !== job) return
  if (!answer.ok) return finish(false, tr('failed', { e: answer.error || tr('unknown_error') }))
  const name = 'My Wallpaper' + (slot === 1 ? '' : ` ${slot}`)
  const note = answer.reduced?.length ? '\n' + tr('adjusted', { list: answer.reduced.join('; ') }) : ''
  const unloaded = answer.reloaded === false ? '\n' + tr('reload_failed', { folder: answer.folder || '' }) : ''
  finish(true, tr('applied', { name, summary: answer.summary, note, folder: answer.folder || '' }) + unloaded)
}

function finish(ok, text) {
  state.busy = false
  state.job = null
  state.uploadId = null
  $('apply').disabled = false
  $('cancel').hidden = true
  setProgress(null)
  setStatus(text, !ok)
}

orca.plugin.on('wallpaper.progress', ({ job, text }) => {
  if (job !== state.job) return
  setStatus(text)
  $('bar').style.width = `${Math.min(95, (parseFloat($('bar').style.width) || 30) + 5)}%`
})
orca.plugin.on('wallpaper.done', (answer) => {
  showResult(answer.job, +document.querySelector('input[name=slot]:checked').value, answer)
})

// The preview matches the user's real terminal Background Opacity when the worker can read it.
orca.plugin.request('wallpaper.env').then(({ terminalOpacity }) => {
  state.terminalOpacity = terminalOpacity
  state.opacityKnown = true
  updateTexts()
  redraw()
}).catch(() => {})

// ---------- resuming a job ----------
// Studio writes the new picture into the plugin's own folder, and Orca reloads a development plugin (and its panel)
// when a file in that folder changes. A reloaded panel has lost everything it knew, so it asks the worker for the
// newest job (the worker reads it from the job file): still running, or finished a moment ago.
function resumeJob() {
  orca.plugin.request('wallpaper.recent', {}).then((recent) => {
    if (!recent || !recent.job) return void restoreFromLibrary(0)
    if (state.busy) return
    state.job = recent.job
    $('editor-box').hidden = false
    if (recent.state === 'done') {
      showResult(recent.job, recent.result?.slot || 1, recent.result || {})
      return void restoreFromLibrary(recent.result?.slot || 0)
    }
    state.busy = true
    $('apply').disabled = true
    $('cancel').hidden = false
    $('cancel').disabled = false
    setProgress(0.5)
    setStatus(recent.text || tr('processing'))
    void pollJob(recent.job, 1)
  }).catch(() => {})
}

// ---------- reopening a saved slot ----------
// The Python tool keeps each slot's original picture, a small preview and the settings used. After Apply (which
// makes Orca reload the panel) and whenever the panel opens, the editor comes back with the last slot's preview
// and settings, so they can be adjusted and applied again; the original never travels to the panel.
async function restoreFromLibrary(wantedSlot) {
  if (state.file || state.library) return
  try {
    const first = await orca.plugin.request('library.get', { slot: wantedSlot || 0, index: 0 })
    if (!first || !first.slot) return
    const parts = [first.data]
    for (let i = 1; i < first.chunks; i++) parts.push((await requestPaced('library.get', { slot: first.slot, index: i })).data)
    const binary = atob(parts.join(''))
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0))
    const url = URL.createObjectURL(new Blob([bytes], { type: 'image/jpeg' }))
    const image = new Image()
    await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; image.src = url })
    URL.revokeObjectURL(url)
    if (state.file || state.library) return // the user picked something while this loaded
    const saved = first.settings, e = saved.edit || {}
    // The editor shows the small preview scaled to the original's size, so the crop keeps the original's pixels.
    Object.assign(state, { library: first.slot, image, natW: saved.width, natH: saved.height, rotate: e.rotate || 0, flipH: !!e.flip_h, flipV: !!e.flip_v })
    const set = (id, value) => { if (value !== undefined && value !== null) { $(id).value = value; showValue(id) } }
    ;['brightness', 'darken', 'blur', 'opacity', 'size', 'position', 'speed'].forEach((id) => set(id, e[id]))
    set('first', e.first_frame); set('last', e.last_frame); set('step', e.frame_step)
    set('start-s', e.start_s); set('end-s', e.end_s)
    let nearest = 0
    WIDTHS.forEach(([, w], i) => { if (Math.abs(w - e.out_w) < Math.abs(WIDTHS[nearest][1] - e.out_w)) nearest = i })
    $('width').selectedIndex = nearest
    const radio = (name, value) => { const r = document.querySelector(`input[name=${name}][value="${value}"]`); if (r) r.checked = true }
    radio('slot', first.slot)
    radio('mode', e.mode || 'stock')
    const [ow, oh] = orientedSize()
    const crop = Array.isArray(e.crop) && e.crop.length === 4 ? e.crop : [0, 0, ow, oh]
    const ratio = (crop[2] - crop[0]) / Math.max(1, crop[3] - crop[1])
    let pick = ASPECTS.findIndex(([, a]) => a && Math.abs(a - ratio) < 0.02)
    if (pick < 0) pick = crop[2] - crop[0] >= ow - 1 && crop[3] - crop[1] >= oh - 1 ? ASPECTS.length - 1 : 0
    $('aspect').selectedIndex = pick
    $('video-range').hidden = !saved.video
    const name = String(saved.original || '').split(/[\\/]/).pop() || ''
    $('source').textContent = tr('restored', { name: 'My Wallpaper' + (first.slot === 1 ? '' : ` ${first.slot}`), file: name, w: saved.width, h: saved.height })
    $('editor-box').hidden = false
    rebuildOriented()
    state.crop = clampCrop(crop)
    redraw()
  } catch {
    // nothing to reopen
  }
}

// ---------- language ----------
/** Texts that are built in code rather than written in index.html. */
function updateTexts() {
  if (!state.file && !state.library) $('source').textContent = tr('source_hint')
  $('preview-note').textContent = state.opacityKnown ? tr('preview_note_opacity', { v: state.terminalOpacity }) : tr('preview_note')
}
function applyLanguage() {
  translateDocument()
  fillSelects()
  updateTexts()
  redraw()
}
applyLanguage()
resumeJob()
// Orca tells a panel its language when the panel opens, so a change made later is picked up the next time
// the panel is shown: check again when the panel regains focus or becomes visible, and once in a while.
function checkLanguage() {
  const next = detectLanguage()
  if (next === language) return
  language = next
  applyLanguage()
}
window.addEventListener('focus', checkLanguage)
document.addEventListener('visibilitychange', checkLanguage)
setInterval(checkLanguage, 2000)

// The Apply bar shows only while the editor does (errors before that still show in the bar's status line).
new MutationObserver(() => document.body.classList.toggle('has-editor', !$('editor-box').hidden))
  .observe($('editor-box'), { attributes: true, attributeFilter: ['hidden'] })
