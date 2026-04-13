<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { toast } from "vue-sonner";

definePageMeta({
  layout: "console",
  middleware: "auth",
});

const auth = useAuth();
const api = useApi();
const loadingOverlay = useLoadingOverlay();

const user = auth.user;

const formData = reactive({
  username: "",
  display_name: "",
  email: "",
  newPassword: "",
});

const avatarUrl = ref("");
const avatarFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);

onMounted(async () => {
  try {
    const profile = await auth.fetchCurrentUser();
    if (profile) {
      formData.username = profile.username || "";
      formData.display_name = profile.display_name || "";
      formData.email = profile.email || "";
      if (profile.avatar_url) {
        avatarUrl.value = profile.avatar_url;
      }
    }
  } catch (error) {
    console.error("Failed to fetch current user profile:", error);
  }
});

const handleAvatarClick = () => {
  fileInput.value?.click();
};

const handleFileChange = (e: Event) => {
  const target = e.target as HTMLInputElement;
  if (target.files && target.files.length > 0) {
    const file = target.files[0];
    if (file) {
      // 本地预览
      avatarUrl.value = URL.createObjectURL(file);
      avatarFile.value = file;
      // 立即上传头像
      uploadAvatar(file);
    }
  }
};

const isUploading = ref(false);

const uploadAvatar = async (file: File) => {
  isUploading.value = true;
  try {
    const formPayload = new FormData();
    formPayload.append("file", file);
    const result = await api.post<{ avatar_url: string }>(
      "/auth/me/avatar",
      formPayload,
    );
    avatarUrl.value = result.avatar_url;
    // 同步更新本地用户状态，通过添加随机参数强制触发各组件头像刷新
    if (user.value) {
      const timestampedUrl = `${result.avatar_url}${result.avatar_url.includes("?") ? "&" : "?"}_t=${Date.now()}`;
      user.value = { ...user.value, avatar_url: timestampedUrl };
    }
    toast.success("头像上传成功");
  } catch (error) {
    toast.error("头像上传失败：" + api.normalizeError(error));
    // 恢复旧头像
    avatarUrl.value = user.value?.avatar_url || "";
    avatarFile.value = null;
  } finally {
    isUploading.value = false;
  }
};

const isSaving = ref(false);

const handleSave = async () => {
  isSaving.value = true;
  loadingOverlay.showLoading("保存中...");
  try {
    // 保存基本信息
    const profile = await api.patch<Record<string, any>>("/auth/me", {
      display_name: formData.display_name || undefined,
      email: formData.email || undefined,
    });

    // 修改密码（如果填写了）
    if (formData.newPassword.trim()) {
      // 暂无独立的旧密码输入，留空表示不修改
      toast.info("密码修改功能需要输入当前密码，请使用专用修改密码入口。");
    }

    // 同步更新前端用户状态
    if (user.value && profile) {
      user.value = {
        ...user.value,
        display_name: profile.display_name || formData.display_name,
        email: profile.email || formData.email,
      };
    }
    toast.success("个人资料已更新");
  } catch (error) {
    toast.error("保存失败：" + api.normalizeError(error));
  } finally {
    isSaving.value = false;
    loadingOverlay.hideLoading();
  }
};
</script>

<template>
  <div class="p-6 md:p-8 md:pl-12 max-w-4xl mt-2">
    <!-- 表单区域 -->
    <div class="space-y-8 max-w-2xl">
      <!-- 头像 -->
      <div class="flex items-start gap-8 pb-4">
        <div
          class="w-32 shrink-0 pt-2 text-[15px] font-medium text-zinc-700 dark:text-zinc-300"
        >
          头像
        </div>
        <div class="flex-1 flex flex-col items-start gap-4">
          <div class="relative group cursor-pointer" @click="handleAvatarClick">
            <Avatar
              class="w-16 h-16 shadow-sm ring-1 ring-zinc-200 dark:ring-zinc-800"
            >
              <AvatarImage
                v-if="avatarUrl"
                :src="avatarUrl"
                class="object-cover"
              />
              <AvatarFallback
                class="bg-[#f06e3e] text-white text-2xl font-semibold"
              >
                {{
                  formData.display_name?.charAt(0) ||
                  formData.username?.charAt(0) ||
                  "U"
                }}
              </AvatarFallback>
            </Avatar>
            <div
              v-if="isUploading"
              class="absolute inset-0 bg-black/50 rounded-full flex items-center justify-center"
            >
              <div
                class="h-5 w-5 animate-spin rounded-full border-2 border-white border-r-transparent"
              />
            </div>
            <div
              v-else
              class="absolute inset-0 bg-black/40 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <span class="text-[10px] text-white font-medium">更换</span>
            </div>
            <input
              type="file"
              ref="fileInput"
              class="hidden"
              accept="image/png, image/jpeg, image/webp, image/gif"
              @change="handleFileChange"
            />
          </div>
        </div>
      </div>

      <!-- 用户名 (只读) -->
      <div class="flex items-center gap-8">
        <div
          class="w-32 shrink-0 text-[15px] font-medium text-zinc-700 dark:text-zinc-300"
        >
          用户名
        </div>
        <div class="flex-1">
          <Input
            v-model="formData.username"
            disabled
            class="h-10 text-[15px] bg-zinc-50 dark:bg-zinc-900 text-zinc-500 cursor-not-allowed border-zinc-200 dark:border-zinc-800"
            placeholder="用户名"
          />
        </div>
      </div>

      <!-- 显示昵称 -->
      <div class="flex items-center gap-8">
        <div
          class="w-32 shrink-0 text-[15px] font-medium text-zinc-700 dark:text-zinc-300"
        >
          显示昵称
        </div>
        <div class="flex-1">
          <Input
            v-model="formData.display_name"
            class="h-10 text-[15px] bg-transparent focus-visible:ring-1 focus-visible:ring-zinc-300 dark:focus-visible:ring-zinc-700"
            placeholder="请输入显示昵称"
          />
        </div>
      </div>

      <!-- 邮箱 -->
      <div class="flex items-center gap-8">
        <div
          class="w-32 shrink-0 text-[15px] font-medium text-zinc-700 dark:text-zinc-300"
        >
          邮箱
        </div>
        <div class="flex-1">
          <Input
            v-model="formData.email"
            type="email"
            class="h-10 text-[15px] bg-transparent focus-visible:ring-1 focus-visible:ring-zinc-300 dark:focus-visible:ring-zinc-700"
            placeholder="admin@example.com"
          />
        </div>
      </div>

      <!-- 修改密码 -->
      <div class="flex items-start gap-8">
        <div
          class="w-32 shrink-0 pt-2 text-[15px] font-medium text-zinc-700 dark:text-zinc-300"
        >
          修改密码
        </div>
        <div class="flex-1">
          <Input
            type="password"
            v-model="formData.newPassword"
            class="h-10 text-[15px] bg-transparent focus-visible:ring-1 focus-visible:ring-zinc-300 dark:focus-visible:ring-zinc-700"
            placeholder="留空表示不修改密码"
          />
        </div>
      </div>

      <!-- 保存按钮 -->
      <div class="flex items-center gap-8 pt-8">
        <div class="w-32 shrink-0">
          <Button
            @click="handleSave"
            :disabled="isSaving"
            class="w-20 bg-zinc-900 hover:bg-zinc-800 text-white dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            <template v-if="isSaving">
              <div
                class="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent"
              />
            </template>
            <template v-else>保存</template>
          </Button>
        </div>
        <div class="flex-1"></div>
      </div>
    </div>
  </div>
</template>
