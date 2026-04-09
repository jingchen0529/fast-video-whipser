<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  Upload,
  Image as ImageIcon,
  Download,
  Trash2,
  FileVideo,
  Music,
  Loader2,
  X,
  Maximize2,
} from "lucide-vue-next";
import { toast } from "vue-sonner";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

definePageMeta({
  layout: "console",
  middleware: "auth",
  ssr: false,
});

useHead({ title: "我的资产" });

const apiService = useApi();
const api = apiService.requestData;
const runtimeConfig = useRuntimeConfig();

const items = ref<any[]>([]);
const storageUsage = ref<{ used_bytes: number; total_bytes: number }>({
  used_bytes: 0,
  total_bytes: 0,
});
const loading = ref(false);
const uploading = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const showDeleteConfirm = ref(false);
const deletingAssetId = ref<string | null>(null);
const deletingLoading = ref(false);

// 预览状态
const previewItem = ref<any | null>(null);
const showPreview = ref(false);

const resolveAssetUrl = (assetId?: string | null): string | null => {
  if (!assetId) return null;
  const apiBase = (runtimeConfig.public.apiBase || "").trim();
  let origin = typeof window !== "undefined" ? window.location.origin : "";
  if (apiBase && typeof window !== "undefined") {
    try {
      origin = new URL(apiBase, window.location.origin).origin;
    } catch {
      origin = window.location.origin;
    }
  }
  const path = `${apiBase}/assets/file/${assetId}`;
  try {
    return new URL(path, `${origin}/`).toString();
  } catch {
    return path;
  }
};

const formatBytes = (bytes: number) => {
  if (bytes === 0) return "0 B";
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
};

const formatTime = (isoString?: string) => {
  if (!isoString) return "";
  const date = new Date(isoString);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${Math.max(1, mins)} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
};

const fetchStorageUsage = async () => {
  try {
    const res = await api<{ used_bytes: number; total_bytes: number }>(
      "/assets/storage",
    );
    if (res) storageUsage.value = res;
  } catch (e) {
    /* ignore */
  }
};

const fetchAssets = async () => {
  loading.value = true;
  try {
    // 默认展示上传资产
    const res = await api<{ items: any[]; total: number }>(
      `/assets?source_type=upload`,
    );
    items.value = res.items || [];
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
};

const handleFileUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  if (!target.files || target.files.length === 0) return;

  uploading.value = true;
  try {
    for (let i = 0; i < target.files.length; i++) {
      const file = target.files[i];
      const formData = new FormData();
      formData.append("file", file);

      await api("/assets/upload", {
        method: "POST",
        body: formData,
      });
    }
    toast.success("上传完毕");
    await fetchAssets();
    await fetchStorageUsage();
  } catch (e) {
    console.error(e);
    toast.error("上传失败，请重试");
  } finally {
    uploading.value = false;
    if (fileInput.value) fileInput.value.value = "";
  }
};

const deleteAsset = (id: string, event: Event) => {
  event.stopPropagation();
  deletingAssetId.value = id;
  showDeleteConfirm.value = true;
};

const confirmDeleteAsset = async () => {
  if (!deletingAssetId.value) return;
  deletingLoading.value = true;
  try {
    await api(`/assets/${deletingAssetId.value}`, { method: "DELETE" });
    toast.success("删除成功");
    await fetchAssets();
    await fetchStorageUsage();
    showDeleteConfirm.value = false;
  } catch (e) {
    toast.error("删除失败");
  } finally {
    deletingLoading.value = false;
    deletingAssetId.value = null;
  }
};

const openPreview = (item: any) => {
  if (item.asset_type === "audio") return;
  previewItem.value = item;
  showPreview.value = true;
};

const downloadAsset = (url: string | null, name: string, event?: Event) => {
  if (event) event.stopPropagation();
  if (!url) return;
  const link = document.createElement("a");
  link.href = url;
  link.download = name || "download";
  link.target = "_blank";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

const getTypeLabel = (type: string) => {
  if (type === "video") return "视频";
  if (type === "audio") return "音频";
  if (type === "image") return "图片";
  return "文件";
};

const getSourceLabel = (source: string) => {
  if (source === "generated") return "AI 生成";
  if (source === "upload") return "本地上传";
  return "其他";
};

onMounted(() => {
  fetchAssets();
  fetchStorageUsage();
});
</script>

<template>
  <div
    class="h-full w-full bg-white dark:bg-[#121212] overflow-hidden flex flex-col p-6"
  >
    <!-- Header: Quota & Upload -->
    <div
      class="flex items-center justify-between pb-6 border-b border-zinc-100 dark:border-zinc-800"
    >
      <div class="flex items-center gap-3">
        <input
          type="file"
          ref="fileInput"
          class="hidden"
          accept="image/*,video/*,audio/*"
          multiple
          @change="handleFileUpload"
        />
        <button
          @click="fileInput?.click()"
          :disabled="uploading"
          class="flex items-center gap-2 px-5 py-2 bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 rounded-xl text-sm font-bold hover:bg-zinc-800 dark:hover:bg-white transition-all shadow-md active:scale-95 disabled:opacity-50"
        >
          <Loader2 v-if="uploading" class="size-4 animate-spin" />
          <Upload v-else class="size-4" />
          上传文件
        </button>
      </div>
    </div>

    <!-- Asset Grid -->
    <div class="flex-1 overflow-y-auto mt-6 relative custom-scrollbar pr-2">
      <div
        v-if="loading && items.length === 0"
        class="absolute inset-0 flex items-center justify-center"
      >
        <Loader2 class="size-6 animate-spin text-zinc-300" />
      </div>

      <div
        v-else-if="items.length === 0"
        class="absolute inset-0 flex flex-col items-center justify-center text-zinc-400 gap-2"
      >
        <div
          class="size-16 rounded-full bg-zinc-50 dark:bg-zinc-900 flex items-center justify-center mb-2"
        >
          <Upload class="size-8 opacity-20" />
        </div>
        <p class="text-sm font-medium">还没有资产数据</p>
      </div>

      <div
        v-else
        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-8 pb-6"
      >
        <div
          v-for="item in items"
          :key="item.id"
          @click="openPreview(item)"
          class="rounded-2xl border border-zinc-100 dark:border-zinc-800 overflow-hidden bg-white dark:bg-zinc-900/50 flex flex-col group hover:border-zinc-300 dark:hover:border-zinc-700 hover:shadow-xl transition-all duration-300 cursor-pointer"
        >
          <div
            class="w-full aspect-[4/3] relative bg-zinc-100 dark:bg-zinc-950 overflow-hidden"
          >
            <div
              class="w-full h-full flex items-center justify-center relative"
            >
              <!-- Preview Components -->
              <video
                v-if="item.asset_type === 'video'"
                :src="resolveAssetUrl(item.id) || undefined"
                class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                muted
                loop
                onmouseover="this.play()"
                onmouseout="this.pause()"
              />
              <div
                v-else-if="item.asset_type === 'audio'"
                class="flex flex-col items-center gap-3"
              >
                <Music class="size-12 text-zinc-300" />
                <span class="text-[10px] text-zinc-500 font-mono"
                  >AUDIO FILE</span
                >
              </div>
              <img
                v-else
                :src="resolveAssetUrl(item.id) || undefined"
                class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
              />

              <!-- Type Overlay -->
              <div
                class="absolute top-3 left-3 bg-white/90 dark:bg-black/60 backdrop-blur-md text-zinc-900 dark:text-white text-[10px] px-2 py-1 rounded-lg border border-black/5 dark:border-white/10 flex items-center gap-1.5 font-bold shadow-sm"
              >
                <FileVideo
                  v-if="item.asset_type === 'video'"
                  class="size-3 text-blue-500"
                />
                <Music
                  v-else-if="item.asset_type === 'audio'"
                  class="size-3 text-purple-500"
                />
                <ImageIcon v-else class="size-3 text-emerald-500" />
                {{ getTypeLabel(item.asset_type) }}
              </div>

              <!-- Source Overlay -->
              <div
                class="absolute top-3 right-3 px-2 py-1 rounded-lg text-[9px] font-black tracking-tight"
                :class="
                  item.source_type === 'generated'
                    ? 'bg-purple-500/10 text-purple-600 border border-purple-200 dark:border-purple-800'
                    : 'bg-zinc-100 text-zinc-600 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700'
                "
              >
                {{ getSourceLabel(item.source_type).toUpperCase() }}
              </div>

              <!-- Hover Zoom Icon -->
              <div
                class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
              >
                <div
                  class="p-3 rounded-full bg-white/20 backdrop-blur-md text-white scale-75 group-hover:scale-100 transition-all duration-300"
                >
                  <Maximize2 class="size-6" />
                </div>
              </div>
            </div>
          </div>

          <div class="px-4 py-4 flex flex-col bg-white dark:bg-[#18181b]">
            <TooltipProvider :delay-duration="300">
              <Tooltip>
                <TooltipTrigger as-child>
                  <div
                    class="text-sm font-semibold text-zinc-800 dark:text-zinc-100 truncate mb-1 cursor-help"
                  >
                    {{ item.file_name }}
                  </div>
                </TooltipTrigger>
                <TooltipContent
                  class="bg-zinc-900 text-white border-zinc-800 px-3 py-1.5 text-xs rounded-lg"
                >
                  <p class="max-w-xs break-all">{{ item.file_name }}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <div class="flex items-center justify-between mt-1">
              <div class="text-[11px] text-zinc-500 font-medium">
                {{ formatBytes(item.size_bytes) }} ·
                {{ formatTime(item.created_at) }}
              </div>
              <div class="flex items-center gap-0.5 translate-x-1">
                <button
                  @click.stop="
                    (e) =>
                      downloadAsset(resolveAssetUrl(item.id), item.file_name, e)
                  "
                  class="p-2 text-zinc-400 hover:text-zinc-900 dark:hover:text-white hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-all"
                >
                  <Download class="size-4" />
                </button>
                <button
                  @click.stop="(e) => deleteAsset(item.id, e)"
                  class="p-2 text-zinc-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-lg transition-all"
                >
                  <Trash2 class="size-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Image/Video Preview Overlay -->
    <Transition name="fade">
      <div
        v-if="showPreview && previewItem"
        class="fixed inset-0 z-50 bg-black/95 backdrop-blur-xl flex flex-col"
        @click="showPreview = false"
      >
        <div class="flex items-center justify-between p-6" @click.stop>
          <div class="flex flex-col">
            <div class="flex items-center gap-2">
              <h3 class="text-white font-bold text-lg leading-none">
                {{ previewItem.file_name }}
              </h3>
              <span
                class="px-1.5 py-0.5 rounded text-[10px] font-bold"
                :class="
                  previewItem.source_type === 'generated'
                    ? 'bg-purple-600 text-white'
                    : 'bg-zinc-700 text-zinc-300'
                "
              >
                {{ getSourceLabel(previewItem.source_type) }}
              </span>
            </div>
            <span class="text-zinc-500 text-xs mt-1.5"
              >{{ formatBytes(previewItem.size_bytes) }} ·
              {{ formatTime(previewItem.created_at) }}</span
            >
          </div>
          <div class="flex items-center gap-3">
            <button
              @click.stop="
                downloadAsset(
                  resolveAssetUrl(previewItem.id),
                  previewItem.file_name,
                )
              "
              class="p-3 bg-white/10 hover:bg-white/20 text-white rounded-full transition-all"
            >
              <Download class="size-5" />
            </button>
            <button
              @click="showPreview = false"
              class="p-3 bg-white/10 hover:bg-white/20 text-white rounded-full transition-all"
            >
              <X class="size-5" />
            </button>
          </div>
        </div>

        <div
          class="flex-1 flex items-center justify-center p-4 lg:p-12 overflow-hidden"
        >
          <div
            class="relative max-w-7xl max-h-full aspect-auto rounded-xl overflow-hidden shadow-[0_0_100px_rgba(0,0,0,0.5)]"
            @click.stop
          >
            <video
              v-if="previewItem.asset_type === 'video'"
              :src="resolveAssetUrl(previewItem.id) || undefined"
              class="w-full h-full max-h-[80vh] object-contain"
              controls
              autoplay
            />
            <img
              v-else
              :src="resolveAssetUrl(previewItem.id) || undefined"
              class="w-full h-full max-h-[80vh] object-contain"
            />
          </div>
        </div>
      </div>
    </Transition>

    <!-- Delete Confirmation -->
    <Dialog v-model:open="showDeleteConfirm">
      <DialogContent
        class="sm:max-w-[400px] border-none shadow-2xl overflow-hidden rounded-[2rem]"
      >
        <DialogHeader class="pt-6">
          <DialogTitle class="text-xl font-bold flex items-center gap-3 px-2">
            <div
              class="p-2.5 rounded-2xl bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400"
            >
              <Trash2 class="size-5" />
            </div>
            确认删除文件？
          </DialogTitle>
          <DialogDescription
            class="pt-4 px-2 text-zinc-500 dark:text-zinc-400 text-sm leading-relaxed"
          >
            该操作无法撤销。该资产将从云端永久删除，所有引用此资产的项目可能会受到影响。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter class="mt-8 gap-3 bg-zinc-50 dark:bg-zinc-900/50 p-6">
          <Button
            variant="ghost"
            class="rounded-xl px-6 h-11 font-semibold"
            @click="showDeleteConfirm = false"
            >取消</Button
          >
          <Button
            variant="destructive"
            class="rounded-xl px-6 h-11 font-bold shadow-lg shadow-red-500/20 active:scale-95 transition-all"
            @click="confirmDeleteAsset"
            :loading="deletingLoading"
          >
            确认永久删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
  background-color: rgba(153, 153, 153, 0.1);
  border-radius: 10px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
