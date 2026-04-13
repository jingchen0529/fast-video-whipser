<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  RefreshCw,
  Search,
  Film,
  Tag,
  Shapes,
  MapPin,
  Sparkles,
  Clock3,
  ChevronRight,
  AlertCircle,
} from "lucide-vue-next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { notifyError, formatDateTime } from "@/utils/common";
import type { MotionAsset, MotionAssetListPayload } from "@/types/api";

definePageMeta({
  layout: "console",
  middleware: "auth",
  ssr: false,
});

useHead({ title: "动作资产库" });

type MotionAssetGroup = {
  groupKey: string;
  sourceVideoAssetId: string | null;
  sourceVideoName: string;
  sourceVideoUrl: string | null;
  items: MotionAsset[];
  actionLabels: string[];
};

const apiService = useApi();
const api = apiService.requestData;
const runtimeConfig = useRuntimeConfig();

const loading = ref(false);
const items = ref<MotionAsset[]>([]);
const searchInput = ref("");
const appliedKeyword = ref("");
const actionFilter = ref("__all");
const sceneFilter = ref("__all");
const reviewFilter = ref("__all");
const selectedItem = ref<MotionAsset | null>(null);
const showDetail = ref(false);

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

const reviewStatusLabel = (status?: string | null) => {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "approved") return "已入库";
  if (normalized === "rejected") return "已驳回";
  if (normalized === "draft") return "草稿";
  return "待审核";
};

const reviewStatusClass = (status?: string | null) => {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "approved") {
    return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/30 dark:bg-emerald-950/30 dark:text-emerald-300";
  }
  if (normalized === "rejected") {
    return "border-red-200 bg-red-50 text-red-700 dark:border-red-900/30 dark:bg-red-950/30 dark:text-red-300";
  }
  return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/30 dark:text-amber-300";
};

const confidenceText = (item: MotionAsset) => {
  const raw = item.metadata_json?.confidence;
  const normalized =
    typeof raw === "number" ? raw : Number.parseFloat(String(raw || ""));
  if (Number.isNaN(normalized)) return "未标注";
  return `${Math.round(normalized * 100)}%`;
};

const fetchMotionAssets = async () => {
  loading.value = true;
  try {
    const params = new URLSearchParams();
    if (appliedKeyword.value.trim()) params.set("q", appliedKeyword.value.trim());
    if (actionFilter.value !== "__all") params.set("action_label", actionFilter.value);
    if (sceneFilter.value !== "__all") params.set("scene_label", sceneFilter.value);
    if (reviewFilter.value !== "__all") params.set("review_status", reviewFilter.value);
    params.set("limit", "100");

    const query = params.toString();
    const data = await api<MotionAssetListPayload>(
      `/assets/motions${query ? `?${query}` : ""}`,
    );
    items.value = data.items || [];
  } catch (error) {
    notifyError(apiService, error, "加载动作资产失败");
  } finally {
    loading.value = false;
  }
};

const handleSearch = async () => {
  appliedKeyword.value = searchInput.value.trim();
  await fetchMotionAssets();
};

const handleFilterChange = async () => {
  await fetchMotionAssets();
};

const resetFilters = async () => {
  searchInput.value = "";
  appliedKeyword.value = "";
  actionFilter.value = "__all";
  sceneFilter.value = "__all";
  reviewFilter.value = "__all";
  await fetchMotionAssets();
};

const actionOptions = computed(() =>
  [...new Set(items.value.map((item) => item.action_label).filter(Boolean))]
    .sort((a, b) => String(a).localeCompare(String(b), "zh-CN")),
);

const sceneOptions = computed(() =>
  [...new Set(items.value.map((item) => item.scene_label).filter(Boolean))]
    .sort((a, b) => String(a).localeCompare(String(b), "zh-CN")),
);

const groupedItems = computed<MotionAssetGroup[]>(() => {
  const groups = new Map<string, MotionAssetGroup>();

  for (const item of items.value) {
    const sourceVideoAssetId = item.source_video_asset_id || null;
    const groupKey = sourceVideoAssetId || `unknown-${item.id}`;
    const sourceVideoName =
      item.source_video_asset?.file_name ||
      (sourceVideoAssetId ? `源视频 ${sourceVideoAssetId.slice(0, 8)}` : "未关联源视频");
    const sourceVideoUrl = resolveAssetUrl(sourceVideoAssetId);

    if (!groups.has(groupKey)) {
      groups.set(groupKey, {
        groupKey,
        sourceVideoAssetId,
        sourceVideoName,
        sourceVideoUrl,
        items: [],
        actionLabels: [],
      });
    }

    const group = groups.get(groupKey)!;
    group.items.push(item);
  }

  return [...groups.values()]
    .map((group) => {
      group.items.sort((a, b) => a.start_ms - b.start_ms);
      group.actionLabels = [
        ...new Set(group.items.map((item) => item.action_label).filter(Boolean)),
      ] as string[];
      return group;
    })
    .sort((a, b) => b.items.length - a.items.length);
});

const stats = computed(() => ({
  videoCount: groupedItems.value.length,
  motionCount: items.value.length,
  pendingCount: items.value.filter((item) => item.review_status === "auto_tagged").length,
  approvedCount: items.value.filter((item) => item.review_status === "approved").length,
}));

const openDetail = (item: MotionAsset) => {
  selectedItem.value = item;
  showDetail.value = true;
};

onMounted(fetchMotionAssets);
</script>

<template>
  <div class="h-full w-full overflow-hidden bg-white p-6 dark:bg-[#121212]">
    <div class="mx-auto flex h-full max-w-7xl flex-col gap-6">
      <div class="flex flex-col gap-4 rounded-3xl border border-zinc-200 bg-zinc-50/60 p-6 dark:border-zinc-800 dark:bg-zinc-950/70">
        <div class="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div class="space-y-2">
            <div class="inline-flex w-fit items-center gap-2 rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-medium text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
              <Sparkles class="size-3.5" />
              每个视频拆成多个动作标签分镜
            </div>
            <div>
              <h1 class="text-3xl font-bold tracking-tight text-zinc-950 dark:text-zinc-50">
                动作资产库
              </h1>
              <p class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                按来源视频聚合查看动作资产，重点看每段分镜对应的动作标签、情绪、场景和运镜。
              </p>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <Button
              variant="outline"
              class="h-10 rounded-xl"
              :disabled="loading"
              @click="fetchMotionAssets"
            >
              <RefreshCw :class="['mr-2 size-4', loading && 'animate-spin']" />
              刷新
            </Button>
          </div>
        </div>

        <div class="grid gap-3 md:grid-cols-4">
          <div class="rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
            <p class="text-xs text-zinc-500">来源视频</p>
            <p class="mt-2 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">
              {{ stats.videoCount }}
            </p>
          </div>
          <div class="rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
            <p class="text-xs text-zinc-500">动作分镜</p>
            <p class="mt-2 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">
              {{ stats.motionCount }}
            </p>
          </div>
          <div class="rounded-2xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/30 dark:bg-amber-950/20">
            <p class="text-xs text-amber-700 dark:text-amber-300">待审核</p>
            <p class="mt-2 text-2xl font-semibold text-amber-900 dark:text-amber-100">
              {{ stats.pendingCount }}
            </p>
          </div>
          <div class="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900/30 dark:bg-emerald-950/20">
            <p class="text-xs text-emerald-700 dark:text-emerald-300">已入库</p>
            <p class="mt-2 text-2xl font-semibold text-emerald-900 dark:text-emerald-100">
              {{ stats.approvedCount }}
            </p>
          </div>
        </div>
      </div>

      <div class="grid gap-3 rounded-3xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950 lg:grid-cols-[minmax(0,2fr)_220px_220px_220px_auto]">
        <div class="flex items-center gap-2 rounded-2xl border border-zinc-200 bg-zinc-50 px-3 dark:border-zinc-800 dark:bg-zinc-900/60">
          <Search class="size-4 text-zinc-400" />
          <Input
            v-model="searchInput"
            placeholder="搜索动作摘要"
            class="border-0 bg-transparent px-0 shadow-none focus-visible:ring-0"
            @keyup.enter="handleSearch"
          />
        </div>

        <Select v-model="actionFilter" @update:model-value="handleFilterChange">
          <SelectTrigger class="h-11 rounded-2xl border-zinc-200 dark:border-zinc-800">
            <SelectValue placeholder="动作标签" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all">全部动作</SelectItem>
            <SelectItem
              v-for="option in actionOptions"
              :key="option"
              :value="option"
            >
              {{ option }}
            </SelectItem>
          </SelectContent>
        </Select>

        <Select v-model="sceneFilter" @update:model-value="handleFilterChange">
          <SelectTrigger class="h-11 rounded-2xl border-zinc-200 dark:border-zinc-800">
            <SelectValue placeholder="场景标签" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all">全部场景</SelectItem>
            <SelectItem
              v-for="option in sceneOptions"
              :key="option"
              :value="option"
            >
              {{ option }}
            </SelectItem>
          </SelectContent>
        </Select>

        <Select v-model="reviewFilter" @update:model-value="handleFilterChange">
          <SelectTrigger class="h-11 rounded-2xl border-zinc-200 dark:border-zinc-800">
            <SelectValue placeholder="审核状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all">全部状态</SelectItem>
            <SelectItem value="auto_tagged">待审核</SelectItem>
            <SelectItem value="approved">已入库</SelectItem>
            <SelectItem value="rejected">已驳回</SelectItem>
          </SelectContent>
        </Select>

        <div class="flex items-center gap-2">
          <Button class="h-11 rounded-2xl" :disabled="loading" @click="handleSearch">
            查询
          </Button>
          <Button
            variant="outline"
            class="h-11 rounded-2xl"
            :disabled="loading"
            @click="resetFilters"
          >
            重置
          </Button>
        </div>
      </div>

      <div class="custom-scrollbar min-h-0 flex-1 overflow-y-auto pr-1">
        <div
          v-if="loading && !groupedItems.length"
          class="flex h-full min-h-[320px] items-center justify-center"
        >
          <RefreshCw class="size-6 animate-spin text-zinc-300" />
        </div>

        <div
          v-else-if="!groupedItems.length"
          class="flex min-h-[320px] flex-col items-center justify-center rounded-3xl border-2 border-dashed border-zinc-200 bg-zinc-50/40 text-center dark:border-zinc-800 dark:bg-zinc-900/20"
        >
          <Film class="size-10 text-zinc-300" />
          <p class="mt-4 text-lg font-medium text-zinc-700 dark:text-zinc-300">
            还没有可展示的动作资产
          </p>
          <p class="mt-2 max-w-lg text-sm text-zinc-500 dark:text-zinc-400">
            先在视频分析或动作提取流程里产出动作资产，之后这里会按来源视频自动聚合展示。
          </p>
        </div>

        <div v-else class="space-y-6">
          <section
            v-for="group in groupedItems"
            :key="group.groupKey"
            class="overflow-hidden rounded-3xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950"
          >
            <div class="grid gap-5 border-b border-zinc-200 p-5 dark:border-zinc-800 lg:grid-cols-[320px_minmax(0,1fr)]">
              <div class="overflow-hidden rounded-2xl border border-zinc-200 bg-black dark:border-zinc-800">
                <video
                  v-if="group.sourceVideoUrl"
                  :src="group.sourceVideoUrl"
                  controls
                  class="aspect-video w-full object-contain"
                />
                <div
                  v-else
                  class="flex aspect-video items-center justify-center text-sm text-white/50"
                >
                  暂无源视频预览
                </div>
              </div>

              <div class="flex min-w-0 flex-col justify-between gap-4">
                <div class="space-y-3">
                  <div class="flex flex-wrap items-center gap-2">
                    <Badge class="border-zinc-200 bg-zinc-100 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                      <Film class="mr-1 size-3.5" />
                      {{ group.items.length }} 条分镜动作
                    </Badge>
                    <Badge
                      v-for="label in group.actionLabels.slice(0, 6)"
                      :key="label"
                      variant="outline"
                      class="border-zinc-200 text-zinc-600 dark:border-zinc-700 dark:text-zinc-300"
                    >
                      {{ label }}
                    </Badge>
                  </div>

                  <div>
                    <h2 class="truncate text-xl font-semibold text-zinc-950 dark:text-zinc-50">
                      {{ group.sourceVideoName }}
                    </h2>
                    <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      Source Asset ID:
                      {{ group.sourceVideoAssetId || "未关联" }}
                    </p>
                  </div>
                </div>

                <div class="flex flex-wrap items-center gap-4 text-sm text-zinc-500 dark:text-zinc-400">
                  <span class="inline-flex items-center gap-1.5">
                    <Tag class="size-4" />
                    标签化动作分镜库
                  </span>
                  <span class="inline-flex items-center gap-1.5">
                    <Shapes class="size-4" />
                    按源视频聚合
                  </span>
                </div>
              </div>
            </div>

            <div class="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
              <button
                v-for="item in group.items"
                :key="item.id"
                type="button"
                class="group rounded-2xl border border-zinc-200 bg-zinc-50/40 p-4 text-left transition-all hover:-translate-y-0.5 hover:border-zinc-300 hover:bg-white hover:shadow-sm dark:border-zinc-800 dark:bg-zinc-900/50 dark:hover:border-zinc-700 dark:hover:bg-zinc-900"
                @click="openDetail(item)"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="space-y-1">
                    <p class="text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                      {{ item.action_label || "未标注动作" }}
                    </p>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">
                      {{ formatRange(item.start_ms, item.end_ms) }}
                    </p>
                  </div>

                  <span
                    class="inline-flex shrink-0 items-center rounded-full border px-2 py-1 text-xs font-medium"
                    :class="reviewStatusClass(item.review_status)"
                  >
                    {{ reviewStatusLabel(item.review_status) }}
                  </span>
                </div>

                <p class="mt-3 line-clamp-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                  {{ item.action_summary }}
                </p>

                <div class="mt-4 flex flex-wrap gap-2">
                  <Badge
                    v-if="item.emotion_label"
                    variant="outline"
                    class="border-zinc-200 text-zinc-600 dark:border-zinc-700 dark:text-zinc-300"
                  >
                    {{ item.emotion_label }}
                  </Badge>
                  <Badge
                    v-if="item.scene_label"
                    variant="outline"
                    class="border-zinc-200 text-zinc-600 dark:border-zinc-700 dark:text-zinc-300"
                  >
                    {{ item.scene_label }}
                  </Badge>
                  <Badge
                    v-if="item.camera_motion"
                    variant="outline"
                    class="border-zinc-200 text-zinc-600 dark:border-zinc-700 dark:text-zinc-300"
                  >
                    {{ item.camera_motion }}
                  </Badge>
                </div>

                <div class="mt-4 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
                  <span class="inline-flex items-center gap-1.5">
                    <Clock3 class="size-3.5" />
                    {{ formatDuration(item.start_ms, item.end_ms) }}
                  </span>
                  <span class="inline-flex items-center gap-1.5">
                    <Sparkles class="size-3.5" />
                    置信度 {{ confidenceText(item) }}
                  </span>
                  <ChevronRight class="size-4 transition-transform group-hover:translate-x-0.5" />
                </div>
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>

    <Dialog v-model:open="showDetail">
      <DialogContent class="max-w-2xl rounded-3xl border-zinc-200 dark:border-zinc-800">
        <DialogHeader>
          <DialogTitle class="text-xl">
            {{ selectedItem?.action_label || "动作资产详情" }}
          </DialogTitle>
          <DialogDescription>
            {{ selectedItem ? formatRange(selectedItem.start_ms, selectedItem.end_ms) : "" }}
          </DialogDescription>
        </DialogHeader>

        <div v-if="selectedItem" class="space-y-5">
          <div class="grid gap-3 md:grid-cols-2">
            <div class="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p class="text-xs text-zinc-500">动作摘要</p>
              <p class="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
                {{ selectedItem.action_summary }}
              </p>
            </div>

            <div class="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p class="text-xs text-zinc-500">来源视频</p>
              <p class="mt-2 break-all text-sm text-zinc-700 dark:text-zinc-300">
                {{
                  selectedItem.source_video_asset?.file_name
                    || selectedItem.source_video_asset_id
                    || "未关联源视频"
                }}
              </p>
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-3">
            <div class="rounded-2xl border border-zinc-200 p-4 dark:border-zinc-800">
              <p class="text-xs text-zinc-500">审核状态</p>
              <p class="mt-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {{ reviewStatusLabel(selectedItem.review_status) }}
              </p>
            </div>
            <div class="rounded-2xl border border-zinc-200 p-4 dark:border-zinc-800">
              <p class="text-xs text-zinc-500">置信度</p>
              <p class="mt-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {{ confidenceText(selectedItem) }}
              </p>
            </div>
            <div class="rounded-2xl border border-zinc-200 p-4 dark:border-zinc-800">
              <p class="text-xs text-zinc-500">创建时间</p>
              <p class="mt-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {{ formatDateTime(selectedItem.created_at) }}
              </p>
            </div>
          </div>

          <div class="flex flex-wrap gap-2">
            <Badge
              v-if="selectedItem.emotion_label"
              variant="outline"
              class="border-zinc-200 dark:border-zinc-700"
            >
              <AlertCircle class="mr-1 size-3.5" />
              {{ selectedItem.emotion_label }}
            </Badge>
            <Badge
              v-if="selectedItem.scene_label"
              variant="outline"
              class="border-zinc-200 dark:border-zinc-700"
            >
              <MapPin class="mr-1 size-3.5" />
              {{ selectedItem.scene_label }}
            </Badge>
            <Badge
              v-if="selectedItem.camera_motion"
              variant="outline"
              class="border-zinc-200 dark:border-zinc-700"
            >
              {{ selectedItem.camera_motion }}
            </Badge>
            <Badge
              v-if="selectedItem.camera_shot"
              variant="outline"
              class="border-zinc-200 dark:border-zinc-700"
            >
              {{ selectedItem.camera_shot }}
            </Badge>
            <Badge
              v-if="selectedItem.temperament_label"
              variant="outline"
              class="border-zinc-200 dark:border-zinc-700"
            >
              {{ selectedItem.temperament_label }}
            </Badge>
            <Badge
              v-if="selectedItem.entrance_style"
              variant="outline"
              class="border-zinc-200 dark:border-zinc-700"
            >
              {{ selectedItem.entrance_style }}
            </Badge>
          </div>

          <div class="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
            <p class="text-xs text-zinc-500">资产 ID</p>
            <p class="mt-2 break-all font-mono text-xs text-zinc-700 dark:text-zinc-300">
              {{ selectedItem.id }}
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
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
