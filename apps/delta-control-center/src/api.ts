export interface Health { status: string; service: string; version: string }
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = sessionStorage.getItem('delta-token');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, {...init, headers});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.message || body.error_code || `HTTP ${response.status}`);
  }
  return response.json();
}
export const getHealth = () => request<Health>('/core/health');

export interface Device {
  id: string; device_uid: string; display_name: string; hostname: string;
  os: string; architecture: string; username: string; agent_version: string;
  capabilities: string[]; status: 'online'|'offline'; last_seen: string;
  recent_commands?: ActivityEvent[];
}
export interface ActivityEvent {id: string; event_type: string; message: string; created_at: string; details: Record<string, unknown>}
export interface CommandResult {success: boolean; message: string; data?: Record<string, unknown>; error_code?: string}
export const getDevices = () => request<Device[]>('/core/api/v1/devices');
export const getDevice = (id: string) => request<Device>(`/core/api/v1/devices/${encodeURIComponent(id)}`);
export const sendCommand = (id: string, action: string, payload = {}) => request<CommandResult>(`/core/api/v1/devices/${encodeURIComponent(id)}/commands`, {method:'POST', body:JSON.stringify({action,payload})});

export interface Task {id:string;title:string;description:string;workspace_id:string|null;status:'todo'|'in_progress'|'done';priority:'low'|'medium'|'high';due_date:string|null;completed_at:string|null}
export interface TaskInput {title:string;description?:string;workspace_id?:string|null;status?:Task['status'];priority?:Task['priority'];due_date?:string|null}
export const getTasks=(filters:Record<string,string>={})=>request<Task[]>('/tasks-api/api/v1/tasks?'+new URLSearchParams(Object.entries(filters).filter(([,v])=>v)));
export const createTask=(body:TaskInput)=>request<Task>('/tasks-api/api/v1/tasks',{method:'POST',body:JSON.stringify(body)});
export const updateTask=(id:string,body:Partial<TaskInput>)=>request<Task>('/tasks-api/api/v1/tasks/'+id,{method:'PATCH',body:JSON.stringify(body)});
export const deleteTask=(id:string)=>request<{success:boolean}>('/tasks-api/api/v1/tasks/'+id,{method:'DELETE'});
export interface Service {service_id:string;name:string;version:string|null;base_url:string;status:string;enabled:boolean;last_health_check:string|null;available_tools:{name:string;description:string}[]}
export const getServices=()=>request<Service[]>('/core/api/v1/services');

export interface Binding {id:string;workspace_id:string;device_id:string;local_path:string;apps:string[];urls:string[]}
export interface Workspace {id:string;name:string;description:string;bindings?:Binding[]}
export const getWorkspaces=()=>request<Workspace[]>('/core/api/v1/workspaces');
export const saveWorkspace=(body:{name:string;description:string},id?:string)=>request<Workspace>('/core/api/v1/workspaces'+(id?'/'+id:''),{method:id?'PATCH':'POST',body:JSON.stringify(body)});
export const deleteWorkspace=(id:string)=>request<{success:boolean}>('/core/api/v1/workspaces/'+id,{method:'DELETE'});
export const saveBinding=(id:string,body:{device_id:string;local_path:string;apps:string[];urls:string[]})=>request<Binding>(`/core/api/v1/workspaces/${id}/bindings`,{method:'POST',body:JSON.stringify(body)});
export const launchWorkspace=(id:string,device_id:string)=>request<CommandResult&{results:CommandResult[]}>(`/core/api/v1/workspaces/${id}/launch`,{method:'POST',body:JSON.stringify({device_id})});

export interface AssistantResponse {id:string;assistant_text:string;tool_calls:{name:string;arguments:Record<string,unknown>}[];tool_results:{tool:string;success:boolean;message:string;data:unknown;duration_ms:number;service_id:string}[];transcript?:string;audio_available?:boolean;audio_base64?:string;tts_error?:string}
export interface Interaction extends AssistantResponse {user_message:string;created_at:string}
export const getHistory=()=>request<Interaction[]>('/core/api/v1/assistant/history');
export const sendMessage=(message:string,device_id?:string)=>request<AssistantResponse>('/core/api/v1/assistant/message',{method:'POST',body:JSON.stringify({message,device_id:device_id||null})});
