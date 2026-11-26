import test from 'node:test'
import assert from 'node:assert/strict'
import { getPythonWorkerStatus, parseWorkerHealth, desktopPresentation } from '../src/runtime.ts'

const info = { pythonVersion: '3.14.0', operatingSystem: 'Windows', cpuArchitecture: 'AMD64', workerProtocolVersion: 1 }
const native = { kind: 'ready', info: { applicationVersion: '0.1.0', operatingSystem: 'windows', cpuArchitecture: 'x86_64', nativeRuntimeAvailable: true } }

test('valid worker response is preserved', async () => {
 assert.deepEqual(await getPythonWorkerStatus(true, async () => info), { kind: 'available', info })
 assert.notEqual(parseWorkerHealth(info), info)
})
test('browser fallback never invokes worker', async () => {
 let calls = 0
 assert.deepEqual(await getPythonWorkerStatus(false, async () => { calls++; return info }), { kind: 'browser' })
 assert.equal(calls, 0)
})
test('malformed and incompatible responses cannot mean available', async () => {
 for (const value of [null, {}, { ...info, pythonVersion: '' }, { ...info, operatingSystem: 3 },
  { ...info, cpuArchitecture: null }, { ...info, workerProtocolVersion: 2 }, { ...info, extra: true }]) {
  assert.equal((await getPythonWorkerStatus(true, async () => value)).kind, 'unavailable')
 }
})
test('native structured errors and rejected requests are handled', async () => {
 for (const value of [new Error('missing'), 'missing', { code: 'timeout', message: 'timed out', stderr: '' }, null]) {
  const result = await getPythonWorkerStatus(true, async () => { throw value })
  assert.equal(result.kind, 'unavailable')
  assert.equal(typeof result.error, 'string')
 }
})
test('native readiness is distinct from worker availability and processing', () => {
 assert.equal(desktopPresentation(native, { kind: 'checking' }).label, 'Native desktop ready')
 assert.equal(desktopPresentation(native, { kind: 'available', info }).label, 'Python worker available')
 assert.equal(desktopPresentation(native, { kind: 'unavailable', error: 'missing' }).label, 'Python worker unavailable')
 for (const worker of [{ kind: 'checking' }, { kind: 'available', info }, { kind: 'unavailable', error: 'missing' }]) {
  assert.match(desktopPresentation(native, worker).detail, /Video processing is not connected/)
 }
})
test('browser and native failures override worker presentation', () => {
 assert.equal(desktopPresentation({ kind: 'browser' }, { kind: 'checking' }).label, 'Browser preview')
 assert.equal(desktopPresentation({ kind: 'unavailable', error: 'denied' }, { kind: 'available', info }).label, 'Runtime unavailable')
})
