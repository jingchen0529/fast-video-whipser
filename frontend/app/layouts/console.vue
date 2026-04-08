<script setup lang="ts">
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
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
  "/video/workbench": "分析工作台",
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
      <div class="flex-1 flex flex-col min-w-0">
        <header
          class="flex h-14 items-center justify-between px-4 border-b border-zinc-200 dark:border-zinc-800 bg-[#ffffff] dark:bg-[#171717] sticky top-0 z-10 transition-colors duration-200"
        >
          <div class="flex items-center gap-3">
            <SidebarTrigger />
            <div class="h-4 w-[1px] bg-zinc-200 dark:bg-zinc-700 mx-1" />
            <span class="text-sm font-semibold transition-colors duration-200">{{
              currentTitle
            }}</span>
          </div>
        </header>
        <main class="flex-1 overflow-auto bg-[#ffffff] dark:bg-[#171717] transition-colors duration-200">
          <slot />
        </main>
      </div>
    </div>
  </SidebarProvider>
</template>
