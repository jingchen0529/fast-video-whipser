import { useState } from "#app";

export const useLoadingOverlay = () => {
  const isLoading = useState<boolean>("global_loading_overlay", () => false);
  const loadingMessage = useState<string>("global_loading_message", () => "正在处理...");

  const showLoading = (message?: string) => {
    if (message) {
      loadingMessage.value = message;
    } else {
      loadingMessage.value = "正在处理...";
    }
    isLoading.value = true;
  };

  const hideLoading = () => {
    isLoading.value = false;
  };

  return {
    isLoading,
    loadingMessage,
    showLoading,
    hideLoading,
  };
};
