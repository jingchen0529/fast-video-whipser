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


export interface AuthMenu {
  id: string;
  parent_id: string | null;
  code: string;
  title: string;
  menu_type: "directory" | "menu" | "link";
  route_path: string;
  route_name?: string | null;
  redirect_path?: string | null;
  icon?: string | null;
  component_key?: string | null;

  sort_order: number;
  is_visible: boolean;
  is_enabled: boolean;
  is_external: boolean;
  open_mode: "self" | "blank";
  is_cacheable: boolean;
  is_affix: boolean;
  active_menu_path?: string | null;
  badge_text?: string | null;
  badge_type?: string | null;
  remark?: string | null;
  meta_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  children?: AuthMenu[];
}

export interface AuthRole {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_system: boolean;
  created_at: string;
  updated_at: string;

  menus?: AuthMenu[];
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

export interface MotionAsset {
  id: string;
  source_video_asset_id: string | null;
  clip_asset_id: string | null;
  thumbnail_asset_id?: string | null;
  project_id: number | null;
  job_id: string | null;
  start_ms: number;
  end_ms: number;
  thumbnail_path?: string | null;
  action_summary: string;
  action_label: string | null;
  entrance_style: string | null;
  emotion_label: string | null;
  temperament_label: string | null;
  scene_label: string | null;
  camera_motion: string | null;
  camera_shot: string | null;
  confidence?: number | null;
  asset_candidate?: boolean;
  origin: string;
  review_status: string;
  copyright_risk_level: string;
  metadata_json: Record<string, any> | null;
  source_video_asset?: {
    id: string;
    asset_type: string | null;
    source_type: string | null;
    file_name: string | null;
    thumbnail_path: string | null;
    metadata_json: Record<string, any> | null;
  } | null;
  clip_asset?: {
    id: string;
    asset_type: string | null;
    source_type: string | null;
    file_name: string | null;
    thumbnail_path: string | null;
    metadata_json: Record<string, any> | null;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface MotionAssetListPayload {
  items: MotionAsset[];
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

export interface MotionExtractionSettings {
  coarse_filter_mode: "keyword" | "permissive";
  min_duration_ms: number;
  max_duration_ms: number;
  signal_score_threshold: number;
  confidence_threshold: number;
  default_provider: string;
  providers: SystemSettingsProviderConfig[];
}

export interface SystemSettingsPayload {
  system: SystemSettingsInfoConfig;
  proxy: SystemSettingsProxyConfig;
  analysis: SystemSettingsProviderGroup;
  transcription: SystemSettingsProviderGroup;
  remake: SystemSettingsProviderGroup;
  motion_extraction: MotionExtractionSettings;
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
  recommended_compute_type: string;
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
