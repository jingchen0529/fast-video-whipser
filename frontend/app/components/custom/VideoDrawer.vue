<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  ExternalLink,
  PlayCircle,
  Video,
  X,
  FileQuestion,
  Type,
  Clapperboard,
} from "lucide-vue-next";

import { cn } from "@/lib/utils";

const props = defineProps<{
  open: boolean;
  project: any;
  videoUrl: string | null;
}>();

const emit = defineEmits<{
  (e: "update:open", val: boolean): void;
}>();

type DetailTab = "script" | "storyboard";

const activeTab = ref<DetailTab>("script");

const sourceUrl = computed(() => {
  return props.project?.source_url || props.videoUrl || "";
});

const timelineSegments = computed(() => {
  const segments = Array.isArray(props.project?.timeline_segments)
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

const storyboardItems = computed(() => {
  const raw = props.project?.storyboard?.items;
  const legacyRaw = props.project?.video_generation?.storyboard;
  const items = Array.isArray(raw)
    ? raw
    : (Array.isArray(legacyRaw) ? legacyRaw : (Array.isArray(legacyRaw?.items) ? legacyRaw.items : []));
  return items.map((item: any, index: number) => ({
    ...item,
    id: item.id || `shot-${index + 1}`,
    index: index + 1,
    shotTypeDisplay: item.shot_type_label || item.shot_type || item.shot_type_code || "未标注",
    cameraAngleDisplay: item.camera_angle_label || item.camera_angle || item.camera_angle_code || "未标注",
    cameraMotionDisplay: item.camera_motion_label || item.camera_motion || item.camera_motion_code || "未标注",
  }));
});

const storyboardSummary = computed(() => {
  return props.project?.storyboard?.summary || "";
});

const formatRange = (start: number, end: number) => {
  const s = (start / 1000).toFixed(1);
  const e = (end / 1000).toFixed(1);
  return `${s}s - ${e}s`;
};

watch(
  () => props.open,
  (open) => {
    if (open) activeTab.value = "script";
  },
);
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
          <div class="px-4 py-2 bg-white dark:bg-[#121212] sticky top-0 z-10 border-b border-[#eee] dark:border-white/10 shadow-[0_2px_4px_rgba(0,0,0,0.02)]">
            <div class="flex items-center gap-1 p-1 bg-[#f1f2f4] dark:bg-white/5 rounded-xl">
              <button
                class="flex-1 py-1.5 text-[13.5px] font-medium rounded-lg transition-all flex items-center justify-center gap-1.5"
                :class="activeTab === 'script' ? 'bg-white dark:bg-[#262626] text-[#1a1a1a] dark:text-white shadow-sm' : 'text-[#666] dark:text-[#aaa] hover:bg-black/5'"
                @click="activeTab = 'script'"
              >
                <Type class="size-[14px]" />
                脚本
              </button>
              <button
                class="flex-1 py-1.5 text-[13.5px] font-medium rounded-lg transition-all flex items-center justify-center gap-1.5"
                :class="activeTab === 'storyboard' ? 'bg-white dark:bg-[#262626] text-[#1a1a1a] dark:text-white shadow-sm' : 'text-[#666] dark:text-[#aaa] hover:bg-black/5'"
                @click="activeTab = 'storyboard'"
              >
                <Clapperboard class="size-[14px]" />
                分镜
              </button>
            </div>
          </div>

          <!-- Content -->
          <div class="p-4 space-y-4 pb-12">
            <!-- Script Tab -->
            <template v-if="activeTab === 'script'">
              <div
                v-for="segment in timelineSegments"
                :key="segment.id"
                class="bg-white dark:bg-[#262626] rounded-xl p-4 border border-[#eee] dark:border-white/5 shadow-sm text-[#1a1a1a] dark:text-white text-[14px] flex gap-3 hover:border-[#ddd] dark:hover:border-white/10 transition-colors group"
              >
                <div class="text-[13px] font-mono font-medium text-[#666] dark:text-[#aaa] shrink-0 pt-0.5 w-[95px] whitespace-nowrap">
                  {{ formatRange(segment.start_ms, segment.end_ms) }}
                </div>
                <div class="flex-1 leading-relaxed">
                  <span v-if="segment.speaker" class="font-semibold text-blue-600 dark:text-blue-400 mr-2">
                    {{ segment.speaker }}:
                  </span>
                  {{ segment.content }}
                </div>
              </div>
              <div v-if="!timelineSegments.length" class="text-center py-20 bg-white dark:bg-[#262626] rounded-2xl border border-dashed border-zinc-200">
                <FileQuestion class="size-8 mx-auto mb-2 opacity-20" />
                <p class="text-sm text-zinc-400">暂无脚本内容</p>
              </div>
            </template>

            <!-- Storyboard Tab -->
            <template v-if="activeTab === 'storyboard'">
              <div
                v-if="storyboardSummary"
                class="bg-white dark:bg-[#262626] rounded-xl p-4 border border-[#eee] dark:border-white/5 shadow-sm"
              >
                <p class="text-[13px] leading-relaxed text-[#555] dark:text-[#bbb]">
                  {{ storyboardSummary }}
                </p>
              </div>
              <div class="overflow-x-auto -mx-4 px-4 custom-scrollbar">
                <table class="w-full border-collapse text-[13px] text-[#1a1a1a] dark:text-white">
                  <thead>
                    <tr class="bg-zinc-100 dark:bg-white/5 text-[12px] font-bold text-[#666] dark:text-[#aaa] uppercase tracking-wider text-left">
                      <th class="p-3 border-b border-[#eee] dark:border-white/10 w-10">#</th>
                      <th class="p-3 border-b border-[#eee] dark:border-white/10 w-24">时间</th>
                      <th class="p-3 border-b border-[#eee] dark:border-white/10">标题</th>
                      <th class="p-3 border-b border-[#eee] dark:border-white/10">镜头特征</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-[#eee] dark:divide-white/10">
                    <tr v-for="item in storyboardItems" :key="item.id" class="bg-white dark:bg-[#121212] hover:bg-[#fafafa] dark:hover:bg-white/5 transition-colors">
                      <td class="p-3 font-mono font-bold align-top text-[#999]">{{ item.index }}</td>
                      <td class="p-3 font-mono align-top text-[#666] dark:text-[#aaa]">{{ formatRange(item.start_ms, item.end_ms) }}</td>
                      <td class="p-3 font-bold align-top leading-relaxed">{{ item.title }}</td>
                      <td class="p-3 align-top space-y-2">
                        <div class="flex flex-wrap gap-1.5 mb-2">
                          <span class="rounded bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 px-1.5 py-0.5 font-bold text-[11px]">{{ item.shotTypeDisplay }}</span>
                          <span class="rounded bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 px-1.5 py-0.5 font-bold text-[11px]">{{ item.cameraAngleDisplay }}</span>
                          <span class="rounded bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-1.5 py-0.5 font-bold text-[11px]">{{ item.cameraMotionDisplay }}</span>
                        </div>
                        <p class="text-[13px] leading-relaxed text-[#555] dark:text-[#bbb]">{{ item.visual_description }}</p>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-if="!storyboardItems.length" class="text-center py-20 bg-white dark:bg-[#262626] rounded-2xl border border-dashed border-zinc-200">
                <Clapperboard class="size-8 mx-auto mb-2 opacity-20" />
                <p class="text-sm text-zinc-400">暂无分镜内容</p>
              </div>
            </template>
          </div>
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
