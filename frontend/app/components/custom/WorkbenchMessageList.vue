<script setup lang="ts">
import { computed } from 'vue';
import LucideIcon from './LucideIcon.vue';

const props = defineProps<{
  messages: any[];
  tasks: any[];
  selectedProject: any;
  loading: boolean;
}>();

const formatDateTime = (value: string | null | undefined) => {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
};

const getMessageTypeLabel = (messageType: string) => {
  const labels: Record<string, string> = {
    "project_request": "分析脚本",
    "workflow_status": "流程更新",
    "analysis_reply": "分析结果",
    "suggestion_reply": "优化建议",
    "workflow_error": "执行异常",
    "chat_question": "分析脚本",
    "chat_reply": "回复"
  };
  return labels[messageType] || messageType;
};

const finishedTasksCount = computed(() => {
    return props.tasks.filter(t => t.status === 'completed').length;
});

const isWorkflowFinished = computed(() => {
    return props.tasks.length > 0 && finishedTasksCount.value === props.tasks.length;
});

const projectHeaderMode = computed(() => {
    const mode = '分析脚本';
    const source = props.selectedProject?.source_url || props.selectedProject?.title || '';
    if (source) return `${mode} · ${source}`;
    return mode;
});
</script>

<template>
  <div class="h-full flex flex-col bg-[#f5f5f5] dark:bg-[#121212]">
    <!-- Top Nav Placeholder (Screenshot match) -->
    <div v-if="selectedProject" class="sticky top-0 z-20 px-6 py-4 bg-[#f5f5f5]/80 dark:bg-[#121212]/80 backdrop-blur-md flex items-center justify-between border-b border-zinc-200/20">
       <div class="flex items-center gap-3 overflow-hidden">
          <LucideIcon name="Menu" class="w-5 h-5 text-zinc-900 dark:text-white shrink-0" />
          <h1 class="text-sm font-bold truncate text-zinc-800 dark:text-zinc-200">
             {{ projectHeaderMode }}
          </h1>
       </div>
    </div>

    <div class="flex-1 overflow-y-auto custom-scrollbar scroll-smooth">
      <!-- Intro State -->
      <div
        v-if="!messages.length && !selectedProject"
        class="h-full flex flex-col items-center justify-center pb-[10vh]"
      >
        <div
          class="w-20 h-20 rounded-[32px] bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center mb-8 shadow-2xl rotate-6"
        >
          <LucideIcon name="Sparkles" class="w-10 h-10 text-white" />
        </div>
        <h1 class="text-3xl font-black text-zinc-900 dark:text-white mb-4 tracking-tighter">
          有什么我能帮你的吗？
        </h1>
        <p class="text-zinc-500 max-w-sm text-center text-md leading-relaxed">
          输入你想让 AI 帮忙的指令，或者粘贴链接，开启深度脚本分析。
        </p>
      </div>

      <!-- Message List -->
      <div v-else class="mx-auto max-w-[800px] py-10 px-6 space-y-10">
        <div
          v-for="(message, index) in messages"
          :key="message.id || index"
          class="flex flex-col"
          :class="message.role === 'user' ? 'items-end' : 'items-start'"
        >
          <!-- Message Bubble -->
          <div
            class="max-w-[85%] rounded-[28px] px-6 py-4 leading-7 text-[15px] shadow-sm transition-all"
            :class="
              message.role === 'user'
                ? 'bg-white text-zinc-900 border border-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 dark:border-white/5'
                : 'bg-transparent text-zinc-900 dark:text-zinc-100'
            "
          >
            <!-- Label for AI (Hidden in some styles, but useful) -->
            <div v-if="message.role === 'assistant'" class="mb-4 flex items-center gap-2">
                <div class="w-8 h-8 rounded-full bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center shrink-0">
                    <LucideIcon name="Bot" class="w-4 h-4 text-zinc-600" />
                </div>
                <span class="text-xs font-black text-zinc-400">助手回复</span>
            </div>

            <div class="whitespace-pre-wrap font-medium">
               <span v-if="message.role === 'user'" class="text-zinc-400 block mb-2">{{ getMessageTypeLabel(message.message_type) }} · {{ formatDateTime(message.created_at) }}</span>
               {{ message.content }}
            </div>

            <!-- Video Preview Card (Screenshot match inside user bubble) -->
            <div v-if="message.role === 'user' && selectedProject?.media_url" class="mt-4 max-w-[120px]">
                <div class="relative aspect-square bg-zinc-900 rounded-2xl overflow-hidden shadow-md group">
                    <video :src="selectedProject.media_url" class="w-full h-full object-cover opacity-60"></video>
                    <div class="absolute inset-0 flex items-center justify-center">
                        <LucideIcon name="Video" class="w-6 h-6 text-white opacity-80" />
                    </div>
                    <div class="absolute bottom-1 right-1">
                        <LucideIcon name="Video" class="w-3.5 h-3.5 text-white/50" />
                    </div>
                </div>
                <p class="mt-1 text-[10px] font-bold text-zinc-400 truncate px-1">
                   {{ getMessageTypeLabel(message.message_type) }} · htt...
                </p>
            </div>
          </div>
        </div>

        <!-- Task Progress (Screenshot match style) -->
        <div v-if="tasks.length" class="flex flex-col items-start gap-4">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-full bg-zinc-200 dark:bg-zinc-800 flex items-center justify-center">
                    <LucideIcon name="Compass" class="w-4 h-4 text-zinc-900 dark:text-white" />
                </div>
                <h3 class="text-[15px] font-black tracking-tight text-zinc-900 dark:text-white">
                    视频分析工作流{{ isWorkflowFinished ? '已完成' : '进行中' }} ({{ finishedTasksCount }}/{{ tasks.length }})
                </h3>
            </div>
            
            <div class="ml-4 pl-8 border-l border-zinc-200/50 dark:border-white/5 space-y-6 pt-2">
                <div v-for="task in tasks" :key="task.id" class="group relative">
                    <h4 class="text-[14px] font-bold" :class="task.status === 'completed' ? 'text-zinc-900 dark:text-zinc-100' : 'text-zinc-400'">
                        {{ task.title }}
                    </h4>
                    <p class="text-[13px] text-zinc-500 mt-1 max-w-[400px]">
                        {{ task.detail }}
                    </p>
                </div>
            </div>
        </div>

        <!-- Bot Loading -->
        <div v-if="loading" class="flex justify-start items-center gap-4">
             <div class="w-8 h-8 rounded-full bg-zinc-100 animate-pulse"></div>
             <p class="text-sm font-bold text-zinc-400">正在拆解视频逻辑...</p>
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
</style>
