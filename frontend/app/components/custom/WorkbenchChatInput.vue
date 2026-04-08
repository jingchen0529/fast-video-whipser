<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import LucideIcon from './LucideIcon.vue';

const props = defineProps<{
  modelValue: string;
  sending: boolean;
  activeMode: 'script' | 'remake' | 'create';
  selectedFile: File | null;
  selectedUrls: string[];
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
  (e: 'update:activeMode', value: 'script' | 'remake' | 'create'): void;
  (e: 'update:selectedFile', value: File | null): void;
  (e: 'send'): void;
  (e: 'upload-click'): void;
  (e: 'link-click'): void;
  (e: 'remove-url'): void;
}>();

const textareaRef = ref<HTMLTextAreaElement | null>(null);

const adjustTextareaHeight = () => {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = `${el.scrollHeight}px`;
};

watch(() => props.modelValue, () => {
  nextTick(adjustTextareaHeight);
});

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
     if (e.metaKey || e.ctrlKey) {
        // Just continue
     } else {
        e.preventDefault();
        emit('send');
     }
  }
};
</script>

<template>
  <div class="max-w-[800px] mx-auto w-full px-4 pb-10">
    <div
      class="bg-[#f0f0f0] dark:bg-zinc-900 border border-zinc-200 dark:border-white/10 rounded-[28px] p-4 pr-6 transition-all focus-within:ring-2 focus-within:ring-zinc-900/5 dark:focus-within:ring-white/5 shadow-sm"
    >
      <form @submit.prevent="emit('send')">
        <div class="relative flex flex-col">
          <!-- Textarea area -->
          <div class="flex-1">
            <textarea
              ref="textareaRef"
              :value="modelValue"
              @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
              class="w-full bg-transparent resize-none outline-none text-[15px] text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 border-none px-2 py-2 overflow-hidden min-h-[48px] transition-[height] duration-200"
              placeholder="输入你想让 AI 帮忙的指令，或者粘贴链接..."
              @keydown="handleKeydown"
            />
          </div>

          <!-- Attachments Row (Above Bottom Bar) -->
          <div v-if="selectedFile || selectedUrls.length" class="flex flex-wrap gap-2 px-2 pb-2">
             <div v-if="selectedFile" class="inline-flex items-center gap-1.5 rounded-xl border border-blue-200 bg-white px-2.5 py-1.5 dark:bg-zinc-800 dark:border-blue-900/40">
                <LucideIcon name="FileText" class="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                <span class="text-[12px] font-bold text-zinc-700 dark:text-zinc-200 truncate max-w-[120px]">{{ selectedFile.name }}</span>
                <button @click.prevent="emit('update:selectedFile', null)" class="hover:text-red-500 transition-colors">
                  <LucideIcon name="X" class="w-3.5 h-3.5" />
                </button>
             </div>
             <div v-if="selectedUrls.length" class="inline-flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-white px-2.5 py-1.5 dark:border-emerald-900/40 dark:bg-zinc-800">
                <LucideIcon name="Link2" class="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                <span class="max-w-[200px] truncate text-[12px] font-bold text-zinc-700 dark:text-zinc-200">{{ selectedUrls[0] }}</span>
                <button @click.prevent="emit('remove-url')" class="hover:text-rose-500 transition-colors">
                  <LucideIcon name="X" class="w-3.5 h-3.5" />
                </button>
             </div>
          </div>

          <!-- Bottom Actions Bar (Screenshot style) -->
          <div class="flex items-center justify-between mt-1 px-1">
            <div class="flex items-center gap-6">
              <button
                @click.prevent="emit('upload-click')"
                type="button"
                class="flex items-center gap-2 text-zinc-500 hover:text-zinc-900 dark:hover:text-white transition-colors group"
              >
                <LucideIcon name="Paperclip" class="w-5 h-5 group-hover:scale-110 transition-transform" />
                <span class="text-[14px] font-bold">上传视频</span>
              </button>

              <button
                @click.prevent="emit('link-click')"
                type="button"
                class="flex items-center gap-2 text-zinc-500 hover:text-zinc-900 dark:hover:text-white transition-colors group"
              >
                <LucideIcon name="Link" class="w-5 h-5 group-hover:scale-110 transition-transform" />
                <span class="text-[14px] font-bold">添加链接</span>
              </button>
            </div>

            <!-- Submit Button (Centered AI Logo placeholder in screenshot? No, it's actually blank in screenshot or just has a small arrow?) -->
             <button
              type="submit"
              :disabled="sending || (!modelValue.trim() && !selectedFile && !selectedUrls.length)"
              class="w-10 h-10 rounded-full bg-white dark:bg-zinc-800 text-zinc-900 dark:text-white flex items-center justify-center disabled:opacity-20 shadow-sm transition-all hover:scale-110 active:scale-95 border border-zinc-100 dark:border-white/5"
            >
              <LucideIcon :name="sending ? 'Loader2' : 'ArrowUp'" class="w-5 h-5" :class="sending ? 'animate-spin' : ''" />
            </button>
          </div>
        </div>
      </form>
    </div>
    
    <!-- Footer Logo Decor -->
    <div class="mt-4 flex justify-center opacity-10">
        <LucideIcon name="Sparkles" class="w-6 h-6" />
    </div>
  </div>
</template>
