import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ProjectListItem {
  id: number;
  conversation_id: string | null;
  title: string;
  source_url: string;
  source_platform: string;
  workflow_type: "analysis" | "create" | "remake";
  source_type: "url" | "upload";
  source_name: string;
  status: string;
  media_url: string | null;
  objective: string;
  summary: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends ProjectListItem {
  script_overview: {
    full_text: string;
    dialogue_text: string;
    narration_text: string;
    caption_text: string;
  };
  ecommerce_analysis: {
    title: string;
    content: string | null;
  };
  source_analysis: any;
  conversation_messages: Array<{
    id: string;
    role: string;
    message_type: string;
    content: string;
    content_json: Record<string, unknown> | null;
    reply_to_message_id: string | null;
    created_at: string;
    _thinking?: boolean;
  }>;
  timeline_segments: Array<{
    id: number;
    segment_type: string;
    speaker: string | null;
    start_ms: number;
    end_ms: number;
    content: string;
  }>;
  video_generation: any;
  task_steps: any[];
}

export const useChatStore = defineStore('chat', () => {
  const projects = ref<ProjectListItem[]>([])
  const selectedProject = ref<ProjectDetail | null>(null)
  const loadingHistory = ref(false)

  return {
    projects,
    selectedProject,
    loadingHistory
  }
})
