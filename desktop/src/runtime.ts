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
