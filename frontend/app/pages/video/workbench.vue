<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

import VideoOverviewDrawer from "~/components/custom/VideoOverviewDrawer.vue";
import TaskTimeline from "~/components/custom/TaskTimeline.vue";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";

definePageMeta({
  layout: "console",
  middleware: "auth",
  ssr: false,
});

const apiService = useApi();
const api = apiService.requestData;
const runtimeConfig = useRuntimeConfig();
const chatStore = useChatStore();
const route = useRoute();

useHead({
  title: "视频分析工作台",
});

type ModeTab = "script" | "remake" | "create";
type ProjectWorkflowType = "analysis" | "create" | "remake";

const activeMode = ref<ModeTab>("script");
const inputText = ref("");
const sending = ref(false);
const errorMessage = ref("");
const selectedFile = ref<File | null>(null);
const selectedUrls = ref<string[]>([]);
const showLinkModal = ref(false);
const linkDraft = ref("");
const linkModalError = ref("");
const showVideoDetailModal = ref(false);

const selectedProject = computed(() => chatStore.selectedProject);
const projects = computed(() => chatStore.projects);

const modePrefills: Record<ModeTab, () => string> = {
  script: () =>
    "从这个视频中提取完整的文本脚本，包括对话、旁白以及所有文字字幕：",
  remake: () => "复刻这个视频的画面细节，包括画面构图、色彩、光影等：",
  create: () =>
    "我希望创作的视频类型：[UGC种草/产品口播/产品演示/痛点-解决/前后对比/反应展示/故事讲述]\n我的目标客群：[种族/地区/职业/生理特征等]\n我的商品名称：\n我的商品卖点：\n我倾向的视频风格：",
};

const modeToWorkflowType = (mode: ModeTab): ProjectWorkflowType =>
  mode === "create" ? "create" : mode === "remake" ? "remake" : "analysis";

const workflowTypeToMode = (workflowType: ProjectWorkflowType): ModeTab =>
  workflowType === "create"
    ? "create"
    : workflowType === "remake"
      ? "remake"
      : "script";

// Initial prefill
inputText.value = modePrefills[activeMode.value]();

let projectPollingTimer: ReturnType<typeof window.setInterval> | null = null;

const stopProjectPolling = () => {
  if (projectPollingTimer) {
    window.clearInterval(projectPollingTimer);
    projectPollingTimer = null;
  }
};

const isProjectTerminal = (status: string | null | undefined) =>
  ["succeeded", "failed", "ready"].includes(
    (status || "").trim().toLowerCase(),
  );

const startProjectPolling = (projectId: number) => {
  stopProjectPolling();
  projectPollingTimer = window.setInterval(async () => {
    try {
      const project = await api<any>(`/projects/${projectId}`);
      chatStore.selectedProject = project;
      if (isProjectTerminal(project.status)) {
        stopProjectPolling();
        const res = await api<any[]>("/projects");
        chatStore.projects = res;
      }
    } catch (error) {
      console.error(error);
      stopProjectPolling();
    }
  }, 2000);
};

const formatDateTime = (value: string | null | undefined) => {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
};

const getMessageTypeLabel = (messageType: string) => {
  const labels: Record<string, string> = {
    project_request: "用户需求",
    workflow_status: "流程更新",
    analysis_reply: "分析结果",
    suggestion_reply: "优化建议",
    workflow_error: "执行异常",
    chat_question: "追问",
    chat_reply: "回复",
  };
  return labels[messageType] || messageType;
};

const handleSend = async () => {
  const objective = inputText.value.trim();
  const sourceUrl = selectedUrls.value[0] || "";

  if (!objective && !selectedFile.value && !sourceUrl) return;

  sending.value = true;
  errorMessage.value = "";

  try {
    if (
      selectedProject.value &&
      isProjectTerminal(selectedProject.value.status)
    ) {
      // Follow-up mode
      const objectiveToSubmit = objective;
      inputText.value = "";

      const res = await api<any>(
        `/projects/${selectedProject.value.id}/messages`,
        {
          method: "POST",
          body: { content: objectiveToSubmit },
        },
      );

      if (chatStore.selectedProject) {
        if (!chatStore.selectedProject.conversation_messages) {
          chatStore.selectedProject.conversation_messages = [];
        }

        chatStore.selectedProject.conversation_messages.push({
          id: "temp-" + Date.now(),
          role: "user",
          message_type: "chat_question",
          content: objectiveToSubmit,
          created_at: new Date().toISOString(),
          content_json: null,
          reply_to_message_id: null,
        });

        chatStore.selectedProject.conversation_messages.push({
          id: res.id,
          role: res.role || "assistant",
          message_type: "chat_reply",
          content: res.content,
          created_at: res.created_at,
          content_json: null,
          reply_to_message_id: null,
        });
      }
    } else {
      // New project mode
      const formData = new FormData();
      if (selectedFile.value) formData.append("file", selectedFile.value);
      formData.append("objective", objective);
      formData.append("workflow_type", modeToWorkflowType(activeMode.value));
      if (sourceUrl) formData.append("source_url", sourceUrl);

      const project = await api<any>("/projects/upload", {
        method: "POST",
        body: formData,
      });
      chatStore.selectedProject = project;
      if (!isProjectTerminal(project.status)) {
        startProjectPolling(project.id);
      }
      inputText.value = "";
      selectedFile.value = null;
      selectedUrls.value = [];
      const res = await api<any[]>("/projects");
      chatStore.projects = res;
    }
  } catch (error) {
    errorMessage.value = apiService.normalizeError(error);
  } finally {
    sending.value = false;
  }
};

const resolveAssetUrl = (value: string | null | undefined): string | null => {
  const normalized = (value || "").trim();
  if (!normalized) return null;
  if (/^(https?:|data:|blob:)/i.test(normalized)) return normalized;
  const apiBase = (runtimeConfig.public.apiBase || "").trim();
  const origin = apiBase ? new URL(apiBase).origin : window.location.origin;
  return new URL(normalized, `${origin}/`).toString();
};

const textareaRef = ref<HTMLTextAreaElement | null>(null);
const adjustTextareaHeight = () => {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
};

watch(inputText, () => {
  nextTick(adjustTextareaHeight);
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

watch(
  () => selectedProject.value?.id,
  (newId) => {
    if (newId && !isProjectTerminal(selectedProject.value?.status)) {
      startProjectPolling(newId);
    } else if (!newId) {
      stopProjectPolling();
      inputText.value = modePrefills[activeMode.value]();
      selectedFile.value = null;
      selectedUrls.value = [];
    }
  },
);

onMounted(async () => {
  if (!chatStore.projects.length) {
    const res = await api<any[]>("/projects");
    chatStore.projects = res;
  }
  nextTick(adjustTextareaHeight);
});

onUnmounted(() => stopProjectPolling());

const handleUploadClick = () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "video/*";
  input.onchange = (e) => {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (file) selectedFile.value = file;
  };
  input.click();
};

const openLinkModal = () => {
  linkDraft.value = selectedUrls.value[0] || "";
  showLinkModal.value = true;
};

const confirmLink = () => {
  let url = linkDraft.value.trim();
  if (!url) return;
  if (!url.startsWith("http")) url = "https://" + url;
  selectedUrls.value = [url];
  showLinkModal.value = false;
};
</script>

<template>
  <div
    class="flex h-full w-full bg-[#fcfcfc] dark:bg-[#121212] overflow-hidden"
  >
    <main class="flex-1 flex flex-col h-full relative">
      <div
        class="flex-1 overflow-y-auto px-6 lg:px-[120px] pb-[180px] pt-10 scroll-smooth custom-scrollbar"
      >
        <!-- Intro State -->
        <div
          v-if="!selectedProject"
          class="h-full flex flex-col items-center justify-center pb-[15vh]"
        >
          <div
            class="w-100 h-20 flex items-center justify-center mb-8 rotate-3 p-4"
          >
            <img
              src="/logo.png"
              class="w-full h-full object-contain"
              alt="Logo"
            />
          </div>
          <h1
            class="text-[32px] font-bold text-zinc-900 dark:text-white mb-4 tracking-tight"
          >
            有什么我能帮你的吗？
          </h1>
        </div>

        <!-- Conversation Content -->
        <div v-else class="mx-auto max-w-[800px] space-y-8">
          <!-- Project Header -->
          <div
            class="rounded-[28px] border border-zinc-100 bg-white p-6 shadow-xl shadow-zinc-200/40 dark:border-zinc-800 dark:bg-zinc-900 dark:shadow-none"
          >
            <div class="flex items-center justify-between mb-6">
              <h2 class="text-xl font-bold truncate pr-4">
                {{ selectedProject.title }}
              </h2>
              <button
                @click="showVideoDetailModal = true"
                class="rounded-full bg-zinc-100 px-4 py-2 text-sm font-medium hover:bg-zinc-200 transition-colors dark:bg-zinc-800"
              >
                查看视频
              </button>
            </div>

            <!-- Messages -->
            <div class="space-y-6">
              <div
                v-for="message in selectedProject.conversation_messages"
                :key="message.id"
                class="flex"
                :class="
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                "
              >
                <div
                  class="max-w-[88%] rounded-[24px] px-5 py-3 shadow-sm border"
                  :class="
                    message.role === 'user'
                      ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900 border-zinc-900'
                      : 'bg-zinc-50 border-zinc-100 dark:bg-zinc-800 dark:border-zinc-700'
                  "
                >
                  <div
                    class="flex items-center gap-2 text-[11px] font-bold opacity-60 mb-1.5 uppercase tracking-wider"
                  >
                    <span>{{ message.role === "user" ? "ME" : "AI" }}</span>
                    <span>·</span>
                    <span>{{ getMessageTypeLabel(message.message_type) }}</span>
                  </div>
                  <p class="text-[15px] leading-relaxed whitespace-pre-wrap">
                    {{ message.content }}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <!-- Task Timeline -->
          <div
            v-if="selectedProject.task_steps?.length"
            class="rounded-[28px] border border-zinc-100 bg-white p-8 shadow-xl shadow-zinc-200/40 dark:border-zinc-800 dark:bg-zinc-900"
          >
            <h3 class="text-lg font-bold mb-6">执行进度</h3>
            <TaskTimeline :tasks="selectedProject.task_steps" />
          </div>
        </div>
      </div>

      <!-- Input Overlay (Restored to original premium style) -->
      <div
        class="absolute bottom-0 left-0 right-0 p-4 lg:px-[120px] bg-gradient-to-t from-[#fcfcfc] via-[#fcfcfc] dark:from-[#121212] dark:via-[#121212] to-transparent pt-12 pb-8"
      >
        <div class="mx-auto w-full max-w-5xl">
          <div
            ref="glowRef"
            @mousemove="handleMouseMove"
            @mouseenter="isHovering = true"
            @mouseleave="isHovering = false"
            class="group relative text-card-foreground rounded-3xl border border-border bg-muted/40 p-4 shadow-lg backdrop-blur-md transition-all focus-within:ring-2 focus-within:ring-blue-500/10"
          >
            <!-- Glowing Border Effect (Flowing style) -->
            <div
              class="pointer-events-none absolute inset-0 rounded-[inherit] transition-opacity"
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
            <form @submit.prevent="handleSend">
              <div class="relative">
                <!-- Mode Switcher -->
                <div class="mb-1.5 flex flex-wrap gap-2">
                  <div class="flex items-center text-xs text-muted-foreground">
                    想做什么
                  </div>

                  <div
                    @click="
                      activeMode = 'script';
                      inputText = modePrefills.script();
                    "
                    :class="
                      activeMode === 'script'
                        ? 'border-emerald-300/50 bg-emerald-50/70 text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-400/10 dark:text-emerald-300'
                        : 'border-transparent text-muted-foreground hover:bg-muted'
                    "
                    class="inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-full border shadow-sm transition-all duration-200 hover:scale-105 active:scale-95 cursor-pointer"
                  >
                    <LucideIcon name="ScrollText" class="h-3.5 w-3.5 mr-1" />
                    分析脚本
                  </div>

                  <div
                    @click="
                      activeMode = 'remake';
                      inputText = modePrefills.remake();
                    "
                    :class="
                      activeMode === 'remake'
                        ? 'border-amber-300/50 bg-amber-50/70 text-amber-700 dark:border-amber-400/40 dark:bg-amber-400/10 dark:text-amber-300'
                        : 'border-transparent text-muted-foreground hover:bg-muted'
                    "
                    class="inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-full border shadow-sm transition-all duration-200 hover:scale-105 active:scale-95 cursor-pointer"
                  >
                    <LucideIcon name="Images" class="h-3.5 w-3.5 mr-1" />
                    复刻爆款
                  </div>

                  <div
                    @click="
                      activeMode = 'create';
                      inputText = modePrefills.create();
                    "
                    :class="
                      activeMode === 'create'
                        ? 'border-blue-400/40 bg-blue-50/70 text-blue-700 dark:border-blue-400/40 dark:bg-blue-400/10 dark:text-blue-300'
                        : 'border-transparent text-muted-foreground hover:bg-muted'
                    "
                    class="inline-flex items-center px-2.5 py-0.5 text-xs font-semibold rounded-full border shadow-sm transition-all duration-200 hover:scale-105 active:scale-95 cursor-pointer"
                  >
                    <LucideIcon name="Clapperboard" class="h-3.5 w-3.5 mr-1" />
                    创作爆款
                  </div>
                </div>

                <!-- Input Box -->
                <textarea
                  ref="textareaRef"
                  v-model="inputText"
                  placeholder="上传视频文件或粘贴 TikTok 视频链接，然后问我任何问题..."
                  class="flex min-h-[60px] w-full rounded-md border border-input bg-transparent py-2 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm resize-none overflow-hidden border-none text-sm text-foreground shadow-none focus-visible:ring-0 px-0"
                  rows="2"
                  @keydown.enter.meta.prevent="handleSend"
                ></textarea>

                <!-- Actions -->
                <div class="mt-2 flex items-center justify-between">
                  <div class="flex items-center gap-2">
                    <button
                      type="button"
                      @click="handleUploadClick"
                      class="inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80 h-8 px-3 text-xs rounded-full"
                    >
                      <LucideIcon name="Upload" class="h-3.5 w-3.5" />
                      上传视频
                    </button>
                    <button
                      type="button"
                      @click="openLinkModal"
                      class="inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80 h-8 px-3 text-xs rounded-full"
                    >
                      <LucideIcon name="Link" class="h-3.5 w-3.5" />
                      添加链接
                    </button>

                    <div
                      v-if="selectedFile"
                      class="text-xs font-bold text-blue-600 bg-blue-50 px-2 py-1 rounded-lg flex items-center gap-1 ml-1"
                    >
                      {{ selectedFile.name }}
                      <LucideIcon
                        name="X"
                        class="w-3 h-3 cursor-pointer"
                        @click="selectedFile = null"
                      />
                    </div>
                    <div
                      v-if="selectedUrls.length"
                      class="text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded-lg flex items-center gap-1 ml-1"
                    >
                      已添加链接
                      <LucideIcon
                        name="X"
                        class="w-3 h-3 cursor-pointer"
                        @click="selectedUrls = []"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    :disabled="
                      sending ||
                      (!inputText.trim() &&
                        !selectedFile &&
                        !selectedUrls.length)
                    "
                    class="inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 shadow h-9 w-9 rounded-full bg-primary text-primary-foreground hover:bg-primary/90"
                  >
                    <LucideIcon
                      :name="sending ? 'Loader2' : 'ArrowUp'"
                      class="h-4 w-4"
                      :class="sending ? 'animate-spin' : ''"
                    />
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      </div>
    </main>

    <!-- Detail Drawer Placeholder -->
    <VideoOverviewDrawer
      v-model:open="showVideoDetailModal"
      :project="selectedProject"
      :videoUrl="resolveAssetUrl(selectedProject?.media_url)"
    />

    <!-- Link Modal -->
    <Dialog v-model:open="showLinkModal">
      <DialogContent
        class="sm:max-w-[425px] rounded-[32px] border-zinc-100 dark:border-zinc-800 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-xl shadow-2xl"
      >
        <DialogHeader>
          <DialogTitle class="text-xl font-bold">添加视频链接</DialogTitle>
        </DialogHeader>
        <div class="py-4">
          <input
            v-model="linkDraft"
            type="text"
            class="w-full h-12 rounded-2xl border bg-zinc-50 dark:bg-zinc-800/50 px-4 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/10 dark:border-zinc-700"
            placeholder="https://..."
          />
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            @click="showLinkModal = false"
            class="rounded-full px-6"
            >取消</Button
          >
          <Button
            @click="confirmLink"
            class="rounded-full px-6 bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
            >确认</Button
          >
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
</style>
