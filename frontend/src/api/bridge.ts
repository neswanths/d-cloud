/**
 * D-Cloud API Bridge Client
 * All calls go through Vite's proxy → http://localhost:8000
 */

const BASE = '/api';

export interface AgentStatus {
    agent_id: string;
    node_id: string;
    url: string;
    status: 'online' | 'offline' | 'degraded';
    chunks_held: number;
}

export interface UploadResponse {
    manifest_hash: string;
    file_hash: string;
    root_hash: string;
    name: string;
    size: number;
    mime_type: string;
    total_chunks: number;
    redundancy_factor: number;
    recipient_pubkey: string;
    dek_algorithm: string;
}

export interface FileEntry {
    action_hash: string;
    name: string;
    size: number;
    mime_type: string;
    file_hash: string;
    root_hash: string;
    total_chunks: number;
    redundancy_factor: number;
    uploader_pubkey: string;
    recipient_pubkey: string;
    dek_algorithm: string;
}

export interface HealthResponse {
    status: string;
    bridge_pubkey_hex: string;
    recipient_pubkey_hex: string;
    connected_conductors: number;
    version: string;
}

async function get<T>(path: string): Promise<T> {
    const res = await fetch(BASE + path);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(BASE + path, {
        method: 'POST',
        headers: body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
        body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

// ── Health ──────────────────────────────────────────────────────────────────

export const getHealth = () => get<HealthResponse>('/health');

// ── Agents ──────────────────────────────────────────────────────────────────

export const getAgentStatus = () => get<AgentStatus[]>('/agents/status');
export const killAgent = (agentId: string) => post<{ status: string; agent_id: string }>(`/agents/${agentId}/kill`);
export const restartAgent = (agentId: string) => post<{ status: string; agent_id: string }>(`/agents/${agentId}/restart`);

// ── Files ───────────────────────────────────────────────────────────────────

export async function uploadFile(file: File): Promise<UploadResponse> {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${BASE}/upload`, { method: 'POST', body: fd });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

export const listFiles = () => get<FileEntry[]>('/files');

export async function downloadFile(manifestHash: string): Promise<{ blob: Blob; filename: string; fileHash: string }> {
    const res = await fetch(`${BASE}/file/${manifestHash}`);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    const filenameMatch = cd.match(/filename="?([^"]+)"?/);
    const filename = filenameMatch?.[1] ?? 'download';
    const fileHash = res.headers.get('X-File-Hash') ?? '';
    return { blob, filename, fileHash };
}
