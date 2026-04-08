<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { toast } from "vue-sonner";
import {
  Check,
  FolderTree,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  MoreHorizontal,
  Search,
  Settings,
  ShieldCheck,
  UserCog,
  Sun,
  Moon,
  Monitor,
  Captions,
  MessageSquarePlus,
  History,
  MessageSquare,
  Trash2,
  Plus
} from "lucide-vue-next";
import { useColorMode } from "@vueuse/core";

import { Button } from "@/components/ui/button";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from "@/components/ui/dropdown-menu";
import { DropdownMenuPortal } from "reka-ui";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";

const auth = useAuth();
const loadingOverlay = useLoadingOverlay();
const route = useRoute();
const colorMode = useColorMode();
const runtimeConfig = useRuntimeConfig();
const loggingOut = ref(false);

const colorPreference = computed(
  () => colorMode.store?.value ?? colorMode.value,
);

const setColorMode = (mode: "light" | "dark" | "auto") => {
  colorMode.value = mode;
};

const user = computed(() => {
  const u = auth.user.value;
  const avatarUrl = u?.avatar_url;
  return {
    name: u?.display_name || u?.username || "Admin",
    email: u?.email || "admin@example.com",
    avatar_url: avatarUrl
      ? `${avatarUrl}${avatarUrl.includes("?") ? "&" : "?"}_t=${Date.now()}`
      : undefined,
  };
});

const apiDocsUrl = computed(() => {
  const explicitUrl = String(runtimeConfig.public.apiDocsUrl || "").trim();
  if (explicitUrl) {
    return explicitUrl;
  }
  return "/docs";
});

async function handleLogout() {
  if (loggingOut.value) {
    return;
  }

  loggingOut.value = true;
  loadingOverlay.showLoading("正在安全退出...");
  try {
    const succeeded = await auth.logout();
    if (succeeded) {
      toast.success("已安全退出登录。");
      return;
    }
    toast.error("退出接口请求失败，已清理本地登录态。");
  } finally {
    loggingOut.value = false;
    loadingOverlay.hideLoading();
  }
}

const brandName = "爆款杀手";
const chatStore = useChatStore();
const apiService = useApi();
const api = apiService.requestData;

const projects = computed(() => chatStore.projects);
const loadingHistory = computed(() => chatStore.loadingHistory);
const selectedProject = computed(() => chatStore.selectedProject);

const loadProjects = async (silent = false) => {
  if (!silent) chatStore.loadingHistory = true;
  try {
    const res = await api<any[]>("/projects");
    chatStore.projects = res;
    return res;
  } catch (error) {
    console.error(error);
    return [];
  } finally {
    if (!silent) chatStore.loadingHistory = false;
  }
};

const handleProjectSelect = async (projectId: number) => {
  if (route.path !== "/video/workbench") {
    await navigateTo("/video/workbench");
  }
  // The workbench component itself should handle loading the detail based on store state or we can do it here
  // Actually, workbench.vue has its own loadProjectDetail. 
  // It's better if we just set the ID or tell the store to load it.
  try {
    const project = await api<any>(`/projects/${projectId}`);
    chatStore.selectedProject = project;
  } catch (error) {
    console.error(error);
  }
};

const startNewChat = () => {
  chatStore.selectedProject = null;
  if (route.path !== "/video/workbench") {
    navigateTo("/video/workbench");
  }
};

onMounted(() => {
  loadProjects();
});

const navMain = [
  {
    items: [
      { title: "仪表盘", url: "/dashboard", icon: LayoutDashboard },
      { title: "视频分析", url: "/video/workbench", icon: Captions },
    ],
  },
  {
    title: "系统管理",
    items: [
      { title: "用户管理", url: "/users", icon: UserCog },
      { title: "角色管理", url: "/roles", icon: ShieldCheck },
      { title: "菜单管理", url: "/menus", icon: FolderTree },
    ],
  },
];
</script>

<template>
  <Sidebar collapsible="icon" class="border-r border-zinc-200">
    <SidebarHeader class="h-14 border-b border-zinc-200 px-4">
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton
                size="lg"
                class="transition-colors rounded-xl h-10"
              >
                <div
                  class="hidden flex-1 items-center group-data-[collapsible=icon]:flex"
                >
                  <img
                    src="/logo.png"
                    :alt="brandName"
                    class="h-7 w-auto max-w-[28px] object-contain"
                  />
                </div>
                <div
                  class="flex flex-1 items-center justify-center gap-2 text-sm font-semibold text-zinc-900 group-data-[collapsible=icon]:hidden"
                >
                  <img
                    src="/logo.png"
                    :alt="brandName"
                    class="h-6 w-auto max-w-[132px] object-contain"
                  />
                  <span class="whitespace-nowrap">{{ brandName }}</span>
                </div>
              </SidebarMenuButton>
            </DropdownMenuTrigger>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>

    <SidebarContent>
      <SidebarGroup v-for="group in navMain" :key="group.title">
        <SidebarGroupLabel class="group-data-[collapsible=icon]:hidden">{{
          group.title
        }}</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarMenuItem v-for="item in group.items" :key="item.title">
              <SidebarMenuButton as-child :is-active="route.path === item.url">
                <NuxtLink :to="item.url">
                  <component :is="item.icon" class="size-4" />
                  <span class="group-data-[collapsible=icon]:hidden">{{
                    item.title
                  }}</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <!-- History Dialogues -->
      <SidebarGroup class="flex-1 overflow-hidden flex flex-col min-h-0">
        <div class="px-2 mb-2 flex items-center justify-between group-data-[collapsible=icon]:hidden">
          <SidebarGroupLabel class="px-0">历史对话</SidebarGroupLabel>
          <Button
            variant="ghost"
            size="icon"
            class="h-7 w-7 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800"
            @click="startNewChat"
          >
            <Plus class="size-3.5" />
          </Button>
        </div>

        <SidebarGroupContent class="flex-1 overflow-y-auto custom-scrollbar">
          <SidebarMenu>
            <SidebarMenuItem class="px-2 mb-1 group-data-[collapsible=icon]:block hidden">
              <SidebarMenuButton @click="startNewChat" tooltip="新建对话">
                <Plus class="size-4" />
              </SidebarMenuButton>
            </SidebarMenuItem>

            <div v-if="loadingHistory && !projects.length" class="px-4 py-2 text-xs text-zinc-400">
              加载中...
            </div>
            
            <SidebarMenuItem v-for="project in projects" :key="project.id">
              <SidebarMenuButton
                :is-active="selectedProject?.id === project.id"
                @click="handleProjectSelect(project.id)"
                class="group/item relative"
              >
                <div class="flex items-center gap-3 overflow-hidden w-full">
                  <MessageSquare class="size-4 shrink-0" />
                  <span class="truncate text-xs group-data-[collapsible=icon]:hidden">
                    {{ project.title || '未命名对话' }}
                  </span>
                </div>
              </SidebarMenuButton>
            </SidebarMenuItem>
            
            <div v-if="!loadingHistory && !projects.length" class="px-4 py-4 text-center group-data-[collapsible=icon]:hidden">
              <p class="text-[11px] text-zinc-400">暂无对话历史</p>
            </div>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </SidebarContent>

    <SidebarFooter>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton as-child>
            <a :href="apiDocsUrl" target="_blank" rel="noreferrer">
              <Settings class="size-4" />
              <span class="group-data-[collapsible=icon]:hidden">API 文档</span>
            </a>
          </SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton as-child>
            <a :href="apiDocsUrl" target="_blank" rel="noreferrer">
              <HelpCircle class="size-4" />
              <span class="group-data-[collapsible=icon]:hidden">Get Help</span>
            </a>
          </SidebarMenuButton>
        </SidebarMenuItem>

        <SidebarMenuItem class="mt-2">
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <SidebarMenuButton
                size="lg"
                class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                :disabled="loggingOut"
              >
                <Avatar class="h-8 w-8 rounded-lg">
                  <AvatarImage
                    v-if="user.avatar_url"
                    :src="user.avatar_url"
                    class="object-cover rounded-lg"
                  />
                  <AvatarFallback class="rounded-lg">{{
                    user.name?.charAt(0)?.toUpperCase() || "U"
                  }}</AvatarFallback>
                </Avatar>
                <div
                  class="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden"
                >
                  <span class="truncate font-semibold">{{ user.name }}</span>
                  <span class="truncate text-xs">{{ user.email }}</span>
                </div>
                <MoreHorizontal
                  class="ml-auto size-4 group-data-[collapsible=icon]:hidden"
                />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              class="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
              align="end"
              :side="'right'"
              :side-offset="8"
            >
              <DropdownMenuLabel class="p-0 font-normal">
                <div
                  class="flex items-center gap-2 px-1 py-1.5 text-left text-sm"
                >
                  <Avatar class="h-8 w-8 rounded-lg">
                    <AvatarImage
                      v-if="user.avatar_url"
                      :src="user.avatar_url"
                      class="object-cover rounded-lg"
                    />
                    <AvatarFallback class="rounded-lg">{{
                      user.name?.charAt(0)?.toUpperCase() || "U"
                    }}</AvatarFallback>
                  </Avatar>
                  <div class="grid flex-1 text-left text-sm leading-tight">
                    <span class="truncate font-semibold">{{ user.name }}</span>
                    <span class="truncate text-xs">{{ user.email }}</span>
                  </div>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuItem @click="navigateTo('/account')">
                  <UserCog class="mr-2 size-4" />
                  账户
                </DropdownMenuItem>
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <component
                      :is="colorMode === 'dark' ? Moon : Sun"
                      class="mr-2 size-4"
                    />
                    主题
                  </DropdownMenuSubTrigger>
                  <DropdownMenuPortal>
                    <DropdownMenuSubContent>
                      <DropdownMenuItem @click="setColorMode('light')">
                        <Sun class="mr-2 size-4" />
                        浅色
                        <Check
                          v-if="colorPreference === 'light'"
                          class="ml-auto size-4"
                        />
                      </DropdownMenuItem>
                      <DropdownMenuItem @click="setColorMode('dark')">
                        <Moon class="mr-2 size-4" />
                        深色
                        <Check
                          v-if="colorPreference === 'dark'"
                          class="ml-auto size-4"
                        />
                      </DropdownMenuItem>
                      <DropdownMenuItem @click="setColorMode('auto')">
                        <Monitor class="mr-2 size-4" />
                        系统
                        <Check
                          v-if="colorPreference === 'auto'"
                          class="ml-auto size-4"
                        />
                      </DropdownMenuItem>
                    </DropdownMenuSubContent>
                  </DropdownMenuPortal>
                </DropdownMenuSub>
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem @click="handleLogout">
                <LogOut class="mr-2 size-4" />
                {{ loggingOut ? "退出中..." : "退出登录" }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarFooter>
  </Sidebar>
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
