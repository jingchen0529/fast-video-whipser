<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { FolderTree, Loader2, Save, PlusCircle } from "lucide-vue-next";
import { toast } from "vue-sonner";
import { notifyError } from "@/utils/common";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import PermissionTree from "@/components/custom/PermissionTree.vue";
import type { PermissionTreeNode } from "@/lib/permissions";
import {
  buildPermissionTree,
  collectPermissionCodes,
} from "@/lib/permissions";
import type { AuthPermission, AuthRole } from "@/types/api";

const props = defineProps<{
  modelValue: boolean;
  role: AuthRole | null;
  permissions: AuthPermission[];
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
  permission_codes: [] as string[],
});

const isEdit = computed(() => !!props.role);

const permissionTree = computed(() => buildPermissionTree(props.permissions));

const setCodes = (
  target: string[],
  code: string,
  checked: boolean | "indeterminate",
) => {
  const enabled = checked === true;
  const nextCodes = new Set(target);
  if (enabled) {
    nextCodes.add(code);
  } else {
    nextCodes.delete(code);
  }
  target.splice(0, target.length, ...nextCodes);
};

const setMultipleCodes = (
  target: string[],
  codes: string[],
  checked: boolean | "indeterminate",
) => {
  const enabled = checked === true;
  const nextCodes = new Set(target);
  for (const code of codes) {
    if (enabled) {
      nextCodes.add(code);
    } else {
      nextCodes.delete(code);
    }
  }
  target.splice(0, target.length, ...nextCodes);
};

const handleTogglePermissionNode = (
  node: PermissionTreeNode,
  checked: boolean | "indeterminate",
) => {
  if (node.permission) {
    setCodes(roleForm.permission_codes, node.permission.code, checked);
    return;
  }

  setMultipleCodes(roleForm.permission_codes, collectPermissionCodes(node), checked);
};

const resetForm = () => {
  if (isEdit.value && props.role) {
    roleForm.code = props.role.code;
    roleForm.name = props.role.name;
    roleForm.description = props.role.description || "";
    roleForm.permission_codes = (props.role.permissions || []).map((item) => item.code);
  } else {
    roleForm.code = "";
    roleForm.name = "";
    roleForm.description = "";
    roleForm.permission_codes = [];
  }
};

watch(() => props.modelValue, (val) => {
  if (val) resetForm();
});



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
        description: roleForm.description,
      });
      if (props.role.code !== "super_admin") {
        await api.put<AuthRole>(`/auth/roles/${props.role.id}/permissions`, {
          permission_codes: roleForm.permission_codes,
        });
      }
      toast.success(`角色 ${roleForm.name} 已更新。`);
    } else {
      await api.post<AuthRole>("/auth/roles", {
        code: roleForm.code,
        name: roleForm.name,
        description: roleForm.description || null,
        permission_codes: roleForm.permission_codes,
      });
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
    <DialogContent class="max-w-[540px] rounded-[24px] p-6 shadow-2xl border-none">
      <DialogHeader>
        <DialogTitle class="text-xl font-bold">
          {{ isEdit ? '编辑角色' : '创建新角色' }}
        </DialogTitle>
        <DialogDescription>
          {{ isEdit ? `正在调整 ${role?.name} 的信息及其权限映射。` : '定义一个新的系统角色，并为其分配初始权限。' }}
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-4 py-2">
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1.5">
            <label class="text-[13px] font-bold text-zinc-900">角色编码</label>
            <Input v-model="roleForm.code" :disabled="isEdit" placeholder="例如：editor" class="h-10 rounded-xl" />
          </div>
          <div class="space-y-1.5">
            <label class="text-[13px] font-bold text-zinc-900">角色显示名</label>
            <Input v-model="roleForm.name" placeholder="例如：编辑员" class="h-10 rounded-xl" />
          </div>
        </div>
        <div class="space-y-1.5">
          <label class="text-[13px] font-bold text-zinc-900">角色说明</label>
          <Input v-model="roleForm.description" placeholder="对该角色的职权范围进行简单描述。" class="h-10 rounded-xl" />
        </div>
        <div class="space-y-2 pt-2">
          <div class="flex items-center justify-between">
            <label class="flex items-center gap-2 text-[13px] font-bold text-zinc-900">
              <FolderTree class="size-4 text-zinc-500" />
              权限配置
            </label>
            <Badge v-if="isEdit && role?.code === 'super_admin'" variant="outline" class="rounded-full bg-zinc-100 text-[10px]">
              全局超级权限
            </Badge>
          </div>
          <div class="max-h-[360px] overflow-y-auto rounded-[20px] border border-zinc-100 mb-2">
            <PermissionTree
              :nodes="permissionTree"
              :selected-codes="roleForm.permission_codes"
              :selectable="true"
              :disabled="isEdit && role?.code === 'super_admin'"
              empty-text="系统暂未定义任何权限项。"
              @toggle="handleTogglePermissionNode"
            />
          </div>
        </div>
        <DialogFooter class="pt-4">
          <Button variant="outline" @click="$emit('update:modelValue', false)" class="h-10 px-6 rounded-xl font-bold">取消</Button>
          <Button @click="handleSaveRole" :disabled="loading" class="h-10 px-6 rounded-xl bg-black text-white font-bold active:scale-95">
            <Loader2 v-if="loading" class="mr-2 size-4 animate-spin" />
            <Save v-else-if="isEdit" class="mr-2 size-4" />
            <PlusCircle v-else class="mr-2 size-4" />
            {{ isEdit ? '保存修改' : '立即创建' }}
          </Button>
        </DialogFooter>
      </div>
    </DialogContent>
  </Dialog>
</template>
