export const PRODUCT_NAME = 'Content Pipeline'
export function Brand() {
 return <div className="wordmark"><svg className="brand-icon" width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M18 6H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h6M22 6h3a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2h-8" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/><path d="m20 4-5 24" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round"/><path d="M9 10h5M21 22h2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg><span>{PRODUCT_NAME}</span></div>
}
