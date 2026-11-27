import test from 'node:test'
import assert from 'node:assert/strict'
import { jobCommand, jobActive, newerJobState, parseJobSnapshot, watchDiagnosticJob } from '../src/runtime.ts'

const idle = { jobId:null, revision:0, state:'Idle', stage:'Idle', startedAt:null, finishedAt:null, progress:{completed:0,total:12}, error:null }
const running = { ...idle, jobId:'job-1', revision:3, state:'Running', stage:'Protocol', startedAt:1000, progress:{completed:5,total:12} }

test('valid state and progress are copied', () => {
 assert.deepEqual(parseJobSnapshot(running),running)
 assert.notEqual(parseJobSnapshot(running).progress,running.progress)
 assert.equal(jobActive('Cancelling'),true)
 assert.equal(jobActive('Completed'),false)
})
test('reject malformed identity, progress, timestamps, state and error', () => {
 for (const value of [null,{}, {...running,state:'invented'}, {...running,revision:NaN},
  {...running,jobId:null}, {...running,finishedAt:2000}, {...running,progress:{completed:13,total:12}},
  {...running,progress:{completed:1.2,total:12}}, {...running,state:'Completed',finishedAt:900},
  {...running,state:'Failed',finishedAt:2000}, {...running,error:{code:'x',message:'x',stderr:''}},
  {...idle,jobId:'invalid'}, {...running,extra:true}]) {
  assert.throws(()=>parseJobSnapshot(value))
 }
})
test('terminal snapshots require finish time and valid outcome', () => {
 for (const state of ['Completed','Cancelled','Failed']) {
  const value={...running,state,finishedAt:2000,progress:{completed:12,total:12},
   error: state==='Failed'?{code:'timeout',message:'Timed out',stderr:''}:null}
  assert.equal(parseJobSnapshot(value).state,state)
 }
})
test('older events or command responses cannot overwrite newer state or jobs', () => {
 assert.equal(newerJobState(running,{...running,revision:2}),running)
 assert.equal(newerJobState(running,{...running,revision:3}),running)
 const next={...running,jobId:'job-2',revision:10}
 assert.equal(newerJobState(next,running),next)
 assert.equal(newerJobState(running,next),next)
})
test('command forwarding and browser mode', async () => {
 let calls=0
 const transport=async (command,args)=>{ calls++; assert.equal(command,'cancel_diagnostic_job'); assert.deepEqual(args,{jobId:'job-1'}); return running }
 assert.deepEqual(await jobCommand('cancel_diagnostic_job',{jobId:'job-1'},true,transport),running)
 assert.equal(await jobCommand('start_diagnostic_job',undefined,false,transport),null)
 assert.equal(calls,1)
 await assert.rejects(jobCommand('start_diagnostic_job',undefined,true,async()=>{ throw new Error('busy') }),/busy/)
})
test('subscribe before reconcile and dispose stale callback', async () => {
 let callback, stopped=0, current=null
 const stop=await watchDiagnosticJob(s=>{ current=newerJobState(current,s) },e=>{ throw e },true,
  async()=>{ callback(running); return idle },
  async cb=>{ callback=cb; return ()=>{stopped++} })
 assert.deepEqual(current,running)
 stop()
 callback({...running,revision:8})
 assert.equal(current.revision,3)
 assert.equal(stopped,1)
})
test('failed reconciliation cleans subscription and malformed events report failure', async () => {
 let stopped=0, callback, failures=0
 await assert.rejects(watchDiagnosticJob(()=>{},()=>{},true,async()=>{throw new Error('offline')},
  async()=>()=>{stopped++}),/offline/)
 assert.equal(stopped,1)
 const stop=await watchDiagnosticJob(()=>{},()=>{failures++},true,async()=>idle,
  async cb=>{callback=cb;return ()=>{}})
 callback({})
 assert.equal(failures,1)
 stop()
})
test('browser subscriptions never invoke native transport or listen', async () => {
 const forbidden=async()=>{throw new Error('must not run')}
 const stop=await watchDiagnosticJob(()=>{},()=>{},false,forbidden,forbidden)
 stop()
})
