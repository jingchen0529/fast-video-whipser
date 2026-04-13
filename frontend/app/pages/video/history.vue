<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import {
  Send,
  Upload,
  Bot,
  UserRound,
  Clapperboard,
  Play,
} from "lucide-vue-next";
import { marked } from "marked";
import { toast } from "vue-sonner";

import VideoDrawer from "~/components/custom/VideoDrawer.vue";
import GenerationDrawer from "~/components/custom/GenerationDrawer.vue";
import TaskTimeline from "~/components/custom/TaskTimeline.vue";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";

definePageMeta({
  layout: "console",
  middleware: "auth",
  ssr: false,
});

// Configure marked for safe rendering
marked.setOptions({ breaks: true, gfm: true });

const apiService = useApi();
const api = apiService.requestData;
const runtimeConfig = useRuntimeConfig();
const chatStore = useChatStore();
const route = useRoute();

const inputText = ref("");
const sending = ref(false);
const errorMessage = ref("");
const selectedFile = ref<File | null>(null);
const showVideoDetail = ref(false);
const showGenerationDetail = ref(false);
const filePreviewUrl = ref<string | null>(null);
const uploadProgress = ref(100);
let simulateTimer: any = null;

watch(selectedFile, (newFile) => {
  if (filePreviewUrl.value) {
    URL.revokeObjectURL(filePreviewUrl.value);
    filePreviewUrl.value = null;
  }
  if (simulateTimer) clearInterval(simulateTimer);

  if (newFile) {
    if (newFile.type.startsWith("image/") || newFile.type.startsWith("video/")) {
      filePreviewUrl.value = URL.createObjectURL(newFile);
    }
    
    // Simulate upload for UX effect
    uploadProgress.value = 0;
    simulateTimer = setInterval(() => {
      uploadProgress.value += Math.floor(Math.random() * 15) + 8;
      if (uploadProgress.value >= 100) {
        uploadProgress.value = 100;
        clearInterval(simulateTimer);
        toast.success("附件已经准备就绪！");
      }
    }, 150);
  } else {
    uploadProgress.value = 100;
  }
});

const project = computed(() => chatStore.selectedProject);
const messages = computed(() => project.value?.conversation_messages || []);
const videoGeneration = computed(() => project.value?.video_generation || null);
const normalizedVideoGenerationStatus = computed(() =>
  String(videoGeneration.value?.status || "")
    .trim()
    .toLowerCase(),
);
const pageTitle = computed(() => {
  if (project.value?.workflow_type === "remake") return "视频复刻详情";
  if (project.value?.workflow_type === "create") return "爆款创作详情";
  return "视频分析详情";
});

useHead(() => ({ title: pageTitle.value }));

const isWorkflowReplyType = (type: string) =>
  type === "analysis_reply" || type === "suggestion_reply";

const renderMarkdown = (content: string) => {
  try {
    return marked.parse(content) as string;
  } catch {
    return content;
  }
};

const generatedVideoUrl = computed(() => {
  const preferred =
    videoGeneration.value?.asset_url ||
    videoGeneration.value?.result_video_url ||
    (project.value?.workflow_type === "analysis" ? project.value?.media_url : null);
  return resolveAssetUrl(preferred);
});

const shouldShowVideoGenerationCard = computed(
  () =>
    !!project.value &&
    project.value.workflow_type !== "analysis" &&
    !!normalizedVideoGenerationStatus.value &&
    normalizedVideoGenerationStatus.value !== "idle",
);

const generationStatusLabel = computed(() => {
  if (normalizedVideoGenerationStatus.value === "succeeded") return "已生成";
  if (normalizedVideoGenerationStatus.value === "failed") return "生成失败";
  return "生成中";
});

const generationPromptPreview = computed(() => {
  const prompt = String(videoGeneration.value?.prompt || "").trim();
  if (!prompt) return "";
  return prompt.length > 220 ? `${prompt.slice(0, 220)}...` : prompt;
});

const visibleMessages = computed(() => {
  const workflowAssistantTypes = new Set([
    "analysis_reply",
    "suggestion_reply",
    "remake_reply",
    "create_reply",
    "video_generation_result",
  ]);
  const rawMessages = messages.value.filter(
    (message) => message.message_type !== "workflow_status" && message.message_type !== "workflow_error",
  );
  const mergedMessages: any[] = [];

  rawMessages.forEach((message) => {
    const lastMessage = mergedMessages[mergedMessages.length - 1];
    const shouldMergeIntoWorkflowReply =
      message.role === "assistant" &&
      workflowAssistantTypes.has(message.message_type) &&
      lastMessage?.role === "assistant" &&
      workflowAssistantTypes.has(lastMessage.message_type);

    if (shouldMergeIntoWorkflowReply) {
      lastMessage.content = [lastMessage.content, message.content]
        .filter(Boolean)
        .join("\n\n");
      lastMessage.created_at = message.created_at;
      lastMessage.id = `${lastMessage.id}-${message.id}`;
      return;
    }

    mergedMessages.push({
      ...message,
      message_type:
        message.role === "assistant" &&
        workflowAssistantTypes.has(message.message_type)
          ? "analysis_reply"
          : message.message_type,
    });
  });

  return mergedMessages;
});

const scrollContainerRef = ref<HTMLElement | null>(null);
const textareaRef = ref<HTMLTextAreaElement | null>(null);

const scrollToBottom = () => {
  nextTick(() => {
    const el = scrollContainerRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
};

const adjustTextareaHeight = () => {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
};

watch(inputText, () => nextTick(adjustTextareaHeight));
watch(visibleMessages, () => scrollToBottom(), { deep: true });

const isTerminal = (status?: string | null) =>
  ["succeeded", "failed", "ready"].includes(
    (status || "").trim().toLowerCase(),
  );

const canSend = computed(
  () =>
    project.value &&
    isTerminal(project.value.status) &&
    (inputText.value.trim() || selectedFile.value),
);

let pollingTimer: ReturnType<typeof setInterval> | null = null;

const stopPolling = () => {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
};

const startPolling = (projectId: number) => {
  stopPolling();
  pollingTimer = setInterval(async () => {
    try {
      const data = await api<any>(`/projects/${projectId}`);
      chatStore.selectedProject = data;
      if (isTerminal(data.status)) {
        stopPolling();
        chatStore.projects = await api<any[]>("/projects");
      }
    } catch {
      stopPolling();
    }
  }, 2000);
};

const loadProject = async (id: number) => {
  try {
    const data = await api<any>(`/projects/${id}`);
    chatStore.selectedProject = data;
    if (!isTerminal(data.status)) startPolling(id);
    scrollToBottom();
  } catch (error) {
    errorMessage.value = apiService.normalizeError(error);
  }
};

const handleSend = async () => {
  if (!canSend.value || !project.value) return;

  const content = inputText.value.trim();
  if (!content) return;

  sending.value = true;
  errorMessage.value = "";
  inputText.value = "";

  // Optimistic user message
  if (!project.value.conversation_messages) {
    project.value.conversation_messages = [];
  }
  project.value.conversation_messages.push({
    id: "temp-" + Date.now(),
    role: "user",
    message_type: "chat_question",
    content,
    created_at: new Date().toISOString(),
    content_json: null,
    reply_to_message_id: null,
  });

  // Immediately show AI "thinking" placeholder
  const aiPlaceholderId = "ai-thinking-" + Date.now();
  project.value.conversation_messages.push({
    id: aiPlaceholderId,
    role: "assistant",
    message_type: "chat_reply",
    content: "",
    created_at: new Date().toISOString(),
    content_json: null,
    reply_to_message_id: null,
    _thinking: true,
  });
  scrollToBottom();

  try {
    const res = await api<any>(`/projects/${project.value.id}/messages`, {
      method: "POST",
      body: { content },
    });
    // Replace the thinking placeholder with real response
    const msgs = project.value.conversation_messages;
    const placeholderIndex = msgs.findIndex((m: any) => m.id === aiPlaceholderId);
    if (placeholderIndex !== -1) {
      msgs[placeholderIndex] = {
        id: res.id,
        role: res.role || "assistant",
        message_type: "chat_reply",
        content: res.content,
        created_at: res.created_at,
        content_json: null,
        reply_to_message_id: null,
      };
    } else {
      msgs.push({
        id: res.id,
        role: res.role || "assistant",
        message_type: "chat_reply",
        content: res.content,
        created_at: res.created_at,
        content_json: null,
        reply_to_message_id: null,
      });
    }
    scrollToBottom();
  } catch (error) {
    // Replace thinking placeholder with error message
    const msgs = project.value.conversation_messages;
    const placeholderIndex = msgs.findIndex((m: any) => m.id === aiPlaceholderId);
    if (placeholderIndex !== -1) {
      msgs.splice(placeholderIndex, 1);
    }
    errorMessage.value = apiService.normalizeError(error);
  } finally {
    sending.value = false;
  }
};

const handleUploadClick = () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "video/*,image/*,audio/*,.pdf,.doc,.docx,.txt";
  input.onchange = (e) => {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (file) selectedFile.value = file;
  };
  input.click();
};

const resolveAssetUrl = (value?: string | null): string | null => {
  const normalized = (value || "").trim();
  if (!normalized) return null;
  if (/^(https?:|data:|blob:)/i.test(normalized)) return normalized;
  const apiBase = (runtimeConfig.public.apiBase || "").trim();
  let origin = "";
  if (import.meta.client) {
    try {
      origin = apiBase
        ? new URL(apiBase, window.location.origin).origin
        : window.location.origin;
    } catch {
      origin = window.location.origin;
    }
  }
  if (!origin) {
    return normalized.startsWith("/") ? normalized : `/${normalized}`;
  }
  try {
    return new URL(normalized, `${origin}/`).toString();
  } catch {
    return normalized.startsWith("/") ? normalized : `/${normalized}`;
  }
};

const getMessageTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    project_request: "用户需求",
    workflow_status: "流程更新",
    analysis_reply: "处理结果",
    suggestion_reply: "处理结果",
    workflow_error: "执行异常",
    chat_question: "追问",
    chat_reply: "回复",
  };
  return labels[type] || type;
};

const getVideoName = (url?: string) => {
  if (!url) return "video.mp4";
  try {
    const base = url.split("?")[0];
    const parts = base ? base.split("/") : [];
    return parts[parts.length - 1] || "video.mp4";
  } catch {
    return "video.mp4";
  }
};

const loadData = async () => {
  const id = Number(route.query.id);
  if (!id) return;
  await loadProject(id);
};

onMounted(() => loadData());
watch(() => route.query.id, () => loadData());

onUnmounted(() => {
  stopPolling();
  if (filePreviewUrl.value) {
    URL.revokeObjectURL(filePreviewUrl.value);
  }
});

const glowRef = ref<HTMLElement | null>(null);
const glowStartAngle = ref(0);
const isHovering = ref(false);

const handleMouseMove = (e: MouseEvent) => {
  if (!glowRef.value) return;
  const rect = glowRef.value.getBoundingClientRect();
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  const angle =
    Math.atan2(e.clientY - centerY, e.clientX - centerX) * (180 / Math.PI);
  glowStartAngle.value = angle + 90;
};
</script>

<template>
  <div
    class="relative flex h-[calc(100vh-3.5rem)] w-full flex-col bg-[#fcfcfc] dark:bg-[#121212] overflow-hidden"
  >
    <!-- Layout Header Portals -->
    <ClientOnly>
      <Teleport to="#header-portal" v-if="project">
        <div class="flex items-center gap-2 overflow-hidden mx-2 min-w-0">
          <TooltipProvider :delay-duration="300">
            <Tooltip>
              <TooltipTrigger as-child>
                <h1 class="text-sm font-bold truncate cursor-help">
                  {{ project.title || "未命名对话" }}
                </h1>
              </TooltipTrigger>
              <TooltipContent
                class="bg-zinc-900 text-white border-zinc-800 px-3 py-1.5 text-xs rounded-lg"
              >
                <p>{{ project.title || "未命名对话" }}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <span
            class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold"
            :class="
              isTerminal(project.status)
                ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400'
                : 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400'
            "
          >
            {{ isTerminal(project.status) ? "已完成" : "执行中..." }}
          </span>
        </div>
      </Teleport>

      <Teleport to="#header-actions" v-if="project">
        <button
          v-if="project.media_url"
          @click="showVideoDetail = true"
          class="shrink-0 rounded-full bg-zinc-100 px-3 py-1.5 text-xs font-medium hover:bg-zinc-200 transition-colors dark:bg-zinc-800 dark:hover:bg-zinc-700 mr-2"
        >
          查看视频
        </button>
      </Teleport>
    </ClientOnly>

    <!-- Messages -->
    <div
      ref="scrollContainerRef"
      class="flex-1 overflow-y-auto px-2 pt-8 pb-[160px] custom-scrollbar relative"
    >
      <div v-if="!project" class="h-full flex items-center justify-center">
        <p class="text-sm text-zinc-400">加载中...</p>
      </div>

      <div v-else class="mx-auto max-w-4xl space-y-4">
        <template v-for="(message, index) in visibleMessages" :key="message.id">
          <div
            class="flex"
            :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
          >
            <div
              class="flex max-w-[88%] items-start gap-3"
              :class="message.role === 'user' ? 'flex-row-reverse' : ''"
            >
              <div
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border shadow-sm"
                :class="
                  message.role === 'user'
                    ? 'border-zinc-900 bg-zinc-900 text-white dark:border-white dark:bg-white dark:text-zinc-900'
                    : 'border-zinc-200 bg-white text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100'
                "
              >
                <UserRound v-if="message.role === 'user'" class="h-4 w-4" />
                <Bot v-else class="h-4 w-4" />
              </div>

              <div
                class="py-3"
                :class="
                  message.role === 'user'
                    ? 'rounded-2xl px-4 shadow-sm bg-[#f5f5f5] text-zinc-900 dark:bg-[#1f1f1f] dark:text-zinc-100 border border-transparent dark:border-zinc-800'
                    : 'text-zinc-900 dark:text-zinc-100 px-1'
                "
              >
                <!-- Thinking animation -->
                <div v-if="message._thinking" class="flex items-center gap-1.5 py-1">
                  <span class="thinking-dot size-2 rounded-full bg-zinc-400 dark:bg-zinc-500" style="animation-delay: 0ms" />
                  <span class="thinking-dot size-2 rounded-full bg-zinc-400 dark:bg-zinc-500" style="animation-delay: 150ms" />
                  <span class="thinking-dot size-2 rounded-full bg-zinc-400 dark:bg-zinc-500" style="animation-delay: 300ms" />
                </div>
                <div v-else class="text-[14px] leading-relaxed markdown-body" v-html="renderMarkdown(message.content)">
                </div>

                <!-- Media Card (Only for first user message) -->
                <div
                  v-if="
                    index === 0 && message.role === 'user' && project.media_url
                  "
                  class="mt-4 flex justify-start"
                >
                  <div
                    @click="showVideoDetail = true"
                    class="flex flex-col items-center justify-center w-24 gap-2 cursor-pointer group"
                  >
                    <div
                      class="w-full aspect-square bg-[#1a1c21] rounded-2xl flex items-center justify-center relative shadow-sm border border-zinc-800 group-hover:border-zinc-600 transition-colors"
                    >
                      <div class="absolute top-2 right-2">
                        <Clapperboard class="size-3.5 text-zinc-400" />
                      </div>
                      <div
                        class="w-10 h-10 bg-zinc-100 hover:scale-105 transition-transform rounded-full flex items-center justify-center shadow-md"
                      >
                        <Play
                          class="size-4 text-zinc-900 ml-0.5"
                          fill="currentColor"
                        />
                      </div>
                    </div>
                    <TooltipProvider :delay-duration="300">
                      <Tooltip>
                        <TooltipTrigger as-child>
                          <span
                            class="text-xs text-zinc-400 font-medium truncate w-full text-center px-1 cursor-help"
                          >
                            {{ getVideoName(project.media_url) }}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent
                          class="bg-zinc-900 text-white border-zinc-800 px-3 py-1.5 text-xs rounded-lg"
                        >
                          <p>{{ getVideoName(project.media_url) }}</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Task Timeline -->
          <div
            v-if="index === 0 && project.task_steps?.length"
            class="flex justify-start my-1 w-full"
          >
            <div class="flex max-w-[88%] w-full items-end gap-3 pl-[52px]">
              <div class="w-full py-2">
                <TaskTimeline :tasks="project.task_steps" />
              </div>
            </div>
          </div>

          <div
            v-if="index === 0 && shouldShowVideoGenerationCard"
            class="flex justify-start my-1 w-full"
          >
            <div class="flex max-w-[88%] w-full items-end gap-3 pl-[52px]">
              <div
                class="w-full rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80"
              >
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p class="text-sm font-semibold text-zinc-900 dark:text-white">
                      视频生成结果
                    </p>
                    <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {{
                        normalizedVideoGenerationStatus === "succeeded"
                          ? "后端任务流已完成，结果已经写回动态资产。"
                          : normalizedVideoGenerationStatus === "failed"
                            ? "视频模型返回失败状态，请检查错误信息。"
                            : "后端正在轮询第三方视频模型任务状态。"
                      }}
                    </p>
                  </div>
                  <span
                    class="rounded-full px-2.5 py-1 text-[11px] font-semibold"
                    :class="
                      normalizedVideoGenerationStatus === 'succeeded'
                        ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400'
                        : normalizedVideoGenerationStatus === 'failed'
                          ? 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-400'
                          : 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400'
                    "
                  >
                    {{ generationStatusLabel }}
                  </span>
                </div>

                <div class="mt-3 flex flex-wrap gap-2 text-xs">
                  <span
                    v-if="videoGeneration?.provider"
                    class="rounded-full bg-zinc-100 px-2.5 py-1 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    Provider: {{ videoGeneration.provider }}
                  </span>
                  <span
                    v-if="videoGeneration?.model"
                    class="rounded-full bg-zinc-100 px-2.5 py-1 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    Model: {{ videoGeneration.model }}
                  </span>
                  <span
                    v-if="videoGeneration?.provider_task_id"
                    class="rounded-full bg-zinc-100 px-2.5 py-1 font-mono text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    Task: {{ videoGeneration.provider_task_id }}
                  </span>
                </div>

                <div
                  v-if="generatedVideoUrl"
                  class="mt-4 overflow-hidden rounded-2xl border border-zinc-200 bg-black dark:border-zinc-800"
                >
                  <video
                    :src="generatedVideoUrl"
                    controls
                    class="max-h-[360px] w-full bg-black object-contain"
                  ></video>
                </div>

                <div
                  v-if="normalizedVideoGenerationStatus === 'failed' && videoGeneration?.error_detail"
                  class="mt-4 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300"
                >
                  {{ videoGeneration.error_detail }}
                </div>



                <div class="mt-6 flex flex-wrap gap-2 pt-5 border-t border-zinc-100 dark:border-zinc-800">
                  <Button
                    @click="showGenerationDetail = true"
                    variant="default"
                    size="sm"
                    class="rounded-full shadow-sm"
                  >
                    查看完整复刻详情
                  </Button>
                  <Button
                    v-if="videoGeneration?.output_asset_id"
                    as-child
                    variant="outline"
                    size="sm"
                    class="rounded-full shadow-sm bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
                  >
                    <a href="/assets">
                      查看资产详情
                    </a>
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- Task Timeline Fallback (if no messages yet) -->
        <div
          v-if="visibleMessages.length === 0 && project.task_steps?.length"
          class="flex justify-start w-full"
        >
          <div class="flex max-w-[88%] w-full items-end gap-3 pl-[52px]">
            <div class="w-full py-2">
              <TaskTimeline :tasks="project.task_steps" />
            </div>
          </div>
        </div>

        <!-- Error -->
        <div
          v-if="errorMessage"
          class="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600 dark:bg-red-950/30 dark:border-red-900/40 dark:text-red-400"
        >
          {{ errorMessage }}
        </div>
      </div>
    </div>

    <!-- Input Area -->
    <div
      v-if="project"
      class="absolute bottom-0 left-0 right-0 p-4 px-2 bg-gradient-to-t from-[#fcfcfc] via-[#fcfcfc] dark:from-[#121212] dark:via-[#121212] to-transparent pt-16 pb-8 z-20 pointer-events-none"
    >
      <div class="mx-auto w-full max-w-4xl pointer-events-auto">
        <div
          ref="glowRef"
          @mousemove="handleMouseMove"
          @mouseenter="isHovering = true"
          @mouseleave="isHovering = false"
          class="group relative text-zinc-900 dark:text-zinc-100 rounded-3xl border border-zinc-200/80 dark:border-zinc-800 bg-white/70 dark:bg-zinc-900/70 p-3 shadow-lg backdrop-blur-xl transition-all focus-within:ring-2 focus-within:ring-blue-500/10"
        >
          <!-- Glowing Border Effect (Flowing style) -->
          <div
            class="pointer-events-none absolute inset-0 rounded-[inherit] transition-opacity duration-300"
            :class="isHovering ? 'opacity-100' : 'opacity-0'"
            :style="{
              '--blur': '0px',
              '--spread': '40',
              '--start': glowStartAngle,
              '--active': isHovering ? '1' : '0',
              '--glowingeffect-border-width': '2px',
              '--repeating-conic-gradient-times': '5',
              '--gradient':
                'radial-gradient(circle, #dd7bbb 10%, #dd7bbb00 20%), radial-gradient(circle at 40% 40%, #d79f1e 5%, #d79f1e00 15%), radial-gradient(circle at 60% 60%, #5a922c 10%, #5a922c00 20%), radial-gradient(circle at 40% 60%, #4c7894 10%, #4c789400 20%), repeating-conic-gradient(from 236.84deg at 50% 50%, #dd7bbb 0%, #d79f1e calc(25% / var(--repeating-conic-gradient-times)), #5a922c calc(50% / var(--repeating-conic-gradient-times)), #4c7894 calc(75% / var(--repeating-conic-gradient-times)), #dd7bbb calc(100% / var(--repeating-conic-gradient-times)))',
            }"
          >
            <div
              class="glow rounded-[inherit] after:content-[''] after:rounded-[inherit] after:absolute after:inset-[calc(-1*var(--glowingeffect-border-width))] after:[border:var(--glowingeffect-border-width)_solid_transparent] after:[background:var(--gradient)] after:[background-attachment:fixed] after:opacity-[var(--active)] after:transition-opacity after:duration-300 after:[mask-clip:padding-box,border-box] after:[mask-composite:intersect] after:[mask-image:linear-gradient(#0000,#0000),conic-gradient(from_calc((var(--start)-var(--spread))*1deg),#00000000_0deg,#fff,#00000000_calc(var(--spread)*2deg))]"
            ></div>
          </div>

          <form
            @submit.prevent="handleSend"
            class="relative z-10 w-full flex flex-col"
          >
            <!-- Attachments Preview -->
            <div v-if="selectedFile" class="mb-2 ml-2 flex flex-wrap gap-2">
              <!-- File Uploading State -->
              <div v-if="uploadProgress < 100" class="flex items-center gap-3 p-3 bg-zinc-50 border border-zinc-200 dark:bg-zinc-800/50 dark:border-zinc-700 rounded-2xl w-fit pr-8 shadow-sm">
                <div class="relative flex items-center justify-center w-10 h-10 rounded-full border border-zinc-200 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 overflow-hidden shrink-0">
                   <span class="text-[10px] font-bold text-zinc-600 dark:text-zinc-300 relative z-10">{{ Math.min(uploadProgress, 99) }}%</span>
                   <div class="absolute bottom-0 left-0 right-0 bg-zinc-300/60 dark:bg-zinc-700 transition-all duration-150" :style="{ height: `${uploadProgress}%` }"></div>
                </div>
                <div class="flex flex-col min-w-0 pr-2">
                  <span class="text-[13px] font-bold text-zinc-700 dark:text-zinc-200 truncate max-w-[200px]">{{ selectedFile.name }}</span>
                  <span class="text-[11px] text-zinc-500 dark:text-zinc-400">处理并上传到云端...</span>
                </div>
              </div>

              <!-- File Preview -->
              <div
                v-if="uploadProgress >= 100"
                class="group relative flex h-16 w-16 items-center justify-center rounded-xl bg-zinc-100 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 overflow-hidden shadow-sm"
              >
                <img
                  v-if="selectedFile.type.startsWith('image/') && filePreviewUrl"
                  :src="filePreviewUrl"
                  class="h-full w-full object-cover"
                />
                <video
                  v-else-if="selectedFile.type.startsWith('video/') && filePreviewUrl"
                  :src="filePreviewUrl"
                  class="h-full w-full object-cover"
                ></video>
                <span v-else class="text-[20px] text-zinc-400">📄</span>
                
                <button
                  type="button"
                  @click.prevent="selectedFile = null"
                  class="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/50 text-white opacity-0 transition-opacity hover:bg-black/70 group-hover:opacity-100 backdrop-blur-md"
                >
                  <span class="text-sm font-light leading-none mb-0.5">&times;</span>
                </button>
                <div class="absolute inset-x-0 bottom-0 flex h-5 items-end bg-gradient-to-t from-black/60 to-transparent px-1 pb-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                  <span class="w-full truncate text-[9px] text-white/90">{{ selectedFile.name }}</span>
                </div>
              </div>
            </div>

            <textarea
              ref="textareaRef"
              v-model="inputText"
              :disabled="!isTerminal(project.status) || sending"
              :placeholder="
                isTerminal(project.status)
                  ? '继续提问...'
                  : '等待工作流执行完成...'
              "
              class="w-full resize-none bg-transparent text-sm outline-none placeholder:text-zinc-400 disabled:opacity-50 disabled:cursor-not-allowed mx-2 mt-1"
              rows="1"
              @keydown.enter.meta.prevent="handleSend"
              @keydown.enter.ctrl.prevent="handleSend"
            />

            <div class="flex items-center justify-between mt-2 pt-1">
              <button
                type="button"
                @click="handleUploadClick"
                :disabled="!isTerminal(project.status)"
                class="inline-flex items-center gap-1.5 rounded-full px-2 py-1.5 text-xs font-medium text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Upload class="size-4" />
                <span class="opacity-80">上传附件</span>
              </button>

              <Button
                type="submit"
                :disabled="!canSend || sending"
                class="shrink-0 h-8 w-8 p-0 rounded-full bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200 disabled:opacity-40 flex items-center justify-center transition-all shadow-sm"
              >
                <Send class="size-3.5 ml-[1px]" />
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- Source Video Detail Drawer -->
    <VideoDrawer
      v-model:open="showVideoDetail"
      :project="project"
      :videoUrl="resolveAssetUrl(project?.media_url)"
    />

    <!-- Generated Video Detail Drawer -->
    <GenerationDrawer
      v-model:open="showGenerationDetail"
      :videoGeneration="videoGeneration"
      :targetVideoUrl="resolveAssetUrl(generatedVideoUrl)"
      :title="project?.title || '生成详情'"
      :sourceUrl="resolveAssetUrl(project?.media_url)"
    />
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(153, 153, 153, 0.2);
  border-radius: 10px;
}

:deep(.markdown-body) {
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}
:deep(.markdown-body > *:first-child) {
  margin-top: 0;
}
:deep(.markdown-body > *:last-child) {
  margin-bottom: 0;
}
:deep(.markdown-body p) {
  margin-bottom: 0.8em;
}
:deep(.markdown-body h1), 
:deep(.markdown-body h2), 
:deep(.markdown-body h3),
:deep(.markdown-body h4) {
  font-weight: 600;
  margin-top: 1.5em;
  margin-bottom: 0.8em;
  line-height: 1.25;
}
:deep(.markdown-body h1) { font-size: 1.5em; }
:deep(.markdown-body h2) { font-size: 1.25em; }
:deep(.markdown-body h3) { font-size: 1.1em; }
:deep(.markdown-body strong) { font-weight: 600; }
:deep(.markdown-body ul) {
  list-style-type: disc;
  padding-left: 1.5em;
  margin-bottom: 0.8em;
}
:deep(.markdown-body ol) {
  list-style-type: decimal;
  padding-left: 1.5em;
  margin-bottom: 0.8em;
}
:deep(.markdown-body li) {
  margin-bottom: 0.25em;
}
:deep(.markdown-body table) {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1em;
  margin-bottom: 1em;
}
:deep(.markdown-body th),
:deep(.markdown-body td) {
  border: 1px solid rgba(128, 128, 128, 0.2);
  padding: 0.5em 0.75em;
  text-align: left;
}
:deep(.markdown-body th) {
  background-color: rgba(128, 128, 128, 0.1);
  font-weight: 600;
}

.thinking-dot {
  animation: thinking-bounce 1.2s ease-in-out infinite;
}

@keyframes thinking-bounce {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-6px);
    opacity: 1;
  }
}
</style>
