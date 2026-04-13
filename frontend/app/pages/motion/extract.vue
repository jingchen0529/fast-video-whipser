<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  Sparkles,
  RefreshCw,
  Play,
  CheckCircle2,
  Loader2,
  CircleDashed,
  AlertCircle,
  Check,
  X,
  Library,
} from "lucide-vue-next";
import { toast } from "vue-sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { notifyError, formatDateTime } from "@/utils/common";
import type { Job, MotionAsset } from "@/types/api";

definePageMeta({
  layout: "console",
  middleware: "auth",
  ssr: false,
});

useHead({ title: "动作提取" });

type ProjectOption = {
  id: number;
  title: string;
  workflow_type: string;
  status: string;
  updated_at: string;
};

type MotionExtractionStep = {
  step_key: string;
  title: string;
  detail: string;
  status: string;
  error_detail?: string | null;
};

const apiService = useApi();
const api = apiService.requestData;
const router = useRouter();

const loadingProjects = ref(false);
const projects = ref<ProjectOption[]>([]);
const selectedProjectId = ref<string>("");

const starting = ref(false);
const currentJob = ref<Job | null>(null);
const extractedItems = ref<MotionAsset[]>([]);
const selectedIds = ref<string[]>([]);
const reviewing = ref(false);

let pollingTimer: ReturnType<typeof setInterval> | null = null;

const availableProjects = computed(() =>
  projects.value.filter(
    (item) =>
      item.workflow_type === "analysis" &&
      ["succeeded", "ready"].includes(String(item.status || "").toLowerCase()),
  ),
);

const steps = computed<MotionExtractionStep[]>(() => {
  const raw = currentJob.value?.result_json?.steps;
  return Array.isArray(raw) ? raw : [];
});

const pendingItems = computed(() =>
  extractedItems.value.filter((item) => item.review_status === "auto_tagged"),
);

const canSubmit = computed(() => !!selectedProjectId.value && !starting.value);

const hasSelectableItems = computed(() => pendingItems.value.length > 0);

const formatRange = (startMs: number, endMs: number) => {
  const formatPoint = (value: number) => {
    const seconds = Math.max(0, Math.floor(value / 1000));
    const minutes = Math.floor(seconds / 60)
      .toString()
      .padStart(2, "0");
    const remain = (seconds % 60).toString().padStart(2, "0");
    return `${minutes}:${remain}`;
  };
  return `${formatPoint(startMs)} - ${formatPoint(endMs)}`;
};

const reviewStatusLabel = (status?: string | null) => {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "approved") return "已入库";
  if (normalized === "rejected") return "已驳回";
  return "待审核";
};

const stepIcon = (status: string) => {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "completed") return CheckCircle2;
  if (normalized === "running" || normalized === "in_progress") return Loader2;
  if (normalized === "failed") return AlertCircle;
  return CircleDashed;
};

const stopPolling = () => {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
};

const fetchProjects = async () => {
  loadingProjects.value = true;
  try {
    const data = await api<ProjectOption[]>("/projects");
    projects.value = data || [];
    if (!selectedProjectId.value && availableProjects.value.length) {
      selectedProjectId.value = String(availableProjects.value[0].id);
    }
  } catch (error) {
    notifyError(apiService, error, "加载项目列表失败");
  } finally {
    loadingProjects.value = false;
  }
};

const refreshJob = async (jobId: string) => {
  try {
    const job = await api<Job>(`/jobs/${jobId}`);
    currentJob.value = job;
    const items = job.result_json?.items;
    extractedItems.value = Array.isArray(items) ? items : [];

    if (["succeeded", "failed", "cancelled"].includes(String(job.status || "").toLowerCase())) {
      stopPolling();
      if (job.status === "succeeded") {
        toast.success(
          `动作提取完成，生成 ${job.result_json?.saved_count || 0} 条动作资产。`,
        );
      }
    }
  } catch (error) {
    stopPolling();
    notifyError(apiService, error, "刷新动作提取状态失败");
  }
};

const startPolling = (jobId: string) => {
  stopPolling();
  pollingTimer = setInterval(() => {
    refreshJob(jobId);
  }, 2000);
};

const startExtraction = async () => {
  if (!canSubmit.value) return;
  starting.value = true;
  selectedIds.value = [];
  extractedItems.value = [];
  currentJob.value = null;

  try {
    const result = await api<{ job_id: string }>("/assets/motions/extract", {
      method: "POST",
      body: { project_id: Number(selectedProjectId.value) },
    });
    await refreshJob(result.job_id);
    if (currentJob.value && !["succeeded", "failed", "cancelled"].includes(String(currentJob.value.status || "").toLowerCase())) {
      startPolling(result.job_id);
    }
  } catch (error) {
    notifyError(apiService, error, "启动动作提取失败");
  } finally {
    starting.value = false;
  }
};

const toggleSelection = (assetId: string) => {
  const index = selectedIds.value.indexOf(assetId);
  if (index >= 0) {
    selectedIds.value.splice(index, 1);
  } else {
    selectedIds.value.push(assetId);
  }
};

const toggleAll = () => {
  if (selectedIds.value.length === pendingItems.value.length) {
    selectedIds.value = [];
    return;
  }
  selectedIds.value = pendingItems.value.map((item) => item.id);
};

const applyBatchReview = async (action: "approve" | "reject") => {
  if (!selectedIds.value.length) return;
  reviewing.value = true;
  try {
    const result = await api<{ reviewed_count: number }>("/assets/motions/batch-review", {
      method: "POST",
      body: {
        ids: selectedIds.value,
        action,
      },
    });
    extractedItems.value = extractedItems.value.map((item) => {
      if (!selectedIds.value.includes(item.id)) return item;
      return {
        ...item,
        review_status: action === "approve" ? "approved" : "rejected",
      };
    });
    toast.success(
      `${action === "approve" ? "已入库" : "已驳回"} ${result.reviewed_count} 条动作资产。`,
    );
    selectedIds.value = [];
  } catch (error) {
    notifyError(apiService, error, "批量审核失败");
  } finally {
    reviewing.value = false;
  }
};

const openLibrary = () => {
  router.push("/assets/motions");
};

onMounted(fetchProjects);
onUnmounted(stopPolling);
</script>

<template>
  <div class="h-full w-full overflow-hidden bg-white p-6 dark:bg-[#121212]">
    <div class="mx-auto flex h-full max-w-6xl flex-col gap-6">
      <div class="rounded-3xl border border-zinc-200 bg-zinc-50/60 p-6 dark:border-zinc-800 dark:bg-zinc-950/60">
        <div class="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div class="space-y-2">
            <div class="inline-flex w-fit items-center gap-2 rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-medium text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
              <Sparkles class="size-3.5" />
              从已分析项目提取动作资产
            </div>
            <div>
              <h1 class="text-3xl font-bold tracking-tight text-zinc-950 dark:text-zinc-50">
                动作提取工作台
              </h1>
              <p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                当前版本先支持从已完成视频分析的项目触发动作提取，并在提取完成后直接做审核流转。
              </p>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <Button
              variant="outline"
              class="h-10 rounded-xl"
              :disabled="loadingProjects"
              @click="fetchProjects"
            >
              <RefreshCw :class="['mr-2 size-4', loadingProjects && 'animate-spin']" />
              刷新项目
            </Button>
            <Button variant="outline" class="h-10 rounded-xl" @click="openLibrary">
              <Library class="mr-2 size-4" />
              打开资产库
            </Button>
          </div>
        </div>
      </div>

      <div class="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <section class="rounded-3xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <div class="space-y-5">
            <div>
              <p class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                选择已分析项目
              </p>
              <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                这里只展示 `analysis` 且已完成的视频分析项目。
              </p>
            </div>

            <Select v-model="selectedProjectId">
              <SelectTrigger class="h-11 rounded-2xl border-zinc-200 dark:border-zinc-800">
                <SelectValue placeholder="选择一个已分析项目" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="project in availableProjects"
                  :key="project.id"
                  :value="String(project.id)"
                >
                  {{ project.title }}
                </SelectItem>
              </SelectContent>
            </Select>

            <div
              v-if="selectedProjectId"
              class="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900/60"
            >
              <p class="text-xs text-zinc-500">最近更新时间</p>
              <p class="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
                {{
                  formatDateTime(
                    availableProjects.find((item) => String(item.id) === selectedProjectId)?.updated_at,
                  )
                }}
              </p>
            </div>

            <Button
              class="h-11 rounded-2xl"
              :disabled="!canSubmit"
              @click="startExtraction"
            >
              <Loader2 v-if="starting" class="mr-2 size-4 animate-spin" />
              <Play v-else class="mr-2 size-4" />
              {{ starting ? "启动中..." : "开始动作提取" }}
            </Button>

            <div
              v-if="!availableProjects.length && !loadingProjects"
              class="rounded-2xl border border-dashed border-zinc-200 px-4 py-6 text-sm text-zinc-500 dark:border-zinc-800 dark:text-zinc-400"
            >
              当前没有可用于动作提取的已分析项目。请先在“视频分析”里跑完一个项目。
            </div>
          </div>
        </section>

        <section class="rounded-3xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                提取进度
              </p>
              <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                基于 job 状态轮询，展示动作提取的步骤流转。
              </p>
            </div>
            <Badge
              v-if="currentJob"
              variant="outline"
              class="border-zinc-200 dark:border-zinc-800"
            >
              {{ currentJob.status }}
            </Badge>
          </div>

          <div v-if="!steps.length" class="mt-6 rounded-2xl border border-dashed border-zinc-200 px-4 py-10 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
            还没有运行中的动作提取任务。
          </div>

          <div v-else class="mt-6 space-y-3">
            <div
              v-for="step in steps"
              :key="step.step_key"
              class="flex items-start gap-3 rounded-2xl border border-zinc-200 bg-zinc-50/60 px-4 py-4 dark:border-zinc-800 dark:bg-zinc-900/50"
            >
              <component
                :is="stepIcon(step.status)"
                :class="[
                  'mt-0.5 size-5 shrink-0',
                  step.status === 'completed' && 'text-emerald-500',
                  (step.status === 'running' || step.status === 'in_progress') && 'animate-spin text-blue-500',
                  step.status === 'failed' && 'text-red-500',
                  step.status === 'pending' && 'text-zinc-300 dark:text-zinc-600',
                ]"
              />
              <div class="min-w-0 flex-1">
                <p class="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {{ step.title }}
                </p>
                <p class="mt-1 text-xs leading-5 text-zinc-500 dark:text-zinc-400">
                  {{ step.detail }}
                </p>
                <p
                  v-if="step.error_detail"
                  class="mt-2 text-xs text-red-500"
                >
                  {{ step.error_detail }}
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>

      <section class="min-h-0 flex-1 overflow-hidden rounded-3xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              候选结果
            </p>
            <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              当前展示本次动作提取写入的动作资产，可直接批量入库或驳回。
            </p>
          </div>

          <div class="flex items-center gap-2">
            <div
              v-if="hasSelectableItems"
              class="flex items-center gap-2 rounded-full border border-zinc-200 px-3 py-1.5 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400"
            >
              <Checkbox
                :checked="selectedIds.length > 0 && selectedIds.length === pendingItems.length"
                @update:checked="toggleAll"
              />
              <span>全选待审核</span>
            </div>
            <Button
              variant="outline"
              class="h-9 rounded-xl"
              :disabled="!selectedIds.length || reviewing"
              @click="applyBatchReview('reject')"
            >
              <X class="mr-1.5 size-4" />
              批量驳回
            </Button>
            <Button
              class="h-9 rounded-xl"
              :disabled="!selectedIds.length || reviewing"
              @click="applyBatchReview('approve')"
            >
              <Check class="mr-1.5 size-4" />
              批量入库
            </Button>
          </div>
        </div>

        <div
          v-if="!extractedItems.length"
          class="mt-6 flex h-[320px] items-center justify-center rounded-2xl border-2 border-dashed border-zinc-200 text-sm text-zinc-500 dark:border-zinc-800 dark:text-zinc-400"
        >
          本次任务还没有产出动作资产。
        </div>

        <div v-else class="custom-scrollbar mt-6 h-[calc(100%-72px)] overflow-y-auto pr-1">
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div
              v-for="item in extractedItems"
              :key="item.id"
              class="rounded-2xl border border-zinc-200 bg-zinc-50/50 p-4 dark:border-zinc-800 dark:bg-zinc-900/50"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-start gap-3">
                  <Checkbox
                    v-if="item.review_status === 'auto_tagged'"
                    :checked="selectedIds.includes(item.id)"
                    @update:checked="toggleSelection(item.id)"
                  />
                  <div>
                    <p class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                      {{ item.action_label || "未标注动作" }}
                    </p>
                    <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {{ formatRange(item.start_ms, item.end_ms) }}
                    </p>
                  </div>
                </div>

                <Badge
                  variant="outline"
                  :class="[
                    'border',
                    item.review_status === 'approved' && 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/30 dark:bg-emerald-950/30 dark:text-emerald-300',
                    item.review_status === 'rejected' && 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/30 dark:bg-red-950/30 dark:text-red-300',
                    item.review_status === 'auto_tagged' && 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/30 dark:text-amber-300',
                  ]"
                >
                  {{ reviewStatusLabel(item.review_status) }}
                </Badge>
              </div>

              <p class="mt-3 line-clamp-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                {{ item.action_summary }}
              </p>

              <div class="mt-4 flex flex-wrap gap-2">
                <Badge v-if="item.emotion_label" variant="outline">{{ item.emotion_label }}</Badge>
                <Badge v-if="item.scene_label" variant="outline">{{ item.scene_label }}</Badge>
                <Badge v-if="item.camera_motion" variant="outline">{{ item.camera_motion }}</Badge>
                <Badge v-if="item.camera_shot" variant="outline">{{ item.camera_shot }}</Badge>
              </div>

              <div class="mt-4 border-t border-zinc-200 pt-4 dark:border-zinc-800">
                <div class="flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
                  <span>置信度 {{ item.metadata_json?.confidence ? `${Math.round(Number(item.metadata_json.confidence) * 100)}%` : "未标注" }}</span>
                  <span>{{ formatDateTime(item.updated_at) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(161, 161, 170, 0.35);
  border-radius: 9999px;
}
</style>
