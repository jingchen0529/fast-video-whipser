<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  Sparkles,
  Play,
  CheckCircle2,
  Loader2,
  CircleDashed,
  AlertCircle,
  X,
  Library,
  Upload,
  Link,
  ArrowUp,
  Image as ImageIcon,
  Film,
} from "lucide-vue-next";
import { toast } from "vue-sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { notifyError } from "@/utils/common";
import type { Job, MotionAsset } from "@/types/api";

definePageMeta({
  layout: "console",
  middleware: "auth",
  ssr: false,
});

useHead({ title: "动作提取" });

type MotionExtractionStep = {
  step_key: string;
  title: string;
  detail: string;
  status: string;
  error_detail?: string | null;
};

type FilteredMotionItem = {
  source_shot_segment_id?: string;
  segment_index?: number;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  title?: string;
  transcript_text?: string;
  visual_summary?: string;
  matched_labels?: string[];
  matched_sources?: string[];
  signal_score?: number;
  filter_reason?: string;
  filter_reason_label?: string;
};

const apiService = useApi();
const api = apiService.requestData;
const router = useRouter();
const runtimeConfig = useRuntimeConfig();

const FILTER_REASON_LABELS: Record<string, string> = {
  duration_too_short: "时长过短",
  duration_too_long: "时长过长",
  no_motion_signal: "未识别到动作信号",
  signal_below_threshold: "信号分不足",
};

const resolveAssetUrl = (assetId?: string | null): string | null => {
  if (!assetId) return null;
  const apiBase = `${runtimeConfig.public.apiBase || ""}`.trim();
  let origin = typeof window !== "undefined" ? window.location.origin : "";
  if (apiBase && typeof window !== "undefined") {
    try {
      origin = new URL(apiBase, window.location.origin).origin;
    } catch {
      origin = window.location.origin;
    }
  }
  const path = `${apiBase}/assets/file/${assetId}`;
  try {
    return new URL(path, `${origin}/`).toString();
  } catch {
    return path;
  }
};

const fileInput = ref<HTMLInputElement | null>(null);
const scrollArea = ref<HTMLElement | null>(null);
const selectedFile = ref<File | null>(null);
const sourceUrl = ref("");
const instructionText = ref("");
const showLinkModal = ref(false);
const linkDraft = ref("");
const showMotionDetail = ref(false);
const selectedMotion = ref<MotionAsset | null>(null);
const textareaRef = ref<any>(null);
const glowRef = ref<HTMLElement | null>(null);
const glowStartAngle = ref(0);
const isHovering = ref(false);

const starting = ref(false);
const extractionPhase = ref<"idle" | "uploading" | "analyzing" | "extracting">("idle");
const currentJob = ref<Job | null>(null);
const extractedItems = ref<MotionAsset[]>([]);

let pollingTimer: ReturnType<typeof setInterval> | null = null;
let projectPollingTimer: ReturnType<typeof setInterval> | null = null;

const steps = computed<MotionExtractionStep[]>(() => {
  if (extractionPhase.value === "uploading") {
    return [
      { step_key: "upload", title: "上传与创建", detail: "正在提交视频内容并初始化分析任务...", status: "running" }
    ];
  }
  if (extractionPhase.value === "analyzing") {
    return [
      { step_key: "upload", title: "上传与创建", detail: "上传成功", status: "completed" },
      { step_key: "analysis", title: "前置视频分析", detail: "正在运行视频分析工作流解析视频内容 (通常需要几分钟)...", status: "running" }
    ];
  }
  const raw = currentJob.value?.result_json?.steps;
  const extractionSteps = Array.isArray(raw) ? raw : [];
  if (extractionPhase.value === "extracting" || currentJob.value) {
    return [
      { step_key: "upload", title: "上传与创建", detail: "上传成功", status: "completed" },
      { step_key: "analysis", title: "前置视频分析", detail: "分析完成", status: "completed" },
      ...extractionSteps
    ];
  }
  return [];
});

const filteredItems = computed<FilteredMotionItem[]>(() => {
  const raw = currentJob.value?.result_json?.filtered_items;
  return Array.isArray(raw) ? raw : [];
});

const filteredSummaryEntries = computed<[string, number][]>(() => {
  const raw = currentJob.value?.result_json?.filtered_summary;
  if (!raw || typeof raw !== "object") return [];
  return Object.entries(raw as Record<string, number>)
    .filter((entry): entry is [string, number] => typeof entry[1] === "number")
    .sort((a, b) => b[1] - a[1]);
});

const canSubmit = computed(() => (!!selectedFile.value || !!sourceUrl.value.trim()) && !starting.value);

const formatRange = (startMs: number, endMs: number) => {
  const formatPoint = (value: number) => {
    const totalSeconds = Math.max(0, Math.floor(value / 1000));
    const minutes = Math.floor(totalSeconds / 60)
      .toString()
      .padStart(2, "0");
    const seconds = (totalSeconds % 60).toString().padStart(2, "0");
    return `${minutes}:${seconds}`;
  };
  return `${formatPoint(startMs)} - ${formatPoint(endMs)}`;
};

const formatDuration = (startMs: number, endMs: number) =>
  `${Math.max(0, endMs - startMs) / 1000}s`;

const formatFilteredReason = (item: FilteredMotionItem) =>
  item.filter_reason_label || item.filter_reason || "已过滤";

const formatFilteredSummaryReason = (reason: string) =>
  FILTER_REASON_LABELS[reason] || reason;

const confidenceText = (item: MotionAsset) => {
  const raw = item.metadata_json?.confidence;
  const normalized =
    typeof raw === "number" ? raw : Number.parseFloat(String(raw || ""));
  if (Number.isNaN(normalized)) return "未标注";
  return `${Math.round(normalized * 100)}%`;
};

const reviewStatusLabel = (status?: string | null) => {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "approved") return "已入库";
  if (normalized === "rejected") return "已驳回";
  return "待审核";
};

const resolveMotionThumbnailUrl = (item?: MotionAsset | null): string | null => {
  if (!item) return null;
  return resolveAssetUrl(
    item.thumbnail_asset_id || item.metadata_json?.thumbnail_asset_id || null,
  );
};

const resolveMotionClipUrl = (item?: MotionAsset | null): string | null => {
  if (!item) return null;
  return resolveAssetUrl(item.clip_asset_id);
};

const stepIcon = (status: string) => {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "completed") return CheckCircle2;
  if (normalized === "running" || normalized === "in_progress") return Loader2;
  if (normalized === "failed") return AlertCircle;
  return CircleDashed;
};

const stopJobPolling = () => {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
};

const stopProjectPolling = () => {
  if (projectPollingTimer) {
    clearInterval(projectPollingTimer);
    projectPollingTimer = null;
  }
};

const triggerFileInput = () => {
  if (fileInput.value) fileInput.value.click();
};

const adjustTextareaHeight = () => {
  const el = textareaRef.value?.$el ?? textareaRef.value;
  if (!el || typeof el.scrollHeight !== "number") return;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
};

const handleMouseMove = (e: MouseEvent) => {
  if (!glowRef.value) return;
  const rect = glowRef.value.getBoundingClientRect();
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  const angle = Math.atan2(e.clientY - centerY, e.clientX - centerX) * (180 / Math.PI);
  glowStartAngle.value = angle + 90;
};

const handleFileChange = (e: Event) => {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (file) {
    selectedFile.value = file;
    sourceUrl.value = "";
  }
};

const removeFile = () => {
  selectedFile.value = null;
  if (fileInput.value) fileInput.value.value = "";
};

const refreshJob = async (jobId: string) => {
  try {
    const job = await api<Job>(`/jobs/${jobId}`);
    currentJob.value = job;
    const items = job.result_json?.items;
    extractedItems.value = Array.isArray(items) ? items : [];

    if (["succeeded", "failed", "cancelled"].includes(String(job.status || "").toLowerCase())) {
      stopJobPolling();
      starting.value = false;
      if (job.status === "succeeded") {
        toast.success(
          `动作提取完成，生成 ${job.result_json?.saved_count || 0} 条动作资产。`,
        );
      }
    }
  } catch (error) {
    stopJobPolling();
    starting.value = false;
    notifyError(apiService, error, "刷新动作提取状态失败");
  }
};

const startJobPolling = (jobId: string) => {
  stopJobPolling();
  pollingTimer = setInterval(() => {
    refreshJob(jobId);
  }, 2000);
};

const pollAnalysisProject = (projectId: number): Promise<void> => {
  return new Promise((resolve, reject) => {
    stopProjectPolling();
    projectPollingTimer = setInterval(async () => {
      try {
        const p = await api<{ status: string; error_message?: string }>(`/projects/${projectId}`);
        const status = (p.status || "").trim().toLowerCase();
        if (["succeeded", "ready"].includes(status)) {
          stopProjectPolling();
          resolve();
        } else if (status === "failed") {
          stopProjectPolling();
          reject(new Error(p.error_message || "前置视频分析任务失败"));
        }
      } catch (error) {
        stopProjectPolling();
        reject(error);
      }
    }, 3000);
  });
};

const startExtraction = async () => {
  if (!canSubmit.value) return;
  starting.value = true;
  extractedItems.value = [];
  currentJob.value = null;
  selectedMotion.value = null;
  extractionPhase.value = "uploading";

  try {
    const formData = new FormData();
    if (selectedFile.value) {
      formData.append("file", selectedFile.value);
    }
    if (sourceUrl.value.trim()) {
      formData.append("source_url", sourceUrl.value.trim());
    }
    formData.append("objective", "");
    formData.append("workflow_type", "analysis");

    const project = await api<{ id: number; status: string }>("/projects/upload", {
      method: "POST",
      body: formData,
    });
    
    extractionPhase.value = "analyzing";
    const status = (project.status || "").trim().toLowerCase();
    if (!["succeeded", "ready"].includes(status)) {
       await pollAnalysisProject(project.id);
    }
    
    extractionPhase.value = "extracting";
    const result = await api<{ job_id: string }>("/assets/motions/extract", {
      method: "POST",
      body: {
        project_id: project.id,
        extraction_hint: instructionText.value.trim() || undefined,
      },
    });
    
    await refreshJob(result.job_id);
    const job = currentJob.value as Job | null;
    const currentStatus = String(job?.status || "").toLowerCase();
    if (currentStatus && !["succeeded", "failed", "cancelled"].includes(currentStatus)) {
      startJobPolling(result.job_id);
    } else {
      starting.value = false;
    }
  } catch (error) {
    notifyError(apiService, error, "启动动作提取失败");
    starting.value = false;
    extractionPhase.value = "idle";
  }
};

const openLinkModal = () => {
  linkDraft.value = sourceUrl.value || "";
  showLinkModal.value = true;
};

const confirmLink = () => {
  let url = linkDraft.value.trim();
  if (!url) return;
  if (!url.startsWith("http")) url = "https://" + url;
  sourceUrl.value = url;
  selectedFile.value = null;
  showLinkModal.value = false;
};

const openLibrary = () => {
  router.push("/assets/motions");
};

const openMotionDetail = (item: MotionAsset) => {
  selectedMotion.value = item;
  showMotionDetail.value = true;
};

const scrollToBottom = () => {
  nextTick(() => {
    if (scrollArea.value) {
      scrollArea.value.scrollTo({ top: scrollArea.value.scrollHeight, behavior: "smooth" });
    }
  });
};

watch([steps, extractedItems], () => {
  scrollToBottom();
}, { deep: true });

watch(instructionText, () => {
  nextTick(adjustTextareaHeight);
});

watch(extractedItems, (items) => {
  if (!items.length) {
    selectedMotion.value = null;
    return;
  }
  if (
    selectedMotion.value &&
    items.some((item) => item.id === selectedMotion.value?.id)
  ) {
    selectedMotion.value = items.find((item) => item.id === selectedMotion.value?.id) ?? items[0] ?? null;
    return;
  }
  selectedMotion.value = items[0] ?? null;
}, { deep: true });

onUnmounted(() => {
  stopJobPolling();
  stopProjectPolling();
});
</script>

<template>
  <div class="relative flex h-full w-full flex-col overflow-hidden bg-[#fcfcfc] dark:bg-[#0f0f0f]">
    <!-- Hidden file input -->
    <input
      type="file"
      accept="video/*"
      class="hidden"
      ref="fileInput"
      @change="handleFileChange"
    />

    <!-- Scrollable content area -->
    <div ref="scrollArea" class="flex-1 overflow-y-auto px-6 pb-[200px] pt-6 lg:px-[120px] custom-scrollbar">
      <div class="mx-auto max-w-4xl">

        <!-- Empty state (no results, no active job) -->
        <div
          v-if="!steps.length && !extractedItems.length && !(currentJob && filteredItems.length)"
          class="flex h-full min-h-[60vh] flex-col items-center justify-center pb-[10vh]"
        >
          <div class="mx-auto flex size-16 items-center justify-center rounded-full bg-zinc-100 dark:bg-zinc-800">
            <Sparkles class="size-7 text-zinc-400" />
          </div>
          <h2 class="mt-6 text-xl font-semibold text-zinc-900 dark:text-zinc-100">动作提取</h2>
          <p class="mt-2 max-w-sm text-center text-sm text-zinc-500 dark:text-zinc-400">
            上传视频文件或粘贴链接，自动分析、提取动作资产并直接入库
          </p>
          <Button variant="ghost" size="sm" class="mt-4 text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100" @click="openLibrary">
            <Library class="mr-1.5 size-4" />
            查看资产库
          </Button>
        </div>

        <!-- Progress steps -->
        <div v-if="steps.length" class="mt-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Loader2 v-if="starting" class="size-4 animate-spin text-zinc-500" />
            <CheckCircle2 v-else-if="currentJob?.status === 'succeeded'" class="size-4 text-emerald-500" />
            <AlertCircle v-else-if="currentJob?.status === 'failed'" class="size-4 text-red-500" />
            <p class="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {{ extractionPhase === "uploading" ? "上传中..." : (extractionPhase === "analyzing" ? "视频分析中..." : (currentJob?.status === 'succeeded' ? "提取完成" : (currentJob?.status === 'failed' ? "提取失败" : "动作提取中..."))) }}
            </p>
          </div>
          <Button variant="ghost" size="sm" class="text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100" @click="openLibrary">
            <Library class="mr-1.5 size-4" />
            资产库
          </Button>
        </div>

        <div class="mt-3 space-y-1">
          <div
            v-for="(step, idx) in steps"
            :key="step.step_key + idx"
            class="flex items-center gap-3 rounded-lg px-3 py-2.5"
          >
            <component
              :is="stepIcon(step.status)"
              :class="[
                'size-4 shrink-0',
                step.status === 'completed' && 'text-emerald-500',
                (step.status === 'running' || step.status === 'in_progress') && 'animate-spin text-zinc-900 dark:text-zinc-100',
                step.status === 'failed' && 'text-red-500',
                step.status === 'pending' && 'text-zinc-300 dark:text-zinc-700',
              ]"
            />
            <div class="min-w-0 flex-1">
              <p
                :class="[
                  'text-sm',
                  step.status === 'completed' ? 'text-zinc-400 dark:text-zinc-500' : 'text-zinc-700 dark:text-zinc-300',
                ]"
              >
                {{ step.title }}
                <span v-if="step.status === 'completed'" class="ml-1 text-xs text-zinc-400 dark:text-zinc-600">&mdash; {{ step.detail }}</span>
              </p>
              <p
                v-if="step.status !== 'completed'"
                class="mt-0.5 text-xs text-zinc-400 dark:text-zinc-500"
              >
                {{ step.detail }}
              </p>
              <p v-if="step.error_detail" class="mt-1 text-xs text-red-500">
                {{ step.error_detail }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- Results -->
      <div v-if="extractedItems.length" class="mt-10">
        <div class="flex items-center justify-between">
          <p class="text-xs font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
            提取结果
            <span class="ml-1.5 text-zinc-900 dark:text-zinc-100">{{ extractedItems.length }}</span>
          </p>
        </div>

        <div class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <button
            v-for="item in extractedItems"
            :key="item.id"
            type="button"
            class="group overflow-hidden rounded-2xl border border-zinc-200 bg-white text-left transition-all hover:-translate-y-0.5 hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900/80 dark:hover:border-zinc-700"
            @click="openMotionDetail(item)"
          >
            <div class="relative aspect-video w-full overflow-hidden bg-zinc-950">
              <img
                v-if="resolveMotionThumbnailUrl(item)"
                :src="resolveMotionThumbnailUrl(item) || undefined"
                class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                alt="动作缩略图"
              />
              <div
                v-else
                class="flex h-full w-full items-center justify-center text-xs text-white/30"
              >
                <ImageIcon class="size-7 opacity-50" />
              </div>
              <div class="absolute inset-0 bg-gradient-to-t from-black/55 via-black/5 to-transparent" />

              <!-- Status pill overlay -->
              <div class="absolute right-2.5 top-2.5">
                <span
                  :class="[
                    'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium backdrop-blur-sm',
                    item.review_status === 'approved' && 'bg-emerald-500/90 text-white',
                    item.review_status === 'rejected' && 'bg-red-500/80 text-white',
                    item.review_status === 'auto_tagged' && 'bg-black/40 text-white/80',
                  ]"
                >
                  {{ reviewStatusLabel(item.review_status) }}
                </span>
              </div>

              <div class="absolute bottom-2.5 left-2.5">
                <span class="inline-flex items-center gap-1 rounded-full bg-black/45 px-2 py-1 text-[10px] font-medium text-white backdrop-blur-sm">
                  <Film class="size-3" />
                  点击查看截图与片段
                </span>
              </div>
            </div>

            <div class="p-3.5">
              <div class="flex items-start justify-between gap-2">
                <p class="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {{ item.action_label || "未标注" }}
                </p>
                <span class="shrink-0 text-xs tabular-nums text-zinc-400">
                  {{ formatRange(item.start_ms, item.end_ms) }}
                </span>
              </div>

              <p v-if="item.action_summary" class="mt-1.5 line-clamp-2 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
                {{ item.action_summary }}
              </p>

              <div v-if="item.emotion_label || item.scene_label || item.camera_shot" class="mt-2.5 flex flex-wrap gap-1">
                <span v-if="item.emotion_label" class="rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                  {{ item.emotion_label }}
                </span>
                <span v-if="item.scene_label" class="rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                  {{ item.scene_label }}
                </span>
                <span v-if="item.camera_shot" class="rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                  {{ item.camera_shot }}
                </span>
              </div>

              <div class="mt-3 flex items-center justify-between text-[11px] text-zinc-400 dark:text-zinc-500">
                <span>{{ formatDuration(item.start_ms, item.end_ms) }}</span>
                <span>置信度 {{ confidenceText(item) }}</span>
              </div>
            </div>
          </button>
        </div>
      </div>

      <div
        v-else-if="currentJob && filteredItems.length"
        class="mt-10 rounded-2xl border border-zinc-200 bg-zinc-50/70 p-4 dark:border-zinc-800 dark:bg-zinc-900/40"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-xs font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              粗筛诊断
            </p>
            <p class="mt-1 text-sm text-zinc-600 dark:text-zinc-300">
              本次任务没有产出候选片段，下面展示被过滤镜头的主要原因。
            </p>
          </div>
          <span class="text-xs text-zinc-400 dark:text-zinc-500">
            共 {{ filteredItems.length }} 个镜头被过滤
          </span>
        </div>

        <div v-if="filteredSummaryEntries.length" class="mt-4 flex flex-wrap gap-2">
          <span
            v-for="[reason, count] in filteredSummaryEntries"
            :key="reason"
            class="rounded-full border border-zinc-200 bg-white px-2.5 py-1 text-[11px] text-zinc-600 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300"
          >
            {{ formatFilteredSummaryReason(reason) }}: {{ count }}
          </span>
        </div>

        <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <div
            v-for="item in filteredItems.slice(0, 6)"
            :key="item.source_shot_segment_id || item.segment_index || `${item.start_ms}-${item.end_ms}`"
            class="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950"
          >
            <div class="flex items-start justify-between gap-2">
              <p class="min-w-0 truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {{ item.title || `镜头 ${item.segment_index || "-"}` }}
              </p>
              <span class="shrink-0 text-xs tabular-nums text-zinc-400">
                {{ formatRange(item.start_ms, item.end_ms) }}
              </span>
            </div>

            <p class="mt-2 text-xs text-amber-600 dark:text-amber-400">
              {{ formatFilteredReason(item) }}
              <span v-if="typeof item.signal_score === 'number'" class="ml-1 text-zinc-400 dark:text-zinc-500">
                信号分 {{ item.signal_score }}
              </span>
            </p>

            <p
              v-if="item.transcript_text || item.visual_summary"
              class="mt-2 line-clamp-3 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400"
            >
              {{ item.transcript_text || item.visual_summary }}
            </p>

            <div v-if="item.matched_sources?.length || item.matched_labels?.length" class="mt-2 flex flex-wrap gap-1">
              <span
                v-for="source in item.matched_sources || []"
                :key="source"
                class="rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
              >
                {{ source }}
              </span>
              <span
                v-for="label in item.matched_labels || []"
                :key="label"
                class="rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
              >
                {{ label }}
              </span>
            </div>
          </div>
        </div>
      </div>

      </div><!-- /mx-auto max-w-4xl -->
    </div><!-- /scrollable content area -->

    <Dialog v-model:open="showMotionDetail">
      <DialogContent class="max-w-4xl rounded-[28px] border-zinc-200 p-0 dark:border-zinc-800">
        <div v-if="selectedMotion" class="overflow-hidden">
          <div class="grid gap-0 lg:grid-cols-[1.05fr_1.2fr]">
            <div class="border-b border-zinc-200 bg-zinc-950 lg:border-b-0 lg:border-r dark:border-zinc-800">
              <img
                v-if="resolveMotionThumbnailUrl(selectedMotion)"
                :src="resolveMotionThumbnailUrl(selectedMotion) || undefined"
                class="aspect-video h-full w-full object-cover"
                alt="动作截图"
              />
              <div
                v-else
                class="flex aspect-video items-center justify-center text-sm text-white/40"
              >
                暂无动作截图
              </div>
            </div>

            <div class="bg-white p-6 dark:bg-zinc-950">
              <DialogHeader class="pr-10">
                <DialogTitle class="text-xl font-semibold text-zinc-950 dark:text-zinc-50">
                  {{ selectedMotion.action_label || "动作资产详情" }}
                </DialogTitle>
              </DialogHeader>

              <div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                <span>{{ formatRange(selectedMotion.start_ms, selectedMotion.end_ms) }}</span>
                <span>·</span>
                <span>{{ formatDuration(selectedMotion.start_ms, selectedMotion.end_ms) }}</span>
                <span>·</span>
                <span>置信度 {{ confidenceText(selectedMotion) }}</span>
              </div>

              <div class="mt-5 overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-950 dark:border-zinc-800">
                <video
                  v-if="resolveMotionClipUrl(selectedMotion)"
                  :src="resolveMotionClipUrl(selectedMotion) || undefined"
                  controls
                  preload="metadata"
                  class="aspect-video w-full object-contain"
                />
                <div
                  v-else
                  class="flex aspect-video items-center justify-center text-sm text-white/40"
                >
                  暂无动作片段
                </div>
              </div>

              <div class="mt-5 rounded-2xl border border-zinc-200 bg-zinc-50/70 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
                <p class="text-xs font-medium uppercase tracking-wide text-zinc-400 dark:text-zinc-500">
                  动作摘要
                </p>
                <p class="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
                  {{ selectedMotion.action_summary || "暂无摘要" }}
                </p>
              </div>

              <div class="mt-4 flex flex-wrap gap-2">
                <span
                  v-if="selectedMotion.emotion_label"
                  class="rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-[11px] text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
                >
                  {{ selectedMotion.emotion_label }}
                </span>
                <span
                  v-if="selectedMotion.scene_label"
                  class="rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-[11px] text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
                >
                  {{ selectedMotion.scene_label }}
                </span>
                <span
                  v-if="selectedMotion.camera_motion"
                  class="rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-[11px] text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
                >
                  {{ selectedMotion.camera_motion }}
                </span>
                <span
                  v-if="selectedMotion.camera_shot"
                  class="rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-[11px] text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
                >
                  {{ selectedMotion.camera_shot }}
                </span>
                <span
                  v-if="selectedMotion.temperament_label"
                  class="rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-[11px] text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
                >
                  {{ selectedMotion.temperament_label }}
                </span>
                <span
                  v-if="selectedMotion.entrance_style"
                  class="rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-[11px] text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
                >
                  {{ selectedMotion.entrance_style }}
                </span>
              </div>

              <div class="mt-5 grid gap-3 sm:grid-cols-2">
                <div class="rounded-2xl border border-zinc-200 p-3 dark:border-zinc-800">
                  <p class="text-[11px] uppercase tracking-wide text-zinc-400 dark:text-zinc-500">截图资产</p>
                  <p class="mt-1 break-all text-xs text-zinc-700 dark:text-zinc-300">
                    {{ selectedMotion.thumbnail_asset_id || selectedMotion.metadata_json?.thumbnail_asset_id || "未生成" }}
                  </p>
                </div>
                <div class="rounded-2xl border border-zinc-200 p-3 dark:border-zinc-800">
                  <p class="text-[11px] uppercase tracking-wide text-zinc-400 dark:text-zinc-500">片段资产</p>
                  <p class="mt-1 break-all text-xs text-zinc-700 dark:text-zinc-300">
                    {{ selectedMotion.clip_asset_id || "未生成" }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    <div
      class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-[#fcfcfc] via-[#fcfcfc] dark:from-[#0f0f0f] dark:via-[#0f0f0f] to-transparent p-4 pt-12 lg:px-[120px] pb-8"
    >
      <div class="mx-auto w-full max-w-4xl">
        <div
          ref="glowRef"
          @mousemove="handleMouseMove"
          @mouseenter="isHovering = true"
          @mouseleave="isHovering = false"
          class="group relative rounded-3xl border border-border bg-muted/40 p-4 shadow-lg backdrop-blur-md transition-all focus-within:ring-2 focus-within:ring-blue-500/10"
        >
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
              class="glow rounded-[inherit] after:absolute after:inset-[calc(-1*var(--glowingeffect-border-width))] after:rounded-[inherit] after:[border:var(--glowingeffect-border-width)_solid_transparent] after:[background:var(--gradient)] after:[background-attachment:fixed] after:opacity-[var(--active)] after:transition-opacity after:duration-300 after:[mask-clip:padding-box,border-box] after:[mask-composite:intersect] after:[mask-image:linear-gradient(#0000,#0000),conic-gradient(from_calc((var(--start)-var(--spread))*1deg),#00000000_0deg,#fff,#00000000_calc(var(--spread)*2deg))]"
            />
          </div>

          <form @submit.prevent="startExtraction">
            <div class="relative">
              <div
                v-if="selectedFile || sourceUrl.trim()"
                class="mb-2 flex flex-wrap gap-2 px-1"
              >
                <div
                  v-if="selectedFile"
                  class="flex items-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50 p-3 pr-8 shadow-sm dark:border-zinc-700 dark:bg-zinc-800/50"
                >
                  <div class="flex size-10 items-center justify-center rounded-full border border-zinc-200 bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900">
                    <Upload class="size-4 text-zinc-500" />
                  </div>
                  <div class="min-w-0 pr-2">
                    <span class="block max-w-[220px] truncate text-[13px] font-bold text-zinc-700 dark:text-zinc-200">
                      {{ selectedFile.name }}
                    </span>
                    <span class="text-[11px] text-zinc-500 dark:text-zinc-400">
                      {{ (selectedFile.size / 1024 / 1024).toFixed(1) }} MB
                    </span>
                  </div>
                  <button
                    type="button"
                    @click.prevent="removeFile"
                    class="absolute right-2 top-2 inline-flex size-5 items-center justify-center rounded-full bg-zinc-200 text-zinc-600 hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-600"
                  >
                    <X class="size-3" />
                  </button>
                </div>

                <div
                  v-if="sourceUrl.trim()"
                  class="group relative flex h-16 max-w-[280px] shrink-0 items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 p-2 shadow-sm dark:border-zinc-700 dark:bg-zinc-800/50"
                >
                  <div class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-zinc-200/60 dark:bg-zinc-700/60">
                    <Link class="size-5 text-zinc-500" />
                  </div>
                  <div class="min-w-0 pr-5">
                    <span class="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-200">视频链接</span>
                    <span class="block truncate text-[10px] text-zinc-500">{{ sourceUrl }}</span>
                  </div>
                  <button
                    type="button"
                    @click.prevent="sourceUrl = ''"
                    class="absolute right-1 top-1 inline-flex size-5 items-center justify-center rounded-full bg-zinc-200 text-zinc-600 opacity-0 transition-opacity hover:bg-zinc-300 group-hover:opacity-100 dark:bg-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-600"
                  >
                    <X class="size-3" />
                  </button>
                </div>
              </div>

              <div class="mb-1.5 flex items-center text-xs text-muted-foreground">
                本次提取辅助提示
              </div>

              <Textarea
                ref="textareaRef"
                v-model="instructionText"
                placeholder="可选：补充本次提取关注重点，例如：优先提取工厂欢迎、设备操作、产品特写。它只会辅助排序和精标，不会覆盖系统默认规则。"
                class="flex min-h-[60px] w-full resize-none overflow-hidden border-none bg-transparent px-0 py-2 text-sm text-foreground shadow-none placeholder:text-muted-foreground focus-visible:ring-0"
                rows="2"
              />

              <div class="mt-2 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    @click="triggerFileInput"
                    class="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full bg-secondary px-3 text-xs font-medium text-secondary-foreground shadow-sm transition-colors hover:bg-secondary/80 h-8"
                  >
                    <Upload class="h-3.5 w-3.5" />
                    上传视频
                  </button>
                  <button
                    type="button"
                    @click="openLinkModal"
                    class="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full bg-secondary px-3 text-xs font-medium text-secondary-foreground shadow-sm transition-colors hover:bg-secondary/80 h-8"
                  >
                    <Link class="h-3.5 w-3.5" />
                    添加链接
                  </button>
                </div>

                <button
                  type="submit"
                  :disabled="!canSubmit"
                  class="inline-flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground shadow transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
                >
                  <Loader2 v-if="starting" class="h-4 w-4 animate-spin" />
                  <ArrowUp v-else class="h-4 w-4" />
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>

    <Dialog v-model:open="showLinkModal">
      <DialogContent
        class="sm:max-w-[425px] rounded-[32px] border-zinc-100 bg-white px-6 py-6 shadow-2xl backdrop-blur-xl dark:border-zinc-800 dark:bg-zinc-900/80 sm:px-7 sm:py-7"
      >
        <DialogHeader class="pr-12">
          <DialogTitle class="text-xl font-bold">添加视频链接</DialogTitle>
        </DialogHeader>
        <div class="py-2">
          <Textarea
            v-model="linkDraft"
            rows="4"
            class="w-full rounded-2xl border bg-zinc-50 px-4 py-3 text-sm focus-visible:ring-2 focus-visible:ring-blue-500/10 dark:border-zinc-700 dark:bg-zinc-800/50"
            placeholder="https://..."
          />
        </div>
        <DialogFooter class="mt-2 gap-3">
          <Button
            variant="outline"
            size="sm"
            @click="showLinkModal = false"
            class="rounded-lg px-4 shadow-none"
          >
            取消
          </Button>
          <Button
            size="sm"
            @click="confirmLink"
            class="rounded-lg bg-zinc-900 px-4 text-white shadow-none hover:bg-zinc-800 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            确认
          </Button>
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
  background: rgba(161, 161, 170, 0.2);
  border-radius: 9999px;
}
</style>
