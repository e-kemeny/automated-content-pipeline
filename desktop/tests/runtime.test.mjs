import test from 'node:test'
import assert from 'node:assert/strict'
import { getRuntimeStatus, parseRuntimeInfo, runtimePresentation } from '../src/runtime.ts'

const info = { applicationVersion: '0.1.0', operatingSystem: 'windows', cpuArchitecture: 'x86_64', nativeRuntimeAvailable: true }
test('native success preserves returned runtime values', async () => {
 assert.deepEqual(await getRuntimeStatus(true, async () => info), { kind: 'ready', info })
})
test('browser preview never invokes a native command', async () => {
 assert.deepEqual(await getRuntimeStatus(false, async () => { throw new Error('must not run') }), { kind: 'browser' })
})
test('invocation errors become unavailable, not a thrown exception', async () => {
 assert.deepEqual(await getRuntimeStatus(true, async () => { throw new Error('denied') }), { kind: 'unavailable', error: 'denied' })
})
test('string and unknown rejections are handled', async () => {
 assert.equal((await getRuntimeStatus(true, async () => { throw 'offline' })).error, 'offline')
 assert.equal((await getRuntimeStatus(true, async () => { throw null })).error, 'Native invocation failed')
})
test('malformed responses cannot produce desktop ready', async () => {
 for (const value of [null, {}, { ...info, applicationVersion: '' }, { ...info, operatingSystem: 42 }, { ...info, cpuArchitecture: null }, { ...info, nativeRuntimeAvailable: 'true' }]) {
  assert.equal((await getRuntimeStatus(true, async () => value)).kind, 'unavailable')
 }
})
test('explicit native unavailable is not success', async () => {
 assert.equal((await getRuntimeStatus(true, async () => ({ ...info, nativeRuntimeAvailable: false }))).kind, 'unavailable')
})
test('response validation returns an independent typed object', () => {
 assert.deepEqual(parseRuntimeInfo(info), info)
 assert.notEqual(parseRuntimeInfo(info), info)
})
test('all status descriptions disclose that Python is not connected', () => {
 for (const status of [{ kind: 'checking' }, { kind: 'browser' }, { kind: 'ready', info }, { kind: 'unavailable', error: 'denied' }]) {
  assert.match(runtimePresentation(status).detail, /Python processing is not connected/)
 }
 assert.equal(runtimePresentation({ kind: 'browser' }).label, 'Browser preview')
 assert.equal(runtimePresentation({ kind: 'ready', info }).label, 'Desktop ready')
 assert.equal(runtimePresentation({ kind: 'unavailable', error: 'denied' }).label, 'Runtime unavailable')
})
