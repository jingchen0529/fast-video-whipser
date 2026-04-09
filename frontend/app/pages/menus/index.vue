<script setup lang="ts">
import { computed, onMounted, ref, reactive } from "vue";
import { Plus, Search, RotateCcw, RefreshCw, FolderTree } from "lucide-vue-next";
import { toast } from "vue-sonner";
import { notifyError } from "@/utils/common";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import PermissionTree from "@/components/custom/PermissionTree.vue";
import { buildPermissionTree } from "@/lib/permissions";
import type { AuthPermission } from "@/types/api";
import PopupForm from "./popupForm.vue";

definePageMeta({
  middleware: "auth",
  layout: "console",
});

const api = useApi();

// --- 响应式状态 ---
const permissions = ref<AuthPermission[]>([]);
const loading = ref(false);
const showPopup = ref(false);
const showSearch = ref(true);

const queryParams = reactive({
  menuName: "",
  status: "all",
});

/**
 * 构建权限树结构
 */
const permissionTree = computed(() => buildPermissionTree(permissions.value));

/**
 * 加载菜单/权限定义数据
 * @param manual 是否手动刷新
 */
const loadData = async (manual = false) => {
  loading.value = true;
  try {
    const permissionList = await api.get<AuthPermission[]>("/auth/permissions");
    permissions.value = permissionList;
    if (manual) {
      toast.success("资源权限列表已刷新。");
    }
  } catch (error) {
    notifyError(api, error, "加载菜单权限数据失败。");
  } finally {
    loading.value = false;
  }
};

/**
 * 执行查询操作
 */
const handleQuery = () => {
    // 此处可扩展前端搜索或 API 条件查询
};

/**
 * 重置查询条件
 */
const resetQuery = () => {
  queryParams.menuName = "";
  queryParams.status = "all";
  handleQuery();
};

/**
 * 打开新增资源弹窗
 */
const openCreatePermission = () => {
  showPopup.value = true;
};

onMounted(async () => {
  await loadData();
});
</script>

<template>
  <div class="p-6 space-y-4">
    <!-- 搜索过滤栏 -->
    <Card v-show="showSearch" class="border-zinc-200/60 shadow-sm rounded-lg">
      <CardContent class="p-4">
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex items-center gap-2">
            <label class="text-[13px] font-medium text-zinc-600 whitespace-nowrap">资源名称：</label>
            <Input v-model="queryParams.menuName" placeholder="模糊搜索" class="h-8 w-48 text-[13px] rounded-md border-zinc-200" />
          </div>
          <div class="flex items-center gap-2">
            <label class="text-[13px] font-medium text-zinc-600 whitespace-nowrap">状态：</label>
             <Select v-model="queryParams.status">
                <SelectTrigger class="h-8 w-32 text-[13px] rounded-md border-zinc-200">
                  <SelectValue placeholder="所有" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">所有</SelectItem>
                  <SelectItem value="0">正常</SelectItem>
                  <SelectItem value="1">停用</SelectItem>
                </SelectContent>
              </Select>
          </div>
          <div class="flex items-center gap-2 ml-auto">
            <Button size="sm" class="h-8 px-4 bg-zinc-900 rounded-[14px] text-white gap-1.5" @click="handleQuery">
              <Search class="size-3.5" /> 搜索
            </Button>
            <Button variant="outline" size="sm" class="h-8 px-4 rounded-[14px] border-zinc-200 text-zinc-600 hover:bg-zinc-50 gap-1.5" @click="resetQuery">
              <RotateCcw class="size-3.5" /> 重置
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <Card class="border-zinc-200/60 shadow-sm rounded-lg overflow-hidden">
      <CardContent class="p-4 space-y-4">
        <!-- 工具栏 -->
         <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Button size="sm" class="h-8 px-3 bg-zinc-900 rounded-[14px] text-white gap-1.5" @click="openCreatePermission">
              <Plus class="size-3.5" /> 新增资源
            </Button>
          </div>
          
          <div class="flex items-center gap-2">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button variant="ghost" size="icon" class="size-8 rounded-full border border-zinc-200" @click="showSearch = !showSearch">
                    <Search class="size-4 text-zinc-500" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>显示/隐藏搜索</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button variant="ghost" size="icon" class="size-8 rounded-full border border-zinc-200" @click="loadData(true)">
                    <RefreshCw :class="['size-4 text-zinc-500', loading && 'animate-spin']" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>刷新</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>

        <!-- 权限树视图 -->
        <div class="border rounded-md border-zinc-100 bg-white">
          <div class="flex items-center gap-2 px-4 py-3 border-b border-zinc-50 bg-zinc-50/50">
            <FolderTree class="size-4 text-zinc-500" />
            <span class="text-sm font-bold text-zinc-700">权限资源树架构</span>
            <span class="text-xs text-zinc-400 ml-auto mx-2">共 {{ permissions.length }} 个节点</span>
          </div>
          <div class="p-4 max-h-[700px] overflow-auto custom-scrollbar">
            <PermissionTree
              :nodes="permissionTree"
              empty-text="暂无定义的资源项。"
            />
          </div>
        </div>
      </CardContent>
    </Card>

    <PopupForm v-model="showPopup" @saved="loadData" />
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #f4f4f5;
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #e4e4e7;
}
</style>
