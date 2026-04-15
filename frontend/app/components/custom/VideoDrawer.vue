<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  Copy,
  ExternalLink,
  PlayCircle,
  Video,
  X,
  FileQuestion,
  Type,
  Clapperboard,
  Image as ImageIcon,
} from "lucide-vue-next";
import { toast } from "vue-sonner";

type VideoTimelineSegment = {
  id?: string | number | null;
  start_ms?: number | null;
  end_ms?: number | null;
  content?: string | null;
  segment_type?: string | null;
};

type VideoStoryboardItem = {
  id?: string | number | null;
  title?: string | null;
  start_ms?: number | null;
  end_ms?: number | null;
  shot_type_label?: string | null;
  shot_type?: string | null;
  shot_type_code?: string | null;
  camera_angle_label?: string | null;
  camera_angle?: string | null;
  camera_angle_code?: string | null;
  camera_motion_label?: string | null;
  camera_motion?: string | null;
  camera_motion_code?: string | null;
  camera_type?: string | null;
  visual_description?: string | null;
  audio_description?: string | null;
  sound_description?: string | null;
};

type VideoShotSegment = {
  id?: string | null;
  segment_index?: number | null;
  start_ms?: number | null;
  end_ms?: number | null;
  keyframe_asset_ids_json?: string[] | null;
  title?: string | null;
  visual_summary?: string | null;
};

type VideoStoryboardDisplayItem = VideoStoryboardItem & {
  id: string | number;
  index: number;
  shotTypeDisplay: string;
  cameraAngleDisplay: string;
  cameraMotionDisplay: string;
  keyframeUrl: string | null;
};

type VideoProject = {
  title?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  timeline_segments?: VideoTimelineSegment[] | null;
  shot_segments?: VideoShotSegment[] | null;
  storyboard?: {
    items?: VideoStoryboardItem[] | null;
  } | null;
  video_generation?: {
    storyboard?: VideoStoryboardItem[] | { items?: VideoStoryboardItem[] | null } | null;
  } | null;
};

const props = defineProps<{
  open: boolean;
  project: VideoProject | null;
  videoUrl: string | null;
}>();

const emit = defineEmits<{
  (e: "update:open", val: boolean): void;
}>();

type DetailTab = "script" | "storyboard";

const runtimeConfig = useRuntimeConfig();

const activeTab = ref<DetailTab>("script");
const selectedScriptSegmentKey = ref<string | null>(null);

const sourceUrl = computed(() => {
  return props.project?.source_url || props.videoUrl || "";
});

const resolveAssetFileUrl = (assetId?: string | null): string | null => {
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

const timelineSegments = computed<VideoTimelineSegment[]>(() => {
  const segments: VideoTimelineSegment[] = Array.isArray(props.project?.timeline_segments)
    ? props.project.timeline_segments
    : [];
  const allowedSegmentTypes = new Set([
    "speech",
    "subtitle",
    "caption",
    "danmu",
    "comment",
    "ocr",
  ]);
  return [...segments]
    .filter((segment) => {
      const segmentType = String(segment?.segment_type || "").trim().toLowerCase();
      if (!segmentType) return true;
      return allowedSegmentTypes.has(segmentType);
    })
    .sort(
    (a, b) => (a.start_ms || 0) - (b.start_ms || 0),
  );
});

const storyboardItems = computed<VideoStoryboardDisplayItem[]>(() => {
  const raw = props.project?.storyboard?.items;
  const legacyRaw = props.project?.video_generation?.storyboard;
  const items: VideoStoryboardItem[] = Array.isArray(raw)
    ? raw
    : (Array.isArray(legacyRaw) ? legacyRaw : (Array.isArray(legacyRaw?.items) ? legacyRaw.items : []));

  // Build shot_segment lookup by segment_index and by id
  const shotSegments = props.project?.shot_segments || [];
  const shotByIndex = new Map<number, VideoShotSegment>();
  const shotById = new Map<string, VideoShotSegment>();
  for (const seg of shotSegments) {
    if (seg.segment_index != null) shotByIndex.set(seg.segment_index, seg);
    if (seg.id) shotById.set(String(seg.id), seg);
  }

  return items.map((item, index) => {
    // Resolve keyframe URL from associated shot_segments
    let keyframeUrl: string | null = null;
    const sourceSegIds: string[] = (item as any).source_segment_ids || [];
    const sourceSegIndexes: number[] = (item as any).source_segment_indexes || [];

    // Try source_segment_ids first, then source_segment_indexes
    const relatedShots: VideoShotSegment[] = [];
    for (const sid of sourceSegIds) {
      const shot = shotById.get(String(sid));
      if (shot) relatedShots.push(shot);
    }
    if (!relatedShots.length) {
      for (const idx of sourceSegIndexes) {
        const shot = shotByIndex.get(idx);
        if (shot) relatedShots.push(shot);
      }
    }
    // Fallback: try matching by index+1
    if (!relatedShots.length) {
      const shot = shotByIndex.get(index + 1);
      if (shot) relatedShots.push(shot);
    }

    for (const shot of relatedShots) {
      const assetIds = shot.keyframe_asset_ids_json;
      if (Array.isArray(assetIds) && assetIds.length > 0) {
        keyframeUrl = resolveAssetFileUrl(assetIds[0]);
        break;
      }
    }

    return {
      ...item,
      id: item.id || `shot-${index + 1}`,
      index: index + 1,
      shotTypeDisplay: item.shot_type_label || item.shot_type || item.shot_type_code || "未标注",
      cameraAngleDisplay: item.camera_angle_label || item.camera_angle || item.camera_angle_code || "未标注",
      cameraMotionDisplay: item.camera_motion_label || item.camera_motion || item.camera_motion_code || "未标注",
      keyframeUrl,
    };
  });
});

const copyText = async (value: string) => {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  if (typeof document === "undefined") {
    throw new Error("Clipboard API unavailable");
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "absolute";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();

  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);

  if (!copied) {
    throw new Error("execCommand copy failed");
  }
};

const handleCopyCurrentTab = async () => {
  const content = currentCopyContent.value;
  const label = activeTab.value === "script" ? "脚本" : "分镜";

  if (!content) {
    toast.error(`暂无可复制的${label}内容`);
    return;
  }

  try {
    await copyText(content);
    toast.success(`${label}内容已复制`);
  } catch (error) {
    console.error("copy content failed", error);
    toast.error(`复制${label}内容失败，请重试`);
  }
};

const getSegmentKey = (segment: VideoTimelineSegment, index: number) => {
  return String(
    segment?.id
      ?? `${segment?.start_ms ?? 0}-${segment?.end_ms ?? 0}-${index}`,
  );
};

const ensureSelectedScriptSegment = () => {
  const segments = timelineSegments.value;
  if (!segments.length) {
    selectedScriptSegmentKey.value = null;
    return;
  }

  const hasSelected = segments.some((segment, index) => {
    return getSegmentKey(segment, index) === selectedScriptSegmentKey.value;
  });

  if (!hasSelected) {
    const firstSegment = segments[0];
    if (firstSegment) {
      selectedScriptSegmentKey.value = getSegmentKey(firstSegment, 0);
    }
  }
};

const formatTimestamp = (ms?: number | null) => {
  const totalSeconds = Math.max(0, Math.floor((ms || 0) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
};

const formatRange = (start?: number | null, end?: number | null) => {
  return `${formatTimestamp(start)} - ${formatTimestamp(end)}`;
};

const scriptCopyContent = computed(() => {
  if (!timelineSegments.value.length) return "";

  return timelineSegments.value
    .map((segment) => {
      const content = String(segment?.content || "").trim();
      if (!content) return "";
      return `${formatRange(segment.start_ms, segment.end_ms)}\n${content}`;
    })
    .filter(Boolean)
    .join("\n\n");
});

const storyboardCopyContent = computed(() => {
  if (!storyboardItems.value.length) return "";

  return storyboardItems.value
    .map((item) => {
      const lines = [
        item.title || `镜头 ${item.index}`,
        `时间：${formatRange(item.start_ms, item.end_ms)}`,
        `镜头类型：${item.shotTypeDisplay}`,
      ];

      if (item.camera_type) {
        lines.push(`相机类型：${item.camera_type}`);
      }

      lines.push(`机位角度：${item.cameraAngleDisplay}`);
      lines.push(`运动方式：${item.cameraMotionDisplay}`);

      if (item.visual_description) {
        lines.push(`画面描述：${item.visual_description}`);
      }

      if (item.audio_description || item.sound_description) {
        lines.push(`声音描述：${item.audio_description || item.sound_description}`);
      }

      return lines.join("\n");
    })
    .join("\n\n");
});

const currentCopyContent = computed(() => {
  return activeTab.value === "script"
    ? scriptCopyContent.value
    : storyboardCopyContent.value;
});


watch(
  () => props.open,
  (open) => {
    if (open) {
      activeTab.value = "script";
      ensureSelectedScriptSegment();
      return;
    }

    selectedScriptSegmentKey.value = null;
  },
);

watch(timelineSegments, () => {
  if (!props.open || activeTab.value !== "script") return;
  ensureSelectedScriptSegment();
});

watch(activeTab, (tab) => {
  if (!props.open || tab !== "script") return;
  ensureSelectedScriptSegment();
});
</script>

<template>
  <Transition
    enter-active-class="transition duration-300 ease-out"
    enter-from-class="opacity-0 translate-x-12"
    enter-to-class="opacity-100 translate-x-0"
    leave-active-class="transition duration-200 ease-in"
    leave-from-class="opacity-100 translate-x-0"
    leave-to-class="opacity-0 translate-x-12"
  >
    <div
      v-if="open"
      class="fixed inset-0 z-[150] flex items-center justify-end bg-black/10 backdrop-blur-[2px] sm:p-4"
      @click.self="emit('update:open', false)"
    >
      <div
        class="w-full h-full sm:h-auto sm:max-h-[calc(100vh-32px)] sm:w-[376px] bg-white dark:bg-[#121212] sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-[#eee] dark:border-white/10 outline-none"
      >
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-4 border-b border-[#eee] dark:border-white/10 shrink-0 bg-white dark:bg-[#121212]">
          <div class="flex items-center gap-2 min-w-0 pr-4">
            <Video class="size-[18px] shrink-0 text-[#1a1a1a] dark:text-white" />
            <h3 class="text-[16px] font-bold text-[#1a1a1a] dark:text-white truncate">
              {{ project?.title || project?.source_name || "视频详情" }}
            </h3>
          </div>
          <button
            class="w-8 h-8 flex items-center justify-center rounded-full text-[#666] hover:bg-[#f3f4f6] dark:hover:bg-white/10 transition-colors"
            @click="emit('update:open', false)"
          >
            <X class="size-[18px]" />
          </button>
        </div>

        <!-- Body -->
        <div class="flex-1 overflow-y-auto bg-[#fafafa] dark:bg-[#1a1a1a] custom-scrollbar">
          <!-- Video Section -->
          <div class="p-4 bg-white dark:bg-[#121212]">
            <div class="w-[333px] h-[192px] mx-auto bg-black rounded-xl overflow-hidden flex items-center justify-center relative shadow-sm">
              <video
                v-if="videoUrl"
                :src="videoUrl"
                controls
                class="w-full h-full object-contain"
              ></video>
              <div v-else class="text-white/50 text-[13px] flex flex-col items-center gap-2">
                <PlayCircle class="size-8 opacity-50" />
                <span>视频正在提取或无法预览</span>
              </div>
            </div>
            <div class="mt-3 flex flex-col items-center gap-2 text-center">
              <a
                v-if="sourceUrl"
                :href="sourceUrl"
                target="_blank"
                class="inline-flex items-center justify-center gap-1.5 text-[13px] text-[#6b7280] dark:text-[#9ca3af] hover:text-[#1a1a1a] dark:hover:text-white transition-colors max-w-full px-4"
              >
                <span class="truncate">{{ sourceUrl }}</span>
                <ExternalLink class="size-3.5 shrink-0" />
              </a>
            </div>
          </div>

          <!-- Tabs -->
          <div class="px-4 py-2 bg-white dark:bg-[#121212] sticky top-0 z-10">
            <div class="flex gap-1 pb-2">
              <button
                class="inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring h-8 rounded-md px-3 text-xs flex-1"
                :class="activeTab === 'script' ? 'bg-primary text-primary-foreground shadow hover:bg-primary/90' : 'hover:bg-accent hover:text-accent-foreground'"
                @click="activeTab = 'script'"
              >
                <Type class="w-3 h-3 mr-1" />
                脚本
              </button>
              <button
                class="inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring h-8 rounded-md px-3 text-xs flex-1"
                :class="activeTab === 'storyboard' ? 'bg-primary text-primary-foreground shadow hover:bg-primary/90' : 'hover:bg-accent hover:text-accent-foreground'"
                @click="activeTab = 'storyboard'"
              >
                <Clapperboard class="w-3 h-3 mr-1" />
                分镜
              </button>
            </div>
          </div>

          <!-- Content -->
          <div class="p-4 space-y-4 pb-12">
            <!-- Script Tab -->
            <template v-if="activeTab === 'script'">
              <button
                v-for="(segment, index) in timelineSegments"
                :key="getSegmentKey(segment, index)"
                type="button"
                class="w-full rounded-lg border p-3 text-left transition-all duration-200"
                :class="
                  selectedScriptSegmentKey === getSegmentKey(segment, index)
                    ? 'border-zinc-900 bg-zinc-100 text-zinc-950 shadow-[0_8px_20px_rgba(15,23,42,0.12)] dark:border-zinc-200 dark:bg-zinc-900 dark:text-zinc-50'
                    : 'border-zinc-200/90 bg-white/95 text-zinc-500 hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950/70 dark:text-zinc-400 dark:hover:border-zinc-700 dark:hover:bg-zinc-900'
                "
                @click="selectedScriptSegmentKey = getSegmentKey(segment, index)"
              >
                <div class="flex items-baseline gap-3">
                  <span
                    class="text-xs font-mono flex-shrink-0 text-primary font-semibold"
                    :class="
                      selectedScriptSegmentKey === getSegmentKey(segment, index)
                        ? 'text-zinc-800 dark:text-zinc-200'
                        : 'text-zinc-400 dark:text-zinc-500'
                    "
                  >
                    {{ formatRange(segment.start_ms, segment.end_ms) }}
                  </span>
                  <div class="min-w-0 flex-1">
                    <span
                      class="text-sm leading-relaxed block text-foreground font-medium"
                      :class="
                        selectedScriptSegmentKey === getSegmentKey(segment, index)
                          ? 'text-zinc-950 dark:text-zinc-50'
                          : 'text-zinc-700 dark:text-zinc-300'
                      "
                    >
                      {{ segment.content }}
                    </span>
                  </div>
                </div>
              </button>
              <div v-if="!timelineSegments.length" class="text-center py-20 bg-white dark:bg-[#262626] rounded-2xl border border-dashed border-zinc-200">
                <FileQuestion class="size-8 mx-auto mb-2 opacity-20" />
                <p class="text-sm text-zinc-400">暂无脚本内容</p>
              </div>
            </template>

            <!-- Storyboard Tab -->
            <template v-if="activeTab === 'storyboard'">
              <div
                v-for="item in storyboardItems"
                :key="item.id"
                class="p-4 rounded-lg border bg-muted/50 hover:bg-muted/80 transition-all"
              >
                <div class="space-y-3">
                  <!-- Keyframe Preview -->
                  <div class="relative w-full aspect-video rounded-lg overflow-hidden bg-zinc-950">
                    <img
                      v-if="item.keyframeUrl"
                      :src="item.keyframeUrl"
                      class="w-full h-full object-cover"
                      loading="lazy"
                    />
                    <div
                      v-else
                      class="flex flex-col items-center justify-center h-full gap-1.5 text-white/30"
                    >
                      <ImageIcon class="size-6" />
                      <span class="text-[11px]">{{ formatRange(item.start_ms, item.end_ms) }}</span>
                    </div>
                  </div>

                  <!-- 标题 + 时间 -->
                  <div class="flex items-center justify-between pb-2 border-b">
                    <h4 class="font-semibold text-sm">{{ item.title }}</h4>
                    <span class="text-xs font-mono text-muted-foreground">{{ formatRange(item.start_ms, item.end_ms) }}</span>
                  </div>

                  <!-- 镜头属性 2列网格 -->
                  <div class="grid grid-cols-2 gap-2 text-xs pt-2 border-t">
                    <div>
                      <span class="text-muted-foreground">镜头类型:</span>
                      <span class="ml-1 font-medium">{{ item.shotTypeDisplay }}</span>
                    </div>
                    <div v-if="item.camera_type">
                      <span class="text-muted-foreground">相机类型:</span>
                      <span class="ml-1 font-medium">{{ item.camera_type }}</span>
                    </div>
                    <div>
                      <span class="text-muted-foreground">机位角度:</span>
                      <span class="ml-1 font-medium">{{ item.cameraAngleDisplay }}</span>
                    </div>
                    <div>
                      <span class="text-muted-foreground">运动方式:</span>
                      <span class="ml-1 font-medium">{{ item.cameraMotionDisplay }}</span>
                    </div>
                  </div>

                  <!-- 画面描述 -->
                  <div v-if="item.visual_description" class="space-y-2">
                    <p class="text-xs font-medium text-muted-foreground uppercase tracking-wide">画面描述</p>
                    <p class="text-sm leading-relaxed font-medium text-foreground">{{ item.visual_description }}</p>
                  </div>

                  <!-- 声音描述 -->
                  <div v-if="item.audio_description || item.sound_description" class="text-sm pt-2 border-t">
                    <p class="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">声音描述</p>
                    <p class="leading-relaxed text-muted-foreground">{{ item.audio_description || item.sound_description }}</p>
                  </div>
                </div>
              </div>

              <div v-if="!storyboardItems.length" class="text-center py-20 bg-white dark:bg-[#262626] rounded-2xl border border-dashed border-zinc-200">
                <Clapperboard class="size-8 mx-auto mb-2 opacity-20" />
                <p class="text-sm text-zinc-400">暂无分镜内容</p>
              </div>
            </template>
          </div>
        </div>

        <div class="shrink-0 border-t border-[#eee] dark:border-white/10 bg-white dark:bg-[#121212] px-4 py-2">
          <button
            type="button"
            class="inline-flex w-full items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 hover:bg-accent hover:text-accent-foreground h-9 rounded-md text-sm px-3"
            :disabled="!currentCopyContent"
            @click="handleCopyCurrentTab"
          >
            <Copy class="w-4 h-4" />
            复制
          </button>
        </div>
      </div>
    </div>
  </Transition>
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
