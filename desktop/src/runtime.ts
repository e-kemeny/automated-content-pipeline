import { invoke, isTauri } from '@tauri-apps/api/core'

export interface RuntimeInfo {
 applicationVersion: string
 operatingSystem: string
 cpuArchitecture: string
 nativeRuntimeAvailable: boolean
}
export type RuntimeStatus =
 | { kind: 'checking' }
 | { kind: 'browser' }
 | { kind: 'ready'; info: RuntimeInfo }
 | { kind: 'unavailable'; error: string }

export function parseRuntimeInfo(value: unknown): RuntimeInfo {
 if (!value || typeof value !== 'object') throw new Error('Invalid runtime response')
 const data = value as Record<string, unknown>
 for (const field of ['applicationVersion', 'operatingSystem', 'cpuArchitecture']) {
  if (typeof data[field] !== 'string' || !data[field].trim()) throw new Error(`Invalid runtime field: ${field}`)
 }
 if (typeof data.nativeRuntimeAvailable !== 'boolean') throw new Error('Invalid native runtime availability')
 return {
  applicationVersion: data.applicationVersion as string,
  operatingSystem: data.operatingSystem as string,
  cpuArchitecture: data.cpuArchitecture as string,
  nativeRuntimeAvailable: data.nativeRuntimeAvailable,
 }
}

// Injectable transport keeps failure/browser tests independent of WebView2.
export async function getRuntimeStatus(
 native = isTauri(),
 request: () => Promise<unknown> = () => invoke<unknown>('get_runtime_info'),
): Promise<RuntimeStatus> {
 if (!native) return { kind: 'browser' }
 try {
  const info = parseRuntimeInfo(await request())
  if (!info.nativeRuntimeAvailable) throw new Error('Native runtime reported unavailable')
  return { kind: 'ready', info }
 } catch (error) {
  return { kind: 'unavailable', error: error instanceof Error ? error.message : typeof error === 'string' ? error : 'Native invocation failed' }
 }
}

export function runtimePresentation(status: RuntimeStatus) {
 const scope = 'Python processing is not connected. File selection is metadata-only.'
 switch (status.kind) {
  case 'checking': return { label: 'Checking runtime', detail: `Checking the desktop connection. ${scope}` }
  case 'browser': return { label: 'Browser preview', detail: `Running outside Tauri. ${scope}` }
  case 'unavailable': return { label: 'Runtime unavailable', detail: `${status.error}. ${scope}` }
  case 'ready': return { label: 'Desktop ready', detail: `Version ${status.info.applicationVersion} · ${status.info.operatingSystem} · ${status.info.cpuArchitecture}. Native runtime available. ${scope}` }
 }
}

export interface WorkerHealth {
 pythonVersion: string
 operatingSystem: string
 cpuArchitecture: string
 workerProtocolVersion: 1
}
export type WorkerStatus =
 | { kind: 'checking' }
 | { kind: 'browser' }
 | { kind: 'available'; info: WorkerHealth }
 | { kind: 'unavailable'; error: string }

export function parseWorkerHealth(value: unknown): WorkerHealth {
 if (!value || typeof value !== 'object') throw new Error('Invalid worker response')
 const data = value as Record<string, unknown>
 const fields = ['pythonVersion', 'operatingSystem', 'cpuArchitecture', 'workerProtocolVersion']
 if (Object.keys(data).length !== fields.length || !fields.every(key => Object.hasOwn(data, key))) {
  throw new Error('Invalid worker response fields')
 }
 for (const field of fields.slice(0, 3)) {
  if (typeof data[field] !== 'string' || !data[field].trim()) throw new Error('Invalid worker runtime information')
 }
 if (data.workerProtocolVersion !== 1) throw new Error('Unsupported worker protocol version')
 return {
  pythonVersion: data.pythonVersion as string,
  operatingSystem: data.operatingSystem as string,
  cpuArchitecture: data.cpuArchitecture as string,
  workerProtocolVersion: 1,
 }
}

export async function getPythonWorkerStatus(
 native = isTauri(),
 request: () => Promise<unknown> = () => invoke<unknown>('check_python_worker'),
): Promise<WorkerStatus> {
 if (!native) return { kind: 'browser' }
 try {
  return { kind: 'available', info: parseWorkerHealth(await request()) }
 } catch (error) {
  const message = error instanceof Error ? error.message
   : typeof error === 'string' ? error
   : error && typeof error === 'object' && 'message' in error && typeof error.message === 'string'
    ? error.message : 'Python worker invocation failed'
  return { kind: 'unavailable', error: message }
 }
}

// One check per page session, including React StrictMode's development remount.
let workerCheck: Promise<WorkerStatus> | undefined
export function checkWorkerOnce(): Promise<WorkerStatus> {
 return workerCheck ??= getPythonWorkerStatus()
}

export function desktopPresentation(native: RuntimeStatus, worker: WorkerStatus) {
 if (native.kind !== 'ready') return runtimePresentation(native)
 const nativeDetail = `Version ${native.info.applicationVersion} · ${native.info.operatingSystem} · ${native.info.cpuArchitecture}.`
 const scope = 'Video processing is not connected. File selection is metadata-only.'
 if (worker.kind === 'available') {
  return { label: 'Python worker available', detail: `${nativeDetail} Python ${worker.info.pythonVersion} · ${worker.info.operatingSystem} · ${worker.info.cpuArchitecture} · protocol ${worker.info.workerProtocolVersion}. Health check only. ${scope}` }
 }
 if (worker.kind === 'unavailable') {
  return { label: 'Python worker unavailable', detail: `${nativeDetail} Native desktop ready. ${worker.error}. ${scope}` }
 }
 return { label: 'Native desktop ready', detail: `${nativeDetail} Checking Python worker. ${scope}` }
}

export type JobPhase = 'Idle' | 'Starting' | 'Running' | 'Cancelling' | 'Completed' | 'Cancelled' | 'Failed'
export interface JobSnapshot {
 jobId: string | null
 revision: number
 state: JobPhase
 stage: string
 startedAt: number | null
 finishedAt: number | null
 progress: { completed: number; total: 12 }
 error: { code: string; message: string; stderr: string } | null
}
export const jobActive = (state: JobPhase) => ['Starting', 'Running', 'Cancelling'].includes(state)
export function parseJobSnapshot(value: unknown): JobSnapshot {
 const invalid = () => { throw new Error('Invalid diagnostic job state') }
 if (!value || typeof value !== 'object') return invalid()
 const v = value as Record<string, unknown>
 const keys = ['jobId', 'revision', 'state', 'stage', 'startedAt', 'finishedAt', 'progress', 'error']
 if (Object.keys(v).length !== keys.length || !keys.every(k => Object.hasOwn(v,k))) return invalid()
 const phases = ['Idle', 'Starting', 'Running', 'Cancelling', 'Completed', 'Cancelled', 'Failed']
 if (typeof v.state !== 'string' || !phases.includes(v.state) ||
     typeof v.stage !== 'string' || !v.stage.trim() || v.stage.length > 100 ||
     !Number.isSafeInteger(v.revision) || (v.revision as number) < 0) return invalid()
 const timestamp = (n: unknown) => typeof n === 'number' && Number.isSafeInteger(n) && n >= 0
 if (v.state === 'Idle') {
  if (v.jobId !== null || v.startedAt !== null || v.finishedAt !== null || v.revision !== 0) return invalid()
 } else if (typeof v.jobId !== 'string' || !v.jobId || !timestamp(v.startedAt)) return invalid()
 const terminal = ['Completed','Cancelled','Failed'].includes(v.state)
 if (terminal ? !timestamp(v.finishedAt) || (v.finishedAt as number) < (v.startedAt as number) : v.finishedAt !== null) return invalid()
 if (!v.progress || typeof v.progress !== 'object') return invalid()
 const p = v.progress as Record<string, unknown>
 if (Object.keys(p).length !== 2 || p.total !== 12 || !Number.isInteger(p.completed) ||
     (p.completed as number) < 0 || (p.completed as number) > 12) return invalid()
 if ((v.state === 'Idle' || v.state === 'Starting') && p.completed !== 0) return invalid()
 if (v.state === 'Completed' && p.completed !== 12) return invalid()
 if (v.state === 'Failed') {
  if (!v.error || typeof v.error !== 'object') return invalid()
  const e = v.error as Record<string, unknown>
  if (Object.keys(e).length !== 3 || typeof e.code !== 'string' || !e.code ||
      typeof e.message !== 'string' || !e.message || typeof e.stderr !== 'string') return invalid()
 } else if (v.error !== null) return invalid()
 return { jobId: v.jobId as string | null, revision: v.revision as number, state: v.state as JobPhase,
  stage: v.stage, startedAt: v.startedAt as number | null, finishedAt: v.finishedAt as number | null,
  progress: { completed: p.completed as number, total: 12 },
  error: v.error === null ? null : { ...(v.error as NonNullable<JobSnapshot['error']>) } }
}
export function newerJobState(previous: JobSnapshot | null, next: JobSnapshot): JobSnapshot {
 return previous && previous.revision >= next.revision ? previous : next
}
type JobTransport = (command: string, args?: Record<string, unknown>) => Promise<unknown>
export async function jobCommand(
 command: 'start_diagnostic_job' | 'get_job_state' | 'cancel_diagnostic_job',
 args?: { jobId: string }, native = isTauri(), transport: JobTransport = invoke,
): Promise<JobSnapshot | null> {
 if (!native) return null
 return parseJobSnapshot(await transport(command, args))
}
export const startDiagnosticJob = () => jobCommand('start_diagnostic_job')
export const getDiagnosticJob = () => jobCommand('get_job_state')
export const cancelDiagnosticJob = (jobId: string) => jobCommand('cancel_diagnostic_job', { jobId })

type Subscribe = (callback: (value: unknown) => void) => Promise<() => void>
export async function watchDiagnosticJob(
 update: (snapshot: JobSnapshot) => void,
 failure: (error: unknown) => void,
 native = isTauri(),
 transport: JobTransport = invoke,
 subscribe: Subscribe = async callback => {
  const { listen } = await import('@tauri-apps/api/event')
  return listen<unknown>('diagnostic-job', event => callback(event.payload))
 },
): Promise<() => void> {
 if (!native) return () => {}
 let active = true
 const stop = await subscribe(value => {
  if (!active) return
  try { update(parseJobSnapshot(value)) } catch (e) { failure(e) }
 })
 const cleanup = () => { active = false; stop() }
 try {
  // Subscribe first so a transition between subscription and snapshot cannot be lost.
  const current = await jobCommand('get_job_state', undefined, true, transport)
  if (active && current) update(current)
 } catch (e) { cleanup(); throw e }
 return cleanup
}
