<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Plus, Pencil, Trash2, RefreshCw } from "lucide-vue-next";
import { toast } from "vue-sonner";
import { notifyError, formatDateTime } from "@/utils/common";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
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
import type { AuthRole, AuthUser } from "@/types/api";
import PopupForm from "./popupForm.vue";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";

definePageMeta({
  middleware: "auth",
  layout: "console",
});

const api = useApi();

// --- 响应式状态 ---
const users = ref<AuthUser[]>([]);
const roles = ref<AuthRole[]>([]);
const loading = ref(false);
const showPopup = ref(false);
const editingUser = ref<AuthUser | null>(null);
const selectedIds = ref<string[]>([]);

// --- 分页属性 ---
const currentPage = ref(1);
const pageSize = ref(10);

// --- 删除确认状态 ---
const showDeleteConfirm = ref(false);
const deleteId = ref<string | null>(null);
const deleteLoading = ref(false);

const totalCount = computed(() => users.value.length);

const sortedUsers = computed(() =>
  [...users.value].sort((a, b) => {
    const timeDiff =
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    return timeDiff !== 0 ? timeDiff : a.id.localeCompare(b.id);
  }),
);

/**
 * 分页截取用户数据
 */
const paginatedUsers = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return sortedUsers.value.slice(start, start + pageSize.value);
});

/**
 * 获取用户列表及角色选项
 * @param manual 是否手动刷新
 */
const loadData = async (manual = false) => {
  loading.value = true;
  try {
    const [userList, roleList] = await Promise.all([
      api.get<AuthUser[]>("/auth/users"),
      api.get<AuthRole[]>("/auth/roles"),
    ]);
    users.value = userList;
    roles.value = roleList;
    if (manual) {
      toast.success("用户列表已自动刷新。");
    }
  } catch (error) {
    notifyError(api, error, "加载数据失败。");
  } finally {
    loading.value = false;
  }
};

/**
 * 弹出新增用户窗口
 */
const openCreate = () => {
  editingUser.value = null;
  showPopup.value = true;
};

/**
 * 弹出编辑用户窗口
 * @param user 目标用户
 */
const openEdit = (user: AuthUser) => {
  editingUser.value = user;
  showPopup.value = true;
};

/**
 * 全选当前页所有用户
 */
const toggleSelectAll = (checked: boolean) => {
  if (checked) {
    selectedIds.value = paginatedUsers.value.map((u) => u.id);
  } else {
    selectedIds.value = [];
  }
};

/**
 * 选中/取消选中单行用户
 */
const toggleSelectRow = (userId: string, checked: boolean) => {
  if (checked) {
    selectedIds.value.push(userId);
  } else {
    selectedIds.value = selectedIds.value.filter((id) => id !== userId);
  }
};

/**
 * 快速切换账号启用/停用状态
 */
const toggleUserStatus = async (user: AuthUser, checked: boolean) => {
  const previousState = user.is_active;
  user.is_active = checked;
  try {
    await api.patch(`/auth/users/${user.id}`, { is_active: checked });
    toast.success(`当前用户状态已${checked ? "启用" : "停用"}。`);
  } catch (error) {
    user.is_active = previousState;
    notifyError(api, error, "更新状态失败，已还原。");
  }
};

/**
 * 触发删除确认对话框
 */
const openDeleteConfirm = (id: string) => {
  deleteId.value = id;
  showDeleteConfirm.value = true;
};

/**
 * 确认执行删除用户接口
 */
const handleDelete = async () => {
  if (!deleteId.value) return;
  deleteLoading.value = true;
  try {
    await api.delete(`/auth/users/${deleteId.value}`);
    toast.success("用户已成功删除。");
    showDeleteConfirm.value = false;
    deleteId.value = null;
    selectedIds.value = [];
    await loadData();
  } catch (error) {
    notifyError(api, error, "删除用户失败。");
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
        <!-- 头部工具栏 -->
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
              variant="default"
              size="sm"
              class="group/button h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] bg-zinc-900 text-white transition-all active:translate-y-px"
              @click="openCreate"
            >
              <Plus class="size-3.5" /> 新增用户
            </Button>
          </div>
        </div>

        <!-- 用户列表表格 -->
        <div class="border rounded-md border-zinc-100 overflow-hidden">
          <Table>
            <TableHeader class="bg-zinc-50/80">
              <TableRow class="h-10 hover:bg-transparent">
                <TableHead class="w-12 text-center">
                  <Checkbox
                    :checked="
                      selectedIds.length === paginatedUsers.length &&
                      paginatedUsers.length > 0
                    "
                    @update:checked="toggleSelectAll"
                  />
                </TableHead>
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >编号</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >头像</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >用户名</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >昵称</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >邮箱地址</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >所属角色</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >账号状态</TableHead
                >
                <TableHead class="text-[13px] font-bold text-zinc-700"
                  >最近登录</TableHead
                >
                <TableHead
                  class="text-[13px] font-bold text-zinc-700 text-center"
                  >操作</TableHead
                >
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow
                v-for="(item, index) in paginatedUsers"
                :key="item.id"
                class="h-12 hover:bg-zinc-50/50 transition-colors group"
              >
                <TableCell class="text-center">
                  <Checkbox
                    :checked="selectedIds.includes(item.id)"
                    @update:checked="
                      (val: boolean) => toggleSelectRow(item.id, !!val)
                    "
                  />
                </TableCell>
                <TableCell class="text-xs text-zinc-500">{{
                  index + 1 + (currentPage - 1) * pageSize
                }}</TableCell>
                <TableCell>
                  <Avatar class="h-8 w-8 rounded-full">
                    <AvatarImage
                      v-if="item.avatar_url"
                      :src="`${item.avatar_url}${item.avatar_url.includes('?') ? '&' : '?'}_t=${Date.now()}`"
                      class="object-cover"
                    />
                    <AvatarFallback class="bg-zinc-100 text-zinc-400 text-[10px]">
                      {{
                        item.display_name?.charAt(0) ||
                        item.username?.charAt(0) ||
                        "U"
                      }}
                    </AvatarFallback>
                  </Avatar>
                </TableCell>
                <TableCell
                  class="text-sm font-semibold cursor-pointer hover:underline"
                  @click="openEdit(item)"
                >
                  {{ item.username }}
                </TableCell>
                <TableCell class="text-sm text-zinc-600">{{
                  item.display_name
                }}</TableCell>
                <TableCell class="text-xs text-zinc-500">{{
                  item.email
                }}</TableCell>
                <TableCell>
                  <div class="flex flex-wrap gap-1">
                    <Badge
                      v-for="role in item.roles"
                      :key="role.id"
                      variant="outline"
                      class="rounded-full bg-zinc-100 text-zinc-600 border-none text-[10px] px-1.5 h-4"
                    >
                      {{ role.name }}
                    </Badge>
                  </div>
                </TableCell>
                <TableCell>
                  <div class="flex items-center text-center">
                    <Switch
                      :id="'status-' + item.id"
                      :model-value="item.is_active"
                      @update:model-value="
                        (val: boolean) => toggleUserStatus(item, !!val)
                      "
                      class="data-[state=checked]:bg-zinc-900"
                    />
                  </div>
                </TableCell>
                <TableCell class="text-[11px] text-zinc-400 tabular-nums">
                  {{ formatDateTime(item.last_login_at) }}
                </TableCell>
                <TableCell>
                  <div class="flex items-center justify-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      class="h-7 px-2 text-zinc-600 hover:bg-zinc-100/50 gap-1 text-[11px] rounded-md"
                      @click="openEdit(item)"
                    >
                      <Pencil class="size-3" /> 编辑
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      class="h-7 px-2 text-red-500 hover:bg-red-50 gap-1 text-[11px] rounded-md"
                      @click="openDeleteConfirm(item.id)"
                    >
                      <Trash2 class="size-3" /> 删除
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
              <TableRow v-if="!loading && totalCount === 0">
                <TableCell
                  colspan="10"
                  class="py-20 text-center text-zinc-500 text-sm"
                >
                  暂无匹配的用户记录数据。
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        <!-- 数据分页 -->
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
      :user="editingUser"
      :roles="roles"
      @saved="loadData"
    />

    <!-- 删除操作二次确认 -->
    <Dialog :open="showDeleteConfirm" @update:open="showDeleteConfirm = $event">
      <DialogContent
        class="sm:max-w-md p-6 rounded-[24px] border-none shadow-2xl"
      >
        <DialogHeader>
          <DialogTitle>确认删除用户</DialogTitle>
          <DialogDescription>
            此操作无法撤销。您确定要删除该用户及其所有相关联的数据吗？
          </DialogDescription>
        </DialogHeader>
        <DialogFooter class="flex justify-end gap-2 mt-6">
          <Button
            variant="ghost"
            size="sm"
            class="h-9 px-4 rounded-xl text-zinc-500 hover:bg-zinc-100"
            @click="showDeleteConfirm = false"
            :disabled="deleteLoading"
          >
            取消
          </Button>
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
