import { formatDuration, formatBytes } from '../mediaFormatting'
import { useEffect, useState } from 'react'
import { Studio } from './Workspaces'
import { mediaCommand, startProcessing } from '../processing'
import type { ExportMode, MediaSelection } from '../processing'
import { cancelDiagnosticJob, getDiagnosticJob, jobActive, newerJobState, watchDiagnosticJob } from '../runtime'
import type { JobSnapshot } from '../runtime'
function errorText(e:unknown) { return e && typeof e==='object' && 'message' in e ? String(e.message) : String(e) }
export function ProcessingStudio({visible}:{visible:boolean}) {
 const [selection,setSelection]=useState<MediaSelection>({source:null,output:null})
 const [mode,setMode]=useState<ExportMode>('both')
 const [job,setJob]=useState<JobSnapshot|null>(null)
 const [pending,setPending]=useState(false)
 const [error,setError]=useState('')
 useEffect(()=>{
  let active=true; let stop:(()=>void)|undefined
  const update=(s:JobSnapshot)=>{if(active)setJob(old=>newerJobState(old,s))}
  const fail=(e:unknown)=>{if(active)setError(errorText(e))}
  void watchDiagnosticJob(update,fail).then(clean=>{if(active)stop=clean;else clean()}).catch(fail)
  const reconcile=()=>{void mediaCommand('get_media_selection').then(s=>{if(active&&s)setSelection(s)}).catch(fail);void getDiagnosticJob().then(s=>{if(s)update(s)}).catch(fail)}
  reconcile();window.addEventListener('focus',reconcile)
  return()=>{active=false;stop?.();window.removeEventListener('focus',reconcile)}
 },[])
 const active=job?jobActive(job.state):false
 async function choose(source:boolean) {
  setPending(true);setError('')
  try {const s=await mediaCommand(source?'select_source_video':'select_output_workspace');if(s)setSelection(old=>source?{...old,source:s.source}:{...old,output:s.output})}
  catch(e){setError(errorText(e))}finally{setPending(false)}
 }
 async function run(cancel=false) {
  setPending(true);setError('')
  try{const s=cancel&&job?.jobId?await cancelDiagnosticJob(job.jobId):await startProcessing(mode);if(s)setJob(old=>newerJobState(old,s))}
  catch(e){setError(errorText(e));try{const s=await getDiagnosticJob();if(s)setJob(old=>newerJobState(old,s))}catch{/* retain failure */}}
  finally{setPending(false)}
 }
 const artifacts=job?.state==='Completed'?job.processing?.artifacts??[]:[]
 return <div hidden={!visible} className="processing-studio">
  <div className="processing-bar" aria-label="Video processing" data-state={job?.state}>
   <label>Export mode <select value={mode} onChange={e=>setMode(e.target.value as ExportMode)} disabled={active||pending}><option value="shorts">Shorts</option><option value="longform">Long-form</option><option value="both">Both</option></select></label>
   <button className="text-button" disabled={active||pending} onClick={()=>void choose(false)}>Choose output folder</button>
   <button className="primary-button" disabled={!job||!selection.source||!selection.output||active||pending} onClick={()=>void run()}>Start processing</button>
   <button className="text-button" disabled={!active||job?.state==='Cancelling'||pending} onClick={()=>void run(true)}>Cancel</button>
   <div className="processing-status" role="status" aria-live="polite" aria-atomic="true">{job?.state==='Idle'?'Ready to configure':job?.stage??'Connecting'}{active&&<progress aria-label="Processing in progress"/>}</div>
  </div>
  {selection.output&&<p className="processing-path" title={selection.output}>Output location: {selection.output}</p>}
  {(error||job?.error)&&<p role="alert" className="file-error">{error||job?.error?.message}</p>}
  {job?.processing&&<p className="processing-path">Job workspace: {job.processing.workspace}{job.state==='Cancelled'||job.state==='Failed'?' · Incomplete; not published as completed outputs':''}</p>}
  {artifacts.length>0&&<details className="processing-results"><summary>{artifacts.filter(a=>a.kind==='shorts'||a.kind==='longform').length} videos ready</summary><ul>{artifacts.map(a=><li key={a.path}><span>{a.kind}{a.duration_seconds!==null?` · ${formatDuration(a.duration_seconds)}`:''}</span><code>{a.path}</code></li>)}</ul></details>}
  <Studio selected={null} onSelect={()=>{}} sourceControls={<>
   <div className="source-content"><h2>{selection.source?.name??'No video selected'}</h2>
    <button className="primary-button" disabled={active||pending} onClick={()=>void choose(true)}>{pending?'Please wait…':selection.source?'Change video':'Import video'}</button>
    {selection.source&&<p className="technical">{selection.source.width} × {selection.source.height} · {formatDuration(selection.source.duration_seconds)} · {formatBytes(selection.source.size_bytes)}</p>}
   </div><div className="source-note">Local processing · Audio-only baseline<br/>Five candidates required. Shorts remain horizontal.</div>
  </>}/>
 </div>
}
