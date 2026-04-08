import { defineNuxtPlugin } from "#app";
import { useLoadingOverlay } from "@/composables/useLoadingOverlay";

export default defineNuxtPlugin((nuxtApp) => {
  const { hideLoading } = useLoadingOverlay();

  // Hide the global loading overlay after every successful route change
  nuxtApp.hook("page:finish", () => {
    hideLoading();
  });
});
