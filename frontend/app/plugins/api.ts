export default defineNuxtPlugin(() => {
  const runtimeConfig = useRuntimeConfig();
  const router = useRouter();
  const forwardedHeaders = import.meta.server
    ? useRequestHeaders(["cookie"])
    : {};
  const userState = useState("auth_user_state", () => null);
  const csrfTokenState = useState<string | null>(
    "auth_csrf_token_state",
    () => null,
  );
  const rememberMeState = useState("auth_remember_me_state", () => false);
  const initializedState = useState("auth_initialized", () => false);
  const redirectingToLogin = useState("auth_redirecting_to_login", () => false);

  const clearLocalAuthState = () => {
    const userCookie = useCookie("auth_user", {
      sameSite: "lax",
      default: () => null,
    });
    const csrfTokenCookie = useCookie<string | null>("auth_csrf_token", {
      sameSite: "lax",
      default: () => null,
    });
    const rememberMeCookie = useCookie("auth_remember_me", {
      sameSite: "lax",
      default: () => false,
    });

    userState.value = null;
    csrfTokenState.value = null;
    rememberMeState.value = false;
    initializedState.value = false;
    userCookie.value = null;
    csrfTokenCookie.value = null;
    rememberMeCookie.value = false;
  };

  const resolveRequestPath = (request: RequestInfo | URL) => {
    if (typeof request === "string") {
      try {
        return new URL(request, "http://local.nuxt").pathname;
      } catch {
        return request;
      }
    }
    if (request instanceof URL) {
      return request.pathname;
    }
    try {
      return new URL(request.url || "", "http://local.nuxt").pathname;
    } catch {
      return request.url || "";
    }
  };

  const shouldHandleUnauthorized = (path: string) => {
    const normalized = path.trim();
    if (!normalized) {
      return false;
    }

    return !new Set([
      "/auth/login",
      "/auth/register",
      "/auth/me",
      "/auth/refresh",
      "/auth/logout",
      "/common/captcha",
      "/common/captcha/verify",
    ]).has(normalized);
  };

  const api = $fetch.create({
    baseURL: runtimeConfig.public.apiBase,
    retry: 0,
    credentials: "include",
    onRequest({ options }) {
      const csrfTokenCookie = useCookie<string | null>("auth_csrf_token", {
        sameSite: "lax",
      });
      const headers = new Headers(options.headers || {});
      headers.set("Accept", "application/json");

      if (import.meta.server) {
        const cookieHeader = forwardedHeaders.cookie;
        if (cookieHeader && !headers.has("cookie")) {
          headers.set("cookie", cookieHeader);
        }
      }

      const method = String(options.method || "GET").toUpperCase();
      const csrfToken = csrfTokenState.value || csrfTokenCookie.value;
      if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
        headers.set("X-CSRF-Token", csrfToken);
      }

      options.headers = headers;
    },
    onResponseError({ request, response }) {
      if (import.meta.server || response.status !== 401) {
        return;
      }

      const requestPath = resolveRequestPath(request);
      if (!shouldHandleUnauthorized(requestPath)) {
        return;
      }

      clearLocalAuthState();
      if (redirectingToLogin.value) {
        return;
      }

      if (router.currentRoute.value.path === "/auth/login") {
        return;
      }

      redirectingToLogin.value = true;
      queueMicrotask(() => {
        router.replace("/auth/login")
          .finally(() => {
            redirectingToLogin.value = false;
          });
      });
    },
  });

  return {
    provide: {
      api,
    },
  };
});
