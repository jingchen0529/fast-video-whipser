<script setup lang="ts">
import { useLoadingOverlay } from "@/composables/useLoadingOverlay";

const { isLoading, loadingMessage } = useLoadingOverlay();
</script>

<template>
  <Transition name="fade-overlay">
    <div v-if="isLoading" class="fixed inset-0 z-[100] flex flex-col items-center justify-center">
      <!-- Premium Glassmorphism Background -->
      <div class="absolute inset-0 bg-white/60 dark:bg-black/60 backdrop-blur-xl transition-colors duration-500"></div>
      
      <!-- Subtle Gradient Glow -->
      <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[40rem] h-[40rem] bg-indigo-500/10 dark:bg-indigo-400/5 rounded-full blur-[120px] pointer-events-none"></div>
      
      <!-- Content Container -->
      <div class="relative flex flex-col items-center">
        <!-- Logo Animation -->
        <div class="relative mb-8 group">
          <div class="absolute inset-0 bg-indigo-500/20 dark:bg-indigo-400/10 rounded-3xl blur-2xl group-hover:blur-3xl transition-all duration-500 scale-125"></div>
          <div class="relative bg-white dark:bg-zinc-900 p-5 rounded-3xl shadow-2xl border border-zinc-200/50 dark:border-zinc-800/50 animate-float">
            <img src="/logo.png" alt="Logo" class="h-12 w-auto max-w-[160px] animate-pulse-subtle object-contain" />
          </div>
          
          <!-- Outer Ring -->
          <div class="absolute -inset-2 border-2 border-dashed border-indigo-500/30 dark:border-indigo-400/20 rounded-[2rem] animate-spin-slow"></div>
        </div>

        <!-- Text Content -->
        <div class="flex flex-col items-center gap-2 text-center px-4">
          <h2 class="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 animate-fade-in-up">
            爆款杀手🥷
          </h2>
          <div class="flex items-center gap-2 px-4 py-2 bg-indigo-50 dark:bg-indigo-950/30 rounded-full border border-indigo-100 dark:border-indigo-900/50 animate-fade-in-up" style="animation-delay: 150ms">
            <div class="flex gap-1">
              <span class="w-1.5 h-1.5 bg-indigo-500 dark:bg-indigo-400 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
              <span class="w-1.5 h-1.5 bg-indigo-500 dark:bg-indigo-400 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
              <span class="w-1.5 h-1.5 bg-indigo-500 dark:bg-indigo-400 rounded-full animate-bounce"></span>
            </div>
            <span class="text-sm font-medium text-indigo-700 dark:text-indigo-300">
              {{ loadingMessage }}
            </span>
          </div>
        </div>
      </div>

      <!-- Progressive Loading Indicator Bar (At bottom) -->
      <div class="absolute bottom-12 w-48 h-1 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
        <div class="h-full bg-indigo-500 dark:bg-indigo-400 animate-shimmer"></div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* Standard Fade Transition */
.fade-overlay-enter-active,
.fade-overlay-leave-active {
  transition: opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-overlay-enter-from,
.fade-overlay-leave-to {
  opacity: 0;
}

/* Animations */
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

.animate-float {
  animation: float 4s ease-in-out infinite;
}

@keyframes spin-slow {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.animate-spin-slow {
  animation: spin-slow 12s linear infinite;
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.animate-shimmer {
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes pulse-subtle {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.8; transform: scale(0.95); }
}

.animate-pulse-subtle {
  animation: pulse-subtle 3s ease-in-out infinite;
}

@keyframes fade-in-up {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fade-in-up {
  animation: fade-in-up 0.6s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}
</style>
