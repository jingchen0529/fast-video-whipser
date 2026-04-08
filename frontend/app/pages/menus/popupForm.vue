<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { KeyRound, Loader2 } from "lucide-vue-next";
import { toast } from "vue-sonner";
import { notifyError } from "@/utils/common";

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
import type { AuthPermission } from "@/types/api";

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const api = useApi();
const loading = ref(false);

const permissionForm = reactive({
  code: "",
  name: "",
  group_name: "",
  description: "",
});

const resetForm = () => {
    permissionForm.code = "";
    permissionForm.name = "";
    permissionForm.group_name = "";
    permissionForm.description = "";
};

watch(() => props.modelValue, (val) => {
  if (val) resetForm();
});



const handleSavePermission = async () => {
  if (!permissionForm.code.trim() || !permissionForm.name.trim() || !permissionForm.group_name.trim()) {
    toast.error("请完整填写唯一编码、名称和所属分组。");
    return;
  }

  loading.value = true;
  try {
    await api.post<AuthPermission>("/auth/permissions", {
      code: permissionForm.code,
      name: permissionForm.name,
      group_name: permissionForm.group_name,
      description: permissionForm.description || null,
    });
    toast.success("资源项创建成功。");
    emit("saved");
    emit("update:modelValue", false);
  } catch (error) {
    notifyError(api, error, "创建资源失败。");
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
          定义菜单/权限资源
        </DialogTitle>
        <DialogDescription>
          创建一个新的资源项，成功后可在“角色管理”中将其授权给特定角色。
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-4 py-4">
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1.5">
            <label class="text-[13px] font-bold text-zinc-900">唯一编码</label>
            <Input v-model="permissionForm.code" placeholder="例如：videos.delete" class="h-10 rounded-xl" />
            <p class="text-[10px] text-zinc-500">用于后端鉴权的底层标识。</p>
          </div>
          <div class="space-y-1.5">
            <label class="text-[13px] font-bold text-zinc-900">显示名称</label>
            <Input v-model="permissionForm.name" placeholder="例如：删除视频" class="h-10 rounded-xl" />
          </div>
        </div>
        <div class="space-y-1.5">
          <label class="text-[13px] font-bold text-zinc-900">所属分组 (父级标识)</label>
          <Input v-model="permissionForm.group_name" placeholder="例如：videos" class="h-10 rounded-xl" />
          <p class="text-[10px] text-zinc-500">组名相同的项会在权限树中自动归类。</p>
        </div>
        <div class="space-y-1.5">
          <label class="text-[13px] font-bold text-zinc-900">描述信息</label>
          <textarea
            v-model="permissionForm.description"
            class="min-h-24 w-full rounded-xl border border-zinc-200 px-3 py-2 text-sm outline-none transition focus:border-zinc-400"
            placeholder="说明该功能的具体作用（可选）。"
          />
        </div>
        <DialogFooter class="pt-2">
          <Button variant="outline" @click="$emit('update:modelValue', false)" class="h-10 px-6 rounded-xl font-bold">取消</Button>
          <Button @click="handleSavePermission" :disabled="loading" class="h-10 px-6 rounded-xl bg-black text-white font-bold active:scale-95">
            <Loader2 v-if="loading" class="mr-2 size-4 animate-spin" />
            <KeyRound v-else class="mr-2 size-4" />
            保存资源
          </Button>
        </DialogFooter>
      </div>
    </DialogContent>
  </Dialog>
</template>
