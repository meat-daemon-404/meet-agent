import type { Artifact, EnvironmentReport, JoinSessionPayload, MeetingSession } from './types';

async function jsonReq<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getEnvironment: () => jsonReq<EnvironmentReport>('/api/environment'),
  getActiveSession: () => jsonReq<{ active: boolean; session: MeetingSession | null }>('/api/session'),
  joinSession: (payload: JoinSessionPayload) =>
    jsonReq<MeetingSession>('/api/session/join', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  leaveSession: (reason = '用户在工作台结束参会') =>
    jsonReq<{ ok: boolean; session: MeetingSession | null }>('/api/session/leave', {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  pauseSession: () => jsonReq<{ ok: boolean }>('/api/session/pause', { method: 'POST' }),
  resumeSession: () => jsonReq<{ ok: boolean }>('/api/session/resume', { method: 'POST' }),
  injectInput: (kind: 'audio' | 'chat', speaker: string, text: string) =>
    jsonReq<{ ok: boolean }>('/api/session/input', {
      method: 'POST',
      body: JSON.stringify({ kind, speaker, text }),
    }),
  simulatorNext: () => jsonReq<{ ok: boolean }>('/api/session/simulator/next', { method: 'POST' }),
  sendChat: (text: string) =>
    jsonReq('/api/session/chat', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  speak: (text: string) =>
    jsonReq<{ ok: boolean }>('/api/session/speak', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  promoteIdea: (ideaId: string, decidedBy = '参会人复核') =>
    jsonReq<{ ok: boolean }>(`/api/session/ideas/${ideaId}/promote`, {
      method: 'POST',
      body: JSON.stringify({ decided_by: decidedBy }),
    }),
  updateAction: (actionId: string, patch: { owner?: string; due_date?: string; completed?: boolean }) =>
    jsonReq<{ ok: boolean }>(`/api/session/actions/${actionId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  upsertArtifact: (payload: {
    artifact_id?: string;
    kind: 'doc' | 'whiteboard';
    title: string;
    content: string;
    mermaid?: string | null;
    updated_by?: string;
  }) =>
    jsonReq<Artifact>('/api/session/artifacts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  resolvePermission: (permissionId: string, approved: boolean) =>
    jsonReq(`/api/session/permissions/${permissionId}`, {
      method: 'POST',
      body: JSON.stringify({ approved }),
    }),
  exportMarkdown: async (sessionId: string): Promise<string> => {
    const res = await fetch(`/api/sessions/${sessionId}/export`);
    if (!res.ok) throw new Error(`Export failed (${res.status})`);
    return res.text();
  },
};
