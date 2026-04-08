import { computed } from "vue";

import type { AuthSessionPayload, AuthUser } from "@/types/api";

export interface LoginPayload {
  login: string;
  password: string;
  captcha_id: string;
  captcha_code: string;
  remember?: boolean;
}

interface LogoutOptions {
  redirectTo?: string | null;
}

interface ClearSessionOptions {
  clearCookies?: boolean;
}

export function useAuth() {
  const api = useApi();
  
  // 使用 useCookie 仅用于持久化
  const userCookie = useCookie<AuthUser | null>("auth_user", {
    sameSite: "lax",
    default: () => null,
  });
  const csrfTokenCookie = useCookie<string | null>("auth_csrf_token", {
    sameSite: "lax",
    default: () => null,
  });
  const rememberMeCookie = useCookie<boolean>("auth_remember_me", {
    sameSite: "lax",
    default: () => false,
  });

  // 使用 useState 保证应用内单例响应式状态
  const user = useState<AuthUser | null>("auth_user_state", () => userCookie.value);
  const csrfToken = useState<string | null>("auth_csrf_token_state", () => csrfTokenCookie.value);
  const rememberMe = useState<boolean>("auth_remember_me_state", () => rememberMeCookie.value);
  
  // 同步状态到 Cookie
  watch(user, (val) => { userCookie.value = val; }, { deep: true });
  watch(csrfToken, (val) => { csrfTokenCookie.value = val; });
  watch(rememberMe, (val) => { rememberMeCookie.value = val; });

  const initialized = useState<boolean>("auth_initialized", () => false);

  const isAuthenticated = computed(() => Boolean(user.value));

  const clearSession = (options?: ClearSessionOptions) => {
    const clearCookies = options?.clearCookies ?? true;
    if (clearCookies) {
      user.value = null;
      csrfToken.value = null;
      rememberMe.value = false;
    }
    initialized.value = false;
  };

  const applySession = (payload: AuthSessionPayload, remember = false) => {
    const userCookie = useCookie<AuthUser | null>("auth_user", {
      sameSite: "lax",
      default: () => null,
      maxAge: remember ? payload.refresh_token_expires_in : undefined,
    });
    const csrfCookie = useCookie<string | null>("auth_csrf_token", {
      sameSite: "lax",
      default: () => null,
      maxAge: remember ? payload.refresh_token_expires_in : undefined,
    });

    userCookie.value = payload.user;
    csrfCookie.value = payload.csrf_token;
    user.value = payload.user;
    csrfToken.value = payload.csrf_token;
    rememberMe.value = remember;
    initialized.value = true;
  };

  const fetchCurrentUser = async (): Promise<AuthUser> => {
    const profile = await api.get<AuthUser>("/auth/me");
    user.value = profile;
    initialized.value = true;
    return profile;
  };

  const refreshSession = async (): Promise<AuthUser | null> => {
    try {
      const payload = await api.post<AuthSessionPayload>("/auth/refresh");
      applySession(payload, rememberMe.value);
      return payload.user;
    } catch {
      clearSession({ clearCookies: import.meta.client });
      return null;
    }
  };

  const initialize = async (): Promise<boolean> => {
    if (initialized.value && user.value) {
      return true;
    }

    try {
      await fetchCurrentUser();
      return true;
    } catch {
      const refreshedUser = await refreshSession();
      if (!refreshedUser) {
        return false;
      }

      try {
        await fetchCurrentUser();
        return true;
      } catch {
        clearSession({ clearCookies: import.meta.client });
        return false;
      }
    }
  };

  const login = async (payload: LoginPayload): Promise<AuthUser> => {
    const login = payload.login.trim();
    const password = payload.password;
    const captchaId = payload.captcha_id.trim();
    const captchaCode = payload.captcha_code.trim();

    if (!login) {
      throw createError({
        statusCode: 400,
        statusMessage: "账号不能为空。",
        data: {
          detail: "账号不能为空。",
        },
      });
    }

    if (password.trim().length < 8) {
      throw createError({
        statusCode: 400,
        statusMessage: "密码长度至少需要 8 位。",
        data: {
          detail: "密码长度至少需要 8 位。",
        },
      });
    }

    if (!captchaId || !captchaCode) {
      throw createError({
        statusCode: 400,
        statusMessage: "验证码不能为空。",
        data: {
          detail: "验证码不能为空。",
        },
      });
    }

    const data = await api.post<AuthSessionPayload>("/auth/login", {
      login,
      password,
      captcha_id: captchaId,
      captcha_code: captchaCode,
      remember: payload.remember ?? false,
    });
    applySession(data, payload.remember ?? false);
    return data.user;
  };

  const logout = async (options?: LogoutOptions) => {
    let succeeded = true;
    try {
      await api.post("/auth/logout");
    } catch {
      // 即使后端会话已失效，也继续清理前端状态。
      succeeded = false;
    }

    clearSession();

    if (options?.redirectTo !== null) {
      await navigateTo(options?.redirectTo || "/auth/login");
    }

    return succeeded;
  };

  return {
    user,
    csrfToken,
    isAuthenticated,
    initialized,
    clearSession,
    initialize,
    fetchCurrentUser,
    refreshSession,
    login,
    logout,
  };
}
