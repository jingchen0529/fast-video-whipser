import tailwindcss from "@tailwindcss/vite";

const env = (
  globalThis as typeof globalThis & {
    process?: {
      env?: Record<string, string | undefined>;
    };
  }
).process?.env ?? {};

const serverApiBase = env.NUXT_API_BASE || "http://127.0.0.1:8000";
const publicApiDocsUrl =
  env.NUXT_API_DOCS_URL || `${serverApiBase}/docs`;
const enableDevtools = env.NUXT_ENABLE_DEVTOOLS === "true";

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: "2025-07-15",
  devtools: { enabled: enableDevtools },
  routeRules: {
    "/dashboard": { prerender: false },
    "/dashboard/**": { prerender: false },
    "/users": { prerender: false },
    "/users/**": { prerender: false },
    "/auth/users": { prerender: false },
  },
  app: {
    head: {
      title: "Cut Killer",
      link: [
        { rel: "icon", type: "image/x-icon", href: "/favicon.ico" },
        { rel: "shortcut icon", type: "image/x-icon", href: "/favicon.ico" },
      ],
    },
  },
  modules: ["@pinia/nuxt", "shadcn-nuxt"],
  css: [
    "~/assets/css/tailwind.css",
    "~/assets/scss/main.scss",
  ],
  components: [
    {
      path: "~/components",
      extensions: ["vue"],
    },
  ],
  vite: {
    plugins: [tailwindcss()],
    optimizeDeps: {
      include: [
        "lucide-vue-next",
        "class-variance-authority",
        "@vueuse/core",
        "reka-ui",
        "clsx",
        "tailwind-merge",
      ],
    },
  },
  runtimeConfig: {
    apiBase: serverApiBase,
    public: {
      apiBase: "/api",
      apiDocsUrl: publicApiDocsUrl,
    },
  },
  shadcn: {
    prefix: "",
    componentDir: "./app/components/ui",
  },
});
