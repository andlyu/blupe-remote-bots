// A browser-scoped capability lets a queue participant stop their own run.
// It carries no human identity and is never included in public run metadata.
const COOKIE = '__Host-blupe-physical';
export function physicalVisitor(request:Request):string|null {
 const value=(request.headers.get('cookie')||'').split(';').map(v=>v.trim()).find(v=>v.startsWith(COOKIE+'='))?.slice(COOKIE.length+1);
 return value&&/^[a-f0-9]{64}$/.test(value)?value:null;
}
export function newPhysicalVisitor():string {
 return Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
}
export function physicalVisitorCookie(value:string):string {
 return `${COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=86400`;
}
