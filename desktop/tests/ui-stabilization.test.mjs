import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { formatDuration, formatBytes } from '../src/mediaFormatting.ts'
import { subscribeJobEvents, watchDiagnosticJob, newerJobState } from '../src/runtime.ts'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('consistent source/export units without invented missing values', () => {
 assert.equal(formatDuration(231.433288), '231.43 s')
 assert.equal(formatDuration(15), '15.00 s')
 assert.equal(formatBytes(1048576), '1.00 MiB')
 for (const missing of [null, undefined, NaN, Infinity, -1]) {
  assert.equal(formatDuration(missing), 'Unavailable')
  assert.equal(formatBytes(missing), 'Unavailable')
 }
})
test('native subscription explicitly matches Rust main-window emission', async () => {
 let observed
 const stop = () => {}
 const cleanup = await subscribeJobEvents(v => observed = v, async (name, handler, options) => {
  assert.equal(name, 'diagnostic-job')
  assert.deepEqual(options, {target:'main'})
  handler({payload:{stage:'Exporting Shorts'}})
  return stop
 })
 assert.equal(observed.stage, 'Exporting Shorts')
 assert.equal(cleanup, stop)
})
test('live processing stages arrive without focus reconciliation and survive stale snapshots', async () => {
 const idle={jobId:null,revision:0,state:'Idle',stage:'Idle',startedAt:null,finishedAt:null,progress:{completed:0,total:12},error:null}
 let callback, current
 const cleanup=await watchDiagnosticJob(s=>current=newerJobState(current,s),e=>{throw e},true,async()=>idle,async cb=>{callback=cb;return()=>{}})
 const running={...idle,jobId:'job-1',revision:2,state:'Running',stage:'Collecting observations and generating shared analysis',startedAt:1,progress:{completed:0,total:0},processing:{workspace:'C:/job',mode:'both',artifacts:[]}}
 callback(running)
 assert.equal(current.stage,running.stage)
 callback({...running,revision:3,stage:'Exporting Shorts'})
 callback(running)
 assert.equal(current.stage,'Exporting Shorts')
 cleanup()
})
test('screen visibility, Unicode labels and bounded layout regression guards', () => {
 const css=read('../src/styles.css'), app=read('../src/App.tsx'), studio=read('../src/components/ProcessingStudio.tsx')
 assert.doesNotMatch(css, /animation:screen-in|left:-10px/)
 assert.match(css, /\.screen-transition \{ opacity:1/)
 assert.match(css, /\.source-content h2 \{ overflow-wrap:anywhere/)
 assert.match(css, /scrollbar-gutter:stable both-edges/)
 assert.match(studio, /selection.source\?\.name/)
 assert.doesNotMatch(studio, /Â|Ã|â€/)
 assert.match(app, /ProcessingStudio visible=\{screen==='studio'\}/)
 assert.match(studio, /processing-status.*aria-live="polite"/)
})
