<script setup lang="ts">
import { SidebarProvider, SidebarTrigger, SidebarInset } from "@/components/ui/sidebar";
import AppSidebar from "@/components/custom/AppSidebar.vue";
import { useRoute } from "vue-router";
import { computed } from "vue";

const route = useRoute();

const titles: Record<string, string> = {
  "/dashboard": "仪表盘",
  "/users": "用户管理",
  "/roles": "角色管理",
  "/menus": "菜单管理",
  "/account": "个人资料",
  "/settings": "系统设置",
  "/video/workbench": "视频分析",
  "/video/history": "视频分析",
  "/motion/extract": "动作提取",
  "/assets": "资产库",
  "/assets/motions": "动作资产库",
};

const currentTitle = computed(() => {
  return titles[route.path] || "仪表盘";
});
</script>

<template>
  <SidebarProvider>
    <div
      class="flex min-h-screen w-full transition-colors duration-200 bg-[#ffffff] dark:bg-[#171717] text-zinc-900 dark:text-zinc-100"
    >
      <AppSidebar />
      <SidebarInset class="flex flex-col min-w-0 bg-transparent">
        <header
          class="flex h-14 items-center justify-between px-4 border-zinc-200 dark:border-zinc-800 bg-white/80 dark:bg-zinc-900/80 backdrop-blur sticky top-0 z-10 transition-colors duration-200"
        >
          <div class="flex items-center gap-3 min-w-0 flex-1">
            <SidebarTrigger />
            <div
              v-if="!route.path.startsWith('/video/history')"
              class="h-4 w-[1px] shrink-0 bg-zinc-200 dark:bg-zinc-700 mx-1"
            ></div>
            <span
              v-if="!route.path.startsWith('/video/history')"
              class="text-sm font-semibold shrink-0 transition-colors duration-200"
            >
              {{ currentTitle }}
            </span>
            <div
              id="header-portal"
              class="flex items-center gap-3 flex-1 min-w-0"
            ></div>
          </div>
          <div
            id="header-actions"
            class="flex items-center shrink-0 gap-2"
          ></div>
        </header>
        <main
          class="flex-1 overflow-auto bg-zinc-50 dark:bg-zinc-950/20 transition-colors duration-200 p-6"
        >
          <div class="h-full">
            <slot />
          </div>
        </main>
      </SidebarInset>
    </div>
  </SidebarProvider>
</template>
