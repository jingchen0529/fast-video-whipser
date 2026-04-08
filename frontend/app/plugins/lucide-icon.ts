import LucideIcon from "~/components/custom/LucideIcon.vue";

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.component("LucideIcon", LucideIcon);
});
