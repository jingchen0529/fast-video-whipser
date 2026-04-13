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
  MessageSquare
} from "lucide-vue-next";

import { cn } from "@/lib/utils";

const props = defineProps<{
  open: boolean;
  videoGeneration: any;
  targetVideoUrl: string | null;
  title: string;
  sourceUrl: string | null;
}>();

const emit = defineEmits<{
  (e: "update:open", val: boolean): void;
}>();

type DetailTab = "prompt" | "script" | "storyboard";

const activeTab = ref<DetailTab>("prompt");

const scriptText = computed(() => {
  return props.videoGeneration?.script?.full_text || "";
});

const storyboardItems = computed(() => {
  const raw = props.videoGeneration?.storyboard?.shots;
  const legacyRaw = props.videoGeneration?.storyboard?.items;
  const items = Array.isArray(raw) ? raw : (Array.isArray(legacyRaw) ? legacyRaw : []);
  
  return items.map((item: any, index: number) => ({
    ...item,
    id: item.id || `shot-${index + 1}`,
    index: index + 1,
    actionDisplay: item.action || item.title || "未标注",
    shotTypeDisplay: item.camera_movement || item.shot_type_label || item.shot_type || "未标注",
    cameraMotionDisplay: item.subject_composition || item.camera_motion_label || item.camera_motion || "未标注",
    durationDisplay: item.duration_ms ? `${(Number(item.duration_ms) / 1000).toFixed(1)}s` : "未标注时间",
    visual_description: item.description || item.visual_description || "",
  }));
});

const storyboardSummary = computed(() => {
  return props.videoGeneration?.storyboard?.summary || "";
});

watch(
  () => props.open,
  (open) => {
    if (open) {
      activeTab.value = props.videoGeneration?.prompt ? "prompt" : "script";
    }
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
        class="w-full h-full sm:h-auto sm:max-h-[calc(100vh-32px)] sm:w-[500px] bg-white dark:bg-[#121212] sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-[#eee] dark:border-white/10 outline-none"
      >
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-4 border-b border-[#eee] dark:border-white/10 shrink-0 bg-white dark:bg-[#121212]">
          <div class="flex items-center gap-2 min-w-0 pr-4">
            <Video class="size-[18px] shrink-0 text-[#1a1a1a] dark:text-white" />
            <h3 class="text-[16px] font-bold text-[#1a1a1a] dark:text-white truncate">
              {{ title }}
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
            <div class="w-full aspect-video max-h-[250px] mx-auto bg-black rounded-xl overflow-hidden flex items-center justify-center relative shadow-sm">
              <video
                v-if="targetVideoUrl"
                :src="targetVideoUrl"
                controls
                class="w-full h-full object-contain"
              ></video>
              <div v-else class="text-white/50 text-[13px] flex flex-col items-center gap-2">
                <PlayCircle class="size-8 opacity-50" />
                <span>生成结果视频还未准备好，或者无法预览</span>
              </div>
            </div>
            <div class="mt-3 flex flex-col items-center gap-2 text-center">
              <a
                v-if="sourceUrl"
                :href="sourceUrl"
                target="_blank"
                class="inline-flex items-center justify-center gap-1.5 text-[13px] text-[#6b7280] dark:text-[#9ca3af] hover:text-[#1a1a1a] dark:hover:text-white transition-colors max-w-full px-4"
              >
                查看原资产 <ExternalLink class="size-3.5 shrink-0" />
              </a>
            </div>
          </div>

          <!-- Tabs -->
          <div class="px-4 py-2 bg-white dark:bg-[#121212] sticky top-0 z-10 border-b border-[#eee] dark:border-white/10 shadow-[0_2px_4px_rgba(0,0,0,0.02)]">
            <div class="flex items-center gap-1 p-1 bg-[#f1f2f4] dark:bg-white/5 rounded-xl">
              <button
                v-if="videoGeneration?.prompt"
                class="flex-1 py-1.5 text-[13.5px] font-medium rounded-lg transition-all flex items-center justify-center gap-1.5"
                :class="activeTab === 'prompt' ? 'bg-white dark:bg-[#262626] text-[#1a1a1a] dark:text-white shadow-sm' : 'text-[#666] dark:text-[#aaa] hover:bg-black/5'"
                @click="activeTab = 'prompt'"
              >
                <MessageSquare class="size-[14px]" />
                摘要
              </button>
              <button
                class="flex-1 py-1.5 text-[13.5px] font-medium rounded-lg transition-all flex items-center justify-center gap-1.5"
                :class="activeTab === 'script' ? 'bg-white dark:bg-[#262626] text-[#1a1a1a] dark:text-white shadow-sm' : 'text-[#666] dark:text-[#aaa] hover:bg-black/5'"
                @click="activeTab = 'script'"
              >
                <Type class="size-[14px]" />
                内容文本
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
            <!-- Prompt Tab -->
            <template v-if="activeTab === 'prompt'">
              <div v-if="videoGeneration?.prompt" class="bg-white dark:bg-[#262626] rounded-xl p-5 border border-[#eee] dark:border-white/5 shadow-sm">
                <p class="whitespace-pre-wrap text-[14px] leading-relaxed text-[#1a1a1a] dark:text-[#eee]">
                  {{ videoGeneration.prompt }}
                </p>
              </div>
              <div v-else class="text-center py-20 bg-white dark:bg-[#262626] rounded-2xl border border-dashed border-zinc-200">
                <MessageSquare class="size-8 mx-auto mb-2 opacity-20" />
                <p class="text-sm text-zinc-400">暂无相关提示词记录</p>
              </div>
            </template>

            <!-- Script Tab -->
            <template v-if="activeTab === 'script'">
              <div
                v-if="scriptText"
                class="bg-white dark:bg-[#262626] rounded-xl p-5 border border-[#eee] dark:border-white/5 shadow-sm text-[#1a1a1a] dark:text-[#eee] text-[14px] leading-8 whitespace-pre-wrap flex gap-3 hover:border-[#ddd] dark:hover:border-white/10 transition-colors group"
              >
                {{ scriptText }}
              </div>
              <div v-if="!scriptText" class="text-center py-20 bg-white dark:bg-[#262626] rounded-2xl border border-dashed border-zinc-200">
                <FileQuestion class="size-8 mx-auto mb-2 opacity-20" />
                <p class="text-sm text-zinc-400">暂无文本内容</p>
              </div>
            </template>

            <!-- Storyboard Tab -->
            <template v-if="activeTab === 'storyboard'">
              <div
                v-if="storyboardSummary"
                class="bg-white dark:bg-[#262626] rounded-xl p-4 border border-[#eee] dark:border-white/5 shadow-sm mb-4"
              >
                <p class="text-[13px] leading-relaxed text-[#555] dark:text-[#bbb]">
                  {{ storyboardSummary }}
                </p>
              </div>
              
              <div class="space-y-4">
                <div v-for="item in storyboardItems" :key="item.id" class="bg-white dark:bg-[#121212] rounded-xl border border-[#eee] dark:border-white/10 p-4 shadow-sm hover:border-[#ddd] dark:hover:border-white/20 transition-colors">
                  <div class="flex items-center justify-between mb-3 border-b border-[#eee] dark:border-white/5 pb-3">
                    <span class="text-[14px] font-bold text-zinc-900 dark:text-zinc-100">镜头 {{ item.index }}: {{ item.actionDisplay }}</span>
                    <span class="text-[12px] font-mono font-medium text-zinc-500 bg-[#f1f2f4] dark:bg-zinc-800 px-2 py-0.5 rounded">{{ item.durationDisplay }}</span>
                  </div>
                  
                  <div class="flex flex-wrap gap-1.5 mb-3">
                    <span v-if="item.shotTypeDisplay !== '未标注'" class="rounded bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 px-2 py-0.5 font-bold text-[11px]">{{ item.shotTypeDisplay }}</span>
                    <span v-if="item.cameraMotionDisplay !== '未标注'" class="rounded bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 font-bold text-[11px]">{{ item.cameraMotionDisplay }}</span>
                  </div>
                  
                  <p class="text-[13px] leading-relaxed text-[#555] dark:text-[#bbb]">{{ item.visual_description }}</p>
                </div>
              </div>
              <div v-if="!storyboardItems.length" class="text-center py-20 bg-white dark:bg-[#262626] rounded-2xl border border-dashed border-zinc-200">
                <Clapperboard class="size-8 mx-auto mb-2 opacity-20" />
                <p class="text-sm text-zinc-400">暂无分镜记录</p>
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
