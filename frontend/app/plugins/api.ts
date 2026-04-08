export default defineNuxtPlugin(() => {
  const runtimeConfig = useRuntimeConfig();
  const csrfToken = useCookie<string | null>("auth_csrf_token", {
    sameSite: "lax",
  });
  const forwardedHeaders = import.meta.server
    ? useRequestHeaders(["cookie"])
    : {};

  const api = $fetch.create({
    baseURL: runtimeConfig.public.apiBase,
    retry: 0,
    credentials: "include",
    onRequest({ options }) {
      const headers = new Headers(options.headers || {});
      headers.set("Accept", "application/json");

      if (import.meta.server) {
        const cookieHeader = forwardedHeaders.cookie;
        if (cookieHeader && !headers.has("cookie")) {
          headers.set("cookie", cookieHeader);
        }
      }

      const method = String(options.method || "GET").toUpperCase();
      if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken.value) {
        headers.set("X-CSRF-Token", csrfToken.value);
      }

      options.headers = headers;
    },
  });

  return {
    provide: {
      api,
    },
  };
});
