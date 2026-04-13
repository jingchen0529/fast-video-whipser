<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import {
  ChevronDown,
  ChevronRight,
  Folder,
  AppWindow,
  FileText,
  FolderTree,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Trash2,
} from "lucide-vue-next";
import { toast } from "vue-sonner";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AuthMenu } from "@/types/api";
import { notifyError } from "@/utils/common";
import MenuPopupForm from "./popupForm.vue";

definePageMeta({
  middleware: "auth",
  layout: "console",
});

type FlattenedMenuNode = AuthMenu & {
  level: number;
  parentId: string | null;
  isVisible: boolean;
};

const api = useApi();

const menus = ref<AuthMenu[]>([]);
const loading = ref(false);
const showSearch = ref(true);
const showDialog = ref(false);
const showDeleteConfirm = ref(false);
const deleteLoading = ref(false);
const selectedMenu = ref<AuthMenu | null>(null);
const deletingMenu = ref<AuthMenu | null>(null);
const expandedKeys = ref<Set<string>>(new Set());

const queryParams = reactive({
  menuName: "",
  menuType: "all",
  status: "all",
});

const flattenMenus = (
  items: AuthMenu[],
  level = 0,
  parentId: string | null = null,
  parentVisible = true,
): FlattenedMenuNode[] => {
  return items.flatMap((item) => {
    const isVisible =
      parentVisible &&
      (parentId === null || expandedKeys.value.has(parentId));
    return [
      {
        ...item,
        level,
        isVisible,
        parentId,
      },
      ...flattenMenus(item.children || [], level + 1, item.id, isVisible),
    ];
  });
};

const allMenus = computed(() => flattenMenus(menus.value));

const filteredMenus = computed(() => {
  const keyword = queryParams.menuName.trim().toLowerCase();

  const hasFilter =
    keyword || queryParams.menuType !== "all" || queryParams.status !== "all";
  if (!hasFilter) {
    return allMenus.value.filter((item) => item.isVisible);
  }

  const matchedNodes = new Set<string>();
  const matchesFilter = (item: AuthMenu) => {
    const matchesKeyword =
      !keyword ||
      [item.title, item.code, item.route_path].some((value) =>
        value && value.toLowerCase().includes(keyword),
      );
    const matchesType =
      queryParams.menuType === "all" || item.menu_type === queryParams.menuType;
    const matchesStatus =
      queryParams.status === "all" ||
      (queryParams.status === "enabled" && item.is_enabled) ||
      (queryParams.status === "disabled" && !item.is_enabled);

    return matchesKeyword && matchesType && matchesStatus;
  };

  const traverse = (items: AuthMenu[]) => {
    let anyMatch = false;
    for (const item of items) {
      const childMatch = item.children ? traverse(item.children) : false;
      const selfMatch = matchesFilter(item);
      if (childMatch || selfMatch) {
        matchedNodes.add(item.id);
        if (childMatch) {
          expandedKeys.value.add(item.id);
        }
        anyMatch = true;
      }
    }
    return anyMatch;
  };
  traverse(menus.value);

  return allMenus.value.filter((item) => matchedNodes.has(item.id));
});

const toggleExpand = (id: string) => {
  const newSet = new Set(expandedKeys.value);
  if (newSet.has(id)) newSet.delete(id);
  else newSet.add(id);
  expandedKeys.value = newSet;
};

const collectDescendantIds = (items: AuthMenu[]): string[] => {
  return items.flatMap((item) => [item.id, ...collectDescendantIds(item.children || [])]);
};

const findMenuById = (items: AuthMenu[], targetId: string): AuthMenu | null => {
  for (const item of items) {
    if (item.id === targetId) {
      return item;
    }
    const matched = findMenuById(item.children || [], targetId);
    if (matched) {
      return matched;
    }
  }
  return null;
};

const parentOptions = computed(() => {
  const excludedIds = new Set<string>();
  if (selectedMenu.value?.id) {
    const current = findMenuById(menus.value, selectedMenu.value.id);
    if (current) {
      for (const itemId of collectDescendantIds([current])) {
        excludedIds.add(itemId);
      }
    }
  }

  return allMenus.value.filter((item) => {
    return item.menu_type === "directory" && !excludedIds.has(item.id);
  });
});

const loadData = async (manual = false) => {
  loading.value = true;
  try {
    menus.value = await api.get<AuthMenu[]>("/menus/tree");
    if (expandedKeys.value.size === 0 && menus.value.length > 0) {
      const getDirs = (items: AuthMenu[]): string[] => {
        return items.flatMap((item) =>
          item.children?.length ? [item.id, ...getDirs(item.children)] : [],
        );
      };
      expandedKeys.value = new Set(getDirs(menus.value));
    }
    if (manual) {
      toast.success("菜单定义已刷新。");
    }
  } catch (error) {
    notifyError(api, error, "加载菜单数据失败。");
  } finally {
    loading.value = false;
  }
};

const handleQuery = () => {
  return;
};

const resetQuery = () => {
  queryParams.menuName = "";
  queryParams.menuType = "all";
  queryParams.status = "all";
  handleQuery();
};

const openCreateMenu = (parent?: AuthMenu) => {
  selectedMenu.value = parent ? ({ parent_id: parent.id } as any) : null;
  showDialog.value = true;
};

const openEditMenu = (menu: AuthMenu) => {
  selectedMenu.value = menu;
  showDialog.value = true;
};

const handleSaved = async () => {
  await loadData();
};

const requestRemoveMenu = (menu: AuthMenu) => {
  deletingMenu.value = menu;
  showDeleteConfirm.value = true;
};

const updateDeleteDialogOpen = (open: boolean) => {
  showDeleteConfirm.value = open;
  if (!open && !deleteLoading.value) {
    deletingMenu.value = null;
  }
};

const confirmRemoveMenu = async () => {
  if (!deletingMenu.value) {
    return;
  }

  deleteLoading.value = true;
  try {
    await api.delete<{ deleted: boolean }>(`/menus/${deletingMenu.value.id}`);
    toast.success("菜单已删除。");
    updateDeleteDialogOpen(false);
    await loadData();
  } catch (error) {
    notifyError(api, error, "删除菜单失败。");
  } finally {
    deleteLoading.value = false;
  }
};

const actionButtonClass =
  "h-[26px] rounded-md border border-zinc-200 bg-white px-2 text-[11px] font-medium text-zinc-700 shadow-none hover:bg-zinc-100";

const hasMenuCode = (menu: AuthMenu) => `${menu.code || ""}`.trim().length > 0;

onMounted(async () => {
  await loadData();
});
</script>


<template>
  <div class="space-y-4 p-6">
    <Card
      v-show="showSearch"
      class="rounded-lg border-zinc-200/60 shadow-sm"
    >
      <CardContent class="p-4">
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex items-center gap-2">
            <label class="whitespace-nowrap text-[13px] font-medium text-zinc-600">
              菜单名称：
            </label>
            <Input
              v-model="queryParams.menuName"
              placeholder="按标题 / 编码 / 路由搜索"
              class="h-8 w-60 rounded-md border-zinc-200 text-[13px]"
            />
          </div>
          <div class="flex items-center gap-2">
            <label class="whitespace-nowrap text-[13px] font-medium text-zinc-600">
              菜单类型：
            </label>
            <Select v-model="queryParams.menuType">
              <SelectTrigger class="h-8 w-32 rounded-md border-zinc-200 text-[13px]">
                <SelectValue placeholder="所有" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">所有</SelectItem>
                <SelectItem value="directory">目录</SelectItem>
                <SelectItem value="menu">菜单</SelectItem>
                <SelectItem value="link">外链</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="flex items-center gap-2">
            <label class="whitespace-nowrap text-[13px] font-medium text-zinc-600">
              状态：
            </label>
            <Select v-model="queryParams.status">
              <SelectTrigger class="h-8 w-32 rounded-md border-zinc-200 text-[13px]">
                <SelectValue placeholder="所有" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">所有</SelectItem>
                <SelectItem value="enabled">启用</SelectItem>
                <SelectItem value="disabled">停用</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="ml-auto flex items-center gap-2">
            <Button
              size="sm"
              class="h-7 gap-1 rounded-[min(var(--radius-md),12px)] bg-zinc-900 px-2.5 text-[0.8rem] text-white transition-all active:translate-y-px"
              @click="handleQuery"
            >
              <Search class="size-3.5" />
              搜索
            </Button>
            <Button
              variant="outline"
              size="sm"
              class="h-7 gap-1 rounded-[min(var(--radius-md),12px)] border-zinc-200 px-2.5 text-[0.8rem] text-zinc-600 transition-all hover:bg-zinc-50 active:translate-y-px"
              @click="resetQuery"
            >
              <RotateCcw class="size-3.5" />
              重置
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <Card class="overflow-hidden rounded-lg border-zinc-200/60 shadow-sm">
      <CardContent class="space-y-4 p-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button
                    variant="ghost"
                    size="icon"
                    class="size-8 rounded-full border border-zinc-200"
                    @click="loadData(true)"
                  >
                    <RefreshCw :class="['size-4 text-zinc-500', loading && 'animate-spin']" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>刷新</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <Button
              size="sm"
              class="h-7 gap-1 rounded-[min(var(--radius-md),12px)] bg-zinc-900 px-2.5 text-[0.8rem] text-white transition-all active:translate-y-px"
              @click="openCreateMenu()"
            >
              <Plus class="size-3.5" />
              新增菜单
            </Button>
          </div>

          <div class="flex items-center gap-2">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button
                    variant="ghost"
                    size="icon"
                    class="size-8 rounded-full border border-zinc-200"
                    @click="showSearch = !showSearch"
                  >
                    <Search class="size-4 text-zinc-500" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>显示/隐藏搜索</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>

        <div class="overflow-hidden rounded-md border border-zinc-100 bg-white">
          <Table class="border-t-0">
            <TableHeader class="bg-zinc-50 hover:bg-zinc-50">
              <TableRow class="h-11 border-b-zinc-100 hover:bg-transparent">
                <TableHead class="w-[320px] text-[13px] font-bold text-zinc-700">
                  菜单名称
                </TableHead>
                <TableHead class="min-w-[180px] text-[13px] font-bold text-zinc-700">
                  请求地址
                </TableHead>
                <TableHead class="w-[88px] text-center text-[13px] font-bold text-zinc-700">
                  类型
                </TableHead>
                <TableHead class="w-[88px] text-center text-[13px] font-bold text-zinc-700">
                  可见
                </TableHead>
                <TableHead class="min-w-[200px] text-[13px] font-bold text-zinc-700">
                  菜单编码
                </TableHead>
                <TableHead class="w-[240px] text-center text-[13px] font-bold text-zinc-700">
                  操作
                </TableHead>
              </TableRow>
            </TableHeader>

            <TableBody v-if="!filteredMenus.length">
              <TableRow>
                <TableCell
                  colspan="6"
                  class="h-32 border-none text-center text-sm text-zinc-400"
                >
                  暂无菜单数据。
                </TableCell>
              </TableRow>
            </TableBody>

            <TableBody v-else>
              <TableRow
                v-for="menu in filteredMenus"
                :key="menu.id"
                class="border-b-zinc-100/80 transition-colors hover:bg-zinc-50/60"
              >
                <TableCell class="border-none p-0">
                  <div
                    class="flex h-full items-center px-4 py-3"
                    :style="{ paddingLeft: `${menu.level * 24 + 16}px` }"
                  >
                    <button
                      class="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm outline-none"
                      :class="
                        menu.children && menu.children.length
                          ? 'cursor-pointer text-zinc-500 hover:bg-zinc-100'
                          : 'pointer-events-none text-transparent'
                      "
                      @click="toggleExpand(menu.id)"
                    >
                      <ChevronDown
                        v-if="expandedKeys.has(menu.id)"
                        class="h-[14px] w-[14px]"
                      />
                      <ChevronRight v-else class="h-[14px] w-[14px]" />
                    </button>

                    <component
                      :is="menu.menu_type === 'directory' ? Folder : (menu.menu_type === 'menu' ? AppWindow : FileText)"
                      class="ml-1 mr-1.5 h-[14px] w-[14px] shrink-0 text-zinc-400"
                    />
                    <span class="whitespace-nowrap text-[13px] font-medium tracking-wide text-zinc-700">
                      {{ menu.title }}
                    </span>
                  </div>
                </TableCell>

                <TableCell class="border-none py-3 font-sans text-[13px] text-zinc-600">
                  {{ menu.route_path || (menu.menu_type === 'directory' ? '#' : '-') }}
                </TableCell>

                <TableCell class="border-none py-3 text-center">
                  <Badge
                    class="h-[22px] rounded border border-zinc-900 bg-zinc-900 px-1.5 py-0.5 text-[11px] font-normal tracking-wide text-white shadow-none"
                  >
                    {{
                      menu.menu_type === "directory"
                        ? "目录"
                        : menu.menu_type === "link"
                          ? "外链"
                          : "菜单"
                    }}
                  </Badge>
                </TableCell>

                <TableCell class="border-none py-3 text-center">
                  <Badge
                    :class="
                      menu.is_visible
                        ? 'h-[22px] rounded border border-zinc-900 bg-zinc-900 px-1.5 py-0.5 text-[11px] font-normal tracking-wide text-white shadow-none'
                        : 'h-[22px] rounded border border-zinc-200 bg-white px-1.5 py-0.5 text-[11px] font-normal tracking-wide text-zinc-500 shadow-none'
                    "
                  >
                    {{ menu.is_visible ? "显示" : "隐藏" }}
                  </Badge>
                </TableCell>

                <TableCell class="border-none py-3 text-zinc-600">
                  <div
                    v-if="hasMenuCode(menu)"
                    class="inline-flex items-center rounded border border-zinc-200 bg-zinc-50 px-1.5 py-0.5 font-mono text-[12px] text-zinc-500"
                  >
                    {{ menu.code }}
                  </div>
                  <span v-else class="text-[13px] text-zinc-400">-</span>
                </TableCell>

                <TableCell class="border-none py-3 text-center">
                  <div class="flex flex-nowrap items-center justify-center gap-1.5 whitespace-nowrap">
                    <Button
                      size="sm"
                      :class="`${actionButtonClass} border-zinc-900 bg-zinc-900 text-white hover:bg-zinc-800`"
                      @click="openEditMenu(menu)"
                    >
                      <Pencil class="h-[11px] w-[11px]" />
                      修改
                    </Button>
                    <Button
                      v-if="menu.menu_type !== 'link'"
                      size="sm"
                      :class="actionButtonClass"
                      @click="openCreateMenu(menu)"
                    >
                      <Plus class="h-[11px] w-[11px]" />
                      新增
                    </Button>
                    <Button
                      size="sm"
                      :class="actionButtonClass"
                      @click="requestRemoveMenu(menu)"
                    >
                      <Trash2 class="h-[11px] w-[11px]" />
                      删除
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>

    <MenuPopupForm
      v-model="showDialog"
      :menu="selectedMenu"
      :parent-options="parentOptions"
      @saved="handleSaved"
    />

    <Dialog
      :open="showDeleteConfirm"
      @update:open="updateDeleteDialogOpen"
    >
      <DialogContent class="sm:max-w-md rounded-[24px] border-none p-6 shadow-2xl">
        <DialogHeader>
          <DialogTitle>确认删除菜单</DialogTitle>
          <DialogDescription>
            确定要删除菜单“{{ deletingMenu?.title || "-" }}”吗？如果该菜单仍包含子菜单，后端会阻止删除。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter class="mt-6 flex justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            class="h-9 rounded-xl px-4 text-zinc-500 hover:bg-zinc-100"
            :disabled="deleteLoading"
            @click="updateDeleteDialogOpen(false)"
          >
            取消
          </Button>
          <Button
            size="sm"
            class="h-9 rounded-xl border border-zinc-900 bg-zinc-900 px-5 font-bold text-white hover:bg-zinc-800"
            :disabled="deleteLoading"
            @click="confirmRemoveMenu"
          >
            <span v-if="deleteLoading" class="mr-2 animate-pulse">◌</span>
            确认删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
