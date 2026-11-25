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
