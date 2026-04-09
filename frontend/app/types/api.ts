export interface ApiResponse<T> {
  code: number;
  router: string;
  params?: Record<string, unknown>;
  data: T;
}

export interface ApiErrorResponse {
  code: number;
  message: string;
  time?: string;
  router?: string;
  params?: Record<string, unknown>;
  details?: unknown;
}

export interface AuthPermission {
  id: string;
  code: string;
  name: string;
  group_name: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuthRole {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_system: boolean;
  created_at: string;
  updated_at: string;
  permissions?: AuthPermission[];
}

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  display_name: string;
  avatar_url?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  last_login_at?: string | null;
  created_at: string;
  updated_at: string;
  roles: AuthRole[];
  permissions: AuthPermission[];
}

export interface AuthSessionPayload {
  token_type: "Cookie";
  csrf_token: string;
  access_token_expires_in: number;
  refresh_token_expires_in: number;
  user: AuthUser;
}

export interface TikTokVideoInfo {
  aweme_id: string;
  desc?: string | null;
  create_time?: number | null;
  duration_ms?: number | null;
  width?: number | null;
  height?: number | null;
  ratio?: string | null;
  cover_url?: string | null;
  download_url: string;
}

export interface TikTokBasicInfo {
  author: string;
  author_nickname?: string | null;
  author_uid?: string | null;
  music_title?: string | null;
  music_author?: string | null;
  statistics: {
    play_count?: number | null;
    digg_count?: number | null;
    comment_count?: number | null;
    share_count?: number | null;
    collect_count?: number | null;
  };
}

export interface TikTokInfoPayload {
  input: string;
  aweme_id: string;
  download_url: string;
  video_info: TikTokVideoInfo;
  tiktok_basic_info: TikTokBasicInfo;
}

export type JobType =
  | "video_analysis"
  | "video_remake"
  | "motion_extraction"
  | "scene_segmentation"
  | "tag_generation";

export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface Job {
  id: string;
  job_type: JobType;
  status: JobStatus;
  progress: number;
  input_asset_id: string | null;
  output_asset_id?: string | null;
  error_message?: string | null;
  result_json?: Record<string, any> | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface MediaAsset {
  id: string;
  asset_type: "video" | "image" | "audio" | "subtitle" | "preview";
  source_type: "upload" | "generated" | "derived" | "extracted";
  file_name: string;
  file_path: string;
  mime_type: string | null;
  size_bytes: number | null;
  duration_ms?: number | null;
  width?: number | null;
  height?: number | null;
  thumbnail_path?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SystemSettingsProxyConfig {
  enabled: boolean;
  http_url: string;
  https_url: string;
  all_url: string;
  no_proxy: string;
}

export interface SystemSettingsProviderConfig {
  provider: string;
  label: string;
  enabled: boolean;
  base_url: string;
  api_key: string;
  default_model: string;
  model_options: string[];
  model_dir: string;
  device: string;
  compute_type: string;
  language: string;
  prompt: string;
  beam_size: number;
  vad_filter: boolean;
}

export interface SystemSettingsProviderGroup {
  default_provider: string;
  providers: SystemSettingsProviderConfig[];
}

export interface SystemSettingsInfoConfig {
  name: string;
  description: string;
  logo_url: string;
}

export interface SystemSettingsPayload {
  system: SystemSettingsInfoConfig;
  proxy: SystemSettingsProxyConfig;
  analysis: SystemSettingsProviderGroup;
  transcription: SystemSettingsProviderGroup;
  remake: SystemSettingsProviderGroup;
}

export interface TranscriptionDependencyStatus {
  installed: boolean;
  version: string;
}

export interface FasterWhisperLocalModel {
  name: string;
  path: string;
}

export interface FasterWhisperCapabilities {
  provider: "faster_whisper";
  available: boolean;
  issues: string[];
  dependency_status: Record<string, TranscriptionDependencyStatus>;
  binary_status: Record<string, boolean>;
  model_dir: string;
  local_models: FasterWhisperLocalModel[];
  available_devices: string[];
  available_compute_types: string[];
  recommended_device: string;
  cuda_device_count: number;
}

export interface OpenAIWhisperCapabilities {
  provider: "openai_whisper_api";
  available: boolean;
  issues: string[];
  supported_models: string[];
  base_url: string;
  file_size_limit_mb: number;
  supported_formats: string[];
}

export interface TranscriptionCapabilitiesPayload {
  default_provider: string;
  providers: {
    faster_whisper: FasterWhisperCapabilities;
    openai_whisper_api: OpenAIWhisperCapabilities;
  };
}
