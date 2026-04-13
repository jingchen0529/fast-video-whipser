<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { 
  FolderTree, 
  Loader2, 
  PlusCircle, 
  Save, 
  Plus, 
  Minus, 
  Folder, 
  AppWindow, 
  FileText, 
  UserCircle 
} from "lucide-vue-next";
import { toast } from "vue-sonner";
import { notifyError } from "@/utils/common";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AuthMenu, AuthRole } from "@/types/api";

type TreeNode = AuthMenu & {
  level: number;
  isLeaf: boolean;
  visible: boolean;
  isLastBranch: boolean[];
  isLast: boolean;
  parentId: string | null;
};

const props = defineProps<{
  modelValue: boolean;
  role: AuthRole | null;
  menuTree: AuthMenu[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const api = useApi();
const loading = ref(false);

const roleForm = reactive({
  code: "",
  name: "",
  description: "",
  menu_ids: [] as string[],
});

const isEdit = computed(() => !!props.role);
const isSuperAdminRole = computed(() =>
  (isEdit.value && props.role?.code === "super_admin") ||
  (!isEdit.value && roleForm.code.trim() === "super_admin"),
);

const expandedKeys = ref<Set<string>>(new Set());
const selectedMenuIdSet = computed(
  () => new Set(roleForm.menu_ids.map((id) => String(id))),
);

const computeNodes = (
  items: AuthMenu[], 
  level: number, 
  isLastBranch: boolean[], 
  parentVisible: boolean, 
  parentId: string | null
): TreeNode[] => {
  let result: TreeNode[] = [];
  items.forEach((item, index) => {
    const isLast = index === items.length - 1;
    const isLeaf = !item.children || item.children.length === 0;
    
    // Node is visible if parent is visible AND parent is expanded
    const visible = parentVisible && (parentId === null || expandedKeys.value.has(parentId));
    
    result.push({
      ...item,
      level,
      isLeaf,
      visible,
      isLastBranch: [...isLastBranch],
      isLast,
      parentId
    });
    
    if (item.children && item.children.length > 0) {
      result = result.concat(computeNodes(item.children, level + 1, [...isLastBranch, isLast], visible, item.id));
    }
  });
  return result;
};

const treeNodes = computed(() => {
  return computeNodes(props.menuTree, 0, [], true, null);
});

const visibleTreeNodes = computed(() => treeNodes.value.filter(n => n.visible));

const parentIdMap = computed(() => {
  const map = new Map<string, string | null>();
  const walk = (items: AuthMenu[], parentId: string | null = null) => {
    for (const item of items) {
      const itemId = String(item.id);
      map.set(itemId, parentId);
      if (item.children?.length) {
        walk(item.children, itemId);
      }
    }
  };
  walk(props.menuTree);
  return map;
});

const childIdsMap = computed(() => {
  const map = new Map<string, string[]>();
  const walk = (items: AuthMenu[]) => {
    for (const item of items) {
      const itemId = String(item.id);
      map.set(
        itemId,
        (item.children || []).map((child) => String(child.id)),
      );
      if (item.children?.length) {
        walk(item.children);
      }
    }
  };
  walk(props.menuTree);
  return map;
});

const collectDescendantIds = (id: string) => {
  const descendants = new Set<string>([id]);
  const queue = [id];
  while (queue.length) {
    const current = queue.shift()!;
    for (const childId of childIdsMap.value.get(current) || []) {
      if (!descendants.has(childId)) {
        descendants.add(childId);
        queue.push(childId);
      }
    }
  }
  return [...descendants];
};

const collectAncestorIds = (id: string) => {
  const ancestors: string[] = [];
  let current = parentIdMap.value.get(id) || null;
  while (current) {
    ancestors.push(current);
    current = parentIdMap.value.get(current) || null;
  }
  return ancestors;
};

const hasSelectedDescendant = (id: string, nextIds: Set<string>) => {
  return collectDescendantIds(id).some(
    (descendantId) => descendantId !== id && nextIds.has(descendantId),
  );
};

// Select All / Unselect All
const isAllSelected = computed(() => {
  if (!treeNodes.value.length) return false;
  return treeNodes.value.every((node) => selectedMenuIdSet.value.has(String(node.id)));
});

const toggleSelectAll = (checked?: boolean | "indeterminate") => {
  if (isSuperAdminRole.value) return;
  const shouldSelect = checked === undefined ? !isAllSelected.value : checked === true;
  if (shouldSelect) {
    roleForm.menu_ids = treeNodes.value.map(n => String(n.id));
  } else {
    roleForm.menu_ids = [];
  }
};

// Expand All / Collapse All
const isAllExpanded = computed(() => {
  const nonLeaves = treeNodes.value.filter(n => !n.isLeaf);
  if (!nonLeaves.length) return false;
  return expandedKeys.value.size === nonLeaves.length;
});

const toggleExpandAll = (checked?: boolean | "indeterminate") => {
  const shouldExpand = checked === undefined ? !isAllExpanded.value : checked === true;
  if (shouldExpand) {
    expandedKeys.value = new Set(treeNodes.value.filter(n => !n.isLeaf).map(n => String(n.id)));
  } else {
    expandedKeys.value = new Set();
  }
};

const toggleExpand = (id: string | number) => {
  const newSet = new Set(expandedKeys.value);
  const strId = String(id);
  if (newSet.has(strId)) newSet.delete(strId);
  else newSet.add(strId);
  expandedKeys.value = newSet;
};

const handleNodeCheck = (node: TreeNode, checked: boolean | 'indeterminate') => {
  if (isSuperAdminRole.value) return;

  const nodeId = String(node.id);
  const isChecked = checked === true;
  const nextIds = new Set(selectedMenuIdSet.value);
  const descendantIds = collectDescendantIds(nodeId);

  if (isChecked) {
    for (const id of descendantIds) {
      nextIds.add(id);
    }
    for (const ancestorId of collectAncestorIds(nodeId)) {
      nextIds.add(ancestorId);
    }
  } else {
    for (const id of descendantIds) {
      nextIds.delete(id);
    }

    let currentParent = parentIdMap.value.get(nodeId) || null;
    while (currentParent) {
      if (!hasSelectedDescendant(currentParent, nextIds)) {
        nextIds.delete(currentParent);
      }
      currentParent = parentIdMap.value.get(currentParent) || null;
    }
  }

  roleForm.menu_ids = [...nextIds];
};

const getNodeCheckState = (id: string | number): boolean | "indeterminate" => {
  if (isSuperAdminRole.value) return true;
  const nodeId = String(id);
  if (selectedMenuIdSet.value.has(nodeId)) {
    return true;
  }
  if (hasSelectedDescendant(nodeId, selectedMenuIdSet.value)) {
    return "indeterminate";
  }
  return false;
};

const resetForm = () => {
  if (props.role) {
    roleForm.code = props.role.code || "";
    roleForm.name = props.role.name || "";
    roleForm.description = props.role.description || "";
    
    const menusAttr = (props.role as any).menus || [];
    const menuIdsAttr = (props.role as any).menu_ids || [];
    
    if (menusAttr.length > 0) {
      roleForm.menu_ids = menusAttr.map((item: any) => String(item.id || item.menu_id || item));
    } else if (menuIdsAttr.length > 0) {
      roleForm.menu_ids = menuIdsAttr.map(String);
    } else {
      roleForm.menu_ids = [];
    }
  } else {
    roleForm.code = "";
    roleForm.name = "";
    roleForm.description = "";
    roleForm.menu_ids = [];
  }
};

watch(
  () => [props.modelValue, props.role?.id, props.menuTree.length],
  ([value]) => {
    if (value) {
      resetForm();
      // 默认展开所有节点
      expandedKeys.value = new Set(treeNodes.value.filter(n => !n.isLeaf).map(n => String(n.id)));
    }
  },
);

const handleSaveRole = async () => {
  if (!isEdit.value && (!roleForm.code.trim() || !roleForm.name.trim())) {
    toast.error("请完整填写角色编码和角色名称。");
    return;
  }
  if (isEdit.value && !roleForm.name.trim()) {
    toast.error("请填写角色名称。");
    return;
  }

  loading.value = true;
  try {
    if (isEdit.value && props.role) {
      await api.patch<AuthRole>(`/auth/roles/${props.role.id}`, {
        name: roleForm.name,
        description: roleForm.description || null,
      });
      if (props.role.code !== "super_admin") {
        await api.put<AuthRole>(`/auth/roles/${props.role.id}/menus`, {
          menu_ids: roleForm.menu_ids,
        });
      }
      toast.success(`角色 ${roleForm.name} 已更新。`);
    } else {
      const createdRole = await api.post<AuthRole>("/auth/roles", {
        code: roleForm.code,
        name: roleForm.name,
        description: roleForm.description || null,
      });
      if (createdRole.code !== "super_admin") {
        await api.put<AuthRole>(`/auth/roles/${createdRole.id}/menus`, {
          menu_ids: roleForm.menu_ids,
        });
      }
      toast.success(`角色 ${roleForm.name} 创建成功。`);
    }
    emit("saved");
    emit("update:modelValue", false);
  } catch (error) {
    notifyError(api, error, isEdit.value ? "保存角色失败。" : "创建角色失败。");
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <Dialog :open="modelValue" @update:open="$emit('update:modelValue', $event)">
    <DialogContent
      class="w-[min(96vw,800px)] max-w-none overflow-hidden rounded-[28px] border border-zinc-200/80 bg-zinc-50/50 p-0 shadow-[0_28px_90px_rgba(15,23,42,0.18)]"
    >
      <div class="flex max-h-[88vh] flex-col bg-white">
        <!-- Header -->
        <DialogHeader class="border-b border-zinc-100 px-6 pb-5 pt-6 bg-white shrink-0">
          <DialogTitle class="text-[22px] font-semibold tracking-tight text-zinc-900">
            {{ isEdit ? '编辑角色' : '创建新角色' }}
          </DialogTitle>
          <DialogDescription class="mt-1 text-sm leading-6 text-zinc-500">
            {{ isEdit ? `正在调整 ${role?.name} 的信息及其菜单范围。` : '定义一个新的系统角色，并为其设置可见菜单。' }}
          </DialogDescription>
        </DialogHeader>

        <!-- Body -->
        <div class="min-h-0 flex-1 overflow-hidden p-6 bg-zinc-50/30">
          <div class="flex h-full gap-6">
            
            <!-- Left Column: Role Details -->
            <div class="flex-shrink-0 w-[300px] h-full flex flex-col gap-4 overflow-y-auto pr-1 custom-scrollbar">
              <div class="rounded-[22px] border border-zinc-200/80 bg-white p-5 shadow-sm">
                <h3 class="font-semibold text-sm text-zinc-900 mb-5 flex items-center gap-2">
                  <UserCircle class="w-4 h-4 text-zinc-500" />
                  角色信息
                </h3>
                
                <div class="space-y-4">
                  <div class="space-y-2">
                    <label class="text-[13px] font-semibold text-zinc-800">角色名称 <span class="text-red-500">*</span></label>
                    <Input
                      v-model="roleForm.name"
                      placeholder="例如：编辑员"
                      class="h-10 rounded-xl border-zinc-200 bg-white px-3 text-[14px]"
                    />
                  </div>
                  
                  <div class="space-y-2">
                    <label class="text-[13px] font-semibold text-zinc-800">权限字符 <span class="text-red-500">*</span></label>
                    <Input
                      v-model="roleForm.code"
                      :disabled="isEdit"
                      placeholder="例如：editor"
                      class="h-10 rounded-xl border-zinc-200 bg-white px-3 text-[14px]"
                    />
                    <p class="text-[11px] text-zinc-400 mt-1">系统内部使用的唯一标识，不可重复。</p>
                  </div>
                  
                  <div class="space-y-2">
                    <label class="text-[13px] font-semibold text-zinc-800">角色说明</label>
                    <Textarea
                      v-model="roleForm.description"
                      placeholder="对该角色的职责范围进行描述..."
                      class="min-h-[100px] rounded-xl border-zinc-200 bg-white resize-none p-3 text-[14px]"
                    />
                  </div>
                </div>
              </div>
            </div>

            <!-- Right Column: Menu Tree -->
            <div class="flex-1 min-w-0 flex flex-col rounded-[22px] border border-zinc-200/80 bg-white shadow-sm overflow-hidden">
              <!-- Tree Toolbar -->
              <div class="flex flex-wrap items-center justify-between border-b border-zinc-100/80 px-5 py-3 bg-white shrink-0">
                <div class="flex items-center gap-2 text-[14px] font-semibold text-zinc-900">
                  <FolderTree class="size-4 text-zinc-500" />
                  菜单分配
                </div>
                
                <div class="flex items-center gap-5 text-sm text-zinc-600">
                  <div class="flex items-center gap-2 hover:text-zinc-900 select-none">
                    <Checkbox
                      :model-value="isAllExpanded"
                      @update:model-value="toggleExpandAll"
                      class="rounded w-4 h-4 shadow-none data-[state=checked]:bg-zinc-900 data-[state=checked]:border-zinc-900 data-[state=checked]:text-white"
                    />
                    <span class="text-[13px]">展开/折叠</span>
                  </div>
                  <div class="flex items-center gap-2 hover:text-zinc-900 select-none">
                    <Checkbox
                      :model-value="isAllSelected"
                      :disabled="isSuperAdminRole"
                      @update:model-value="toggleSelectAll"
                      class="rounded w-4 h-4 shadow-none data-[state=checked]:bg-zinc-900 data-[state=checked]:border-zinc-900 data-[state=checked]:text-white"
                    />
                    <span class="text-[13px]">全选/全不选</span>
                  </div>
                </div>
              </div>

              <!-- Tree View -->
              <ScrollArea class="flex-1 min-h-0 bg-white relative">
                <div v-if="isSuperAdminRole" class="absolute inset-x-0 top-0 z-10 px-4 py-3 bg-blue-50/80 border-b border-blue-100 text-blue-700 text-[13px] flex items-center justify-center backdrop-blur-sm">
                  超级管理员默认拥有全部菜单权限，不可取消勾选。
                </div>
                
                <div class="p-5 pb-8" :class="isSuperAdminRole ? 'pt-14' : ''">
                  <div class="min-w-max">
                    <div v-for="node in visibleTreeNodes" :key="node.id" class="flex items-center py-[2px] hover:bg-zinc-50/80 transition-colors pr-6 group rounded-lg">
                      <!-- Indentation Lines -->
                      <div class="flex items-center h-full self-stretch">
                        <template v-for="(isLast, i) in node.isLastBranch" :key="i">
                          <div class="w-[24px] h-full flex justify-center items-center relative">
                          </div>
                        </template>

                        <!-- Node Connector -->
                        <div class="w-[24px] h-full flex justify-center items-center relative">
                          <button v-if="!node.isLeaf" @click="toggleExpand(node.id)" class="relative z-10 w-[14px] h-[14px] bg-white border border-zinc-300 rounded-[2px] flex items-center justify-center text-zinc-500 hover:text-zinc-800 hover:border-zinc-500 transition-colors cursor-pointer outline-none">
                            <Minus v-if="expandedKeys.has(node.id)" class="w-2.5 h-2.5" />
                            <Plus v-else class="w-2.5 h-2.5" />
                          </button>
                        </div>
                      </div>

                      <!-- Node Content -->
                      <div class="flex items-center gap-2.5 ml-1 min-w-0 flex-1 select-none">
                        <Checkbox 
                          :model-value="getNodeCheckState(node.id)"
                          :disabled="isSuperAdminRole"
                          @update:model-value="handleNodeCheck(node, $event)"
                          class="data-[state=checked]:bg-zinc-900 data-[state=checked]:border-zinc-900 data-[state=checked]:text-white transition-all shadow-[0_1px_2px_rgba(0,0,0,0.05)] w-[15px] h-[15px] rounded-[3px] shrink-0"
                        />
                        <component 
                          :is="node.menu_type === 'directory' ? Folder : (node.menu_type === 'menu' ? AppWindow : FileText)" 
                          class="w-[15px] h-[15px] shrink-0 transition-colors"
                          :class="node.menu_type === 'directory' ? 'text-zinc-400 fill-zinc-200' : 'text-zinc-400 group-hover:text-zinc-600'" 
                        />
                        <button
                          type="button"
                          class="text-left"
                          @click="handleNodeCheck(node, getNodeCheckState(node.id) !== true)"
                        >
                          <span
                            class="text-[13px] whitespace-nowrap pt-0.5"
                            :class="getNodeCheckState(node.id) === true ? 'text-zinc-900 font-medium' : 'text-zinc-600'"
                          >
                          {{ node.title }}
                          </span>
                        </button>
                      </div>

                      <!-- Permission String -->
                      <div v-if="node.code && node.code.includes(':')" class="ml-10 min-w-32 shrink-0">
                        <span class="text-[11px] text-zinc-400 font-mono tracking-wide px-1.5 py-0.5 rounded transition-colors"
                              :class="getNodeCheckState(node.id) !== false ? 'text-zinc-500 bg-zinc-100' : 'bg-transparent group-hover:bg-zinc-100/50'">
                          {{ node.code }}
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  <div v-if="!treeNodes.length" class="text-center py-20 text-zinc-400 text-sm">
                    暂无可用的菜单数据
                  </div>
                </div>
              </ScrollArea>
            </div>
            
          </div>
        </div>

        <!-- Footer -->
        <DialogFooter class="border-t border-zinc-100 bg-white px-6 py-4 shrink-0 shadow-[0_-10px_20px_rgba(0,0,0,0.01)]">
          <Button variant="outline" @click="$emit('update:modelValue', false)" class="h-10 rounded-xl px-6 font-semibold bg-white border-zinc-200 hover:bg-zinc-50 transition-colors">
            取消
          </Button>
          <Button @click="handleSaveRole" :disabled="loading" class="h-10 rounded-xl bg-zinc-900 px-6 text-white font-semibold hover:bg-black active:scale-[0.98] shadow-sm transition-all focus-visible:ring-2 ring-offset-2 ring-zinc-900">
            <Loader2 v-if="loading" class="mr-2 size-4 animate-spin" />
            <Save v-else-if="isEdit" class="mr-2 size-4" />
            <PlusCircle v-else class="mr-2 size-4" />
            {{ isEdit ? '保存修改' : '确认创建' }}
          </Button>
        </DialogFooter>
      </div>
    </DialogContent>
  </Dialog>
</template>
