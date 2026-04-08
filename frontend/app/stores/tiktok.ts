import { defineStore } from "pinia";

import type { TikTokInfoPayload } from "@/types/api";

export const useTiktokStore = defineStore("tiktok", () => {
  const api = useApi();

  const query = ref("https://www.tiktok.com/@demo/video/7339393672959757570");
  const result = ref<TikTokInfoPayload | null>(null);
  const pending = ref(false);
  const error = ref<string | null>(null);
  const lastResolvedAt = ref<string | null>(null);

  async function fetchVideoInfo(value = query.value) {
    const normalizedValue = value.trim();
    if (!normalizedValue) {
      error.value = "请输入 TikTok 作品链接或作品 ID。";
      return null;
    }

    pending.value = true;
    error.value = null;

    try {
      const data = await api.post<TikTokInfoPayload>("/tiktok/info", {
        value: normalizedValue,
      });
      query.value = normalizedValue;
      result.value = data;
      lastResolvedAt.value = new Date().toISOString();
      return data;
    } catch (requestError) {
      result.value = null;
      error.value = api.normalizeError(requestError);
      throw requestError;
    } finally {
      pending.value = false;
    }
  }

  function reset() {
    result.value = null;
    error.value = null;
    lastResolvedAt.value = null;
  }

  return {
    query,
    result,
    pending,
    error,
    lastResolvedAt,
    fetchVideoInfo,
    reset,
  };
});
