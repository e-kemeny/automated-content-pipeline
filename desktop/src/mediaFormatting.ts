/** Format actual values only; missing/invalid metadata is never replaced by zero. */
export function formatDuration(seconds: number | null | undefined): string {
 return typeof seconds === 'number' && Number.isFinite(seconds) && seconds >= 0
  ? `${seconds.toFixed(2)} s` : 'Unavailable'
}
export function formatBytes(bytes: number | null | undefined): string {
 return typeof bytes === 'number' && Number.isFinite(bytes) && bytes >= 0
  ? `${(bytes / 1048576).toFixed(2)} MiB` : 'Unavailable'
}
