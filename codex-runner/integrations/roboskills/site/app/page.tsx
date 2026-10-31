import Workspace from './workspace';
import { env } from 'cloudflare:workers';
import { getChatGPTUser } from './chatgpt-auth';
export const dynamic = 'force-dynamic';
export default async function Home() { const u=await getChatGPTUser();return <Workspace operator={!!u && u.email.toLowerCase()===((env as unknown as {RUNNER_OWNER_EMAIL?:string}).RUNNER_OWNER_EMAIL||'').toLowerCase()} initialName={u?.fullName||''} initialEmail={u?.email||''}/>;}
