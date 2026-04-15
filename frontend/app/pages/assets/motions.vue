<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  RefreshCw,
  Search,
  Film,
  MapPin,
  Sparkles,
  Clock3,
  ChevronRight,
  AlertCircle,
  ArrowLeft,
  Play,
  Image as ImageIcon,
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
const selectedItem = ref<MotionAsset | null>(null);
const showDetail = ref(false);
const selectedGroup = ref<MotionAssetGroup | null>(null);

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
    params.set("limit", "1000"); // Expand limit to allow robust client-side global content search.

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

const groupedItems = computed<MotionAssetGroup[]>(() => {
  const groups = new Map<string, MotionAssetGroup>();
  const kw = appliedKeyword.value.trim().toLowerCase();

  for (const item of items.value) {
    if (kw) {
      const matchStr = [
        item.action_summary,
        item.action_label,
        item.scene_label,
        item.emotion_label,
        item.camera_motion,
        item.camera_shot,
        item.temperament_label,
        item.entrance_style,
        item.source_video_asset?.file_name
      ].filter(Boolean).join(" ").toLowerCase();
      
      if (!matchStr.includes(kw)) continue;
    }

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
}));

const openDetail = (item: MotionAsset) => {
  selectedItem.value = item;
  showDetail.value = true;
};

const enterGroup = (group: MotionAssetGroup) => {
  selectedGroup.value = group;
};

const leaveGroup = () => {
  selectedGroup.value = null;
};

onMounted(fetchMotionAssets);
</script>

<template>
  <div class="h-full w-full overflow-hidden bg-white p-6 dark:bg-[#121212]">
    <div class="mx-auto flex h-full max-w-7xl flex-col gap-6">

      <!-- ===== DETAIL VIEW: single video's motions ===== -->
      <template v-if="selectedGroup">
        <!-- Back header -->
        <div class="flex items-center gap-3">
          <button
            type="button"
            class="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-zinc-600 transition-colors hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
            @click="leaveGroup"
          >
            <ArrowLeft class="size-4" />
            返回列表
          </button>
        </div>

        <!-- Video info header -->
        <div class="grid gap-5 rounded-3xl border border-zinc-200 bg-zinc-50/60 p-5 dark:border-zinc-800 dark:bg-zinc-950/70 lg:grid-cols-[360px_minmax(0,1fr)]">
          <div class="overflow-hidden rounded-2xl border border-zinc-200 bg-black dark:border-zinc-800">
            <video
              v-if="selectedGroup.sourceVideoUrl"
              :src="selectedGroup.sourceVideoUrl"
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
                  {{ selectedGroup.items.length }} 条分镜动作
                </Badge>
                <Badge
                  v-for="label in selectedGroup.actionLabels.slice(0, 6)"
                  :key="label"
                  variant="outline"
                  class="border-zinc-200 text-zinc-600 dark:border-zinc-700 dark:text-zinc-300"
                >
                  {{ label }}
                </Badge>
              </div>
              <div>
                <h2 class="truncate text-xl font-semibold text-zinc-950 dark:text-zinc-50">
                  {{ selectedGroup.sourceVideoName }}
                </h2>
                <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  Source Asset ID: {{ selectedGroup.sourceVideoAssetId || "未关联" }}
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- Motion cards for this video -->
        <div class="custom-scrollbar min-h-0 flex-1 overflow-y-auto pr-1">
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <button
              v-for="item in selectedGroup.items"
              :key="item.id"
              type="button"
              class="group rounded-2xl border border-zinc-200 bg-zinc-50/40 p-4 text-left transition-all hover:-translate-y-0.5 hover:border-zinc-300 hover:bg-white hover:shadow-sm dark:border-zinc-800 dark:bg-zinc-900/50 dark:hover:border-zinc-700 dark:hover:bg-zinc-900"
              @click="openDetail(item)"
            >
              <div class="relative mb-4 aspect-video overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-950 dark:border-zinc-800">
                <img
                  v-if="resolveMotionThumbnailUrl(item)"
                  :src="resolveMotionThumbnailUrl(item) || undefined"
                  class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                  alt="动作截图"
                />
                <div
                  v-else
                  class="flex h-full w-full items-center justify-center bg-zinc-900 text-zinc-500"
                >
                  <ImageIcon class="size-8 opacity-60" />
                </div>
                <div class="absolute inset-0 bg-gradient-to-t from-black/55 via-black/5 to-transparent" />
                <div class="absolute left-3 top-3">
                  <span class="inline-flex items-center gap-1 rounded-full bg-black/45 px-2 py-1 text-[10px] font-medium text-white backdrop-blur-sm">
                    <Play class="size-3" />
                    点击查看截图与片段
                  </span>
                </div>
              </div>
              <div class="flex items-start justify-between gap-3">
                <div class="space-y-1">
                  <p class="text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                    {{ item.action_label || "未标注动作" }}
                  </p>
                  <p class="text-xs text-zinc-500 dark:text-zinc-400">
                    {{ formatRange(item.start_ms, item.end_ms) }}
                  </p>
                </div>
              </div>
              <p class="mt-3 line-clamp-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                {{ item.action_summary }}
              </p>
              <div class="mt-4 flex flex-wrap gap-2">
                <Badge v-if="item.emotion_label" variant="outline" class="border-zinc-200 text-zinc-600 dark:border-zinc-700 dark:text-zinc-300">{{ item.emotion_label }}</Badge>
                <Badge v-if="item.scene_label" variant="outline" class="border-zinc-200 text-zinc-600 dark:border-zinc-700 dark:text-zinc-300">{{ item.scene_label }}</Badge>
                <Badge v-if="item.camera_motion" variant="outline" class="border-zinc-200 text-zinc-600 dark:border-zinc-700 dark:text-zinc-300">{{ item.camera_motion }}</Badge>
              </div>
              <div class="mt-4 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
                <span class="inline-flex items-center gap-1.5"><Clock3 class="size-3.5" />{{ formatDuration(item.start_ms, item.end_ms) }}</span>
                <span class="inline-flex items-center gap-1.5"><Sparkles class="size-3.5" />置信度 {{ confidenceText(item) }}</span>
                <ChevronRight class="size-4 transition-transform group-hover:translate-x-0.5" />
              </div>
            </button>
          </div>
        </div>
      </template>

      <!-- ===== LIST VIEW: video cards ===== -->
      <template v-else>

      <div class="flex items-center justify-between pb-2 mb-2 px-2">
        <div class="space-y-1 hidden md:block">
          <h1 class="text-2xl font-bold tracking-tight text-zinc-950 dark:text-zinc-50">
            动作资产库
          </h1>
        </div>

        <div class="flex flex-1 md:flex-none items-center justify-end gap-3">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  variant="ghost"
                  size="icon"
                  class="size-9 shrink-0 rounded-full border border-zinc-200 bg-white shadow-sm dark:bg-zinc-900 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800"
                  @click="fetchMotionAssets"
                  :disabled="loading"
                >
                  <RefreshCw :class="['size-4 text-zinc-600 dark:text-zinc-400', loading && 'animate-spin']" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>手动刷新</TooltipContent>
            </Tooltip>
          </TooltipProvider>

          <div class="relative w-full max-w-sm md:w-80">
            <Search class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-400" />
            <Input
              v-model="searchInput"
              placeholder="搜索任何内容..."
              class="h-9 pl-9 rounded-xl border-zinc-200/60 shadow-sm text-sm bg-white dark:bg-zinc-950 dark:border-zinc-800 focus-visible:ring-1"
              @keyup.enter="handleSearch"
            />
          </div>
          <Button variant="default" size="sm" class="h-9 px-4 rounded-xl font-medium shadow-sm transition-all text-sm bg-zinc-900 text-white dark:bg-zinc-50 dark:text-zinc-900 hover:opacity-90 active:scale-95 shrink-0" @click="handleSearch">
            搜索
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

        <!-- Video card grid -->
        <div v-else class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <div
            v-for="group in groupedItems"
            :key="group.groupKey"
            class="group cursor-pointer overflow-hidden rounded-2xl border border-zinc-200 bg-white transition-all hover:-translate-y-0.5 hover:border-zinc-300 hover:shadow-lg dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-700"
            @click="enterGroup(group)"
          >
            <!-- Video thumbnail -->
            <div class="relative aspect-video w-full overflow-hidden bg-zinc-950">
              <video
                v-if="group.sourceVideoUrl"
                :src="group.sourceVideoUrl"
                class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                muted
                preload="metadata"
              />
              <div
                v-else
                class="flex h-full w-full items-center justify-center"
              >
                <Film class="size-10 text-white/20" />
              </div>
              <!-- Motion count overlay -->
              <div class="absolute bottom-2.5 right-2.5">
                <span class="inline-flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[11px] font-medium text-white backdrop-blur-sm">
                  <Play class="size-3" />
                  {{ group.items.length }} 条动作
                </span>
              </div>
              <!-- Hover overlay -->
              <div class="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
                <span class="rounded-full bg-white/20 px-4 py-2 text-sm font-medium text-white backdrop-blur-md">
                  查看动作
                </span>
              </div>
            </div>

            <!-- Card info -->
            <div class="p-4">
              <h3 class="truncate text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                {{ group.sourceVideoName }}
              </h3>
              <div class="mt-2.5 flex flex-wrap gap-1">
                <Badge
                  v-for="label in group.actionLabels.slice(0, 3)"
                  :key="label"
                  variant="outline"
                  class="border-zinc-200 text-[10px] text-zinc-600 dark:border-zinc-700 dark:text-zinc-300"
                >
                  {{ label }}
                </Badge>
                <Badge
                  v-if="group.actionLabels.length > 3"
                  variant="outline"
                  class="border-zinc-200 text-[10px] text-zinc-400 dark:border-zinc-700"
                >
                  +{{ group.actionLabels.length - 3 }}
                </Badge>
              </div>
              <div class="mt-3 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
                <span class="inline-flex items-center gap-1">
                  <Film class="size-3.5" />
                  {{ group.items.length }} 条分镜
                </span>
                <ChevronRight class="size-4 transition-transform group-hover:translate-x-0.5" />
              </div>
            </div>
          </div>
        </div>
      </div>

      </template><!-- /v-else LIST VIEW -->
    </div>

    <Dialog v-model:open="showDetail">
      <DialogContent class="max-w-2xl rounded-3xl border-zinc-200 dark:border-zinc-800 max-h-[90vh] overflow-y-auto custom-scrollbar">
        <DialogHeader>
          <DialogTitle class="text-xl">
            {{ selectedItem?.action_label || "动作资产详情" }}
          </DialogTitle>
          <DialogDescription>
            {{ selectedItem ? formatRange(selectedItem.start_ms, selectedItem.end_ms) : "" }}
          </DialogDescription>
        </DialogHeader>

        <div v-if="selectedItem" class="space-y-5 mt-2">
          <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
            <div class="overflow-hidden rounded-3xl border border-zinc-200 bg-zinc-950 dark:border-zinc-800">
              <img
                v-if="resolveMotionThumbnailUrl(selectedItem)"
                :src="resolveMotionThumbnailUrl(selectedItem) || undefined"
                class="aspect-video w-full object-cover"
                alt="动作截图"
              />
              <div
                v-else
                class="flex aspect-video items-center justify-center text-sm text-white/45"
              >
                暂无动作截图
              </div>
            </div>

            <div class="overflow-hidden rounded-3xl border border-zinc-200 bg-zinc-950 dark:border-zinc-800">
              <video
                v-if="resolveMotionClipUrl(selectedItem)"
                :src="resolveMotionClipUrl(selectedItem) || undefined"
                controls
                preload="metadata"
                class="aspect-video w-full object-contain"
              />
              <div
                v-else
                class="flex aspect-video items-center justify-center text-sm text-white/45"
              >
                暂无动作片段
              </div>
            </div>
          </div>

          <div class="grid gap-3 md:grid-cols-2">
            <div class="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p class="text-xs text-zinc-500">动作摘要</p>
              <p class="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
                {{ selectedItem.action_summary || "暂无动作摘要" }}
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

          <div class="grid gap-3 md:grid-cols-2">
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
