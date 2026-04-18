<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { toast } from "vue-sonner";
import {
  Check,
  Captions,
  ChevronDown,
  ChevronRight,
  FolderTree,
  HardDrive,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  Monitor,
  MoreHorizontal,
  Moon,
  Pencil,
  Plus,
  MessageSquare,
  Shapes,
  ShieldCheck,
  Sparkles,
  Sun,
  Settings,
  Trash2,
  UserCog,
} from "lucide-vue-next";
import { useColorMode } from "@vueuse/core";
import type { Component } from "vue";
import type { AuthMenu } from "@/types/api";

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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
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
} from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

const auth = useAuth();
const loadingOverlay = useLoadingOverlay();
const route = useRoute();
const colorMode = useColorMode();
const runtimeConfig = useRuntimeConfig();
const loggingOut = ref(false);
const avatarCacheBust = ref("");

onMounted(() => {
  avatarCacheBust.value = String(Date.now());
});

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
      ? `${avatarUrl}${avatarUrl.includes("?") ? "&" : "?"}_t=${avatarCacheBust.value}`
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
    toast.error("服务端退出失败，已清理本地状态；如仍自动登录，请刷新页面或清理站点 Cookie。");
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

const handleProjectSelect = (projectId: number) => {
  useRouter().push({ path: '/video/history', query: { id: projectId } });
};

const startNewChat = () => {
  chatStore.selectedProject = null;
  navigateTo("/video/workbench");
};

const handleNavClick = (url: string) => {
  if (url === "/video/workbench") {
    chatStore.selectedProject = null;
  }
};

const renamingProjectId = ref<number | null>(null);
const renameTitle = ref("");
const showRenameDialog = ref(false);

const deletingProjectId = ref<number | null>(null);
const deletingProjectTitle = ref("");
const showDeleteDialog = ref(false);
const isHistoryOpen = ref(true);

const handleRename = (project: any) => {
  renamingProjectId.value = project.id;
  renameTitle.value = project.title || "";
  showRenameDialog.value = true;
};

const submitRename = async () => {
  if (renamingProjectId.value === null || !renameTitle.value.trim()) {
    showRenameDialog.value = false;
    return;
  }
  const id = renamingProjectId.value;
  try {
    await api(`/projects/${id}`, {
      method: "PATCH",
      body: { title: renameTitle.value.trim() },
    });
    chatStore.projects = chatStore.projects.map((p: any) =>
      p.id === id ? { ...p, title: renameTitle.value.trim() } : p,
    );
    if (chatStore.selectedProject?.id === id) {
      chatStore.selectedProject.title = renameTitle.value.trim();
    }
    toast.success("重命名完成");
    showRenameDialog.value = false;
  } catch (error) {
    toast.error("操作失败，请重试");
  }
};

const handleDeleteRequest = (project: any) => {
  deletingProjectId.value = project.id;
  deletingProjectTitle.value = project.title || "未命名对话";
  showDeleteDialog.value = true;
};

const confirmDelete = async () => {
  if (deletingProjectId.value === null) return;
  const id = deletingProjectId.value;
  try {
    await api(`/projects/${id}`, { method: "DELETE" });
    chatStore.projects = chatStore.projects.filter((p: any) => p.id !== id);
    if (chatStore.selectedProject?.id === id) {
      chatStore.selectedProject = null;
      useRouter().push("/video/workbench");
    }
    toast.success("对话已删除");
    showDeleteDialog.value = false;
  } catch (error) {
    toast.error("删除失败");
  }
};

type SidebarNavigationItem = AuthMenu & {
  level: number;
  hasChildren: boolean;
};

type SidebarNavigationGroup = {
  key: string;
  title: string | null;
  items: SidebarNavigationItem[];
};

const navigationMenus = ref<AuthMenu[]>([]);
const navigationRequestFailed = ref(false);

  const iconMap: Record<string, Component> = {
    Captions,
    FolderTree,
    HardDrive,
    LayoutDashboard,
    Settings,
  ShieldCheck,
  Shapes,
  Sparkles,
  UserCog,
};

const createFallbackMenu = (
  menu: Partial<AuthMenu> &
    Pick<AuthMenu, "id" | "code" | "title" | "menu_type">,
): AuthMenu => ({
  parent_id: null,
  route_path: "",
  route_name: null,
  redirect_path: null,
  icon: null,
  component_key: null,

  sort_order: 0,
  is_visible: true,
  is_enabled: true,
  is_external: false,
  open_mode: "self",
  is_cacheable: false,
  is_affix: false,
  active_menu_path: null,
  badge_text: null,
  badge_type: null,
  remark: null,
  meta_json: {},
  created_at: "",
  updated_at: "",
  children: [],
  ...menu,
});

const fallbackMenus: AuthMenu[] = [
  createFallbackMenu({
    id: "fallback-dashboard",
    code: "dashboard.root",
    title: "仪表盘",
    menu_type: "menu",
    route_path: "/dashboard",
    icon: "LayoutDashboard",
    sort_order: 10,
  }),
  createFallbackMenu({
    id: "fallback-system",
    code: "system.root",
    title: "系统",
    menu_type: "directory",
    icon: "Settings",
    sort_order: 20,
    children: [
      createFallbackMenu({
        id: "fallback-users",
        parent_id: "fallback-system",
        code: "system.users",
        title: "用户管理",
        menu_type: "menu",
        route_path: "/users",
        icon: "UserCog",

        sort_order: 10,
      }),
      createFallbackMenu({
        id: "fallback-roles",
        parent_id: "fallback-system",
        code: "system.roles",
        title: "角色管理",
        menu_type: "menu",
        route_path: "/roles",
        icon: "ShieldCheck",

        sort_order: 20,
      }),
      createFallbackMenu({
        id: "fallback-menus",
        parent_id: "fallback-system",
        code: "system.menus",
        title: "菜单管理",
        menu_type: "menu",
        route_path: "/menus",
        icon: "FolderTree",

        sort_order: 30,
      }),
    ],
  }),
  createFallbackMenu({
    id: "fallback-creation",
    code: "creation.root",
    title: "创作",
    menu_type: "directory",
    icon: "Sparkles",
    sort_order: 30,
    children: [
      createFallbackMenu({
        id: "fallback-video-analysis",
        parent_id: "fallback-creation",
        code: "video.analysis",
        title: "视频分析",
        menu_type: "menu",
        route_path: "/video/workbench",
        icon: "Captions",

        sort_order: 10,
      }),
      createFallbackMenu({
        id: "fallback-motion-extract",
        parent_id: "fallback-creation",
        code: "motion.extract",
        title: "动作提取",
        menu_type: "menu",
        route_path: "/motion/extract",
        icon: "Shapes",
        sort_order: 20,
      }),
    ],
  }),
  createFallbackMenu({
    id: "fallback-space",
    code: "space.root",
    title: "空间",
    menu_type: "directory",
    icon: "HardDrive",
    sort_order: 40,
    children: [
      createFallbackMenu({
        id: "fallback-assets",
        parent_id: "fallback-space",
        code: "space.assets",
        title: "资产库",
        menu_type: "menu",
        route_path: "/assets",
        icon: "Shapes",

        sort_order: 10,
      }),
      createFallbackMenu({
        id: "fallback-motion-assets",
        parent_id: "fallback-space",
        code: "space.motions",
        title: "动作资产库",
        menu_type: "menu",
        route_path: "/assets/motions",
        icon: "Sparkles",
        sort_order: 20,
      }),
    ],
  }),
];


const effectiveNavigationMenus = computed(() => {
  if (navigationRequestFailed.value) {
    return fallbackMenus;
  }
  return navigationMenus.value;
});

const flattenNavigationItems = (
  items: AuthMenu[],
  level = 0,
): SidebarNavigationItem[] => {
  return items.flatMap((item) => {
    const children = flattenNavigationItems(item.children || [], level + 1);
    return [
      {
        ...item,
        level,
        hasChildren: children.length > 0,
      },
      ...children,
    ];
  });
};

const navigationGroups = computed<SidebarNavigationGroup[]>(() => {
  return effectiveNavigationMenus.value.flatMap((item): SidebarNavigationGroup[] => {
    if (item.menu_type === "directory") {
      const items = flattenNavigationItems(item.children || []);
      if (!items.length) {
        return [];
      }
      return [
        {
          key: item.id,
          title: item.title,
          items,
        },
      ];
    }

    return [
      {
        key: item.id,
        title: null,
        items: flattenNavigationItems([item]),
      },
    ];
  });
});

const resolveMenuIcon = (menu: AuthMenu) => {
  return (menu.icon && iconMap[menu.icon]) || (menu.menu_type === "directory"
    ? FolderTree
    : LayoutDashboard);
};

const isMenuActive = (menu: AuthMenu) => {
  const activePath = (menu.active_menu_path || menu.route_path || "").trim();
  if (!activePath) {
    return false;
  }

  // /video/history 由侧边栏历史对话列表负责高亮，不高亮导航菜单项
  if (route.path.startsWith('/video/history')) {
    return false;
  }

  if (route.path === activePath) {
    return true;
  }

  // 处理子路径情况：找出所有匹配当前路由的菜单，保留最长的匹配项以防止多个父路径菜单同时高亮
  if (route.path.startsWith(`${activePath}/`)) {
    const allMenuItems = effectiveNavigationMenus.value.flatMap(m => flattenNavigationItems([m]));
    let bestMatchLen = 0;
    
    allMenuItems.forEach((m) => {
      const p = (m.active_menu_path || m.route_path || "").trim();
      if (p && (route.path === p || route.path.startsWith(`${p}/`))) {
        if (p.length > bestMatchLen) {
          bestMatchLen = p.length;
        }
      }
    });

    return activePath.length >= bestMatchLen;
  }

  return false;
};

const loadNavigation = async () => {
  try {
    navigationMenus.value = await api<AuthMenu[]>("/auth/me/navigation");
    navigationRequestFailed.value = false;
  } catch (error) {
    navigationRequestFailed.value = true;
    navigationMenus.value = [];
    console.error(error);
  }
};

onMounted(async () => {
  await Promise.all([loadProjects(), loadNavigation()]);
});
</script>

<template>
  <Sidebar variant="inset" collapsible="icon" class="border-r border-zinc-200">
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
                  class="flex items-center gap-2 text-sm font-semibold text-zinc-900"
                >
                  <img
                    src="/logo.png"
                    :alt="brandName"
                    class="h-7 w-auto max-w-[132px] object-contain shrink-0"
                  />
                  <span
                    class="whitespace-nowrap group-data-[collapsible=icon]:hidden"
                    >{{ brandName }}</span
                  >
                </div>
              </SidebarMenuButton>
            </DropdownMenuTrigger>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>

    <SidebarContent>
      <SidebarGroup v-for="group in navigationGroups" :key="group.key">
        <SidebarGroupLabel
          v-if="group.title"
          class="group-data-[collapsible=icon]:hidden"
        >
          {{ group.title }}
        </SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarMenuItem
              v-for="item in group.items"
              :key="item.id"
            >
              <template v-if="item.menu_type === 'directory'">
                <div
                  class="flex items-center gap-2 px-2 py-1.5 text-[11px] font-medium text-zinc-400 group-data-[collapsible=icon]:hidden"
                  :style="{ paddingLeft: `${8 + item.level * 12}px` }"
                >
                  <component :is="resolveMenuIcon(item)" class="size-3.5 shrink-0" />
                  <span class="truncate">{{ item.title }}</span>
                </div>
              </template>

              <template v-else-if="item.is_external || item.menu_type === 'link'">
                <SidebarMenuButton as-child :is-active="isMenuActive(item)">
                  <a
                    :href="item.route_path || '#'"
                    :target="item.open_mode === 'blank' ? '_blank' : '_self'"
                    rel="noreferrer"
                  >
                    <div
                      class="flex w-full items-center gap-2"
                      :style="{ paddingLeft: `${item.level * 12}px` }"
                    >
                      <component :is="resolveMenuIcon(item)" class="size-4 shrink-0" />
                      <span class="group-data-[collapsible=icon]:hidden">{{
                        item.title
                      }}</span>
                    </div>
                  </a>
                </SidebarMenuButton>
              </template>

              <template v-else>
                <SidebarMenuButton as-child :is-active="isMenuActive(item)">
                  <NuxtLink
                    :to="item.route_path || '/dashboard'"
                    @click="handleNavClick(item.route_path || '')"
                  >
                    <div
                      class="flex w-full items-center gap-2"
                      :style="{ paddingLeft: `${item.level * 12}px` }"
                    >
                      <component :is="resolveMenuIcon(item)" class="size-4 shrink-0" />
                      <span class="group-data-[collapsible=icon]:hidden">{{
                        item.title
                      }}</span>
                    </div>
                  </NuxtLink>
                </SidebarMenuButton>
              </template>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <SidebarGroup v-if="!navigationGroups.length">
        <SidebarGroupContent>
          <div class="px-4 py-2 text-xs text-zinc-400 group-data-[collapsible=icon]:hidden">
            暂无可用菜单
          </div>
        </SidebarGroupContent>
      </SidebarGroup>

      <SidebarGroup
        class="mt-2 pt-2 border-t border-zinc-100 dark:border-zinc-800/50 flex flex-col min-h-0"
      >
        <Collapsible v-model:open="isHistoryOpen" class="w-full">
          <div
            class="px-2 mb-1 group-data-[collapsible=icon]:hidden"
          >
            <CollapsibleTrigger as-child>
              <div
                class="flex items-center justify-between cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-800/50 px-2 py-1.5 rounded-md transition-colors"
              >
                <SidebarGroupLabel class="px-0 cursor-pointer h-auto py-0"
                  >历史对话</SidebarGroupLabel
                >
                <component
                  :is="isHistoryOpen ? ChevronDown : ChevronRight"
                  class="size-3.5 text-zinc-500"
                />
              </div>
            </CollapsibleTrigger>
          </div>

          <CollapsibleContent class="flex-1 overflow-y-auto custom-scrollbar">
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem
                  class="px-2 mb-1 group-data-[collapsible=icon]:block hidden"
                >
                  <SidebarMenuButton @click="startNewChat" tooltip="新建对话">
                    <Plus class="size-4" />
                  </SidebarMenuButton>
                </SidebarMenuItem>

                <div
                  v-if="loadingHistory && !projects.length"
                  class="px-4 py-2 text-xs text-zinc-400"
                >
                  加载中...
                </div>

                <SidebarMenuItem v-for="project in projects" :key="project.id">
                  <SidebarMenuButton
                    :is-active="route.path.startsWith('/video/history') && Number(route.query.id) === project.id"
                    @click="handleProjectSelect(project.id)"
                    class="group/item relative h-9 w-full transition-all duration-200 hover:bg-zinc-100/80 dark:hover:bg-zinc-800/80"
                  >
                    <div
                      class="flex items-center gap-2.5 overflow-hidden w-full pr-6 group-hover/item:pr-8"
                    >
                      <MessageSquare
                        class="size-3.5 shrink-0 transition-colors"
                        :class="
                          selectedProject?.id === project.id
                            ? 'text-zinc-400'
                            : 'text-zinc-400 group-hover/item:text-zinc-600 dark:group-hover/item:text-zinc-300'
                        "
                      />
                      <div class="flex-1 overflow-hidden mt-0.5">
                        <TooltipProvider :delay-duration="800">
                          <Tooltip>
                            <TooltipTrigger as-child>
                              <span
                                class="truncate text-[12px] block group-data-[collapsible=icon]:hidden font-medium cursor-help"
                                :class="
                                  selectedProject?.id === project.id
                                    ? 'text-zinc-900 dark:text-zinc-100'
                                    : 'text-zinc-600 dark:text-zinc-400'
                                "
                              >
                                {{ project.title || "未命名对话" }}
                              </span>
                            </TooltipTrigger>
                            <TooltipContent
                              side="right"
                              class="bg-zinc-900 text-white border-zinc-800 px-3 py-1.5 text-xs rounded-lg max-w-[240px]"
                            >
                              <p>{{ project.title || "未命名对话" }}</p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </div>
                    </div>

                    <!-- More Options Menu -->
                    <div
                      class="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover/item:opacity-100 focus-within:opacity-100 transition-opacity group-data-[collapsible=icon]:hidden"
                      @click.stop
                    >
                      <DropdownMenu>
                        <DropdownMenuTrigger as-child>
                          <Button
                            variant="ghost"
                            size="icon"
                            class="h-6 w-6 rounded-md hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100"
                          >
                            <MoreHorizontal class="size-3.5" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" class="w-28">
                          <DropdownMenuItem @click="handleRename(project)">
                            <Pencil class="mr-2 size-3.5" />
                            <span>重命名</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            @click="handleDeleteRequest(project)"
                            class="text-red-500 focus:text-red-500"
                          >
                            <Trash2 class="mr-2 size-3.5" />
                            <span>删除</span>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </SidebarMenuButton>
                </SidebarMenuItem>

                <div
                  v-if="!loadingHistory && !projects.length"
                  class="px-4 py-4 text-center group-data-[collapsible=icon]:hidden"
                >
                  <p class="text-[11px] text-zinc-400">暂无对话历史</p>
                </div>
              </SidebarMenu>
            </SidebarGroupContent>
          </CollapsibleContent>
        </Collapsible>
      </SidebarGroup>
    </SidebarContent>

    <SidebarFooter>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            as-child
            :is-active="route.path.startsWith('/settings')"
          >
            <NuxtLink to="/settings">
              <Settings class="size-4" />
              <span class="group-data-[collapsible=icon]:hidden">系统设置</span>
            </NuxtLink>
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
                  <TooltipProvider :delay-duration="500">
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <span class="truncate font-semibold cursor-help">{{
                          user.name
                        }}</span>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        <p>{{ user.name }}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>

                  <TooltipProvider :delay-duration="500">
                    <Tooltip>
                      <TooltipTrigger as-child>
                        <span class="truncate text-xs cursor-help">{{
                          user.email
                        }}</span>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        <p>{{ user.email }}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
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

    <!-- Project Rename Dialog -->
    <Dialog v-model:open="showRenameDialog">
      <DialogContent class="sm:max-w-[600px] rounded-2xl">
        <DialogHeader>
          <DialogTitle class="text-lg font-semibold">重命名对话</DialogTitle>
          <DialogDescription class="text-sm text-zinc-500">
            请输入该对话的新标题。
          </DialogDescription>
        </DialogHeader>
        <div class="grid gap-4 py-4">
          <Textarea
            v-model="renameTitle"
            placeholder="对话标题"
            class="min-h-[100px] w-full rounded-2xl border border-zinc-200 bg-zinc-50/50 p-3 text-sm focus-visible:ring-2 focus-visible:ring-zinc-900/10 focus-visible:border-zinc-900 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-100 dark:focus-visible:border-white dark:focus-visible:ring-white/10 resize-y"
            @keydown.enter.prevent="submitRename"
          />
        </div>
        <DialogFooter class="gap-3">
          <Button
            variant="ghost"
            class="rounded-full px-6"
            @click="showRenameDialog = false"
            >取消</Button
          >
          <Button
            class="rounded-full px-6 bg-zinc-900 hover:bg-zinc-800 text-white dark:bg-zinc-100 dark:hover:bg-zinc-200 dark:text-zinc-900"
            @click="submitRename"
            :disabled="!renameTitle.trim()"
            >确定</Button
          >
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Project Delete Dialog -->
    <Dialog v-model:open="showDeleteDialog">
      <DialogContent class="sm:max-w-[400px] rounded-2xl">
        <DialogHeader>
          <DialogTitle class="text-lg font-semibold flex items-center gap-2">
            <div
              class="p-2 rounded-full bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400"
            >
              <Trash2 class="size-4" />
            </div>
            删除对话
          </DialogTitle>
          <DialogDescription
            class="pt-2 text-zinc-600 dark:text-zinc-400 leading-relaxed"
          >
            确定要删除该对话吗？删除后将无法恢复。<br />
            <span
              class="mt-2 block font-medium text-zinc-900 dark:text-zinc-100"
              >"{{ deletingProjectTitle }}"</span
            >
          </DialogDescription>
        </DialogHeader>
        <DialogFooter class="mt-4 gap-3">
          <Button
            variant="ghost"
            class="rounded-full px-6"
            @click="showDeleteDialog = false"
            >取消</Button
          >
          <Button
            variant="destructive"
            class="rounded-full px-6"
            @click="confirmDelete"
            >删除</Button
          >
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
