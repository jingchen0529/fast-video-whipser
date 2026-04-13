<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { 
  Save, 
  PlusCircle, 
  Loader2,
  Layout,
  Globe,
  Monitor,
  Settings2,
  Type,
  Link,
  Info
} from "lucide-vue-next";
import { toast } from "vue-sonner";
import { notifyError } from "@/utils/common";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AuthMenu } from "@/types/api";

const props = defineProps<{
  modelValue: boolean;
  menu: AuthMenu | null;
  parentOptions: any[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const api = useApi();
const loading = ref(false);

const ROOT_PARENT_VALUE = "__root__";

const createDefaultForm = () => ({
  code: "",
  title: "",
  menu_type: "menu" as AuthMenu["menu_type"],
  route_path: "",
  route_name: "",
  redirect_path: "",
  icon: "",
  component_key: "",
  parent_id: ROOT_PARENT_VALUE,
  sort_order: 0,
  is_visible: true,
  is_enabled: true,
  is_external: false,
  open_mode: "self" as "self" | "blank",
  is_cacheable: false,
  is_affix: false,
  active_menu_path: "",
  badge_text: "",
  badge_type: "",
  remark: "",
  meta_json: "{}",
});

const menuForm = reactive(createDefaultForm());

const isEdit = computed(() => !!props.menu);

const resetForm = () => {
  if (props.menu) {
    const menu = props.menu;
    menuForm.code = menu.code || "";
    menuForm.title = menu.title || "";
    menuForm.menu_type = menu.menu_type || "menu";
    menuForm.route_path = menu.route_path || "";
    menuForm.route_name = menu.route_name || "";
    menuForm.redirect_path = menu.redirect_path || "";
    menuForm.icon = menu.icon || "";
    menuForm.component_key = menu.component_key || "";
    menuForm.parent_id = menu.parent_id || ROOT_PARENT_VALUE;
    menuForm.sort_order = menu.sort_order || 0;
    menuForm.is_visible = menu.is_visible ?? true;
    menuForm.is_enabled = menu.is_enabled ?? true;
    menuForm.is_external = menu.is_external ?? false;
    menuForm.open_mode = (menu.open_mode as any) || "self";
    menuForm.is_cacheable = menu.is_cacheable ?? false;
    menuForm.is_affix = menu.is_affix ?? false;
    menuForm.active_menu_path = menu.active_menu_path || "";
    menuForm.badge_text = menu.badge_text || "";
    menuForm.badge_type = menu.badge_type || "";
    menuForm.remark = menu.remark || "";
    menuForm.meta_json = JSON.stringify(menu.meta_json || {}, null, 2);
  } else {
    Object.assign(menuForm, createDefaultForm());
  }
};

watch(
  () => [props.modelValue, props.menu?.id],
  ([value]) => {
    if (value) {
      resetForm();
    }
  },
);

const buildPayload = () => {
  if (!menuForm.code.trim() && !isEdit.value) {
    throw new Error("菜单编码不能为空。");
  }
  if (!menuForm.title.trim()) {
    throw new Error("菜单名称不能为空。");
  }

  let parsedMetaJson: Record<string, unknown> = {};
  try {
    parsedMetaJson = menuForm.meta_json.trim()
      ? JSON.parse(menuForm.meta_json)
      : {};
  } catch (error) {
    throw new Error("扩展元数据必须是合法的 JSON。");
  }

  return {
    code: menuForm.code.trim(),
    title: menuForm.title.trim(),
    menu_type: menuForm.menu_type,
    route_path: menuForm.route_path.trim(),
    route_name: menuForm.route_name.trim() || null,
    redirect_path: menuForm.redirect_path.trim() || null,
    icon: menuForm.icon.trim() || null,
    component_key: menuForm.component_key.trim() || null,
    parent_id: menuForm.parent_id === ROOT_PARENT_VALUE ? null : menuForm.parent_id,
    sort_order: Number(menuForm.sort_order || 0),
    is_visible: menuForm.is_visible,
    is_enabled: menuForm.is_enabled,
    is_external: menuForm.is_external,
    open_mode: menuForm.open_mode,
    is_cacheable: menuForm.is_cacheable,
    is_affix: menuForm.is_affix,
    active_menu_path: menuForm.active_menu_path.trim() || null,
    badge_text: menuForm.badge_text.trim() || null,
    badge_type: menuForm.badge_type.trim() || null,
    remark: menuForm.remark.trim() || null,
    meta_json: parsedMetaJson,
  };
};

const handleSaveMenu = async () => {
  try {
    const payload = buildPayload();
    loading.value = true;
    if (isEdit.value && props.menu) {
      const { code: _code, ...patchPayload } = payload;
      await api.patch<AuthMenu>(`/menus/${props.menu.id}`, patchPayload);
      toast.success("菜单已更新。");
    } else {
      await api.post<AuthMenu>("/menus", payload);
      toast.success("菜单已创建。");
    }
    emit("saved");
    emit("update:modelValue", false);
  } catch (error) {
    if (error instanceof Error) {
      toast.error(error.message);
      return;
    }
    notifyError(api, error, "保存菜单失败。");
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <Dialog :open="modelValue" @update:open="$emit('update:modelValue', $event)">
    <DialogContent
      class="w-[min(96vw,900px)] max-w-none overflow-hidden rounded-[28px] border border-zinc-200/80 bg-zinc-50/50 p-0 shadow-[0_28px_90px_rgba(15,23,42,0.18)]"
    >
      <div class="flex max-h-[90vh] flex-col bg-white">
        <!-- Header -->
        <DialogHeader class="border-b border-zinc-100 px-8 pb-5 pt-6 bg-white shrink-0 text-left">
          <DialogTitle class="text-[22px] font-semibold tracking-tight text-zinc-900">
            {{ isEdit ? '编辑菜单' : '新增菜单' }}
          </DialogTitle>
          <DialogDescription class="mt-1 text-sm leading-6 text-zinc-500">
            配置菜单的基本属性、路由导航及显示控制，构建系统导航体系。
          </DialogDescription>
        </DialogHeader>

        <!-- Body -->
        <ScrollArea class="flex-1 min-h-0 bg-zinc-50/30">
          <div class="px-8 py-6">
            <div class="grid grid-cols-1 md:grid-cols-12 gap-6">
              
              <!-- Left Column: Core Settings -->
              <div class="md:col-span-12 lg:col-span-8 space-y-6">
                <!-- Group 1: Identity & Hierarchy -->
                <div class="rounded-[22px] border border-zinc-200/80 bg-white p-6 shadow-sm">
                  <h3 class="font-semibold text-sm text-zinc-900 mb-5 flex items-center gap-2">
                    <Type class="w-4 h-4 text-zinc-500" />
                    核心定义
                  </h3>
                  <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div class="space-y-2">
                      <label class="text-[13px] font-semibold text-zinc-800">菜单标题 <span class="text-red-500">*</span></label>
                      <Input
                        v-model="menuForm.title"
                        placeholder="例如：用户管理"
                        class="h-11 rounded-xl border-zinc-200 bg-white px-3 text-[14px] focus:ring-1 focus:ring-zinc-900"
                      />
                    </div>
                    <div class="space-y-2">
                      <label class="text-[13px] font-semibold text-zinc-800">菜单编码 <span class="text-red-500">*</span></label>
                      <Input
                        v-model="menuForm.code"
                        :disabled="isEdit"
                        placeholder="例如：sys:user:list"
                        class="h-11 rounded-xl border-zinc-200 bg-white px-3 text-[14px] focus:ring-1 focus:ring-zinc-900"
                      />
                      <p class="text-[11px] text-zinc-400">作为权限唯一标识，创建后不可修改。</p>
                    </div>
                    <div class="space-y-2">
                      <label class="text-[13px] font-semibold text-zinc-800">菜单类型</label>
                      <Select v-model="menuForm.menu_type">
                        <SelectTrigger class="h-11 rounded-xl border-zinc-200 bg-white px-3 text-[14px]">
                          <SelectValue placeholder="选择类型" />
                        </SelectTrigger>
                        <SelectContent class="rounded-xl">
                          <SelectItem value="directory">目录 (Directory)</SelectItem>
                          <SelectItem value="menu">菜单 (Menu)</SelectItem>
                          <SelectItem value="link">外链 (Link)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div class="space-y-2">
                      <label class="text-[13px] font-semibold text-zinc-800">父级菜单</label>
                      <Select v-model="menuForm.parent_id">
                        <SelectTrigger class="h-11 rounded-xl border-zinc-200 bg-white px-3 text-[14px]">
                          <SelectValue placeholder="选择父级" />
                        </SelectTrigger>
                        <SelectContent class="rounded-xl max-h-60">
                          <SelectItem :value="ROOT_PARENT_VALUE">顶部根目录</SelectItem>
                          <SelectItem
                            v-for="item in parentOptions"
                            :key="item.id"
                            :value="item.id"
                          >
                            {{ `${"— ".repeat(item.level)}${item.title}` }}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>

                <!-- Group 2: Routing & Navigation -->
                <div class="rounded-[22px] border border-zinc-200/80 bg-white p-6 shadow-sm">
                  <h3 class="font-semibold text-sm text-zinc-900 mb-5 flex items-center gap-2">
                    <Monitor class="w-4 h-4 text-zinc-500" />
                    路由导航
                  </h3>
                  <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div class="space-y-2">
                      <label class="text-[13px] font-semibold text-zinc-800">路由路径 (Path)</label>
                      <Input
                        v-model="menuForm.route_path"
                        placeholder="例如：/system/user"
                        class="h-11 rounded-xl border-zinc-200 bg-white px-3 text-[14px]"
                      />
                    </div>
                    <div class="space-y-2">
                      <label class="text-[13px] font-semibold text-zinc-800">组件标识 (Key)</label>
                      <Input
                        v-model="menuForm.component_key"
                        placeholder="例如：UserManagement"
                        class="h-11 rounded-xl border-zinc-200 bg-white px-3 text-[14px]"
                      />
                    </div>
                    <div class="space-y-2">
                      <label class="text-[13px] font-semibold text-zinc-800">路由名称 (Name)</label>
                      <Input
                        v-model="menuForm.route_name"
                        placeholder="例如：SysUser"
                        class="h-11 rounded-xl border-zinc-200 bg-white px-3 text-[14px]"
                      />
                    </div>
                    <div class="space-y-2">
                      <label class="text-[13px] font-semibold text-zinc-800">重定向路径</label>
                      <Input
                        v-model="menuForm.redirect_path"
                        placeholder="例如：/dashboard"
                        class="h-11 rounded-xl border-zinc-200 bg-white px-3 text-[14px]"
                      />
                    </div>
                    <div class="space-y-2">
                      <label class="text-[13px] font-semibold text-zinc-800">高亮菜单路径</label>
                      <Input
                        v-model="menuForm.active_menu_path"
                        placeholder="例如：/system/log"
                        class="h-11 rounded-xl border-zinc-200 bg-white px-3 text-[14px]"
                      />
                    </div>
                    <div class="space-y-2">
                      <label class="text-[13px] font-semibold text-zinc-800">打开方式</label>
                      <Select v-model="menuForm.open_mode">
                        <SelectTrigger class="h-11 rounded-xl border-zinc-200 bg-white px-3 text-[14px]">
                          <SelectValue placeholder="默认方式" />
                        </SelectTrigger>
                        <SelectContent class="rounded-xl">
                          <SelectItem value="self">当前窗口 (Self)</SelectItem>
                          <SelectItem value="blank">新窗口 (Blank)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Right Column: Visuals & Metadata -->
              <div class="md:col-span-12 lg:col-span-4 space-y-6">
                <!-- Group 3: Appearance & Status -->
                <div class="rounded-[22px] border border-zinc-200/80 bg-white p-6 shadow-sm">
                  <h3 class="font-semibold text-sm text-zinc-900 mb-5 flex items-center gap-2">
                    <Settings2 class="w-4 h-4 text-zinc-500" />
                    显示控制
                  </h3>
                  <div class="space-y-5">
                    <div class="flex items-center justify-between">
                      <div class="space-y-0.5">
                        <div class="text-[13px] font-semibold text-zinc-800">显示状态</div>
                        <div class="text-[11px] text-zinc-400">控制菜单在导航栏是否可见</div>
                      </div>
                      <Switch v-model:checked="menuForm.is_visible" />
                    </div>
                    <div class="flex items-center justify-between border-t border-zinc-50 pt-3">
                      <div class="space-y-0.5">
                        <div class="text-[13px] font-semibold text-zinc-800">启用状态</div>
                        <div class="text-[11px] text-zinc-400">关闭后该菜单路径将不可访问</div>
                      </div>
                      <Switch v-model:checked="menuForm.is_enabled" />
                    </div>
                    <div class="flex items-center justify-between border-t border-zinc-50 pt-3">
                      <div class="space-y-0.5">
                        <div class="text-[13px] font-semibold text-zinc-800">外链菜单</div>
                        <div class="text-[11px] text-zinc-400">是否作为独立外部链接跳转</div>
                      </div>
                      <Switch v-model:checked="menuForm.is_external" />
                    </div>
                    <div class="flex items-center justify-between border-t border-zinc-50 pt-3">
                      <div class="space-y-0.5">
                        <div class="text-[13px] font-semibold text-zinc-800">页面缓存</div>
                        <div class="text-[11px] text-zinc-400">使用 Keep-Alive 保持页面状态</div>
                      </div>
                      <Switch v-model:checked="menuForm.is_cacheable" />
                    </div>
                    <div class="flex items-center justify-between border-t border-zinc-50 pt-3">
                      <div class="space-y-0.5">
                        <div class="text-[13px] font-semibold text-zinc-800">固定页签</div>
                        <div class="text-[11px] text-zinc-400">标签栏中不可关闭的快捷项</div>
                      </div>
                      <Switch v-model:checked="menuForm.is_affix" />
                    </div>

                    <div class="space-y-4 pt-4 border-t border-zinc-50">
                      <div class="space-y-2">
                        <label class="text-[13px] font-semibold text-zinc-800">排序权重</label>
                        <Input
                          v-model.number="menuForm.sort_order"
                          type="number"
                          class="h-10 rounded-xl border-zinc-200 bg-white px-3 text-[14px]"
                        />
                      </div>
                      <div class="space-y-2">
                        <label class="text-[13px] font-semibold text-zinc-800">图标标识</label>
                        <Input
                          v-model="menuForm.icon"
                          placeholder="例如：User"
                          class="h-10 rounded-xl border-zinc-200 bg-white px-3 text-[14px]"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Group 4: Badges -->
                <div class="rounded-[22px] border border-zinc-200/80 bg-white p-6 shadow-sm">
                  <h3 class="font-semibold text-sm text-zinc-900 mb-5 flex items-center gap-2">
                    <Globe class="w-4 h-4 text-zinc-500" />
                    提示角标
                  </h3>
                  <div class="space-y-4">
                    <div class="space-y-2">
                       <label class="text-[13px] font-semibold text-zinc-800">文字内容</label>
                       <Input v-model="menuForm.badge_text" placeholder="例如：New" class="h-10 rounded-xl px-3" />
                    </div>
                    <div class="space-y-2">
                       <label class="text-[13px] font-semibold text-zinc-800">角标类型</label>
                       <Input v-model="menuForm.badge_type" placeholder="例如：danger / info" class="h-10 rounded-xl px-3" />
                    </div>
                  </div>
                </div>
              </div>

              <!-- Full Width Footer: Remark & JSON -->
              <div class="md:col-span-12 grid grid-cols-1 md:grid-cols-2 gap-6 pb-4">
                <div class="rounded-[22px] border border-zinc-200/80 bg-white p-6 shadow-sm">
                  <h3 class="font-semibold text-sm text-zinc-900 mb-5 flex items-center gap-2">
                    <Info class="w-4 h-4 text-zinc-500" />
                    备注说明
                  </h3>
                  <Textarea
                    v-model="menuForm.remark"
                    placeholder="选填，描述菜单用途或特殊逻辑..."
                    class="min-h-[120px] rounded-xl border-zinc-200 bg-white resize-none p-3 text-[14px]"
                  />
                </div>
                <div class="rounded-[22px] border border-zinc-200/80 bg-white p-6 shadow-sm">
                  <h3 class="font-semibold text-sm text-zinc-900 mb-5 flex items-center gap-2">
                    <Link class="w-4 h-4 text-zinc-500" />
                    扩展元数据 (JSON)
                  </h3>
                  <Textarea
                    v-model="menuForm.meta_json"
                    placeholder='{"key": "value"}'
                    class="min-h-[120px] rounded-xl border-zinc-200 bg-white font-mono text-xs p-3"
                  />
                </div>
              </div>
            </div>
          </div>
        </ScrollArea>

        <!-- Footer -->
        <DialogFooter class="border-t border-zinc-100 bg-white px-8 py-4 shrink-0 shadow-[0_-10px_20px_rgba(0,0,0,0.01)] text-right">
          <Button variant="outline" @click="$emit('update:modelValue', false)" class="h-11 rounded-xl px-8 font-semibold bg-white border-zinc-200 hover:bg-zinc-50 transition-colors">
            取消
          </Button>
          <Button @click="handleSaveMenu" :disabled="loading" class="h-11 rounded-xl bg-zinc-900 px-8 text-white font-semibold hover:bg-black active:scale-[0.98] shadow-sm transition-all focus-visible:ring-2 ring-offset-2 ring-zinc-900">
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

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #e4e4e7;
  border-radius: 10px;
}
</style>
