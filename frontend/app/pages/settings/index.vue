<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  RefreshCw,
  Save,
  ShieldCheck,
  UploadCloud,
  CheckCircle2,
  Activity,
  Type,
  Image as ImageIcon,
} from "lucide-vue-next";
import { toast } from "vue-sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { notifyError, formatDateTime } from "@/utils/common";
import type {
  SystemSettingsPayload,
  SystemSettingsProviderConfig,
} from "@/types/api";

definePageMeta({
  middleware: "auth",
  layout: "console",
});

const api = useApi();
const auth = useAuth();

const loading = ref(false);
const savingSection = ref<"general" | "proxy" | "chat" | "video" | null>(null);
const testing = ref(false);
const loadError = ref("");
const lastSavedAt = ref<string | null>(null);
const activeTab = ref("general");
const initialized = ref(false);

const createDefaultSettingsState = (): SystemSettingsPayload => ({
  system: {
    name: "爆款杀手",
    description: "您的专属 AI 工作平台",
    logo_url: "/logo.png",
  },
  proxy: {
    enabled: false,
    http_url: "",
    https_url: "",
    all_url: "",
    no_proxy: "",
  },
  analysis: {
    default_provider: "openai",
    providers: [
      {
        provider: "openai",
        label: "OpenAI",
        enabled: true,
        base_url: "https://api.openai.com/v1",
        api_key: "",
        default_model: "gpt-4.1",
        model_options: ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
      },
      {
        provider: "gemini",
        label: "Gemini",
        enabled: false,
        base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
        api_key: "",
        default_model: "gemini-2.5-flash",
        model_options: [
          "gemini-2.5-pro",
          "gemini-2.5-flash",
          "gemini-2.5-flash-lite",
        ],
      },
      {
        provider: "doubao",
        label: "豆包",
        enabled: true,
        base_url: "https://ark.cn-beijing.volces.com/api/v3",
        api_key: "",
        default_model: "doubao-seed-1-6-250615",
        model_options: [
          "doubao-seed-1-6-250615",
          "doubao-pro",
          "doubao-lite",
          "doubao-thinking",
        ],
      },
      {
        provider: "kimi",
        label: "Kimi",
        enabled: false,
        base_url: "https://api.moonshot.cn/v1",
        api_key: "",
        default_model: "kimi-k2",
        model_options: ["kimi-k2", "kimi-thinking", "moonshot-v1-128k"],
      },
      {
        provider: "qwen",
        label: "千问",
        enabled: false,
        base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key: "",
        default_model: "qwen-plus",
        model_options: ["qwen-max", "qwen-plus", "qwen-turbo"],
      },
      {
        provider: "deepseek",
        label: "DeepSeek",
        enabled: false,
        base_url: "https://api.deepseek.com/v1",
        api_key: "",
        default_model: "deepseek-chat",
        model_options: ["deepseek-chat", "deepseek-reasoner"],
      },
      {
        provider: "custom",
        label: "自定义�
�容服务",
        enabled: false,
        base_url: "",
        api_key: "",
        default_model: "custom-model",
        model_options: ["custom-model"],
      },
    ],
  },
  remake: {
    default_provider: "doubao",
    providers: [
      {
        provider: "doubao",
        label: "豆�
",
        enabled: true,
        base_url: "",
        api_key: "",
        default_model: "seedance-pro",
        model_options: ["seedance-pro", "seedance-lite"],
      },
      {
        provider: "kling",
        label: "可灵",
        enabled: false,
        base_url: "",
        api_key: "",
        default_model: "kling-v1",
        model_options: ["kling-v1", "kling-master"],
      },
      {
        provider: "veo",
        label: "Veo",
        enabled: false,
        base_url: "",
        api_key: "",
        default_model: "veo-3",
        model_options: ["veo-3", "veo-2"],
      },
      {
        provider: "wanxiang",
        label: "万相",
        enabled: false,
        base_url: "",
        api_key: "",
        default_model: "wanx-video",
        model_options: ["wanx-video", "wanx-image-to-video"],
      },
      {
        provider: "custom",
        label: "自定义视频模型",
        enabled: false,
        base_url: "",
        api_key: "",
        default_model: "custom-video-model",
        model_options: ["custom-video-model"],
      },
    ],
  },
});

const mergeProviderGroup = (
  defaults: SystemSettingsPayload["analysis"],
  incoming?: Partial<SystemSettingsPayload["analysis"]> | null,
) => {
  const incomingProviders = new Map(
    (incoming?.providers || []).map((provider) => [
      provider.provider,
      provider,
    ]),
  );
  const providers = defaults.providers.map((provider) => ({
    ...provider,
    ...(incomingProviders.get(provider.provider) || {}),
    model_options: incomingProviders.get(provider.provider)?.model_options
      ?.length
      ? [...(incomingProviders.get(provider.provider)?.model_options || [])]
      : [...provider.model_options],
  }));
  const extraProviders = (incoming?.providers || []).filter(
    (provider) =>
      !defaults.providers.some((item) => item.provider === provider.provider),
  );

  return {
    default_provider:
      incoming?.default_provider &&
      providers.some((item) => item.provider === incoming.default_provider)
        ? incoming.default_provider
        : defaults.default_provider,
    providers: [...providers, ...extraProviders],
  };
};

const normalizeSettingsPayload = (
  payload?: Partial<SystemSettingsPayload> | null,
): SystemSettingsPayload => {
  const defaults = createDefaultSettingsState();
  return {
    system: {
      ...defaults.system,
      ...(payload?.system || {}),
    },
    proxy: {
      ...defaults.proxy,
      ...(payload?.proxy || {}),
    },
    analysis: mergeProviderGroup(defaults.analysis, payload?.analysis),
    remake: mergeProviderGroup(defaults.remake, payload?.remake),
  };
};

const formState = ref<SystemSettingsPayload>(createDefaultSettingsState());

const selectedChatProvider = ref<string>("openai");
const selectedVideoProvider = ref<string>("doubao");

const proxyHost = computed({
  get: () => {
    const raw = formState.value.proxy?.http_url || "";
    const withoutProtocol = raw.replace(/^https?:\/\//, "");
    return withoutProtocol.split(":")[0] || "";
  },
  set: (val) => {
    if (!formState.value.proxy) return;
    const port = proxyPort.value;
    formState.value.proxy.http_url = val
      ? `http://${val}${port ? ":" + port : ""}`
      : "";
  },
});

const proxyPort = computed({
  get: () => {
    const raw = formState.value.proxy?.http_url || "";
    const withoutProtocol = raw.replace(/^https?:\/\//, "");
    const parts = withoutProtocol.split(":");
    return parts.length > 1 ? parts[1] : "";
  },
  set: (val) => {
    if (!formState.value.proxy) return;
    const host = proxyHost.value;
    if (host) {
      formState.value.proxy.http_url = `http://${host}${val ? ":" + val : ""}`;
    }
  },
});

const canUpdate = computed(() => {
  const currentUser = auth.user.value;
  if (!currentUser) return false;
  return (
    currentUser.is_superuser ||
    currentUser.permissions.some((item) => item.code === "settings.update")
  );
});

const getModelOptionsText = (provider: SystemSettingsProviderConfig) => {
  if (!provider || !provider.model_options) return "";
  const options = [...provider.model_options];
  const defaultModel = (provider.default_model || "").trim();
  if (defaultModel && !options.includes(defaultModel)) {
    options.unshift(defaultModel);
  }
  return options.join("\n");
};

const handleModelOptionsInput = (
  provider: SystemSettingsProviderConfig,
  event: Event,
) => {
  if (!provider) return;
  const target = event.target as HTMLTextAreaElement | null;
  const value = target?.value || "";
  provider.model_options = Array.from(
    new Set(
      value
        .replace(/,/g, "\n")
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
};

const normalizeLoadErrorMessage = (error: unknown) => {
  const message = api.normalizeError(error);
  if (message.includes("settings.view")) {
    return "当前账号没有系统设置查看权限，请使用管理员账号登录后查看。";
  }
  if (message.includes("Method Not Allowed")) {
    return "当前后端还不支持该设置接口的探测请求，请重启后端后再试。";
  }
  if (message.includes("Not Found")) {
    return "当前后端进程还没有加载系统设置接口，请重启后端服务后再试。";
  }
  return message;
};

const testConnection = async () => {
  testing.value = true;
  try {
    const res = await api.get<{ status: string }>("/health");
    if (res.status === "ok") {
      toast.success("后端服务连接正常");
    } else {
      toast.warning("后端服务响应异常");
    }
  } catch (error) {
    notifyError(api, error, "连接测试失败");
  } finally {
    testing.value = false;
  }
};

const loadSettings = async (manual = false) => {
  loading.value = true;
  loadError.value = "";
  try {
    const data = await api.get<SystemSettingsPayload>("/settings");
    formState.value = normalizeSettingsPayload(data);
    selectedChatProvider.value =
      formState.value.analysis?.default_provider ||
      formState.value.analysis?.providers?.[0]?.provider ||
      "openai";
    selectedVideoProvider.value =
      formState.value.remake?.default_provider ||
      formState.value.remake?.providers?.[0]?.provider ||
      "doubao";
    lastSavedAt.value = new Date().toISOString();
    initialized.value = true;
    if (manual) toast.success("设置已刷新");
  } catch (error) {
    loadError.value = normalizeLoadErrorMessage(error);
    formState.value = normalizeSettingsPayload(formState.value);
    initialized.value = true;
    notifyError(api, error, "无法加载系统�
�置");
  } finally {
    loading.value = false;
  }
};

const saveSettings = async (
  section: "general" | "proxy" | "chat" | "video",
  label: string,
) => {
  if (!formState.value || !canUpdate.value || savingSection.value) return;

  savingSection.value = section;
  try {
    const data = await api.patch<SystemSettingsPayload>(
      "/settings",
      normalizeSettingsPayload(JSON.parse(JSON.stringify(formState.value))),
    );
    formState.value = normalizeSettingsPayload(data);
    lastSavedAt.value = new Date().toISOString();
    toast.success(`${label}保存成功`);
  } catch (error) {
    notifyError(api, error, "保存失败");
  } finally {
    savingSection.value = null;
  }
};

const fileInputRef = ref<HTMLInputElement | null>(null);
const uploadingLogo = ref(false);

const triggerLogoUpload = () => {
  fileInputRef.value?.click();
};

const handleLogoFile = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file || !formState.value) return;

  if (!file.type.startsWith("image/")) {
    toast.error("请选择有效的图片文件");
    return;
  }

  uploadingLogo.value = true;
  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await api.post<{ stored_name: string }>(
      "/common/upload",
      formData,
    );
    if (formState.value.system) {
      formState.value.system.logo_url = `/uploads/${res.stored_name}`;
    }
    toast.success("Logo 上传成功");
  } catch (error) {
    notifyError(api, error, "Logo 上传失败");
  } finally {
    uploadingLogo.value = false;
    target.value = "";
  }
};

onMounted(async () => {
  await loadSettings();
});
</script>

<template>
  <div class="p-6 space-y-8 max-w-5xl mx-auto">
    <!-- Main View -->
    <div
      v-if="loading && !initialized"
      class="min-h-[400px] flex items-center justify-center"
    >
      <div class="flex flex-col items-center gap-4">
        <RefreshCw class="size-10 text-zinc-200 animate-spin" />
        <span class="text-zinc-400 font-medium">� �置同步中...</span>
      </div>
    </div>

    <div v-else-if="formState">
      <div
        v-if="loadError"
        class="mb-6 flex items-start justify-between gap-4 rounded-xl border border-amber-200 bg-amber-50 px-2 py-2 text-sm text-amber-700 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-300"
      >
        <div class="space-y-1">
          <p class="font-bold">
            设置数据未完� �从后端加载，当前� �展示本地� �底� �置
          </p>
          <p>{{ loadError }}</p>
        </div>
        <Button
          variant="outline"
          class="rounded-xl border-amber-300 bg-white text-amber-700 hover:bg-amber-100"
          @click="() => loadSettings(true)"
        >
          重试
        </Button>
      </div>
      <!-- Only render Tabs if system config is actually present to prevent sub-property access errors -->
      <Tabs v-if="formState.system" v-model="activeTab" class="w-full">
        <div
          class="mb-8 rounded-xl border border-zinc-200 bg-white p-1 dark:border-zinc-800 dark:bg-zinc-950"
        >
          <TabsList
            class="flex h-11 w-full gap-1 bg-transparent p-0 border-none"
          >
            <TabsTrigger
              value="general"
              class="h-full flex-1 rounded-lg border bg-white text-sm font-semibold text-zinc-900 transition-colors data-[state=active]:border-zinc-900 data-[state=active]:bg-zinc-900 data-[state=active]:text-white dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:data-[state=active]:border-zinc-100 dark:data-[state=active]:bg-zinc-100 dark:data-[state=active]:text-zinc-950"
            >
              通用� �置
            </TabsTrigger>
            <TabsTrigger
              value="proxy"
              class="h-full flex-1 rounded-lg border bg-white text-sm font-semibold text-zinc-900 transition-colors data-[state=active]:border-zinc-900 data-[state=active]:bg-zinc-900 data-[state=active]:text-white dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:data-[state=active]:border-zinc-100 dark:data-[state=active]:bg-zinc-100 dark:data-[state=active]:text-zinc-950"
            >
              网络代理
            </TabsTrigger>
            <TabsTrigger
              value="chat"
              class="h-full flex-1 rounded-lg border bg-white text-sm font-semibold text-zinc-900 transition-colors data-[state=active]:border-zinc-900 data-[state=active]:bg-zinc-900 data-[state=active]:text-white dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:data-[state=active]:border-zinc-100 dark:data-[state=active]:bg-zinc-100 dark:data-[state=active]:text-zinc-950"
            >
              模型后端
            </TabsTrigger>
            <TabsTrigger
              value="video"
              class="h-full flex-1 rounded-lg border bg-white text-sm font-semibold text-zinc-900 transition-colors data-[state=active]:border-zinc-900 data-[state=active]:bg-zinc-900 data-[state=active]:text-white dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:data-[state=active]:border-zinc-100 dark:data-[state=active]:bg-zinc-100 dark:data-[state=active]:text-zinc-950"
            >
              视频引擎
            </TabsTrigger>
          </TabsList>
        </div>

        <!-- General Tab -->
        <TabsContent
          value="general"
          class="space-y-6 focus-visible:outline-none"
        >
          <Card
            class="rounded-xl border-zinc-200 bg-white shadow-none dark:border-zinc-800 dark:bg-zinc-950"
          >
            <CardContent class="flex flex-col px-4">
              <div class="flex flex-col gap-6">
                <!-- Icon -->
                <div class="space-y-3">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >平台图标</label
                  >
                  <div class="flex items-center gap-5">
                    <button
                      type="button"
                      class="group relative flex h-20 w-20 items-center justify-center overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-50 transition-colors hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900/50 dark:hover:bg-zinc-800"
                      @click="triggerLogoUpload"
                      :disabled="uploadingLogo"
                    >
                      <img
                        v-if="formState.system.logo_url"
                        :src="formState.system.logo_url"
                        class="h-full w-full object-contain p-2"
                      />
                      <ImageIcon
                        v-else
                        class="size-8 text-zinc-300 dark:text-zinc-700"
                      />
                      <div
                        class="absolute inset-0 flex items-center justify-center bg-zinc-900/40 opacity-0 transition-opacity group-hover:opacity-100"
                      >
                        <UploadCloud class="size-6 text-white" />
                      </div>
                    </button>
                    <div class="space-y-1.5">
                      <p
                        class="text-sm font-semibold text-zinc-900 dark:text-white"
                      >
                        更换 Logo
                      </p>
                      <p class="text-xs text-zinc-500">
                        建议使用正方形、透明底的纯色或渐变色图标。
                      </p>
                    </div>
                  </div>
                </div>

                <!-- Name -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >平台名称</label
                  >
                  <Input
                    v-model="formState.system.name"
                    placeholder="设置平台名称"
                    class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  />
                </div>

                <!-- Description -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >平台简述</label
                  >
                  <textarea
                    v-model="formState.system.description"
                    placeholder="�
�于该平台的简短描述"
                    class="min-h-[124px] w-full rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm outline-none transition-colors dark:border-zinc-800 dark:bg-zinc-950"
                  />
                </div>
              </div>

              <div
                class="flex items-center justify-between gap-5 pt-4 dark:border-zinc-800"
              >
                <div
                  class="flex items-center gap-1.5 w-fit rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 dark:border-emerald-900/30 dark:bg-emerald-950/50 dark:text-emerald-500"
                >
                  <CheckCircle2 class="size-3.5" />
                  后端服务：Ready
                </div>

                <div class="flex items-center gap-2">
                  <Button
                    @click="testConnection"
                    :disabled="testing || !!savingSection"
                    class="h-8 min-w-8 rounded-md border border-zinc-200 bg-white px-3 text-xs font-medium text-zinc-900 shadow-none duration-200 ease-linear hover:bg-zinc-100 active:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:hover:bg-zinc-800 dark:active:bg-zinc-800"
                    variant="secondary"
                  >
                    {{ testing ? "验证中..." : "深度链路测试" }}
                  </Button>
                  <Button
                    class="h-8 min-w-8 rounded-md border border-zinc-900 bg-zinc-900 px-3 text-xs font-medium text-white shadow-none duration-200 ease-linear hover:bg-zinc-900/90 active:bg-zinc-900/90 dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-zinc-100/90 dark:active:bg-zinc-100/90"
                    :disabled="!canUpdate || !!savingSection || loading"
                    @click="saveSettings('general', '通用�
�置')"
                  >
                    <Save
                      :class="[
                        'mr-1.5 size-3.5',
                        savingSection === 'general' && 'animate-pulse',
                      ]"
                    />
                    {{
                      savingSection === "general" ? "保存中..." : "保存通用�
�置"
                    }}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <!-- Proxy Tab -->
        <TabsContent
          v-if="formState.proxy"
          value="proxy"
          class="space-y-6 focus-visible:outline-none"
        >
          <Card
            class="rounded-xl border-zinc-200 bg-white shadow-none dark:border-zinc-800 dark:bg-zinc-950"
          >
            <CardContent class="flex flex-col px-4">
              <div class="flex flex-col gap-6 pt-4">
                <!-- 是否开启代理 -->
                <div class="space-y-2">
                  <div class="flex items-center justify-between">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >是否开启代理</label
                    >
                    <Switch
                      :checked="formState.proxy.enabled"
                      @update:checked="
                        (val: boolean) => {
                          formState.proxy.enabled = val;
                          if (!val) saveSettings('proxy', '代理�
�局开�
�');
                        }
                      "
                      class="data-[state=checked]:bg-zinc-900 dark:data-[state=checked]:bg-zinc-100"
                    />
                  </div>
                  <p class="text-xs text-zinc-500 ml-1">
                    设置系统级别的网络出口代理链路� �局总开� �。
                  </p>
                </div>

                <div
                  :class="[
                    'flex flex-col gap-6 transition-opacity duration-200',
                    !formState.proxy.enabled
                      ? 'opacity-40 pointer-events-none'
                      : '',
                  ]"
                >
                  <!-- HTTP 代理地址 -->
                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >HTTP 代理地址</label
                    >
                    <Input
                      v-model="proxyHost"
                      placeholder="例如: 127.0.0.1"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                  </div>

                  <!-- HTTP 代理端口 -->
                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >HTTP 代理端口</label
                    >
                    <Input
                      v-model="proxyPort"
                      placeholder="例如: 7890"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                  </div>
                </div>
              </div>

              <!-- 保存按钮 -->
              <div
                :class="[
                  'flex items-center justify-between gap-5 pt-4 mt-6 border-t border-zinc-200 dark:border-zinc-800 transition-opacity duration-200',
                  !formState.proxy.enabled
                    ? 'opacity-40 pointer-events-none'
                    : '',
                ]"
              >
                <div class="space-y-1">
                  <p
                    class="text-sm font-semibold text-zinc-900 dark:text-zinc-100"
                  >
                    保存代理� �置
                  </p>
                  <p class="text-xs text-zinc-500">
                    代理参数修改后只按此按钮局部保存。
                  </p>
                </div>

                <div class="flex items-center gap-2">
                  <Button
                    class="h-8 min-w-8 rounded-md border border-zinc-900 bg-zinc-900 px-3 text-xs font-medium text-white shadow-none duration-200 ease-linear hover:bg-zinc-900/90 active:bg-zinc-900/90 dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-zinc-100/90 dark:active:bg-zinc-100/90"
                    :disabled="!canUpdate || !!savingSection || loading"
                    @click="saveSettings('proxy', '代理配置')"
                  >
                    <Save
                      :class="[
                        'mr-1.5 size-3.5',
                        savingSection === 'proxy' && 'animate-pulse',
                      ]"
                    />
                    {{ savingSection === "proxy" ? "保存中..." : "保存配置" }}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <!-- Chat Tab -->
        <TabsContent
          v-if="formState.analysis"
          value="chat"
          class="space-y-6 focus-visible:outline-none"
        >
          <Card
            class="rounded-xl border-zinc-200 bg-white shadow-none dark:border-zinc-800 dark:bg-zinc-950"
          >
            <CardContent class="flex flex-col px-4">
              <div class="flex flex-col gap-6 pt-4">
                <!-- Selects -->
                <div class="grid gap-4 md:grid-cols-2">
                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >选择平台</label
                    >
                    <select
                      v-model="selectedChatProvider"
                      class="block h-11 w-full rounded-lg border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-900 outline-none shadow-none dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100"
                    >
                      <option
                        v-for="p in formState.analysis.providers"
                        :key="p.provider"
                        :value="p.provider"
                      >
                        {{ p.label }}
                      </option>
                    </select>
                  </div>
                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >默认引擎</label
                    >
                    <select
                      v-model="formState.analysis.default_provider"
                      class="block h-11 w-full rounded-lg border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-900 outline-none shadow-none dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100"
                    >
                      <option
                        v-for="p in formState.analysis.providers"
                        :key="p.provider"
                        :value="p.provider"
                      >
                        {{ p.label }}
                      </option>
                    </select>
                  </div>
                </div>

                <template
                  v-for="provider in formState.analysis.providers"
                  :key="provider.provider"
                >
                  <div
                    v-if="selectedChatProvider === provider.provider"
                    class="flex flex-col gap-6 pt-2"
                  >
                    <!-- Enable Switch -->
                    <div class="space-y-2">
                      <div class="flex items-center justify-between">
                        <label class="text-[12px] font-bold text-zinc-400 ml-1"
                          >启用 {{ provider.label }}</label
                        >
                        <Switch
                          v-model:checked="provider.enabled"
                          class="data-[state=checked]:bg-zinc-900 dark:data-[state=checked]:bg-zinc-100"
                        />
                      </div>
                      <p class="text-xs text-zinc-500 ml-1">
                        开启后该平台接口可在对话与分析工作流中被调度。
                      </p>
                    </div>

                    <div
                      :class="[
                        'flex flex-col gap-6 transition-opacity duration-200',
                        !provider.enabled
                          ? 'opacity-40 pointer-events-none'
                          : '',
                      ]"
                    >
                      <div class="grid gap-6 md:grid-cols-2">
                        <div class="space-y-2">
                          <label
                            class="text-[12px] font-bold text-zinc-400 ml-1"
                            >API Base Endpoint</label
                          >
                          <Input
                            v-model="provider.base_url"
                            class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                          />
                        </div>
                        <div class="space-y-2">
                          <label
                            class="text-[12px] font-bold text-zinc-400 ml-1"
                            >Preferred Model</label
                          >
                          <Input
                            v-model="provider.default_model"
                            class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                          />
                        </div>
                      </div>

                      <div class="space-y-2">
                        <label class="text-[12px] font-bold text-zinc-400 ml-1"
                          >Secret Authentication Key</label
                        >
                        <Input
                          v-model="provider.api_key"
                          type="password"
                          class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                        />
                      </div>
                      <div class="space-y-2">
                        <label class="text-[12px] font-bold text-zinc-400 ml-1"
                          >Model Availability Pool</label
                        >
                        <textarea
                          :value="getModelOptionsText(provider)"
                          @input="handleModelOptionsInput(provider, $event)"
                          class="min-h-[100px] w-full rounded-lg border border-zinc-200 bg-white px-4 py-3 font-mono text-sm outline-none transition-colors dark:border-zinc-800 dark:bg-zinc-950"
                        />
                      </div>
                    </div>
                  </div>
                </template>
              </div>

              <!-- Footer Buttons -->
              <div
                class="flex items-center justify-between gap-5 pt-4 dark:border-zinc-800"
              >
                <div
                  class="flex items-center gap-1.5 w-fit rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 dark:border-emerald-900/30 dark:bg-emerald-950/50 dark:text-emerald-500"
                >
                  <CheckCircle2 class="size-3.5" />
                  后端服务：Ready
                </div>

                <div class="flex items-center gap-2">
                  <Button
                    class="h-8 min-w-8 rounded-md border border-zinc-900 bg-zinc-900 px-3 text-xs font-medium text-white shadow-none duration-200 ease-linear hover:bg-zinc-900/90 active:bg-zinc-900/90 dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-zinc-100/90 dark:active:bg-zinc-100/90"
                    :disabled="!canUpdate || !!savingSection || loading"
                    @click="saveSettings('chat', '模型后端配置')"
                  >
                    <Save
                      :class="[
                        'mr-1.5 size-3.5',
                        savingSection === 'chat' && 'animate-pulse',
                      ]"
                    />
                    {{
                      savingSection === "chat" ? "保存中..." : "保存模型配置"
                    }}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <!-- Video Tab -->
        <TabsContent
          v-if="formState.remake"
          value="video"
          class="space-y-6 focus-visible:outline-none"
        >
          <Card
            class="rounded-xl border-zinc-200 bg-white shadow-none dark:border-zinc-800 dark:bg-zinc-950"
          >
            <CardContent class="flex flex-col px-4">
              <div class="flex flex-col gap-6 pt-4">
                <!-- Selects -->
                <div class="grid gap-4 md:grid-cols-2">
                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >选择平台</label
                    >
                    <select
                      v-model="selectedVideoProvider"
                      class="block h-11 w-full rounded-lg border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-900 outline-none shadow-none dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100"
                    >
                      <option
                        v-for="p in formState.remake.providers"
                        :key="p.provider"
                        :value="p.provider"
                      >
                        {{ p.label }}
                      </option>
                    </select>
                  </div>
                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >活动引擎</label
                    >
                    <select
                      v-model="formState.remake.default_provider"
                      class="block h-11 w-full rounded-lg border border-zinc-200 bg-white px-4 text-sm font-semibold text-zinc-900 outline-none shadow-none dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100"
                    >
                      <option
                        v-for="p in formState.remake.providers"
                        :key="p.provider"
                        :value="p.provider"
                      >
                        {{ p.label }}
                      </option>
                    </select>
                  </div>
                </div>

                <template
                  v-for="provider in formState.remake.providers"
                  :key="provider.provider"
                >
                  <div
                    v-if="selectedVideoProvider === provider.provider"
                    class="flex flex-col gap-6 pt-2"
                  >
                    <!-- Enable Switch -->
                    <div class="space-y-2">
                      <div class="flex items-center justify-between">
                        <label class="text-[12px] font-bold text-zinc-400 ml-1"
                          >启用 {{ provider.label }}</label
                        >
                        <Switch
                          v-model:checked="provider.enabled"
                          class="data-[state=checked]:bg-zinc-900 dark:data-[state=checked]:bg-zinc-100"
                        />
                      </div>
                      <p class="text-xs text-zinc-500 ml-1">
                        开启后该平台接口可在视频生成工作流中被调度。
                      </p>
                    </div>

                    <div
                      :class="[
                        'flex flex-col gap-6 transition-opacity duration-200',
                        !provider.enabled
                          ? 'opacity-40 pointer-events-none'
                          : '',
                      ]"
                    >
                      <div class="grid gap-6 md:grid-cols-2">
                        <div class="space-y-2">
                          <label
                            class="text-[12px] font-bold text-zinc-400 ml-1"
                            >Endpoint URL</label
                          >
                          <Input
                            v-model="provider.base_url"
                            class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                          />
                        </div>
                        <div class="space-y-2">
                          <label
                            class="text-[12px] font-bold text-zinc-400 ml-1"
                            >Engine Version</label
                          >
                          <Input
                            v-model="provider.default_model"
                            class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                          />
                        </div>
                      </div>

                      <div class="space-y-2">
                        <label class="text-[12px] font-bold text-zinc-400 ml-1"
                          >Authentication Credentials</label
                        >
                        <Input
                          v-model="provider.api_key"
                          type="password"
                          class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                        />
                      </div>
                      <div class="space-y-2">
                        <label class="text-[12px] font-bold text-zinc-400 ml-1"
                          >Capability Matrix (Models)</label
                        >
                        <textarea
                          :value="getModelOptionsText(provider)"
                          @input="handleModelOptionsInput(provider, $event)"
                          class="min-h-[100px] w-full rounded-lg border border-zinc-200 bg-white px-4 py-3 font-mono text-sm outline-none transition-colors dark:border-zinc-800 dark:bg-zinc-950"
                        />
                      </div>
                    </div>
                  </div>
                </template>
              </div>

              <!-- Footer Buttons -->
              <div
                class="flex items-center justify-between gap-5 pt-4 dark:border-zinc-800"
              >
                <div
                  class="flex items-center gap-1.5 w-fit rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 dark:border-emerald-900/30 dark:bg-emerald-950/50 dark:text-emerald-500"
                >
                  <CheckCircle2 class="size-3.5" />
                  后端服务：Ready
                </div>

                <div class="flex items-center gap-2">
                  <Button
                    class="h-8 min-w-8 rounded-md border border-zinc-900 bg-zinc-900 px-3 text-xs font-medium text-white shadow-none duration-200 ease-linear hover:bg-zinc-900/90 active:bg-zinc-900/90 dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-zinc-100/90 dark:active:bg-zinc-100/90"
                    :disabled="!canUpdate || !!savingSection || loading"
                    @click="saveSettings('video', '视频引擎配置')"
                  >
                    <Save
                      :class="[
                        'mr-1.5 size-3.5',
                        savingSection === 'video' && 'animate-pulse',
                      ]"
                    />
                    {{
                      savingSection === "video" ? "保存中..." : "保存视频配置"
                    }}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>

    <!-- Error State View -->
    <div
      v-if="loadError && !loading && !formState"
      class="flex flex-col items-center justify-center p-16 space-y-6 bg-red-500/5 rounded-[40px] border border-red-500/10"
    >
      <div
        class="size-16 rounded-full bg-red-500/10 flex items-center justify-center"
      >
        <Activity class="size-8 text-red-500" />
      </div>
      <div class="text-center">
        <h3 class="text-lg font-bold text-zinc-900 dark:text-white">
          配置加载异常
        </h3>
        <p class="text-sm text-red-500/80 mt-1 max-w-sm">{{ loadError }}</p>
      </div>
      <Button
        @click="() => loadSettings()"
        variant="outline"
        class="rounded-2xl h-11 px-10 font-bold border-red-200 hover:bg-red-50 text-red-600"
      >
        重新初始化配置
      </Button>
    </div>
  </div>
</template>

<style scoped>
/* Remove focus outline for a cleaner look */
div[role="tabpanel"] {
  @apply outline-none;
}

select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%23ccc'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.75rem center;
  background-size: 0.9rem;
  padding-right: 2.25rem;
}
</style>
