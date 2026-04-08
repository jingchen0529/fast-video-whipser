<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from "vue";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

const props = defineProps<{
  open: boolean;
  project: any;
  videoUrl: string | null;
}>();

const emit = defineEmits<{
  (e: "update:open", val: boolean): void;
}>();

const videoRef = ref<HTMLVideoElement | null>(null);
const currentTime = ref(0);

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

// Danmaku Engine
const danmakuList = ref<any[]>([]);

let animationFrame: number;

const startDanmaku = () => {
  if (!props.project?.timeline_segments) return;
  
  // Initialize danmakus based on timeline_segments
  danmakuList.value = props.project.timeline_segments.map((seg: any) => {
    return {
      text: seg.content,
      start_ms: seg.start_ms,
      end_ms: seg.end_ms,
      top: Math.random() * 60 + 10, // random top 10% to 70%
      speed: Math.random() * 2 + 3, // basic speed
      left: 100, // percentage initially out of right side
      active: false,
      completed: false,
    };
  });

  const updateDanmaku = () => {
    const currentMs = currentTime.value;
    const isPlaying = videoRef.value && !videoRef.value.paused;
    
    danmakuList.value.forEach((d) => {
      if (currentMs >= d.start_ms && currentMs <= d.end_ms + 5000 && !d.completed) {
        d.active = true;
        if (isPlaying) {
          d.left -= d.speed * 0.1; // move left
        }
      } else if (currentMs > d.end_ms + 5000) {
        d.active = false;
        d.completed = true;
      } else if (currentMs < d.start_ms) {
        // Reset if seeking backwards
        d.active = false;
        d.completed = false;
        d.left = 100;
      }
    });
    
    animationFrame = requestAnimationFrame(updateDanmaku);
  };
  
  updateDanmaku();
};

watch(() => props.open, (val) => {
  if (val) {
    currentTime.value = 0;
    setTimeout(() => {
      startDanmaku();
    }, 100);
  } else {
    cancelAnimationFrame(animationFrame);
    if (videoRef.value) {
      videoRef.value.pause();
    }
  }
});
</script>

<template>
  <Sheet :open="open" @update:open="emit('update:open', $event)">
    <SheetContent class="w-full lg:max-w-3xl bg-white dark:bg-[#121212] overflow-y-auto">
      <SheetHeader class="mb-4">
        <SheetTitle>{{ project?.title || '视频预览' }}</SheetTitle>
      </SheetHeader>
      
      <div v-if="videoUrl" class="relative w-full aspect-video bg-black rounded-lg overflow-hidden flex items-center justify-center group">
        <video 
          ref="videoRef"
          :src="videoUrl" 
          controls 
          class="w-full h-full object-contain"
          @timeupdate="handleTimeUpdate"
        ></video>

        <!-- Danmaku Layer -->
        <div class="absolute inset-0 pointer-events-none overflow-hidden">
          <template v-for="(danmaku, idx) in danmakuList" :key="idx">
            <div 
              v-if="danmaku.active"
              class="absolute whitespace-nowrap text-white font-bold text-lg px-2 py-0.5 rounded shadow-sm"
              :style="{ 
                top: `${danmaku.top}%`, 
                left: `${danmaku.left}%`,
                textShadow: '1px 1px 2px rgba(0,0,0,0.8), -1px -1px 2px rgba(0,0,0,0.8), 1px -1px 2px rgba(0,0,0,0.8), -1px 1px 2px rgba(0,0,0,0.8)'
              }"
            >
              {{ danmaku.text }}
            </div>
          </template>
        </div>

        <!-- Subtitle Layer -->
        <div v-if="activeSubtitle" class="absolute bottom-12 w-full text-center pointer-events-none px-4">
          <span class="inline-block bg-black/60 text-white px-4 py-1.5 rounded-lg text-lg sm:text-xl font-medium tracking-wide backdrop-blur-sm">
            {{ activeSubtitle.content }}
          </span>
        </div>
      </div>
      <div v-else class="w-full aspect-video bg-zinc-100 dark:bg-zinc-800 rounded-lg flex items-center justify-center">
        <p class="text-zinc-500">无法加载视频</p>
      </div>

      <div class="mt-6 space-y-4">
        <div v-if="project?.summary" class="p-4 bg-zinc-50 dark:bg-zinc-900 rounded-xl">
          <h3 class="text-sm font-semibold mb-2">视频摘要</h3>
          <p class="text-sm text-zinc-600 dark:text-zinc-300">
            {{ project.summary }}
          </p>
        </div>
        
        <div v-if="project?.timeline_segments && project.timeline_segments.length > 0" class="space-y-2">
          <h3 class="text-sm font-semibold">脚本片段</h3>
          <div class="max-h-[300px] overflow-y-auto space-y-2 custom-scrollbar pr-2">
             <div 
                v-for="seg in project.timeline_segments" 
                :key="seg.id"
                class="text-sm p-3 rounded-lg border border-zinc-100 dark:border-zinc-800 cursor-pointer transition-colors"
                :class="currentTime >= seg.start_ms && currentTime <= seg.end_ms ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800' : 'bg-white dark:bg-zinc-900 hover:bg-zinc-50 dark:hover:bg-zinc-800'"
                @click="videoRef && (videoRef.currentTime = seg.start_ms / 1000)"
             >
                <div class="flex justify-between text-xs text-zinc-500 mb-1">
                  <span>{{ seg.speaker || '未知' }}</span>
                  <span>{{ Math.floor(seg.start_ms / 1000) }}s - {{ Math.floor(seg.end_ms / 1000) }}s</span>
                </div>
                <p class="text-zinc-700 dark:text-zinc-300">{{ seg.content }}</p>
             </div>
          </div>
        </div>
      </div>
    </SheetContent>
  </Sheet>
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
