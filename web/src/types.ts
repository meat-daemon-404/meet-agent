export interface DiscoveredAgent {
  id: string;
  name: string;
  protocol: 'agy-stream' | 'acp' | 'cli' | 'demo';
  command: string;
  args: string[];
  available: boolean;
  resolved_path: string | null;
  description: string;
  supports_workspace: boolean;
  supports_permission_callback: boolean;
}

export interface EnvironmentReport {
  platform: string;
  tencent_meeting_installed: boolean;
  tencent_meeting_path: string | null;
  tencent_meeting_running: boolean;
  mumu_installed: boolean;
  mumu_manager_path: string | null;
  mumu_adb_path: string | null;
  audio_input_devices: string[];
  audio_loopback_devices: string[];
  audio_output_devices: string[];
  has_virtual_audio_cable: boolean;
  has_virtual_camera: boolean;
  virtual_camera_backend: string | null;
  discovered_agents: DiscoveredAgent[];
  warnings: string[];
}

export interface TranscriptSegment {
  id: string;
  speaker: string;
  text: string;
  timestamp: string;
  source: 'audio' | 'chat' | 'simulator' | 'manual';
  confidence: number;
}

export interface ChatMessage {
  id: string;
  sender: string;
  text: string;
  timestamp: string;
  direction: 'inbound' | 'outbound';
}

export interface IdeaItem {
  id: string;
  content: string;
  proposer: string;
  status: 'exploring' | 'parked' | 'adopted' | 'needs_confirmation';
  evidence_quote: string;
  evidence_ts: string;
  downgraded_reason: string | null;
}

export interface OpenQuestion {
  id: string;
  question: string;
  raised_by: string;
  blockers: string;
  resolved: boolean;
  resolution: string | null;
  timestamp: string;
}

export interface DecisionItem {
  id: string;
  summary: string;
  decided_by: string;
  evidence_quote: string;
  evidence_ts: string;
  confidence: number;
  confirmed_by_human: boolean;
}

export interface ActionItem {
  id: string;
  task: string;
  owner: string;
  due_date: string | null;
  evidence_quote: string;
  needs_owner: boolean;
  completed: boolean;
  timestamp: string;
}

export interface MemoryGraph {
  ideas: IdeaItem[];
  open_questions: OpenQuestion[];
  decisions: DecisionItem[];
  action_items: ActionItem[];
}

export interface Artifact {
  id: string;
  kind: 'doc' | 'whiteboard';
  title: string;
  content: string;
  mermaid: string | null;
  sticky_notes: Array<{ group: string; text: string; color?: string }>;
  version: number;
  updated_at: string;
  updated_by: string;
}

export interface AgentTraceEvent {
  id: string;
  timestamp: string;
  brain_id: string;
  kind: 'init' | 'thought' | 'tool_call' | 'tool_result' | 'text_delta' | 'result' | 'error' | 'system';
  title: string;
  content: string;
  metadata: Record<string, unknown>;
}

export interface PermissionRequest {
  id: string;
  timestamp: string;
  brain_id: string;
  tool_name: string;
  summary: string;
  parameters: Record<string, unknown>;
  status: 'pending' | 'approved' | 'denied';
  decided_at: string | null;
}

export interface MeetingSession {
  id: string;
  meeting_code: string;
  meeting_title: string;
  display_name: string;
  adapter_name: string;
  brain_id: string;
  workspace_dir: string;
  status: 'idle' | 'joining' | 'in_meeting' | 'paused' | 'leaving' | 'ended' | 'error';
  visual_state:
    | 'idle'
    | 'listening'
    | 'thinking'
    | 'building_artifact'
    | 'speaking'
    | 'waiting_approval'
    | 'paused';
  status_subtitle: string;
  active_speaker: string | null;
  started_at: string;
  ended_at: string | null;
  conversation_id: string | null;
  transcript: TranscriptSegment[];
  chat_history: ChatMessage[];
  memory: MemoryGraph;
  artifacts: Artifact[];
  agent_traces: AgentTraceEvent[];
  permissions: PermissionRequest[];
  enable_tts: boolean;
  enable_virtual_cam: boolean;
}

export interface JoinSessionPayload {
  meeting_code: string;
  meeting_title: string;
  password?: string | null;
  display_name: string;
  adapter: 'tencent-desktop' | 'mumu-android' | 'simulator' | 'voov-web';
  brain: string;
  workspace_dir?: string | null;
  enable_virtual_cam: boolean;
  enable_tts: boolean;
  send_join_notice: boolean;
}
