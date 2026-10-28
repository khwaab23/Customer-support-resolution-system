export class ApiError extends Error { constructor(message: string, readonly status: number) { super(message); } }
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, credentials: "include" });
  if (!response.ok) { let detail = "Request failed"; try { detail = (await response.json() as {detail?: string}).detail ?? detail; } catch { /* safe default */ } throw new ApiError(detail, response.status); }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}
const cookie = (name: string) => document.cookie.split("; ").find((v) => v.startsWith(`${name}=`))?.slice(name.length + 1);
async function csrf(): Promise<Record<string, string>> { await request<void>("/v1/auth/csrf"); const token = cookie("techdemo_csrf"); if (!token) throw new Error("CSRF cookie was not set"); return {"X-CSRF-Token": decodeURIComponent(token)}; }
export type User = { user_id: string; role: "CUSTOMER" | "ADMIN"; customer_id: string | null };
export type Review = { review_id:string; ticket_id:string; workflow_id:string; issue_category:string; review_status:string; eligibility_status:string; created_at:string; resume_state:string };
export type Detail = Review & { ticket_message:string; assessment:{assessment_status:string; reasons:string[]; missing_information:string[]; policy_references:{policy_id:string;policy_version:string;source:string;section_heading:string;effective_date:string|null}[]; proposed_refundable_amount_minor:number|null}; decision:string|null; decision_reason:string|null; investigation_status:string|null; workflow_status:string|null; audit_events:string[]; version:number };
export async function login(email:string,password:string) { const headers = await csrf(); return request<User>("/v1/auth/login", {method:"POST",headers:{"Content-Type":"application/json",...headers},body:JSON.stringify({email,password})}); }
export const me = () => request<User>("/v1/auth/me");
export async function logout() { const headers = await csrf(); return request<void>("/v1/auth/logout",{method:"POST",headers}); }
export const reviews = (status?:string) => request<{reviews:Review[]}>(`/v1/admin/reviews${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const review = (id:string) => request<Detail>(`/v1/admin/reviews/${encodeURIComponent(id)}`);
export async function decide(id:string, decision:string, reason:string|undefined, version:number) { const headers=await csrf(); return request<Detail>(`/v1/admin/reviews/${encodeURIComponent(id)}/decision`,{method:"POST",headers:{"Content-Type":"application/json",...headers},body:JSON.stringify({decision,reason,version})}); }
