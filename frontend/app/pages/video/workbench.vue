<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "vue-sonner";
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

type ModeTab = "script" | "remake" | "create" | "";
type ProjectWorkflowType = "analysis" | "create" | "remake";

const activeMode = ref<ModeTab>("");
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

const modePrefills: Record<Exclude<ModeTab, "">, () => string> = {
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

// Initial prefill removed to start empty

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
      inputText.value = "";
      selectedFile.value = null;
      selectedUrls.value = [];
      const res = await api<any[]>("/projects");
      chatStore.projects = res;
      await navigateTo(`/video/history?id=${project.id}`);
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
  let origin = window.location.origin;
  if (apiBase) {
    try {
      origin = new URL(apiBase, window.location.origin).origin;
    } catch {
      origin = window.location.origin;
    }
  }
  try {
    return new URL(normalized, `${origin}/`).toString();
  } catch {
    return normalized.startsWith("/") ? normalized : `/${normalized}`;
  }
};

const textareaRef = ref<any>(null);
const adjustTextareaHeight = () => {
  const el = textareaRef.value?.$el ?? textareaRef.value;
  if (!el || typeof el.scrollHeight !== "number") return;
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
      inputText.value = activeMode.value
        ? modePrefills[activeMode.value as Exclude<ModeTab, "">]()
        : "";
      selectedFile.value = null;
      selectedUrls.value = [];
    }
  },
);

onMounted(async () => {
  // workbench should always be for new projects
  chatStore.selectedProject = null;

  if (!chatStore.projects.length) {
    const res = await api<any[]>("/projects");
    chatStore.projects = res;
  }
  nextTick(adjustTextareaHeight);
});

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
    if (
      newFile.type.startsWith("image/") ||
      newFile.type.startsWith("video/")
    ) {
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

onUnmounted(() => {
  stopProjectPolling();
  if (filePreviewUrl.value) {
    URL.revokeObjectURL(filePreviewUrl.value);
  }
});

const handleUploadClick = () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "video/*,image/*,audio/*";
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
        <div class="h-full flex flex-col items-center justify-center pb-[15vh]">
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
                <!-- Attachments Preview -->
                <div
                  v-if="selectedFile || selectedUrls.length"
                  class="mb-2 flex flex-wrap gap-2 px-1"
                >
                  <!-- File Uploading State -->
                  <div
                    v-if="selectedFile && uploadProgress < 100"
                    class="flex items-center gap-3 p-3 bg-zinc-50 border border-zinc-200 dark:bg-zinc-800/50 dark:border-zinc-700 rounded-2xl w-fit pr-8 shadow-sm"
                  >
                    <div
                      class="relative flex items-center justify-center w-10 h-10 rounded-full border border-zinc-200 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-900 overflow-hidden shrink-0"
                    >
                      <span
                        class="text-[10px] font-bold text-zinc-600 dark:text-zinc-300 relative z-10"
                        >{{ Math.min(uploadProgress, 99) }}%</span
                      >
                      <div
                        class="absolute bottom-0 left-0 right-0 bg-zinc-300/60 dark:bg-zinc-700 transition-all duration-150"
                        :style="{ height: `${uploadProgress}%` }"
                      ></div>
                    </div>
                    <div class="flex flex-col min-w-0 pr-2">
                      <span
                        class="text-[13px] font-bold text-zinc-700 dark:text-zinc-200 truncate max-w-[200px]"
                        >{{ selectedFile.name }}</span
                      >
                      <span class="text-[11px] text-zinc-500 dark:text-zinc-400"
                        >处理并上传到云端...</span
                      >
                    </div>
                  </div>

                  <!-- File Preview -->
                  <div
                    v-if="selectedFile && uploadProgress >= 100"
                    class="group relative flex h-16 w-16 items-center justify-center rounded-xl bg-zinc-100 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 overflow-hidden shadow-sm"
                  >
                    <img
                      v-if="
                        selectedFile.type.startsWith('image/') && filePreviewUrl
                      "
                      :src="filePreviewUrl"
                      class="h-full w-full object-cover"
                    />
                    <video
                      v-else-if="
                        selectedFile.type.startsWith('video/') && filePreviewUrl
                      "
                      :src="filePreviewUrl"
                      class="h-full w-full object-cover"
                    ></video>
                    <LucideIcon
                      v-else
                      name="File"
                      class="size-6 text-zinc-400"
                    />

                    <button
                      type="button"
                      @click.prevent="selectedFile = null"
                      class="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/50 text-white opacity-0 transition-opacity hover:bg-black/70 group-hover:opacity-100 backdrop-blur-md"
                    >
                      <LucideIcon name="X" class="size-3" />
                    </button>
                    <!-- Small title overlay -->
                    <div
                      class="absolute inset-x-0 bottom-0 flex h-5 items-end bg-gradient-to-t from-black/60 to-transparent px-1 pb-0.5 opacity-0 transition-opacity group-hover:opacity-100"
                    >
                      <span class="w-full truncate text-[9px] text-white/90">{{
                        selectedFile.name
                      }}</span>
                    </div>
                  </div>

                  <!-- URL Previews -->
                  <div
                    v-for="url in selectedUrls"
                    :key="url"
                    class="group relative flex h-16 max-w-[200px] shrink-0 items-center gap-2 rounded-xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 p-2 shadow-sm"
                  >
                    <div
                      class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-zinc-200/50 dark:bg-zinc-700/50"
                    >
                      <LucideIcon name="Link" class="size-5 text-zinc-500" />
                    </div>
                    <div class="flex flex-col min-w-0 pr-4">
                      <span
                        class="truncate text-[11px] font-semibold text-zinc-700 dark:text-zinc-200"
                        >网页链接</span
                      >
                      <span class="truncate text-[10px] text-zinc-500">{{
                        url
                      }}</span>
                    </div>
                    <button
                      type="button"
                      @click.prevent="selectedUrls = []"
                      class="absolute right-0 top-0 flex size-5 -translate-x-1 translate-y-1 items-center justify-center rounded-full bg-zinc-200 dark:bg-zinc-600 text-zinc-600 dark:text-zinc-300 opacity-0 transition-opacity hover:bg-zinc-300 dark:hover:bg-zinc-500 group-hover:opacity-100"
                    >
                      <LucideIcon name="X" class="size-3" />
                    </button>
                  </div>
                </div>

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
                <Textarea
                  ref="textareaRef"
                  v-model="inputText"
                  placeholder="上传视频文件或粘贴 TikTok 视频链接，然后问我任何问题..."
                  class="flex min-h-[60px] w-full rounded-md border border-input bg-transparent py-2 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm resize-none overflow-hidden border-none text-sm text-foreground shadow-none focus-visible:ring-0 px-0"
                  rows="2"
                  @keydown.enter.meta.prevent="handleSend"
                />

                <!-- Actions -->
                <div class="mt-2 flex items-center justify-between">
                  <div class="flex items-center gap-2">
                    <button
                      type="button"
                      @click="handleUploadClick"
                      class="inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80 h-8 px-3 text-xs rounded-full"
                    >
                      <LucideIcon name="Upload" class="h-3.5 w-3.5" />
                      上传附件
                    </button>
                    <button
                      type="button"
                      @click="openLinkModal"
                      class="inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80 h-8 px-3 text-xs rounded-full"
                    >
                      <LucideIcon name="Link" class="h-3.5 w-3.5" />
                      添加链接
                    </button>
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

    <!-- Link Modal -->
    <Dialog v-model:open="showLinkModal">
      <DialogContent
        class="sm:max-w-[425px] rounded-[32px] border-zinc-100 bg-white/80 px-6 py-6 shadow-2xl backdrop-blur-xl dark:border-zinc-800 dark:bg-zinc-900/80 sm:px-7 sm:py-7"
      >
        <DialogHeader class="pr-12">
          <DialogTitle class="text-xl font-bold">添加视频链接</DialogTitle>
        </DialogHeader>
        <div class="py-2">
          <input
            v-model="linkDraft"
            type="text"
            class="w-full h-12 rounded-2xl border bg-zinc-50 dark:bg-zinc-800/50 px-4 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/10 dark:border-zinc-700"
            placeholder="https://..."
          />
        </div>
        <DialogFooter class="mt-2 gap-3">
          <Button
            variant="outline"
            @click="showLinkModal = false"
            class="h-12 rounded-full px-7"
            >取消</Button
          >
          <Button
            @click="confirmLink"
            class="h-12 rounded-full px-7 bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
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
