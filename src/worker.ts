// Wallpaper Studio worker. A panel cannot write files and a panel request carries at most 64 KiB, so the
// panel streams the chosen image here in chunks. The worker reassembles it in a temp folder and runs
// wallpaper_cli.py (the tested Python image pipeline), which writes the slot's wallpaper and theme files
// into the ASCII themes plugin. Progress and the result are posted back to the panel.
import type { OrcaWorkerApi } from 'orca/worker'
import { spawn, spawnSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { readdirSync } from 'node:fs'
import { appendFile, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024
const MAX_CHUNK_BYTES = 45 * 1024 // base64 of this stays under the 64 KiB request limit
const UPLOAD_IDLE_MS = 5 * 60 * 1000
// The Python image tools ship inside this plugin, next to src/.
const TOOLS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'tools')

// Worker messages follow Orca's UI language. The panel sends it with its requests ("vi-VN" gives Vietnamese;
// every other language gets English) and the worker remembers the latest one for errors raised later.
let language: 'vi' | 'en' = 'vi'
function setLanguage(code: unknown): void {
  if (typeof code === 'string' && code) language = code.toLowerCase().startsWith('vi') ? 'vi' : 'en'
}
const TEXT: Record<string, [string, string]> = {
  python_missing: ['Không chạy được Python ({python}): {error}', 'Could not run Python ({python}): {error}'],
  no_python: [
    'Không tìm thấy Python có Pillow. Hãy cài Python 3 rồi chạy "pip install Pillow", hoặc nhập đường dẫn python.exe trong cài đặt plugin.',
    'No Python with Pillow was found. Install Python 3 and run "pip install Pillow", or enter the path of python.exe in the plugin settings.'
  ],
  tool_stopped: ['Công cụ xử lý ảnh dừng (mã {code}). {tail}', 'The image tool stopped (code {code}). {tail}'],
  cancelled: ['Đã hủy.', 'Cancelled.'],
  too_big: ['Ảnh phải nhỏ hơn {mb} MB.', 'The image must be smaller than {mb} MB.'],
  expired: ['Phiên gửi ảnh đã hết hạn. Hãy chọn lại ảnh.', 'The upload session expired. Choose the image again.'],
  out_of_order: ['Mảnh ảnh đến sai thứ tự.', 'An image chunk arrived out of order.'],
  size_mismatch: ['Dữ liệu ảnh không khớp kích thước.', 'The image data does not match its size.'],
  not_sent: ['Ảnh chưa được gửi đủ.', 'The image was not fully sent.'],
  bad_slot: ['Ô hình nền không hợp lệ.', 'Invalid wallpaper slot.'],
  processing: ['Đang xử lý ảnh…', 'Processing the image…']
}
function say(key: string, params: Record<string, string | number> = {}): string {
  const [vietnamese, english] = TEXT[key]
  return (language === 'vi' ? vietnamese : english).replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? ''))
}

type Upload = { dir: string; file: string; expected: number; received: number; next: number; touched: number }
const uploads = new Map<string, Upload>()

// Why kept here and polled by the panel: a posted "done" can miss the panel (closed, reloaded), and the
// panel's polling requests also count as activity, so Orca does not reap the worker mid-encode.
type Job = {
  state: 'running' | 'done'
  text: string
  result?: Record<string, unknown>
  finished?: number
  child?: ReturnType<typeof spawn>
}
const jobs = new Map<string, Job>()
const JOB_KEEP_MS = 10 * 60 * 1000

function fail(code: string, message: string): Error {
  return Object.assign(new Error(message), { code })
}

/** Commands that might start a Python with Pillow, in the order to try: the plugin setting, then the usual launchers
 *  and the per-user install folders. A command is a program plus any leading arguments (`py -3`). */
function pythonCandidates(configured: string): string[][] {
  const list: string[][] = []
  if (configured) list.push([configured])
  list.push(['py', '-3'], ['python3'], ['python'])
  const local = process.env.LOCALAPPDATA ?? (process.env.USERPROFILE ? join(process.env.USERPROFILE, 'AppData', 'Local') : '')
  if (local) {
    for (const base of [join(local, 'Python'), join(local, 'Programs', 'Python')]) {
      try {
        for (const name of readdirSync(base).sort().reverse()) list.push([join(base, name, 'python.exe')])
      } catch {
        // that install folder does not exist
      }
    }
  }
  return list
}

const pythonFound = new Map<string, string[]>()
/** The first candidate that can import Pillow, remembered per setting value; null when none can. */
function findPython(configured: string): string[] | null {
  const known = pythonFound.get(configured)
  if (known) return known
  for (const command of pythonCandidates(configured)) {
    const probe = spawnSync(command[0], [...command.slice(1), '-I', '-c', 'import PIL'], { windowsHide: true, timeout: 10_000 })
    if (probe.status === 0) {
      pythonFound.set(configured, command)
      return command
    }
  }
  return null
}

type Tools = { python: string[] | null; cli: string; env: Record<string, string> }
async function tools(orca: OrcaWorkerApi): Promise<Tools> {
  let settings: Record<string, unknown> = {}
  try {
    settings = ((await orca.host.call('settings.get', {})) as { settings?: Record<string, unknown> }).settings ?? {}
  } catch {
    // no settings: the defaults below apply
  }
  const text = (value: unknown) => (typeof value === 'string' ? value.trim() : '')
  return {
    python: findPython(text(settings.python)),
    cli: join(TOOLS_DIR, 'wallpaper_cli.py'),
    // The Python side keeps the My Wallpaper themes in this folder (empty: a default folder in the user's home).
    env: { WALLPAPER_THEMES_DIR: text(settings.themesDir) }
  }
}

/** Runs the CLI: stderr lines starting with PROGRESS go to onProgress, stdout's last line is the JSON answer. */
function runCli(
  python: string[],
  args: string[],
  onProgress: (text: string) => void,
  onChild: (child: ReturnType<typeof spawn>) => void = () => undefined,
  extraEnv: Record<string, string> = {}
): Promise<Record<string, unknown>> {
  return new Promise((resolve) => {
    // Why: Orca gives workers an allowlisted environment without APPDATA, which the Python side needs to
    // find Orca's profile; ELECTRON_RUN_AS_NODE must not leak into child processes.
    const env: Record<string, string | undefined> = { ...process.env, ...extraEnv }
    env.APPDATA ??= env.USERPROFILE ? join(env.USERPROFILE, 'AppData', 'Roaming') : undefined
    env.LOCALAPPDATA ??= env.USERPROFILE ? join(env.USERPROFILE, 'AppData', 'Local') : undefined
    delete env.ELECTRON_RUN_AS_NODE
    const child = spawn(python[0], [...python.slice(1), '-I', ...args], { windowsHide: true, env })
    onChild(child)
    let out = ''
    let err = ''
    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (chunk: string) => {
      out += chunk
    })
    child.stderr.on('data', (chunk: string) => {
      err += chunk
      for (const line of chunk.split(/\r?\n/)) {
        if (line.startsWith('PROGRESS ')) onProgress(line.slice(9))
      }
    })
    child.on('error', (error) => resolve({ ok: false, error: say('python_missing', { python: python.join(' '), error: error.message }) }))
    child.on('close', (code) => {
      const last = out.trim().split(/\r?\n/).pop() ?? ''
      try {
        resolve(JSON.parse(last))
      } catch {
        const tail = err.split(/\r?\n/).filter((line) => line && !line.startsWith('PROGRESS ')).slice(-3).join(' ')
        resolve({ ok: false, error: say('tool_stopped', { code: code ?? '', tail }).trim() })
      }
    })
  })
}

async function dropUpload(id: string): Promise<void> {
  const upload = uploads.get(id)
  uploads.delete(id)
  if (upload) await rm(upload.dir, { recursive: true, force: true }).catch(() => undefined)
}

export default function activate(orca: OrcaWorkerApi): void {
  // Uploads abandoned mid-way (panel closed) are removed after a few idle minutes.
  const sweep = setInterval(() => {
    const now = Date.now()
    for (const [id, upload] of uploads) if (now - upload.touched > UPLOAD_IDLE_MS) void dropUpload(id)
    for (const [id, job] of jobs) if (job.finished && now - job.finished > JOB_KEEP_MS) jobs.delete(id)
  }, 60 * 1000)

  // Cancelling an upload drops what arrived; cancelling a job stops Python. The slot's wallpaper is only
  // replaced at the very end of a successful run, so a cancelled job leaves the current one in place.
  orca.panels.handle('upload.cancel', async ({ id }: { id: string }) => {
    await dropUpload(String(id ?? ''))
    return { ok: true }
  })

  orca.panels.handle('wallpaper.cancel', async ({ job, lang }: { job: string; lang?: string }) => {
    setLanguage(lang)
    const entry = jobs.get(String(job ?? ''))
    if (!entry || entry.state === 'done') return { ok: false }
    Object.assign(entry, { state: 'done', result: { ok: false, error: say('cancelled') }, finished: Date.now() })
    entry.child?.kill()
    orca.log('wallpaper.apply cancelled')
    return { ok: true }
  })

  orca.panels.handle('wallpaper.status', async ({ job }: { job: string }) => {
    const entry = jobs.get(String(job ?? ''))
    if (!entry) return { state: 'unknown' }
    return { state: entry.state, text: entry.text, result: entry.result ?? null }
  })
  sweep.unref?.()

  orca.panels.handle('wallpaper.env', async () => {
    const { python, cli, env } = await tools(orca)
    if (!python) {
      orca.log('wallpaper.env: no Python with Pillow found')
      return { terminalOpacity: 0.6, error: say('no_python') }
    }
    const answer = await runCli(python, [cli, 'env'], () => undefined, undefined, env)
    if (typeof answer.terminalOpacity === 'number') return { terminalOpacity: answer.terminalOpacity }
    // Why surface it: a missing Python or tools folder otherwise only shows up later, on Apply.
    orca.log(`wallpaper.env failed (${python.join(' ')} ${cli}): ${JSON.stringify(answer)}`)
    return { terminalOpacity: 0.6, error: String(answer.error ?? 'unknown error') }
  })

  orca.panels.handle('upload.begin', async ({ name, size, lang }: { name: string; size: number; lang?: string }) => {
    setLanguage(lang)
    if (!Number.isFinite(size) || size <= 0 || size > MAX_UPLOAD_BYTES) {
      throw fail('invalid_params', say('too_big', { mb: MAX_UPLOAD_BYTES / 1048576 }))
    }
    const ext = /\.(jpe?g|png|webp|bmp|gif)$/i.exec(String(name ?? ''))?.[0].toLowerCase() ?? '.img'
    const dir = await mkdtemp(join(tmpdir(), 'orca-wallpaper-'))
    const file = join(dir, 'source' + ext)
    await writeFile(file, new Uint8Array(0))
    const id = randomUUID()
    uploads.set(id, { dir, file, expected: size, received: 0, next: 0, touched: Date.now() })
    return { id, chunkBytes: MAX_CHUNK_BYTES }
  })

  orca.panels.handle('upload.chunk', async ({ id, index, data }: { id: string; index: number; data: string }) => {
    const upload = uploads.get(id)
    if (!upload) throw fail('conflict', say('expired'))
    if (index !== upload.next) throw fail('conflict', say('out_of_order'))
    const bytes = Buffer.from(String(data ?? ''), 'base64')
    if (bytes.length > MAX_CHUNK_BYTES || upload.received + bytes.length > upload.expected) {
      await dropUpload(id)
      throw fail('invalid_params', say('size_mismatch'))
    }
    await appendFile(upload.file, bytes)
    upload.received += bytes.length
    upload.next += 1
    upload.touched = Date.now()
    return { received: upload.received }
  })

  // Answers at once with a job id; the slow encode runs in the background and reports through panel
  // posts, because a request answer must arrive within 120 s at most.
  orca.panels.handle(
    'wallpaper.apply',
    async ({ id, slot, edit, lang }: { id: string; slot: number; edit: unknown; lang?: string }, context: { panel?: string } = {}) => {
      setLanguage(lang)
      const upload = uploads.get(id)
      if (!upload || upload.received !== upload.expected) throw fail('conflict', say('not_sent'))
      if (![1, 2, 3].includes(slot)) throw fail('invalid_params', say('bad_slot'))
      const job = randomUUID()
      const target = context.panel ? { panel: context.panel } : undefined
      const entry: Job = { state: 'running', text: say('processing') }
      jobs.set(job, entry)
      const finish = (result: Record<string, unknown>) => {
        if (entry.state === 'done') return // already cancelled
        Object.assign(entry, { state: 'done', result, finished: Date.now() })
        try {
          orca.panels.post('wallpaper.done', { job, ...result }, target)
        } catch (error) {
          orca.log(`wallpaper.done post failed: ${String(error)}`)
        }
      }
      orca.log(`wallpaper.apply slot ${slot}: started (${upload.received} bytes)`)
      void (async () => {
        try {
          const { python, cli, env } = await tools(orca)
          if (!python) return finish({ ok: false, error: say('no_python') })
          const editFile = join(upload.dir, 'edit.json')
          // The Python tool writes its own messages (progress, adjustments, errors) in the same language.
          await writeFile(editFile, JSON.stringify({ ...(edit as Record<string, unknown> | null ?? {}), lang: language }), 'utf8')
          let lastPost = 0
          const answer = await runCli(python, [cli, 'apply', upload.file, String(slot), editFile], (text) => {
            entry.text = text
            const now = Date.now()
            if (now - lastPost > 400) {
              lastPost = now
              try {
                orca.panels.post('wallpaper.progress', { job, text }, target)
              } catch {
                // the panel polls wallpaper.status anyway
              }
            }
          }, (child) => {
            entry.child = child
          }, env)
          orca.log(`wallpaper.apply slot ${slot}: ${JSON.stringify(answer)}`)
          finish(answer)
        } catch (error) {
          orca.log(`wallpaper.apply slot ${slot} failed: ${String((error as Error)?.stack ?? error)}`)
          finish({ ok: false, error: String((error as Error)?.message ?? error) })
        } finally {
          await dropUpload(id)
        }
      })()
      return { job }
    }
  )
}

export function deactivate(): void {
  for (const id of [...uploads.keys()]) void dropUpload(id)
}
