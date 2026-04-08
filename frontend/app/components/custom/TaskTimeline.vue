<script setup lang="ts">
import LucideIcon from "./LucideIcon.vue";
import { computed } from "vue";

interface TaskStep {
  id: number;
  step_key: string;
  title: string;
  detail: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  error_detail: string | null;
  display_order: number;
  updated_at: string;
}

const props = defineProps<{
  tasks: TaskStep[];
}>();

const sortedTasks = computed(() => {
  return [...props.tasks].sort((a, b) => a.display_order - b.display_order);
});

const getStatusIcon = (status: string) => {
  switch (status) {
    case "pending": return "Circle";
    case "in_progress": return "Loader2";
    case "completed": return "CheckCircle2";
    case "failed": return "AlertCircle";
    default: return "Circle";
  }
};

const getStatusClass = (status: string) => {
  switch (status) {
    case "pending": return "text-zinc-400";
    case "in_progress": return "text-blue-500 animate-spin";
    case "completed": return "text-green-500";
    case "failed": return "text-red-500";
    default: return "text-zinc-400";
  }
};
</script>

<template>
  <div class="space-y-6">
    <div v-for="(task, index) in sortedTasks" :key="task.id" class="relative pl-8 pb-6 border-l-2 border-zinc-200 dark:border-zinc-800 last:border-0 last:pb-0">
      <div 
        class="absolute -left-[11px] top-0 w-5 h-5 rounded-full bg-white dark:bg-[#1a1a1a] flex items-center justify-center border-2"
        :class="task.status === 'completed' ? 'border-green-500' : task.status === 'in_progress' ? 'border-blue-500' : 'border-zinc-300 dark:border-zinc-700'"
      >
        <div 
          v-if="task.status === 'completed'" 
          class="w-2.5 h-2.5 rounded-full bg-green-500"
        />
        <div 
          v-else-if="task.status === 'in_progress'" 
          class="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse"
        />
      </div>
      
      <div>
        <div class="flex items-center gap-2">
          <h4 class="font-bold text-[15px] leading-none" :class="task.status === 'failed' ? 'text-red-500' : ''">
            {{ task.title }}
          </h4>
          <span 
            v-if="task.status === 'in_progress'" 
            class="text-[11px] font-medium bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400 px-1.5 py-0.5 rounded"
          >
            执行中
          </span>
        </div>
        <p class="mt-1.5 text-[13px] text-zinc-500 leading-relaxed">
          {{ task.detail }}
        </p>
        <div v-if="task.status === 'failed' && task.error_detail" class="mt-2 text-[12px] text-red-500 bg-red-50 dark:bg-red-900/10 p-2 rounded border border-red-100 dark:border-red-900/20">
          {{ task.error_detail }}
        </div>
      </div>
    </div>
  </div>
</template>
