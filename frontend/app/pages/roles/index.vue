<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Plus, Pencil, Trash2, RefreshCw } from "lucide-vue-next";
import { toast } from "vue-sonner";
import { notifyError } from "@/utils/common";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Pagination } from "@/components/ui/pagination";
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
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import type { AuthPermission, AuthRole } from "@/types/api";
import PopupForm from "./popupForm.vue";

definePageMeta({
  middleware: "auth",
  layout: "console",
});

const api = useApi();

// --- 响应式状态 ---
const roles = ref<AuthRole[]>([]); // 角色列表
const permissions = ref<AuthPermission[]>([]); // 权限资源列表 (用于分配)
const loading = ref(false); // 全局加载状态
const showPopup = ref(false); // 控制新增/编辑弹窗
const editingRole = ref<AuthRole | null>(null); // 当前编辑的角色对象
const selectedIds = ref<string[]>([]); // 选中的行 ID

// --- 分页属性 ---
const currentPage = ref(1);
const pageSize = ref(10);

// --- 删除确认状态 ---
const showDeleteConfirm = ref(false);
const deleteRoleObj = ref<AuthRole | null>(null);
const deleteLoading = ref(false);

const totalCount = computed(() => roles.value.length);

const sortedRoles = computed(() =>
  [...roles.value].sort((a, b) => {
    const timeDiff =
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    return timeDiff !== 0 ? timeDiff : a.id.localeCompare(b.id);
  }),
);

/**
 * 分页截取角色数据
 */
const paginatedRoles = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return sortedRoles.value.slice(start, start + pageSize.value);
});

/**
 * 加载数据（角色列表 + 权限定义）
 * @param manual 是否手动刷新
 */
const loadData = async (manual = false) => {
  loading.value = true;
  try {
    const [roleList, permissionList] = await Promise.all([
      api.get<AuthRole[]>("/auth/roles"),
      api.get<AuthPermission[]>("/auth/permissions"),
    ]);
    roles.value = roleList;
    permissions.value = permissionList;
    if (manual) {
      toast.success("角色列表已刷新。");
    }
  } catch (error) {
    notifyError(api, error, "加载数据失败。");
  } finally {
    loading.value = false;
  }
};

/**
 * 打开新增角色窗口
 */
const openCreateRole = () => {
  editingRole.value = null;
  showPopup.value = true;
};

/**
 * 打开编辑角色窗口
 * @param role 角色对象
 */
const openEditRole = (role: AuthRole) => {
  editingRole.value = role;
  showPopup.value = true;
};

/**
 * 全选当前页
 */
const toggleSelectAll = (checked: boolean) => {
  if (checked) {
    selectedIds.value = paginatedRoles.value.map((r) => r.id);
  } else {
    selectedIds.value = [];
  }
};

/**
 * 打开删除确认对话框
 * @param role 目标角色
 */
const openDeleteConfirm = (role: AuthRole) => {
  if (role.is_system) {
    toast.error("系统内置角色无法删除。");
    return;
  }
  deleteRoleObj.value = role;
  showDeleteConfirm.value = true;
};

/**
 * 执行实际的角色删除接口
 */
const handleDelete = async () => {
  if (!deleteRoleObj.value) return;
  deleteLoading.value = true;
  try {
    await api.delete(`/auth/roles/${deleteRoleObj.value.id}`);
    toast.success("角色已成功删除。");
    showDeleteConfirm.value = false;
    deleteRoleObj.value = null;
    selectedIds.value = [];
    await loadData();
  } catch (error) {
    notifyError(api, error, "删除角色失败。");
  } finally {
    deleteLoading.value = false;
  }
};

onMounted(async () => {
  await loadData();
});
</script>

<template>
  <div class="p-6 space-y-4">
    <Card class="border-zinc-200/60 shadow-sm rounded-lg overflow-hidden">
      <CardContent class="p-4 space-y-4">
        <!-- 头部按钮栏 -->
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
                    <RefreshCw
                      :class="[
                        'size-4 text-zinc-500',
                        loading && 'animate-spin',
                      ]"
                    />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>手动刷新</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <Button
              size="sm"
              class="h-7 px-3 bg-zinc-900 rounded-[min(var(--radius-md),12px)] text-white gap-1.5 active:translate-y-px"
              @click="openCreateRole"
            >
              <Plus class="size-3.5" /> 新增角色
            </Button>
          </div>
        </div>

        <!-- 角色列表表格 -->
        <div class="border rounded-md border-zinc-100 overflow-hidden">
          <Table>
            <TableHeader class="bg-zinc-50/80">
              <TableRow class="h-10 hover:bg-transparent">
                <TableHead class="w-12 text-center">
                  <Checkbox
                    :checked="
                      selectedIds.length === paginatedRoles.length &&
                      paginatedRoles.length > 0
                    "
                    @update:checked="toggleSelectAll"
                  />
                </TableHead>
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >编号</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >角色名称</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >唯一编码</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >权限概览</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >系统标识</TableHead
                >
                <TableHead
                  class="text-[13px] font-bold text-zinc-700 text-center"
                  >操作</TableHead
                >
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow
                v-for="(item, index) in paginatedRoles"
                :key="item.id"
                class="h-12 hover:bg-zinc-50/50 transition-colors group"
              >
                <TableCell class="text-center">
                  <Checkbox
                    :checked="selectedIds.includes(item.id)"
                    @update:checked="
                      (val: boolean) =>
                        val
                          ? selectedIds.push(item.id)
                          : (selectedIds = selectedIds.filter(
                              (id) => id !== item.id,
                            ))
                    "
                  />
                </TableCell>
                <TableCell class="text-xs text-zinc-500">{{
                  index + 1 + (currentPage - 1) * pageSize
                }}</TableCell>
                <TableCell
                  class="text-sm font-semibold text-admin-blue cursor-pointer hover:underline"
                  @click="openEditRole(item)"
                >
                  {{ item.name }}
                </TableCell>
                <TableCell class="text-xs font-mono text-zinc-600">{{
                  item.code
                }}</TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    class="rounded-full bg-admin-cyan/5 text-admin-cyan border-admin-cyan/20 text-[10px] px-2 h-5"
                  >
                    {{ item.permissions?.length || 0 }} 项权限
                  </Badge>
                </TableCell>
                <TableCell>
                  <div class="flex items-center">
                    <Switch
                      :checked="!item.is_system"
                      disabled
                      class="data-[state=checked]:bg-admin-cyan cursor-not-allowed opacity-80"
                    />
                  </div>
                </TableCell>
                <TableCell>
                  <div class="flex items-center justify-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      class="h-7 px-2 text-zinc-600 hover:bg-zinc-100/50 gap-1 text-[11px] rounded-md"
                      @click="openEditRole(item)"
                    >
                      <Pencil class="size-3" /> 编辑
                    </Button>
                    <Button
                      v-if="!item.is_system"
                      variant="ghost"
                      size="sm"
                      class="h-7 px-2 text-red-500 hover:bg-red-50 gap-1 text-[11px] rounded-md"
                      @click="openDeleteConfirm(item)"
                    >
                      <Trash2 class="size-3" /> 删除
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
              <TableRow v-if="!loading && roles.length === 0">
                <TableCell
                  colspan="7"
                  class="py-20 text-center text-zinc-500 text-sm"
                >
                  暂无定义的系统角色数据。
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        <!-- 分页控制 -->
        <div class="flex items-center justify-between px-2 py-1">
          <Pagination
            v-if="totalCount > 0"
            :total-count="totalCount"
            :page-size="pageSize"
            :current-page="currentPage"
            @update:current-page="currentPage = $event"
            @update:page-size="pageSize = $event"
            class="border-none"
          />
        </div>
      </CardContent>
    </Card>

    <PopupForm
      v-model="showPopup"
      :role="editingRole"
      :permissions="permissions"
      @saved="loadData"
    />

    <!-- 安全删除提示 -->
    <Dialog :open="showDeleteConfirm" @update:open="showDeleteConfirm = $event">
      <DialogContent
        class="sm:max-w-md p-6 rounded-[24px] border-none shadow-2xl"
      >
        <DialogHeader>
          <DialogTitle>确认删除角色</DialogTitle>
          <DialogDescription>
            此操作无法撤销。您确定要删除角色“{{
              deleteRoleObj?.name
            }}”吗？这可能会影响已分配该角色的用户。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter class="flex justify-end gap-2 mt-6">
          <Button
            variant="ghost"
            size="sm"
            class="h-9 px-4 rounded-xl text-zinc-500 hover:bg-zinc-100"
            @click="showDeleteConfirm = false"
            :disabled="deleteLoading"
            >取消</Button
          >
          <Button
            variant="destructive"
            size="sm"
            class="h-9 px-5 rounded-xl font-bold shadow-lg shadow-red-500/20 active:scale-95 transition-all"
            @click="handleDelete"
            :disabled="deleteLoading"
          >
            <span v-if="deleteLoading" class="animate-spin mr-2">◌</span>
            确认删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
