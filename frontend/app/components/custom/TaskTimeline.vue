<script setup lang="ts">
import { computed, ref, type Component } from "vue";
import {
  AlertCircle,
  BrainCircuit,
  Captions,
  Check,
  CheckCircle2,
  Clapperboard,
  ChevronDown,
  ChevronUp,
  CircleDashed,
  Lightbulb,
  Link2,
  LoaderCircle,
  MessageSquareText,
  PartyPopper,
  ScanSearch,
  ShieldCheck,
} from "lucide-vue-next";

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

const collapsed = ref(false);

const sortedTasks = computed(() =>
  [...(props.tasks || [])].sort((a, b) => a.display_order - b.display_order),
);

// Only show tasks that have started (completed, in_progress, failed) — hide pending
const visibleTasks = computed(() =>
  sortedTasks.value.filter((task) => task.status !== "pending"),
);

const completedCount = computed(
  () => visibleTasks.value.filter((task) => task.status === "completed").length,
);

const totalCount = computed(() => sortedTasks.value.length);

const activeTask = computed(
  () => sortedTasks.value.find((task) => task.status === "in_progress") || null,
);

const failedTask = computed(
  () => sortedTasks.value.find((task) => task.status === "failed") || null,
);

const isAllCompleted = computed(
  () => totalCount.value > 0 && completedCount.value === totalCount.value,
);

const headerTitle = computed(() => {
  if (failedTask.value) {
    return `执行异常 · ${failedTask.value.title} (${completedCount.value}/${totalCount.value})`;
  }
  if (isAllCompleted.value) {
    return `所有任务已完成 (${completedCount.value}/${totalCount.value})`;
  }
  return `处理中 · ${activeTask.value?.title || "等待执行"} (${completedCount.value}/${totalCount.value})`;
});

const getStatusLabel = (status: string) => {
  switch (status) {
    case "pending":
      return "待执行";
    case "in_progress":
      return "进行中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return status;
  }
};

const getStatusIcon = (status: TaskStep["status"]): Component => {
  switch (status) {
    case "completed":
      return CheckCircle2;
    case "in_progress":
      return LoaderCircle;
    case "failed":
      return AlertCircle;
    default:
      return CircleDashed;
  }
};

const getStepIcon = (stepKey: string): Component => {
  const iconMap: Record<string, Component> = {
    extract_video_link: Link2,
    validate_video_link: ShieldCheck,
    segment_video_shots: Clapperboard,
    analyze_video_content: ScanSearch,
    identify_audio_content: Captions,
    generate_storyboard: BrainCircuit,
    generate_response: MessageSquareText,
    generate_suggestions: Lightbulb,
    finish: PartyPopper,
  };
  return iconMap[stepKey] || BrainCircuit;
};

const getStepStatusClass = (status: TaskStep["status"]) => {
  switch (status) {
    case "completed":
      return "text-emerald-600 dark:bg-emerald-950/20 dark:text-emerald-400";
    case "in_progress":
      return "border-zinc-900 bg-zinc-900 text-white dark:border-white dark:text-zinc-900";
    case "failed":
      return "border-red-500 bg-red-50 text-red-600 dark:bg-red-950/20 dark:text-red-400";
    default:
      return "border-zinc-200 bg-white text-zinc-400 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-500";
  }
};

const getStatusTextClass = (status: TaskStep["status"]) => {
  switch (status) {
    case "completed":
      return "text-emerald-500";
    case "in_progress":
      return "text-zinc-900 dark:text-white";
    case "failed":
      return "text-red-500";
    default:
      return "text-zinc-400";
  }
};
</script>

<template>
  <div class="space-y-2.5">
    <button
      type="button"
      class="flex w-full items-center justify-between px-1 text-left transition-colors hover:text-zinc-900 dark:hover:text-white"
      @click="collapsed = !collapsed"
    >
      <div class="flex items-center gap-2">
        <div
          class="flex h-6 w-6 items-center justify-center rounded-full border border-zinc-200 bg-white text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300"
        >
          <Check v-if="isAllCompleted" class="size-3 text-emerald-500" />
          <AlertCircle v-else-if="failedTask" class="size-3 text-red-500" />
          <LoaderCircle v-else class="size-3 animate-spin" />
        </div>
        <p class="text-[13px] font-medium text-zinc-600 dark:text-zinc-300">
          {{ headerTitle }}
        </p>
      </div>

      <ChevronUp v-if="!collapsed" class="size-3.5 text-zinc-400" />
      <ChevronDown v-else class="size-3.5 text-zinc-400" />
    </button>

    <div
      v-if="!collapsed && visibleTasks.length"
      class="space-y-3 border-l border-zinc-200/80 pl-10 dark:border-zinc-800"
    >
      <div
        v-for="task in visibleTasks"
        :key="task.id"
        class="relative pb-0.5 last:pb-0"
      >
        <div
          class="absolute -left-[29px] top-0 flex items-center justify-center"
          :class="
            task.status === 'completed'
              ? 'h-5 w-5 text-emerald-500'
              : 'h-5 w-5 rounded-full border-[1.5px] shadow-sm ' + getStepStatusClass(task.status)
          "
        >
          <component
            :is="getStatusIcon(task.status)"
            :class="[
              task.status === 'completed' ? 'size-[18px]' : 'size-2.5',
              task.status === 'in_progress' ? 'animate-spin' : ''
            ]"
          />
        </div>

        <div class="space-y-0.5">
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h4
              class="text-[13px] font-semibold leading-5 text-zinc-900 dark:text-white"
            >
              {{ task.title }}
            </h4>
            <span
              class="text-[11px] font-medium"
              :class="getStatusTextClass(task.status)"
            >
              {{ getStatusLabel(task.status) }}
            </span>
          </div>

          <div
            class="flex items-start gap-1.5 text-[12px] leading-5 text-zinc-400"
          >
            <component
              :is="getStepIcon(task.step_key)"
              class="mt-0.5 size-3 shrink-0 text-zinc-300"
            />
            <p>{{ task.detail }}</p>
          </div>

          <div
            v-if="task.status === 'failed' && task.error_detail"
            class="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs leading-5 text-red-600 dark:border-red-900/30 dark:bg-red-950/20 dark:text-red-400"
          >
            {{ task.error_detail }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
