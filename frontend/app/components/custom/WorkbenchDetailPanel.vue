<script setup lang="ts">
import { ref, watch, computed } from "vue";
import LucideIcon from "./LucideIcon.vue";

const props = defineProps<{
  project: any;
  videoUrl: string | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const videoRef = ref<HTMLVideoElement | null>(null);
const currentTime = ref(0);
const activeTab = ref<'analysis' | 'timeline'>('analysis');

const handleTimeUpdate = () => {
  if (videoRef.value) {
    currentTime.value = videoRef.value.currentTime * 1000;
  }
};

const activeSubtitle = computed(() => {
  if (!props.project?.timeline_segments) return null;
  const currentMs = currentTime.value;
  return props.project.timeline_segments.find(
    (seg: any) => currentMs >= seg.start_ms && currentMs <= seg.end_ms
  );
});

const formatMs = (ms: number) => {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

const jumpToTime = (ms: number) => {
  if (videoRef.value) {
    videoRef.value.currentTime = ms / 1000;
    videoRef.value.play();
  }
};

const projectTitleInfo = computed(() => {
    const mode = '分析脚本';
    const source = props.project?.source_url || props.project?.title || '';
    return `${mode} · ${source}`;
});
</script>

<template>
  <div class="h-full flex flex-col bg-[#fcfcfc] dark:bg-zinc-950 border-l border-zinc-200/50 dark:border-white/5 relative shadow-2xl">
    <!-- Header (Screenshot style) -->
    <div class="px-5 py-4 flex items-center justify-between bg-white dark:bg-zinc-900 border-b border-zinc-100 dark:border-white/5">
       <div class="flex items-center gap-2 group overflow-hidden max-w-[85%]">
          <LucideIcon name="Video" class="w-4 h-4 text-zinc-900 dark:text-white shrink-0" />
          <h2 class="text-sm font-bold truncate tracking-tight text-zinc-900 dark:text-zinc-100">
              {{ projectTitleInfo }}
          </h2>
       </div>
       <button @click="emit('close')" class="p-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors">
          <LucideIcon name="X" class="w-4 h-4 text-zinc-400" />
       </button>
    </div>

    <!-- Main Content Area -->
    <div class="flex-1 overflow-y-auto custom-scrollbar">
        <!-- Video Section (Vertical centric in screenshot) -->
        <div class="p-4 flex flex-col items-center">
          <div v-if="videoUrl" class="relative w-full aspect-[9/16] max-w-[320px] bg-black rounded-3xl overflow-hidden shadow-2xl ring-1 ring-zinc-100 dark:ring-zinc-800">
            <video 
              ref="videoRef"
              :src="videoUrl" 
              controls 
              class="w-full h-full object-cover"
              @timeupdate="handleTimeUpdate"
            ></video>

            <!-- Subtitle Layer -->
            <div v-if="activeSubtitle" class="absolute bottom-20 w-full text-center pointer-events-none px-4">
              <span class="inline-block bg-black/60 text-white px-3 py-1.5 rounded-xl text-sm font-medium backdrop-blur-md border border-white/10">
                {{ activeSubtitle.content }}
              </span>
            </div>
          </div>
          <div v-else class="w-full aspect-[9/16] max-w-[320px] bg-zinc-100 dark:bg-zinc-800/50 rounded-3xl flex flex-col items-center justify-center border-2 border-dashed border-zinc-200 dark:border-zinc-800">
            <LucideIcon name="VideoOff" class="w-10 h-10 text-zinc-200 mb-2" />
            <p class="text-xs font-bold text-zinc-400">视频流未就绪</p>
          </div>
          
          <!-- Download/External Link (Screenshot match) -->
          <div class="mt-6 flex flex-col items-center gap-2">
             <button class="text-[13px] font-bold text-blue-500 hover:underline">
                打开可播放视频文件
             </button>
             <p class="text-[12px] text-zinc-400 px-6 text-center break-all line-clamp-1">
                {{ project?.source_url }}
             </p>
          </div>
        </div>

        <!-- Tab Switcher (Pill style in screenshot) -->
        <div class="px-6 py-4">
            <div class="bg-zinc-100 dark:bg-zinc-900 p-1 rounded-full flex gap-1">
                <button 
                   @click="activeTab = 'analysis'"
                   class="flex-1 py-2 px-4 rounded-full text-sm font-bold transition-all"
                   :class="activeTab === 'analysis' ? 'bg-white dark:bg-zinc-800 text-zinc-900 dark:text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-700'"
                >
                    <div class="flex items-center justify-center gap-2">
                        <LucideIcon name="Sparkles" class="w-4 h-4" />
                        分析
                    </div>
                </button>
                <button 
                   @click="activeTab = 'timeline'"
                   class="flex-1 py-2 px-4 rounded-full text-sm font-bold transition-all"
                   :class="activeTab === 'timeline' ? 'bg-white dark:bg-zinc-800 text-zinc-900 dark:text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-700'"
                >
                    时间轴
                </button>
            </div>
        </div>

        <!-- Tab Content -->
        <div class="px-6 pb-20">
            <div v-if="activeTab === 'analysis'" class="space-y-4">
                <!-- Analysis Content Card (Screenshot style) -->
                <div class="bg-white dark:bg-zinc-900 border border-zinc-100 dark:border-white/5 rounded-3xl p-6 shadow-sm">
                    <div class="flex items-center gap-3 mb-4">
                         <div class="p-1.5 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
                            <LucideIcon name="Sparkles" class="w-4 h-4 text-purple-600 dark:text-purple-400" />
                         </div>
                         <h3 class="text-sm font-bold text-zinc-900 dark:text-zinc-100">
                             TikTok 电商效果深度分析
                         </h3>
                    </div>
                    
                    <div class="prose prose-sm dark:prose-invert max-w-none text-zinc-600 dark:text-zinc-300">
                        <p class="font-bold mb-2">TikTok 电商效果深度分析</p>
                        <p class="text-[13px] leading-relaxed">AI 分析内容正在渲染，包含了针对电商视频的钩子设计、转化逻辑、以及画面节奏的深度拆解...</p>
                        <!-- Add more mock content to match screenshot visualization -->
                    </div>
                </div>
            </div>
            
            <div v-else-if="activeTab === 'timeline'" class="space-y-3 pt-2">
                <div 
                    v-for="seg in project?.timeline_segments" 
                    :key="seg.id"
                    @click="jumpToTime(seg.start_ms)"
                    class="group p-4 rounded-2xl transition-all cursor-pointer border border-transparent"
                    :class="currentTime >= seg.start_ms && currentTime <= seg.end_ms 
                    ? 'bg-zinc-900 text-white shadow-xl dark:bg-white dark:text-zinc-900' 
                    : 'bg-white dark:bg-zinc-900/50 hover:bg-zinc-50 dark:hover:bg-zinc-800 border-zinc-100 dark:border-white/5'"
                >
                    <div class="flex items-center justify-between mb-1.5 opacity-60 text-[10px] font-bold">
                        <span>{{ seg.speaker || 'SPEAKER' }}</span>
                        <span>{{ formatMs(seg.start_ms) }}</span>
                    </div>
                    <p class="text-sm font-bold leading-relaxed line-clamp-3">{{ seg.content }}</p>
                </div>
            </div>
        </div>
    </div>
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

/* Custom vertical layout for player if video is tall */
video {
    object-position: center top;
}
</style>
