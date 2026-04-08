<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { BadgeX, Loader2, Plus, Save } from "lucide-vue-next";
import { toast } from "vue-sonner";
import { notifyError } from "@/utils/common";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AuthRole, AuthUser } from "@/types/api";

const props = defineProps<{
  modelValue: boolean;
  user: AuthUser | null;
  roles: AuthRole[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const api = useApi();

const loading = ref(false);

const form = reactive({
  username: "",
  email: "",
  password: "",
  display_name: "",
  role_codes: [] as string[],
  is_active: true,
  is_superuser: false,
});

const isEdit = computed(() => !!props.user);

const sortedRoles = computed(() =>
  [...props.roles].sort((left, right) => {
    if (left.is_system !== right.is_system) {
      return Number(right.is_system) - Number(left.is_system);
    }
    return left.name.localeCompare(right.name, "zh-Hans-CN");
  }),
);

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



const resetForm = () => {
  if (isEdit.value && props.user) {
    form.username = props.user.username;
    form.email = props.user.email;
    form.password = "";
    form.display_name = props.user.display_name || "";
    form.role_codes = props.user.roles.map((role) => role.code);
    form.is_active = props.user.is_active;
    form.is_superuser = props.user.is_superuser;
  } else {
    form.username = "";
    form.email = "";
    form.password = "";
    form.display_name = "";
    form.role_codes = props.roles.some((role) => role.code === "user")
      ? ["user"]
      : [];
    form.is_active = true;
    form.is_superuser = false;
  }
};

watch(
  () => props.modelValue,
  (val) => {
    if (val) resetForm();
  },
);

const handleSave = async () => {
  if (!isEdit.value) {
    if (!form.username.trim()) return toast.error("请输入用户名。");
    if (!form.email.trim()) return toast.error("请输入邮箱。");
    if (form.password.trim().length < 8)
      return toast.error("密码长度至少需要 8 位。");
  } else {
    if (!form.email.trim()) return toast.error("请输入邮箱。");
  }

  loading.value = true;
  try {
    if (isEdit.value && props.user) {
      const payload: any = {
        email: form.email,
        display_name: form.display_name,
        is_active: form.is_active,
        is_superuser: form.is_superuser,
      };
      if (form.password.trim()) {
        if (form.password.trim().length < 8) {
          toast.error("密码长度至少需要 8 位。");
          loading.value = false;
          return;
        }
        payload.password = form.password;
      }
      await api.patch<AuthUser>(`/auth/users/${props.user.id}`, payload);
      await api.post<AuthUser>(`/auth/users/${props.user.id}/roles`, {
        role_codes: form.role_codes,
      });
      toast.success(`用户 ${props.user.username} 已更新。`);
    } else {
      const createdUser = await api.post<AuthUser>("/auth/users", {
        username: form.username,
        email: form.email,
        password: form.password,
        display_name: form.display_name || null,
        role_codes: form.role_codes,
        is_active: form.is_active,
        is_superuser: form.is_superuser,
      });
      toast.success(`用户 ${createdUser.username} 创建成功。`);
    }
    emit("saved");
    emit("update:modelValue", false);
  } catch (error) {
    notifyError(api, error, isEdit.value ? "保存用户失败。" : "创建用户失败。");
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <Dialog :open="modelValue" @update:open="$emit('update:modelValue', $event)">
    <DialogContent
      class="flex max-h-[90vh] max-w-[800px] flex-col p-0 rounded-[24px] overflow-hidden shadow-2xl border-none"
    >
      <DialogHeader class="p-6 pb-2 border-b border-zinc-100 bg-white shrink-0">
        <DialogTitle class="text-xl font-bold">{{
          isEdit ? "编辑" : "新增"
        }}</DialogTitle>
      </DialogHeader>

      <div class="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar">
        <div class="space-y-6">
          <div class="space-y-2">
            <label class="text-[13px] font-bold text-zinc-900 ml-1"
              >用户名</label
            >
            <Input
              v-model="form.username"
              placeholder="例如：operator01"
              :disabled="isEdit"
              class="h-10 rounded-xl border-zinc-200"
            />
          </div>
          <div class="space-y-2">
            <label class="text-[13px] font-bold text-zinc-900 ml-1">邮箱</label>
            <Input
              v-model="form.email"
              type="email"
              placeholder="例如：operator@example.com"
              class="h-10 rounded-xl border-zinc-200"
            />
          </div>
          <div class="space-y-2">
            <label class="text-[13px] font-bold text-zinc-900 ml-1">密码</label>
            <Input
              v-model="form.password"
              type="password"
              placeholder="密码为空则不修改，至少8位字符"
              class="h-10 rounded-xl border-zinc-200"
            />
          </div>
          <div class="space-y-2">
            <label class="text-[13px] font-bold text-zinc-900 ml-1"
              >显示名</label
            >
            <Input
              v-model="form.display_name"
              placeholder="例如：运营同学"
              class="h-10 rounded-xl border-zinc-200"
            />
          </div>

          <div class="space-y-3">
            <label class="text-[13px] font-bold text-zinc-900 ml-1"
              >角色分配</label
            >
            <div
              class="flex flex-wrap gap-2.5 rounded-2xl border border-zinc-200 p-4 bg-zinc-50/50"
            >
              <label
                v-for="role in sortedRoles"
                :key="role.id"
                class="flex items-center gap-2.5 rounded-xl border border-zinc-200 bg-white px-4 py-2 text-sm transition-all hover:border-zinc-400 hover:shadow-sm cursor-pointer group"
              >
                <Checkbox
                  :checked="form.role_codes.includes(role.code)"
                  @update:checked="setCodes(form.role_codes, role.code, $event)"
                  class="rounded-md"
                />
                <span
                  class="text-zinc-700 font-bold group-hover:text-zinc-900"
                  >{{ role.name }}</span
                >
                <Badge
                  v-if="role.is_system"
                  variant="secondary"
                  class="rounded-full px-2 py-0 h-4 text-[10px] bg-zinc-200/50 border-none font-medium"
                >
                  系统
                </Badge>
              </label>
            </div>
          </div>

          <div class="flex items-center gap-8 pt-2 ml-1">
            <label class="flex items-center gap-2.5 cursor-pointer group">
              <Checkbox
                :checked="form.is_active"
                @update:checked="form.is_active = $event === true"
                class="rounded-md"
              />
              <span
                class="text-sm font-bold text-zinc-700 group-hover:text-zinc-900 transition-colors"
                >启用账户</span
              >
            </label>
            <label class="flex items-center gap-2.5 cursor-pointer group">
              <Checkbox
                :checked="form.is_superuser"
                @update:checked="form.is_superuser = $event === true"
                class="rounded-md"
              />
              <span
                class="text-sm font-bold text-zinc-700 group-hover:text-zinc-900 transition-colors"
                >超级管理员权限</span
              >
            </label>
          </div>
        </div>
      </div>

      <DialogFooter
        class="flex items-center justify-end gap-2 p-4 pt-2 border-t border-zinc-100 bg-white min-h-[60px] shrink-0"
      >
        <Button
          variant="outline"
          @click="$emit('update:modelValue', false)"
          class="h-7 inline-flex items-center justify-center gap-1.5 text-xs rounded-md px-3 font-medium border-zinc-200 hover:bg-zinc-50 transition-colors"
        >
          <BadgeX class="size-3.5" />
          <span>取消</span>
        </Button>
        <Button
          @click="handleSave"
          :disabled="loading"
          class="h-7 inline-flex items-center justify-center gap-1.5 text-xs bg-zinc-900 text-white hover:bg-zinc-800 transition-colors rounded-md px-3 font-medium shadow-sm outline-none"
        >
          <Loader2 v-if="loading" class="size-3.5 animate-spin" />
          <Plus v-else-if="!isEdit" class="size-3.5" />
          <Save v-else class="size-3.5" />
          <span>{{ isEdit ? "保存修改" : "确认新增" }}</span>
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #e4e4e7;
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #d4d4d8;
}
</style>
