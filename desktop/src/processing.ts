import { isTauri, invoke } from '@tauri-apps/api/core'
import { parseJobSnapshot } from './runtime.ts'
export type ExportMode = 'shorts' | 'longform' | 'both'
export interface VideoSource { path:string; name:string; size_bytes:number; modified_ms:number; duration_seconds:number; width:number; height:number }
export interface MediaSelection { source:VideoSource|null; output:string|null }
type Transport = (command:string,args?:Record<string,unknown>)=>Promise<unknown>
export function parseSource(value:unknown):VideoSource {
 if (!value || typeof value!=='object') throw new Error('Invalid source metadata')
 const s=value as VideoSource
 if (Object.keys(s).length!==7 || !s.path || typeof s.path!=='string' || !s.name || typeof s.name!=='string' ||
     !Number.isSafeInteger(s.size_bytes) || s.size_bytes<=0 || !Number.isSafeInteger(s.modified_ms) || s.modified_ms<0 ||
     !Number.isFinite(s.duration_seconds) || s.duration_seconds<=0 || !Number.isInteger(s.width) || s.width<=0 || !Number.isInteger(s.height) || s.height<=0) throw new Error('Invalid source metadata')
 return {...s}
}
export async function mediaCommand(command:'select_source_video'|'select_output_workspace'|'get_media_selection',native=isTauri(),transport:Transport=invoke):Promise<MediaSelection|null> {
 if (!native) return null
 const value=await transport(command)
 if (command==='select_source_video') return value===null?null:{source:parseSource(value),output:null}
 if (command==='select_output_workspace') {
  if(value===null)return null
  if(typeof value!=='string'||!value)throw new Error('Invalid output folder')
  return {source:null,output:value}
 }
 if(!value || typeof value!=='object')throw new Error('Invalid native selection')
 const s=value as MediaSelection
 if(Object.keys(s).length!==2 || (s.output!==null && (typeof s.output!=='string'||!s.output)))throw new Error('Invalid native selection')
 return {source:s.source===null?null:parseSource(s.source),output:s.output}
}
export async function startProcessing(mode:ExportMode,native=isTauri(),transport:Transport=invoke) {
 if(!native)return null
 if(!['shorts','longform','both'].includes(mode))throw new Error('Unsupported export mode')
 return parseJobSnapshot(await transport('start_processing_job',{mode}))
}
