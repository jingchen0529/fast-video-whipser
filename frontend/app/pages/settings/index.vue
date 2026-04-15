<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  RefreshCw,
  Save,
  UploadCloud,
  CheckCircle2,
  Activity,
  Image as ImageIcon,
  Cpu,
  Cloud,
  Eye,
  EyeOff,
} from "lucide-vue-next";
import { toast } from "vue-sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { notifyError, formatDateTime } from "@/utils/common";
import type {
  MotionExtractionSettings,
  SystemSettingsPayload,
  SystemSettingsProviderConfig,
  TranscriptionCapabilitiesPayload,
} from "@/types/api";

definePageMeta({
  middleware: "auth",
  layout: "console",
});

const api = useApi();
const auth = useAuth();
const runtimeConfig = useRuntimeConfig();

const loading = ref(false);
const savingSection = ref<
  "general" | "proxy" | "chat" | "transcription" | "video" | "motion" | null
>(null);
const testing = ref(false);
const loadError = ref("");
const lastSavedAt = ref<string | null>(null);
const activeTab = ref("general");
const initialized = ref(false);
const showChatApiKey = ref(false);
const showTranscriptionApiKey = ref(false);
const showVideoApiKey = ref(false);

const createProviderConfig = (
  overrides: Partial<SystemSettingsProviderConfig> &
    Pick<SystemSettingsProviderConfig, "provider" | "label">,
): SystemSettingsProviderConfig => ({
  provider: overrides.provider,
  label: overrides.label,
  enabled: overrides.enabled ?? false,
  base_url: overrides.base_url ?? "",
  api_key: overrides.api_key ?? "",
  default_model: overrides.default_model ?? "",
  model_options: overrides.model_options ?? [],
  model_dir: overrides.model_dir ?? "",
  device: overrides.device ?? "auto",
  compute_type: overrides.compute_type ?? "auto",
  language: overrides.language ?? "",
  prompt: overrides.prompt ?? "",
  beam_size: overrides.beam_size ?? 5,
  vad_filter: overrides.vad_filter ?? true,
});

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
      createProviderConfig({
        provider: "openai",
        label: "OpenAI",
        enabled: true,
        base_url: "https://api.openai.com/v1",
        api_key: "",
        default_model: "gpt-4.1",
        model_options: ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
      }),
      createProviderConfig({
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
      }),
      createProviderConfig({
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
      }),
      createProviderConfig({
        provider: "kimi",
        label: "Kimi",
        enabled: false,
        base_url: "https://api.moonshot.cn/v1",
        api_key: "",
        default_model: "kimi-k2",
        model_options: ["kimi-k2", "kimi-thinking", "moonshot-v1-128k"],
      }),
      createProviderConfig({
        provider: "qwen",
        label: "千问",
        enabled: false,
        base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key: "",
        default_model: "qwen-plus",
        model_options: ["qwen-max", "qwen-plus", "qwen-turbo"],
      }),
      createProviderConfig({
        provider: "deepseek",
        label: "DeepSeek",
        enabled: false,
        base_url: "https://api.deepseek.com/v1",
        api_key: "",
        default_model: "deepseek-chat",
        model_options: ["deepseek-chat", "deepseek-reasoner"],
      }),
      createProviderConfig({
        provider: "custom",
        label: "自定义兼容服务",
        enabled: false,
        base_url: "",
        api_key: "",
        default_model: "custom-model",
        model_options: ["custom-model"],
      }),
    ],
  },
  transcription: {
    default_provider: "faster_whisper",
    providers: [
      createProviderConfig({
        provider: "faster_whisper",
        label: "本地 faster-whisper",
        enabled: true,
        base_url: "",
        api_key: "",
        default_model: "small",
        model_options: [
          "tiny",
          "base",
          "small",
          "medium",
          "large-v3",
          "large-v3-turbo",
        ],
        model_dir: "./models/faster-whisper",
        device: "auto",
        compute_type: "auto",
        language: "",
        prompt: "",
        beam_size: 5,
        vad_filter: true,
      }),
      createProviderConfig({
        provider: "openai_whisper_api",
        label: "OpenAI Whisper API",
        enabled: false,
        base_url: "https://api.openai.com/v1",
        api_key: "",
        default_model: "whisper-1",
        model_options: [
          "whisper-1",
          "gpt-4o-mini-transcribe",
          "gpt-4o-transcribe",
        ],
        model_dir: "",
        device: "server",
        compute_type: "server",
        language: "",
        prompt: "",
        beam_size: 5,
        vad_filter: true,
      }),
    ],
  },
  remake: {
    default_provider: "doubao",
    providers: [
      createProviderConfig({
        provider: "doubao",
        label: "豆包",
        enabled: true,
        base_url: "",
        api_key: "",
        default_model: "seedance-pro",
        model_options: ["seedance-pro", "seedance-lite"],
      }),
      createProviderConfig({
        provider: "kling",
        label: "可灵",
        enabled: false,
        base_url: "https://api-beijing.klingai.com",
        api_key: "",
        default_model: "kling-v3",
        model_options: ["kling-v3", "kling-v3-omni", "kling-video-o1", "kling-v2-6"],
      }),
      createProviderConfig({
        provider: "veo",
        label: "Veo",
        enabled: false,
        base_url: "",
        api_key: "",
        default_model: "veo-3.0-generate-001",
        model_options: [
          "veo-3.0-generate-001",
          "veo-3.0-fast-generate-001",
          "veo-3.1-generate-001",
          "veo-3.1-fast-generate-001",
          "veo-2.0-generate-001",
        ],
      }),
      createProviderConfig({
        provider: "wanxiang",
        label: "万相",
        enabled: false,
        base_url: "",
        api_key: "",
        default_model: "wanx-video",
        model_options: ["wanx-video", "wanx-image-to-video"],
      }),
      createProviderConfig({
        provider: "custom",
        label: "自定义视频模型",
        enabled: false,
        base_url: "",
        api_key: "",
        default_model: "custom-video-model",
        model_options: ["custom-video-model"],
      }),
    ],
  },
  motion_extraction: {
    coarse_filter_mode: "keyword",
    min_duration_ms: 800,
    max_duration_ms: 15000,
    signal_score_threshold: 3,
    confidence_threshold: 0.6,
    default_provider: "openai",
    providers: [
      createProviderConfig({
        provider: "openai",
        label: "OpenAI",
        enabled: true,
        base_url: "https://api.openai.com/v1",
        api_key: "",
        default_model: "gpt-4.1-mini",
        model_options: ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"],
      }),
      createProviderConfig({
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
      }),
      createProviderConfig({
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
        ],
      }),
      createProviderConfig({
        provider: "deepseek",
        label: "DeepSeek",
        enabled: false,
        base_url: "https://api.deepseek.com/v1",
        api_key: "",
        default_model: "deepseek-chat",
        model_options: ["deepseek-chat", "deepseek-reasoner"],
      }),
      createProviderConfig({
        provider: "custom",
        label: "自定义兼容服务",
        enabled: false,
        base_url: "",
        api_key: "",
        default_model: "custom-model",
        model_options: ["custom-model"],
      }),
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

type ProviderGroupKey = "analysis" | "transcription" | "remake";
type ProviderBooleanField = "enabled" | "vad_filter";

const ensureDefaultProviderEnabled = (
  payload: SystemSettingsPayload,
  groupKey: ProviderGroupKey,
) => {
  const group = payload[groupKey];
  const defaultProviderKey = group?.default_provider;
  if (!group || !defaultProviderKey) return;

  const target = group.providers.find(
    (provider) => provider.provider === defaultProviderKey,
  );
  if (target) {
    target.enabled = true;
  }
};

const mergeMotionExtractionSettings = (
  defaults: MotionExtractionSettings,
  incoming?: Partial<MotionExtractionSettings> | null,
): MotionExtractionSettings => {
  const providerGroup = mergeProviderGroup(
    { default_provider: defaults.default_provider, providers: defaults.providers },
    incoming ? { default_provider: incoming.default_provider, providers: incoming.providers } : null,
  );
  return {
    coarse_filter_mode: incoming?.coarse_filter_mode || defaults.coarse_filter_mode,
    min_duration_ms: incoming?.min_duration_ms ?? defaults.min_duration_ms,
    max_duration_ms: incoming?.max_duration_ms ?? defaults.max_duration_ms,
    signal_score_threshold: incoming?.signal_score_threshold ?? defaults.signal_score_threshold,
    confidence_threshold: incoming?.confidence_threshold ?? defaults.confidence_threshold,
    ...providerGroup,
  };
};

const normalizeSettingsPayload = (
  payload?: Partial<SystemSettingsPayload> | null,
): SystemSettingsPayload => {
  const defaults = createDefaultSettingsState();
  const result: SystemSettingsPayload = {
    system: {
      ...defaults.system,
      ...(payload?.system || {}),
    },
    proxy: {
      ...defaults.proxy,
      ...(payload?.proxy || {}),
    },
    analysis: mergeProviderGroup(defaults.analysis, payload?.analysis),
    transcription: mergeProviderGroup(
      defaults.transcription,
      payload?.transcription,
    ),
    remake: mergeProviderGroup(defaults.remake, payload?.remake),
    motion_extraction: mergeMotionExtractionSettings(
      defaults.motion_extraction,
      payload?.motion_extraction,
    ),
  };

  // 强制启用所有默认 provider，避免数据库中残留的 enabled=false 导致功能不可用
  ensureDefaultProviderEnabled(result, "analysis");
  ensureDefaultProviderEnabled(result, "transcription");
  ensureDefaultProviderEnabled(result, "remake");

  return result;
};

const formState = ref<SystemSettingsPayload>(createDefaultSettingsState());

const selectedChatProvider = ref<string>("openai");
const selectedTranscriptionProvider = ref<string>("faster_whisper");
const selectedVideoProvider = ref<string>("doubao");
const selectedMotionProvider = ref<string>("openai");
const showMotionApiKey = ref(false);
const transcriptionCapabilities = ref<TranscriptionCapabilitiesPayload | null>(
  null,
);
const transcriptionCapabilitiesLoading = ref(false);
const transcriptionCapabilitiesError = ref("");
const transcriptionCapabilitiesAvailable = ref<boolean | null>(null);

const currentChatProvider = computed(
  () =>
    formState.value.analysis?.providers?.find(
      (p) => p.provider === selectedChatProvider.value,
    ) || null,
);

const selectedDefaultChatProvider = computed({
  get: () =>
    formState.value.analysis?.default_provider ||
    selectedChatProvider.value ||
    "openai",
  set: (provider: string) => {
    if (!formState.value.analysis) return;
    formState.value.analysis.default_provider = provider;
    selectedChatProvider.value = provider;
    updateProviderBooleanField("analysis", provider, "enabled", true);
  },
});

const currentTranscriptionProvider = computed(
  () =>
    formState.value.transcription?.providers?.find(
      (p) => p.provider === selectedTranscriptionProvider.value,
    ) || null,
);

const currentVideoProvider = computed(
  () =>
    formState.value.remake?.providers?.find(
      (p) => p.provider === selectedVideoProvider.value,
    ) || null,
);

const currentMotionProvider = computed(
  () =>
    formState.value.motion_extraction?.providers?.find(
      (p) => p.provider === selectedMotionProvider.value,
    ) || null,
);

const selectedDefaultMotionProvider = computed({
  get: () =>
    formState.value.motion_extraction?.default_provider ||
    selectedMotionProvider.value ||
    "openai",
  set: (provider: string) => {
    if (!formState.value.motion_extraction) return;
    formState.value.motion_extraction.default_provider = provider;
    selectedMotionProvider.value = provider;
    const target = formState.value.motion_extraction.providers.find(
      (p) => p.provider === provider,
    );
    if (target) target.enabled = true;
  },
});

const videoBaseUrlPlaceholder = computed(() => {
  switch (currentVideoProvider.value?.provider) {
    case "doubao":
      return "留空则使用默认地址；若走方舟请填 https://ark.cn-beijing.volces.com/api/v3";
    case "kling":
      return "默认可用北京域名，海外可改为新加坡域名";
    case "veo":
      return "填写完整 Vertex AI publisher model endpoint";
    default:
      return "填写接口地址";
  }
});

const videoBaseUrlHint = computed(() => {
  switch (currentVideoProvider.value?.provider) {
    case "doubao":
      return "豆包默认走 https://operator.las.cn-beijing.volces.com。若使用方舟/ARK，请只填写 https://ark.cn-beijing.volces.com/api/v3";
    case "kling":
      return "可灵默认走 https://api-beijing.klingai.com，若你的服务部署在海外，请改成官方海外域名。";
    case "veo":
      return "Veo 需要完整的 publisher model endpoint，后端会自动拼接 :predictLongRunning 和 :fetchPredictOperation。";
    default:
      return "";
  }
});

const videoApiKeyPlaceholder = computed(() => {
  switch (currentVideoProvider.value?.provider) {
    case "kling":
      return "填写 Bearer Token，或 AccessKey:SecretKey";
    case "veo":
      return "填写 Google Cloud OAuth Bearer Token";
    default:
      return "填写密钥";
  }
});

const videoApiKeyHint = computed(() => {
  switch (currentVideoProvider.value?.provider) {
    case "kling":
      return "可灵支持直接填短期 Bearer Token，也支持填 AccessKey:SecretKey 由后端临时生成 JWT。";
    case "veo":
      return "Veo 使用 Google Cloud OAuth 令牌；如果不指定 output_storage_uri，后端会优先接收内联 bytes 结果并直接入库。";
    default:
      return "";
  }
});

const currentTranscriptionCapability = computed(() => {
  if (!transcriptionCapabilities.value) return null;
  return (
    transcriptionCapabilities.value.providers?.[
      selectedTranscriptionProvider.value as keyof TranscriptionCapabilitiesPayload["providers"]
    ] || null
  );
});

const updateProviderBooleanField = (
  groupKey: ProviderGroupKey,
  providerKey: string,
  field: ProviderBooleanField,
  checked: boolean,
) => {
  const group = formState.value[groupKey];
  const target = group?.providers?.find(
    (provider) => provider.provider === providerKey,
  );
  if (!target) return;
  target[field] = checked;
};

const currentTranscriptionIssues = computed(() => {
  const issues = currentTranscriptionCapability.value?.issues;
  return Array.isArray(issues) ? issues : [];
});

const fasterWhisperCapability = computed(
  () => transcriptionCapabilities.value?.providers?.faster_whisper || null,
);

const openAIWhisperCapability = computed(
  () => transcriptionCapabilities.value?.providers?.openai_whisper_api || null,
);

const pickExistingProvider = (
  providers: SystemSettingsPayload["analysis"]["providers"] | undefined,
  preferred: string | null | undefined,
  fallback: string,
) => {
  if (!Array.isArray(providers) || !providers.length) return fallback;
  if (preferred && providers.some((item) => item.provider === preferred)) {
    return preferred;
  }
  return providers[0]?.provider || fallback;
};

const syncSelectedProviders = (
  mode: "current-first" | "default-first" = "current-first",
) => {
  const preferredChatProvider =
    mode === "default-first"
      ? formState.value.analysis?.default_provider || selectedChatProvider.value
      : selectedChatProvider.value ||
        formState.value.analysis?.default_provider;
  const preferredTranscriptionProvider =
    mode === "default-first"
      ? formState.value.transcription?.default_provider ||
        selectedTranscriptionProvider.value
      : selectedTranscriptionProvider.value ||
        formState.value.transcription?.default_provider;
  const preferredVideoProvider =
    mode === "default-first"
      ? formState.value.remake?.default_provider || selectedVideoProvider.value
      : selectedVideoProvider.value || formState.value.remake?.default_provider;

  selectedChatProvider.value = pickExistingProvider(
    formState.value.analysis?.providers,
    preferredChatProvider,
    "openai",
  );
  selectedTranscriptionProvider.value = pickExistingProvider(
    formState.value.transcription?.providers,
    preferredTranscriptionProvider,
    "faster_whisper",
  );
  selectedVideoProvider.value = pickExistingProvider(
    formState.value.remake?.providers,
    preferredVideoProvider,
    "doubao",
  );

  const preferredMotionProvider =
    mode === "default-first"
      ? formState.value.motion_extraction?.default_provider || selectedMotionProvider.value
      : selectedMotionProvider.value || formState.value.motion_extraction?.default_provider;
  selectedMotionProvider.value = pickExistingProvider(
    formState.value.motion_extraction?.providers,
    preferredMotionProvider,
    "openai",
  );
};

const isAbsoluteAssetUrl = (value: string) =>
  /^(https?:)?\/\//.test(value) ||
  value.startsWith("data:") ||
  value.startsWith("blob:");

const resolveAssetUrl = (rawUrl?: string | null) => {
  const normalized = `${rawUrl || ""}`.trim();
  if (!normalized) return "";
  if (isAbsoluteAssetUrl(normalized)) return normalized;

  const apiBase = `${runtimeConfig.public.apiBase || ""}`.trim();
  let origin = "";

  if (import.meta.client) {
    try {
      origin = apiBase
        ? new URL(apiBase, window.location.origin).origin
        : window.location.origin;
    } catch {
      origin = window.location.origin;
    }
  }

  if (!origin) {
    return normalized.startsWith("/") ? normalized : `/${normalized}`;
  }

  try {
    return new URL(normalized, `${origin}/`).toString();
  } catch {
    return normalized.startsWith("/") ? normalized : `/${normalized}`;
  }
};

const resolvedSystemLogoUrl = computed(() =>
  resolveAssetUrl(formState.value.system?.logo_url),
);

const canUpdate = computed(() => {
  const currentUser = auth.user.value;
  if (!currentUser) return false;
  return currentUser.is_superuser;
});

const getProxySourceUrl = () =>
  `${formState.value.proxy?.http_url || formState.value.proxy?.https_url || formState.value.proxy?.all_url || ""}`.trim();

const parseProxyEndpoint = (rawValue: string) => {
  const value = `${rawValue || ""}`.trim();
  if (!value) {
    return {
      host: "",
      port: "",
    };
  }

  const candidate = value.includes("://") ? value : `http://${value}`;

  try {
    const url = new URL(candidate);
    return {
      host: url.hostname,
      port: url.port,
    };
  } catch {
    const withoutProtocol = value.replace(/^[a-z]+:\/\//i, "");
    const [hostPort = ""] = withoutProtocol.split("/");
    const lastColonIndex = hostPort.lastIndexOf(":");

    if (lastColonIndex === -1) {
      return {
        host: hostPort,
        port: "",
      };
    }

    return {
      host: hostPort.slice(0, lastColonIndex),
      port: hostPort.slice(lastColonIndex + 1),
    };
  }
};

const updateProxyEndpoint = (host: string, port: string) => {
  const normalizedHost = host.trim();
  const normalizedPort = port.trim();
  const endpoint = normalizedHost
    ? `http://${normalizedHost}${normalizedPort ? `:${normalizedPort}` : ""}`
    : "";

  formState.value.proxy.http_url = endpoint;
  formState.value.proxy.https_url = endpoint;
  formState.value.proxy.all_url = "";
};

const proxyHost = computed({
  get: () => parseProxyEndpoint(getProxySourceUrl()).host,
  set: (value: string) => {
    updateProxyEndpoint(value, proxyPort.value);
  },
});

const proxyPort = computed({
  get: () => parseProxyEndpoint(getProxySourceUrl()).port,
  set: (value: string) => {
    updateProxyEndpoint(proxyHost.value, value);
  },
});

const proxyEnabled = computed(() => Boolean(formState.value.proxy?.enabled));
const proxyInputsDisabled = computed(
  () => !proxyEnabled.value || Boolean(savingSection.value) || loading.value,
);

const handleProxyEnabledChange = (checked: boolean) => {
  const enabled = checked === true;
  formState.value.proxy.enabled = enabled;

  if (!enabled) {
    void saveSettings("proxy", "代理全局开关");
  }
};

const normalizeLoadErrorMessage = (error: unknown) => {
  const message = api.normalizeError(error);
  if (message.includes("settings.view")) {
    return "当前账号无法访问系统设置，请使用管理员账号登录后查看。";
  }
  if (message.includes("Method Not Allowed")) {
    return "当前后端还不支持该设置接口的探测请求，请重启后端后再试。";
  }
  if (message.includes("Not Found")) {
    return "当前后端进程还没有加载系统设置接口，请重启后端服务后再试。";
  }
  return message;
};

const normalizeTranscriptionCapabilitiesErrorMessage = (error: unknown) => {
  const message = api.normalizeError(error);
  if (message.includes("Method Not Allowed")) {
    return "当前后端还不支持转写能力检测接口，请重启后端后再试。";
  }
  if (message.includes("Not Found") || message.includes("404")) {
    return "当前后端进程还没有加载转写能力检测接口，请重启后端服务后再试。";
  }
  return message;
};

const isValidHttpBaseUrl = (value: string) =>
  /^https?:\/\//i.test((value || "").trim());

const validateProviderBaseUrls = (payload: SystemSettingsPayload) => {
  const groups: Array<{
    key: ProviderGroupKey;
    label: string;
  }> = [
    { key: "analysis", label: "模型后端" },
    { key: "transcription", label: "Whisper 配置" },
    { key: "remake", label: "视频引擎配置" },
  ];

  for (const group of groups) {
    const providerGroup = payload[group.key];
    for (const provider of providerGroup.providers) {
      const baseUrl = (provider.base_url || "").trim();
      if (!baseUrl) continue;
      if (isValidHttpBaseUrl(baseUrl)) continue;

      const suffix =
        group.key === "remake"
          ? "这里填写的是接口地址，不是模型名。"
          : "请输入完整接口地址。";
      throw new Error(
        `${group.label} / ${provider.label} 的 API Base Endpoint 必须以 http:// 或 https:// 开头。${suffix}`,
      );
    }
  }

  // Also validate motion_extraction providers
  for (const provider of payload.motion_extraction?.providers || []) {
    const baseUrl = (provider.base_url || "").trim();
    if (!baseUrl) continue;
    if (isValidHttpBaseUrl(baseUrl)) continue;
    throw new Error(
      `动作提取 / ${provider.label} 的 API Base Endpoint 必须以 http:// 或 https:// 开头。请输入完整接口地址。`,
    );
  }
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

const refreshTranscriptionCapabilities = async (manual = false) => {
  transcriptionCapabilitiesLoading.value = true;
  transcriptionCapabilitiesError.value = "";
  try {
    const data = await api.post<TranscriptionCapabilitiesPayload>(
      "/settings/transcription/capabilities",
      normalizeSettingsPayload(JSON.parse(JSON.stringify(formState.value))),
    );
    transcriptionCapabilities.value = data;
    transcriptionCapabilitiesAvailable.value = true;
    if (manual) {
      toast.success("本地转写能力已刷新");
    }
  } catch (error) {
    transcriptionCapabilitiesAvailable.value = false;
    transcriptionCapabilitiesError.value =
      normalizeTranscriptionCapabilitiesErrorMessage(error);
    if (manual) {
      notifyError(api, error, "刷新转写能力失败");
    }
  } finally {
    transcriptionCapabilitiesLoading.value = false;
  }
};

const loadSettings = async (manual = false) => {
  loading.value = true;
  loadError.value = "";
  try {
    const data = await api.get<SystemSettingsPayload>("/settings");
    formState.value = normalizeSettingsPayload(data);
    syncSelectedProviders("default-first");
    lastSavedAt.value = new Date().toISOString();
    initialized.value = true;
    if (manual) toast.success("设置已刷新");
  } catch (error) {
    loadError.value = normalizeLoadErrorMessage(error);
    formState.value = normalizeSettingsPayload(formState.value);
    syncSelectedProviders();
    initialized.value = true;
    notifyError(api, error, "无法加载系统设置");
  } finally {
    loading.value = false;
  }
};

const saveSettings = async (
  section: "general" | "proxy" | "chat" | "transcription" | "video" | "motion",
  label: string,
) => {
  if (!formState.value || !canUpdate.value || savingSection.value) return;

  savingSection.value = section;
  try {
    const payload = normalizeSettingsPayload(
      JSON.parse(JSON.stringify(formState.value)),
    );
    validateProviderBaseUrls(payload);
    if (section === "chat") {
      ensureDefaultProviderEnabled(payload, "analysis");
    }
    if (section === "transcription") {
      ensureDefaultProviderEnabled(payload, "transcription");
    }
    if (section === "video") {
      ensureDefaultProviderEnabled(payload, "remake");
    }
    if (section === "motion") {
      const me = payload.motion_extraction;
      const dp = me?.default_provider;
      if (me && dp) {
        const target = me.providers.find((p) => p.provider === dp);
        if (target) target.enabled = true;
      }
    }

    const data = await api.patch<SystemSettingsPayload>("/settings", payload);
    formState.value = normalizeSettingsPayload(data);
    syncSelectedProviders();
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
    const res = await api.post<{ stored_name: string; file_url?: string }>(
      "/common/upload",
      formData,
    );
    if (formState.value.system) {
      formState.value.system.logo_url =
        res.file_url || `/uploads/common/${res.stored_name}`;
    }
    toast.success("Logo 上传成功，记得保存通用设置");
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
        <span class="text-zinc-400 font-medium">设置同步中...</span>
      </div>
    </div>

    <div v-else-if="formState">
      <div
        v-if="loadError"
        class="mb-6 flex items-start justify-between gap-4 rounded-xl border border-amber-200 bg-amber-50 px-2 py-2 text-sm text-amber-700 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-300"
      >
        <div class="space-y-1">
          <p class="font-bold">
            设置数据未能从后端加载，当前仅展示本地兜底配置
          </p>
          <p>{{ loadError }}</p>
        </div>
        <Button
          variant="outline"
          class="rounded-xl border-amber-300 bg-white text-amber-700 hover:bg-amber-100"
          @click="loadSettings(true)"
        >
          重试
        </Button>
      </div>
      <!-- Only render Tabs if system config is actually present to prevent sub-property access errors -->
      <Tabs v-if="formState.system" v-model="activeTab" class="w-full">
        <div
          class="mb-8 rounded-lg border border-zinc-200 bg-zinc-50/80 p-0.5 dark:border-zinc-800 dark:bg-zinc-900/60"
        >
          <TabsList
            class="flex h-9 w-full gap-0.5 bg-transparent p-0 border-none"
          >
            <TabsTrigger
              value="general"
              class="h-full flex-1 rounded-md border border-transparent bg-transparent px-3 text-[13px] font-medium text-zinc-600 transition-colors hover:text-zinc-900 data-[state=active]:border-zinc-900 data-[state=active]:bg-zinc-900 data-[state=active]:text-white dark:text-zinc-400 dark:hover:text-zinc-100 dark:data-[state=active]:border-zinc-900 dark:data-[state=active]:bg-zinc-900 dark:data-[state=active]:text-white"
            >
              通用设置
            </TabsTrigger>
            <TabsTrigger
              value="proxy"
              class="h-full flex-1 rounded-md border border-transparent bg-transparent px-3 text-[13px] font-medium text-zinc-600 transition-colors hover:text-zinc-900 data-[state=active]:border-zinc-900 data-[state=active]:bg-zinc-900 data-[state=active]:text-white dark:text-zinc-400 dark:hover:text-zinc-100 dark:data-[state=active]:border-zinc-900 dark:data-[state=active]:bg-zinc-900 dark:data-[state=active]:text-white"
            >
              网络代理
            </TabsTrigger>
            <TabsTrigger
              value="chat"
              class="h-full flex-1 rounded-md border border-transparent bg-transparent px-3 text-[13px] font-medium text-zinc-600 transition-colors hover:text-zinc-900 data-[state=active]:border-zinc-900 data-[state=active]:bg-zinc-900 data-[state=active]:text-white dark:text-zinc-400 dark:hover:text-zinc-100 dark:data-[state=active]:border-zinc-900 dark:data-[state=active]:bg-zinc-900 dark:data-[state=active]:text-white"
            >
              对话模型
            </TabsTrigger>
            <TabsTrigger
              value="transcription"
              class="h-full flex-1 rounded-md border border-transparent bg-transparent px-3 text-[13px] font-medium text-zinc-600 transition-colors hover:text-zinc-900 data-[state=active]:border-zinc-900 data-[state=active]:bg-zinc-900 data-[state=active]:text-white dark:text-zinc-400 dark:hover:text-zinc-100 dark:data-[state=active]:border-zinc-900 dark:data-[state=active]:bg-zinc-900 dark:data-[state=active]:text-white"
            >
              Whisper 配置
            </TabsTrigger>
            <TabsTrigger
              value="video"
              class="h-full flex-1 rounded-md border border-transparent bg-transparent px-3 text-[13px] font-medium text-zinc-600 transition-colors hover:text-zinc-900 data-[state=active]:border-zinc-900 data-[state=active]:bg-zinc-900 data-[state=active]:text-white dark:text-zinc-400 dark:hover:text-zinc-100 dark:data-[state=active]:border-zinc-900 dark:data-[state=active]:bg-zinc-900 dark:data-[state=active]:text-white"
            >
              视频模型
            </TabsTrigger>
            <TabsTrigger
              value="motion"
              class="h-full flex-1 rounded-md border border-transparent bg-transparent px-3 text-[13px] font-medium text-zinc-600 transition-colors hover:text-zinc-900 data-[state=active]:border-zinc-900 data-[state=active]:bg-zinc-900 data-[state=active]:text-white dark:text-zinc-400 dark:hover:text-zinc-100 dark:data-[state=active]:border-zinc-900 dark:data-[state=active]:bg-zinc-900 dark:data-[state=active]:text-white"
            >
              动作提取
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
                        v-if="resolvedSystemLogoUrl"
                        :src="resolvedSystemLogoUrl"
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
                      <p class="text-xs text-zinc-400">
                        上传后会先预览，保存通用设置后正式生效。
                      </p>
                    </div>
                  </div>
                  <input
                    ref="fileInputRef"
                    type="file"
                    class="hidden"
                    accept="image/png,image/jpeg,image/webp,image/gif,image/x-icon,image/vnd.microsoft.icon,image/svg+xml"
                    @change="handleLogoFile"
                  />
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
                    placeholder="适用于该平台的简短描述"
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
                    @click="saveSettings('general', '通用设置')"
                  >
                    <Save
                      :class="[
                        'mr-1.5 size-3.5',
                        savingSection === 'general' && 'animate-pulse',
                      ]"
                    />
                    {{
                      savingSection === "general" ? "保存中..." : "保存通用设置"
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
                      :checked="proxyEnabled"
                      @update:checked="handleProxyEnabledChange"
                      class="data-[state=checked]:bg-zinc-900 dark:data-[state=checked]:bg-zinc-100"
                    />
                  </div>
                  <p class="text-xs text-zinc-500 ml-1">
                    设置系统级别的网络出口代理链路全局总开关。
                  </p>
                </div>

                <div
                  :class="[
                    'flex flex-col gap-6 transition-opacity duration-200',
                    !proxyEnabled ? 'opacity-40' : '',
                  ]"
                >
                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >代理 IP</label
                    >
                    <Input
                      v-model="proxyHost"
                      placeholder="例如: 127.0.0.1"
                      :disabled="proxyInputsDisabled"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                  </div>

                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >代理端口</label
                    >
                    <Input
                      v-model="proxyPort"
                      inputmode="numeric"
                      placeholder="例如: 7890"
                      :disabled="proxyInputsDisabled"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                  </div>
                  <p class="text-xs text-zinc-500 ml-1">
                    保存时会自动写入 HTTP 和 HTTPS 代理地址，格式为
                    `http://IP:端口`。
                  </p>
                </div>
              </div>

              <!-- 保存按钮 -->
              <div
                :class="[
                  'flex items-center justify-between gap-5 pt-4 mt-6 border-t border-zinc-200 dark:border-zinc-800 transition-opacity duration-200',
                  !proxyEnabled
                    ? 'opacity-40 pointer-events-none'
                    : '',
                ]"
              >
                <div class="space-y-1">
                  <p
                    class="text-sm font-semibold text-zinc-900 dark:text-zinc-100"
                  >
                    保存代理配置
                  </p>
                  <p class="text-xs text-zinc-500">
                    当前仅需填写代理 IP 和端口。
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
            <CardContent class="flex flex-col gap-6 px-4 pt-4">
              <!-- 选择平台 -->
              <div class="space-y-2">
                <label class="text-[12px] font-bold text-zinc-400 ml-1"
                  >默认 AI 对话模型</label
                >
                <Select v-model="selectedDefaultChatProvider">
                  <SelectTrigger
                    class="h-11 w-full rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  >
                    <SelectValue placeholder="选择默认 AI 对话模型" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem
                      v-for="p in formState.analysis.providers"
                      :key="p.provider"
                      :value="p.provider"
                    >
                      {{ p.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <p class="text-xs text-zinc-500 ml-1">
                  这里切换后，保存配置会直接更新当前生效的 AI 对话模型。
                </p>
              </div>

              <template v-if="currentChatProvider">
                <!-- Model -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >Model</label
                  >
                  <Input
                    v-model="currentChatProvider.default_model"
                    placeholder="填写模型名称，如 gpt-4.1"
                    class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  />
                </div>

                <!-- API Base Endpoint -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >API Base Endpoint</label
                  >
                  <Input
                    v-model="currentChatProvider.base_url"
                    placeholder="填写接口地址，如 https://api.openai.com/v1"
                    class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  />
                </div>

                <!-- API Key -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >API Key</label
                  >
                  <div class="relative">
                    <Input
                      v-model="currentChatProvider.api_key"
                      :type="showChatApiKey ? 'text' : 'password'"
                      placeholder="填写密钥"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 pr-12 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                    <button
                      type="button"
                      class="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200"
                      @click="showChatApiKey = !showChatApiKey"
                    >
                      <EyeOff v-if="showChatApiKey" class="size-4" />
                      <Eye v-else class="size-4" />
                    </button>
                  </div>
                </div>
              </template>

              <!-- Footer -->
              <div
                class="flex items-center justify-end pt-4 border-t border-zinc-200 dark:border-zinc-800"
              >
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
                  {{ savingSection === "chat" ? "保存中..." : "保存模型配置" }}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <!-- Transcription Tab -->
        <TabsContent
          v-if="formState.transcription"
          value="transcription"
          class="space-y-6 focus-visible:outline-none"
        >
          <Card
            class="rounded-xl border-zinc-200 bg-white shadow-none dark:border-zinc-800 dark:bg-zinc-950"
          >
            <CardContent class="flex flex-col gap-6 px-4 pt-4">
              <div
                class="rounded-xl border border-zinc-200 bg-zinc-50/80 p-4 dark:border-zinc-800 dark:bg-zinc-900/60"
              >
                <div class="flex items-start justify-between gap-4">
                  <div class="space-y-1">
                    <p
                      class="text-sm font-semibold text-zinc-900 dark:text-zinc-100"
                    >
                      转写引擎运行时检测
                    </p>
                    <p class="text-xs text-zinc-500">
                      基于当前表单配置预览本地依赖、模型目录和 OpenAI
                      接口可用项。
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    class="h-8 rounded-md px-3 text-xs"
                    :disabled="transcriptionCapabilitiesLoading"
                    @click="refreshTranscriptionCapabilities(true)"
                  >
                    <RefreshCw
                      :class="[
                        'mr-1.5 size-3.5',
                        transcriptionCapabilitiesLoading && 'animate-spin',
                      ]"
                    />
                    {{
                      transcriptionCapabilitiesLoading
                        ? "检测中..."
                        : "刷新检测"
                    }}
                  </Button>
                </div>

                <p
                  v-if="transcriptionCapabilitiesError"
                  class="mt-3 text-xs text-red-500"
                >
                  {{ transcriptionCapabilitiesError }}
                </p>
              </div>

              <div class="space-y-2">
                <label class="text-[12px] font-bold text-zinc-400 ml-1"
                  >默认转写引擎</label
                >
                <Select v-model="formState.transcription.default_provider">
                  <SelectTrigger
                    class="h-11 w-full rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  >
                    <SelectValue placeholder="选择默认转写引擎" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem
                      v-for="p in formState.transcription.providers"
                      :key="p.provider"
                      :value="p.provider"
                    >
                      {{ p.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div class="space-y-2">
                <label class="text-[12px] font-bold text-zinc-400 ml-1"
                  >编辑配置</label
                >
                <Select v-model="selectedTranscriptionProvider">
                  <SelectTrigger
                    class="h-11 w-full rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  >
                    <SelectValue placeholder="选择转写提供方" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem
                      v-for="p in formState.transcription.providers"
                      :key="p.provider"
                      :value="p.provider"
                    >
                      {{ p.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <template v-if="currentTranscriptionProvider">
                <div
                  v-if="currentTranscriptionCapability"
                  class="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950"
                >
                  <div class="flex items-center gap-2">
                    <Cpu
                      v-if="selectedTranscriptionProvider === 'faster_whisper'"
                      class="size-4 text-zinc-500"
                    />
                    <Cloud v-else class="size-4 text-zinc-500" />
                    <p
                      class="text-sm font-semibold text-zinc-900 dark:text-zinc-100"
                    >
                      {{
                        selectedTranscriptionProvider === "faster_whisper"
                          ? "本地能力检测"
                          : "OpenAI 接口检测"
                      }}
                    </p>
                  </div>

                  <div
                    v-if="selectedTranscriptionProvider === 'faster_whisper'"
                    class="mt-4 space-y-4"
                  >
                    <div class="flex flex-wrap gap-2">
                      <span
                        v-for="(
                          dep, depName
                        ) in fasterWhisperCapability?.dependency_status || {}"
                        :key="depName"
                        class="rounded-full px-2.5 py-1 text-[11px] font-medium"
                        :class="
                          dep.installed
                            ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400'
                            : 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-400'
                        "
                      >
                        {{ depName }} · {{ dep.installed ? "已安装" : "缺失" }}
                      </span>
                    </div>

                    <div class="flex flex-wrap gap-2">
                      <span
                        class="rounded-full px-2.5 py-1 text-[11px] font-medium"
                        :class="
                          fasterWhisperCapability?.binary_status?.ffmpeg
                            ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400'
                            : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300'
                        "
                      >
                        ffmpeg ·
                        {{
                          fasterWhisperCapability?.binary_status?.ffmpeg
                            ? "可用"
                            : "未检测到"
                        }}
                      </span>
                      <span
                        class="rounded-full px-2.5 py-1 text-[11px] font-medium"
                        :class="
                          fasterWhisperCapability?.binary_status?.ffprobe
                            ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400'
                            : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300'
                        "
                      >
                        ffprobe ·
                        {{
                          fasterWhisperCapability?.binary_status?.ffprobe
                            ? "可用"
                            : "未检测到"
                        }}
                      </span>
                    </div>

                    <div class="space-y-1">
                      <p class="text-xs font-semibold text-zinc-500">
                        本地模型目录
                      </p>
                      <p
                        class="text-xs text-zinc-600 dark:text-zinc-300 break-all"
                      >
                        {{ fasterWhisperCapability?.model_dir || "未设置" }}
                      </p>
                      <p class="text-xs text-zinc-500">
                        检测到
                        {{
                          fasterWhisperCapability?.local_models?.length || 0
                        }}
                        个本地模型，推荐设备 / 精度：
                        {{
                          fasterWhisperCapability?.recommended_device || "cpu"
                        }}
                        /
                        {{
                          fasterWhisperCapability?.recommended_compute_type ||
                          "int8"
                        }}
                      </p>
                    </div>

                    <div
                      v-if="fasterWhisperCapability?.local_models?.length"
                      class="space-y-2"
                    >
                      <p class="text-xs font-semibold text-zinc-500">
                        已发现本地模型
                      </p>
                      <div class="flex flex-wrap gap-2">
                        <span
                          v-for="model in fasterWhisperCapability?.local_models ||
                          []"
                          :key="model.path"
                          class="rounded-full bg-zinc-100 px-2.5 py-1 text-[11px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                        >
                          {{ model.name }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div v-else class="mt-4 space-y-3">
                    <p class="text-xs text-zinc-500">
                      单文件大小限制约
                      {{
                        openAIWhisperCapability?.file_size_limit_mb
                      }}MB，支持格式：
                      {{
                        openAIWhisperCapability?.supported_formats?.join(", ")
                      }}
                    </p>
                    <div class="flex flex-wrap gap-2">
                      <span
                        v-for="issue in openAIWhisperCapability?.issues || []"
                        :key="issue"
                        class="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] text-amber-700 dark:bg-amber-950/30 dark:text-amber-300"
                      >
                        {{ issue }}
                      </span>
                    </div>
                  </div>

                  <div
                    v-if="currentTranscriptionIssues.length"
                    class="mt-4 space-y-1"
                  >
                    <p class="text-xs font-semibold text-zinc-500">提醒</p>
                    <p
                      v-for="issue in currentTranscriptionIssues"
                      :key="issue"
                      class="text-xs text-zinc-600 dark:text-zinc-300"
                    >
                      {{ issue }}
                    </p>
                  </div>
                </div>

                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >默认模型</label
                  >
                  <Input
                    v-model="currentTranscriptionProvider.default_model"
                    placeholder="例如 whisper-1 / small / large-v3"
                    class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  />
                  <p class="text-xs text-zinc-500 ml-1">
                    {{
                      selectedTranscriptionProvider === "faster_whisper"
                        ? "可填写标准模型名，若本地目录存在同名模型则优先使用本地模型。"
                        : "推荐默认使用 whisper-1；如需兼容新模型，也可以直接手填。"
                    }}
                  </p>
                </div>

                <div
                  v-if="selectedTranscriptionProvider === 'faster_whisper'"
                  class="space-y-6"
                >
                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >本地模型目录</label
                    >
                    <Input
                      v-model="currentTranscriptionProvider.model_dir"
                      placeholder="例如 ./models/faster-whisper"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                  </div>

                    <div class="grid gap-4 md:grid-cols-2">
                      <div class="space-y-2">
                      <label class="text-[12px] font-bold text-zinc-400 ml-1"
                        >运行设备</label
                      >
                      <Select v-model="currentTranscriptionProvider.device">
                        <SelectTrigger
                          class="h-11 w-full rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                        >
                          <SelectValue placeholder="选择设备" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem
                            v-for="device in fasterWhisperCapability?.available_devices || [
                              'auto',
                              'cpu',
                            ]"
                            :key="device"
                            :value="device"
                          >
                            {{ device }}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div class="space-y-2">
                      <label class="text-[12px] font-bold text-zinc-400 ml-1"
                        >计算精度</label
                      >
                      <Select
                        v-model="currentTranscriptionProvider.compute_type"
                      >
                        <SelectTrigger
                          class="h-11 w-full rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                        >
                          <SelectValue placeholder="选择精度" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem
                            v-for="computeType in fasterWhisperCapability?.available_compute_types || [
                              'auto',
                              'default',
                              'int8',
                              'float16',
                            ]"
                            :key="computeType"
                            :value="computeType"
                          >
                            {{ computeType }}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      </div>
                    </div>
                    <p class="text-xs text-zinc-500 ml-1">
                      当前环境推荐使用
                      {{
                        fasterWhisperCapability?.recommended_device || "cpu"
                      }}
                      /
                      {{
                        fasterWhisperCapability?.recommended_compute_type ||
                        "int8"
                      }}。
                      如果之前一直保留 `auto` 或 `default`，运行时也会自动按这个推荐值执行。
                    </p>
                  </div>

                <div v-else class="space-y-6">
                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >API Base Endpoint</label
                    >
                    <Input
                      v-model="currentTranscriptionProvider.base_url"
                      placeholder="填写接口地址，如 https://api.openai.com/v1"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                  </div>

                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >API Key</label
                    >
                    <div class="relative">
                      <Input
                        v-model="currentTranscriptionProvider.api_key"
                        :type="showTranscriptionApiKey ? 'text' : 'password'"
                        placeholder="填写 OpenAI API Key"
                        class="h-11 rounded-lg border-zinc-200 bg-white px-4 pr-12 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                      />
                      <button
                        type="button"
                        class="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200"
                        @click="
                          showTranscriptionApiKey = !showTranscriptionApiKey
                        "
                      >
                        <EyeOff v-if="showTranscriptionApiKey" class="size-4" />
                        <Eye v-else class="size-4" />
                      </button>
                    </div>
                  </div>
                </div>

                <div class="grid gap-4 md:grid-cols-2">
                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >语言提示</label
                    >
                    <Input
                      v-model="currentTranscriptionProvider.language"
                      placeholder="留空自动识别，例如 zh / en"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                  </div>

                  <div class="space-y-2">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >Beam Size</label
                    >
                    <Input
                      v-model="currentTranscriptionProvider.beam_size"
                      type="number"
                      min="1"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                  </div>
                </div>

                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >初始 Prompt</label
                  >
                  <textarea
                    v-model="currentTranscriptionProvider.prompt"
                    placeholder="可选：给转写器一些术语、品牌名或语言风格提示"
                    class="min-h-[110px] w-full rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm outline-none transition-colors dark:border-zinc-800 dark:bg-zinc-950"
                  />
                </div>

                <div class="space-y-2">
                  <div class="flex items-center justify-between">
                    <label class="text-[12px] font-bold text-zinc-400 ml-1"
                      >启用 VAD 过滤</label
                    >
                    <Switch
                      :checked="currentTranscriptionProvider.vad_filter"
                      @update:checked="
                        (checked: boolean) =>
                          updateProviderBooleanField(
                            'transcription',
                            currentTranscriptionProvider!.provider,
                            'vad_filter',
                            checked,
                          )
                      "
                      class="data-[state=checked]:bg-zinc-900 dark:data-[state=checked]:bg-zinc-100"
                    />
                  </div>
                  <p class="text-xs text-zinc-500 ml-1">
                    对本地 faster-whisper 更有帮助，可过滤长静音片段。
                  </p>
                </div>
              </template>

              <div
                class="flex items-center justify-end pt-4 border-t border-zinc-200 dark:border-zinc-800"
              >
                <Button
                  class="h-8 min-w-8 rounded-md border border-zinc-900 bg-zinc-900 px-3 text-xs font-medium text-white shadow-none duration-200 ease-linear hover:bg-zinc-900/90 active:bg-zinc-900/90 dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-zinc-100/90 dark:active:bg-zinc-100/90"
                  :disabled="!canUpdate || !!savingSection || loading"
                  @click="saveSettings('transcription', 'Whisper 配置')"
                >
                  <Save
                    :class="[
                      'mr-1.5 size-3.5',
                      savingSection === 'transcription' && 'animate-pulse',
                    ]"
                  />
                  {{
                    savingSection === "transcription"
                      ? "保存中..."
                      : "保存 Whisper 配置"
                  }}
                </Button>
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
            <CardContent class="flex flex-col gap-6 px-4 pt-4">
              <!-- 选择平台 -->
              <div class="space-y-2">
                <label class="text-[12px] font-bold text-zinc-400 ml-1"
                  >选择平台</label
                >
                <Select v-model="selectedVideoProvider">
                  <SelectTrigger
                    class="h-11 w-full rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  >
                    <SelectValue placeholder="选择平台" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem
                      v-for="p in formState.remake.providers"
                      :key="p.provider"
                      :value="p.provider"
                    >
                      {{ p.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <template v-if="currentVideoProvider">
                <!-- Model -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >Model</label
                  >
                  <Input
                    v-model="currentVideoProvider.default_model"
                    placeholder="填写模型名称，如 seedance-pro"
                    class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  />
                </div>

                <!-- API Base Endpoint -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >API Base Endpoint</label
                  >
                  <Input
                    v-model="currentVideoProvider.base_url"
                    :placeholder="videoBaseUrlPlaceholder"
                    class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  />
                  <p
                    v-if="videoBaseUrlHint"
                    class="text-[11px] leading-5 text-zinc-500 dark:text-zinc-400"
                  >
                    {{ videoBaseUrlHint }}
                  </p>
                </div>

                <!-- API Key -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >API Key</label
                  >
                  <div class="relative">
                    <Input
                      v-model="currentVideoProvider.api_key"
                      :type="showVideoApiKey ? 'text' : 'password'"
                      :placeholder="videoApiKeyPlaceholder"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 pr-12 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                    <button
                      type="button"
                      class="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200"
                      @click="showVideoApiKey = !showVideoApiKey"
                    >
                      <EyeOff v-if="showVideoApiKey" class="size-4" />
                      <Eye v-else class="size-4" />
                    </button>
                  </div>
                  <p
                    v-if="videoApiKeyHint"
                    class="text-[11px] leading-5 text-zinc-500 dark:text-zinc-400"
                  >
                    {{ videoApiKeyHint }}
                  </p>
                </div>
              </template>

              <!-- Footer -->
              <div
                class="flex items-center justify-end pt-4 border-t border-zinc-200 dark:border-zinc-800"
              >
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
                  {{ savingSection === "video" ? "保存中..." : "保存视频配置" }}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <!-- Motion Extraction Tab -->
        <TabsContent
          v-if="formState.motion_extraction"
          value="motion"
          class="space-y-6 focus-visible:outline-none"
        >
          <Card
            class="rounded-xl border-zinc-200 bg-white shadow-none dark:border-zinc-800 dark:bg-zinc-950"
          >
            <CardContent class="flex flex-col gap-6 px-4 pt-4">
              <!-- Coarse filter mode -->
              <div class="space-y-2">
                <label class="text-[12px] font-bold text-zinc-400 ml-1"
                  >粗筛模式</label
                >
                <Select v-model="formState.motion_extraction.coarse_filter_mode">
                  <SelectTrigger
                    class="h-11 w-full rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  >
                    <SelectValue placeholder="选择粗筛模式" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="keyword">关键词匹配</SelectItem>
                    <SelectItem value="permissive">宽松模式 (全部送审)</SelectItem>
                  </SelectContent>
                </Select>
                <p class="text-xs text-zinc-500 ml-1">
                  {{ formState.motion_extraction.coarse_filter_mode === "permissive"
                    ? "宽松模式下所有时长合规的镜头都直接进入 LLM 精标，召回率最高但 token 消耗更大。"
                    : "关键词模式下只有匹配到动作关键词且信号分达标的镜头才会进入精标流程。"
                  }}
                </p>
              </div>

              <!-- Duration range -->
              <div class="grid grid-cols-2 gap-4">
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >最短时长 (ms)</label
                  >
                  <Input
                    v-model.number="formState.motion_extraction.min_duration_ms"
                    type="number"
                    placeholder="800"
                    class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  />
                </div>
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >最长时长 (ms)</label
                  >
                  <Input
                    v-model.number="formState.motion_extraction.max_duration_ms"
                    type="number"
                    placeholder="15000"
                    class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  />
                </div>
              </div>

              <!-- Signal score threshold (only in keyword mode) -->
              <div
                v-if="formState.motion_extraction.coarse_filter_mode === 'keyword'"
                class="space-y-2"
              >
                <label class="text-[12px] font-bold text-zinc-400 ml-1"
                  >信号分阈值</label
                >
                <Input
                  v-model.number="formState.motion_extraction.signal_score_threshold"
                  type="number"
                  placeholder="3"
                  class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                />
                <p class="text-xs text-zinc-500 ml-1">
                  粗筛阶段的综合信号分需达到此阈值才进入精标，数值越低召回越多。默认 3。
                </p>
              </div>

              <!-- Confidence threshold -->
              <div class="space-y-2">
                <label class="text-[12px] font-bold text-zinc-400 ml-1"
                  >置信度阈值</label
                >
                <Input
                  v-model.number="formState.motion_extraction.confidence_threshold"
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  placeholder="0.6"
                  class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                />
                <p class="text-xs text-zinc-500 ml-1">
                  精标后 LLM 返回的置信度需达到此阈值才会保留。取值范围 0~1，越低保留越多。
                </p>
              </div>

              <!-- Separator -->
              <div class="border-t border-zinc-200 dark:border-zinc-800" />

              <!-- Provider selection -->
              <div class="space-y-2">
                <label class="text-[12px] font-bold text-zinc-400 ml-1"
                  >精标模型</label
                >
                <Select v-model="selectedDefaultMotionProvider">
                  <SelectTrigger
                    class="h-11 w-full rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  >
                    <SelectValue placeholder="选择精标模型" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem
                      v-for="p in formState.motion_extraction.providers"
                      :key="p.provider"
                      :value="p.provider"
                    >
                      {{ p.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <p class="text-xs text-zinc-500 ml-1">
                  动作提取精标使用的 LLM 模型，独立于对话模型配置。
                </p>
              </div>

              <template v-if="currentMotionProvider">
                <!-- Model -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >Model</label
                  >
                  <Input
                    v-model="currentMotionProvider.default_model"
                    placeholder="填写模型名称"
                    class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  />
                </div>

                <!-- Base URL -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >API Base Endpoint</label
                  >
                  <Input
                    v-model="currentMotionProvider.base_url"
                    placeholder="填写接口地址"
                    class="h-11 rounded-lg border-zinc-200 bg-white px-4 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                  />
                </div>

                <!-- API Key -->
                <div class="space-y-2">
                  <label class="text-[12px] font-bold text-zinc-400 ml-1"
                    >API Key</label
                  >
                  <div class="relative">
                    <Input
                      v-model="currentMotionProvider.api_key"
                      :type="showMotionApiKey ? 'text' : 'password'"
                      placeholder="填写密钥"
                      class="h-11 rounded-lg border-zinc-200 bg-white px-4 pr-12 shadow-none dark:border-zinc-800 dark:bg-zinc-950"
                    />
                    <button
                      type="button"
                      class="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200"
                      @click="showMotionApiKey = !showMotionApiKey"
                    >
                      <EyeOff v-if="showMotionApiKey" class="size-4" />
                      <Eye v-else class="size-4" />
                    </button>
                  </div>
                </div>
              </template>

              <!-- Footer -->
              <div
                class="flex items-center justify-end pt-4 border-t border-zinc-200 dark:border-zinc-800"
              >
                <Button
                  class="h-8 min-w-8 rounded-md border border-zinc-900 bg-zinc-900 px-3 text-xs font-medium text-white shadow-none duration-200 ease-linear hover:bg-zinc-900/90 active:bg-zinc-900/90 dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-zinc-100/90 dark:active:bg-zinc-100/90"
                  :disabled="!canUpdate || !!savingSection || loading"
                  @click="saveSettings('motion', '动作提取配置')"
                >
                  <Save
                    :class="[
                      'mr-1.5 size-3.5',
                      savingSection === 'motion' && 'animate-pulse',
                    ]"
                  />
                  {{ savingSection === "motion" ? "保存中..." : "保存动作提取配置" }}
                </Button>
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
        @click="loadSettings()"
        variant="outline"
        class="rounded-2xl h-11 px-10 font-bold border-red-200 hover:bg-red-50 text-red-600"
      >
        重新初始化配置
      </Button>
    </div>
  </div>
</template>

<style scoped>
div[role="tabpanel"] {
  @apply outline-none;
}
</style>
