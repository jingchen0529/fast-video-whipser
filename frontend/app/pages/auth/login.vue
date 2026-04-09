<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import PeekCharacters from "@/components/custom/PeekCharacters.vue";

definePageMeta({
  middleware: "guest",
});

const form = reactive({
  login: "",
  password: "",
  remember: false,
});

const auth = useAuth();
const loadingOverlay = useLoadingOverlay();
const router = useRouter();
const loading = ref(false);
const showPassword = ref(false);
const isTyping = ref(false);
const passwordFocused = ref(false);
const captchaCode = ref("");
const error = ref("");
const successMessage = ref("");
const captcha = useCaptcha();

const isPasswordGuardMode = computed(() => passwordFocused.value);
const isBusy = computed(() => loading.value || captcha.loading.value);

const loadCaptcha = async () => {
  try {
    await captcha.refreshCaptcha();
  } catch {
    // 错误提示由 composable 持有，这里不重复处理。
  }
};

const handleSubmit = async () => {
  error.value = "";
  successMessage.value = "";

  if (!form.login.trim()) {
    error.value = "请输入账号。";
    return;
  }

  if (form.password.trim().length < 8) {
    error.value = "密码长度至少需要 8 位。";
    return;
  }

  if (!captchaCode.value.trim()) {
    error.value = "请输入验证码。";
    return;
  }

  loading.value = true;

  try {
    const user = await auth.login({
      login: form.login.trim(),
      password: form.password,
      captcha_id: captcha.captchaId.value,
      captcha_code: captchaCode.value,
      remember: form.remember,
    });
    
    // Show premium loading overlay before transition
    loadingOverlay.showLoading(`欢迎回来，${user.display_name}。正在进入您的工作空间...`);
    
    await router.push("/dashboard");
    
    // We don't hide it immediately here to ensure the transition is smooth
  } catch (submitError: unknown) {
    error.value = authErrorMessage(submitError);
    captchaCode.value = "";
    await loadCaptcha();
    loadingOverlay.hideLoading();
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  await loadCaptcha();
});

const authErrorMessage = (submitError: unknown) => {
  const normalized = useApi().normalizeError(submitError);
  if (normalized === "Request failed.") {
    return "登录失败，请稍后重试。";
  }
  return normalized;
};

useHead({
  title: "Login",
});
</script>

<template>
  <main class="login-page">
    <div class="login-container">
      <section class="left-panel">
        <div class="left-top">
          <div class="brand-mark">
            <div class="brand-mark-inner">
              <img src="/favicon.ico" alt="Brand Icon" class="brand-icon" />
            </div>
          </div>
          <span class="brand-name">爆款杀手🥷</span>
        </div>

        <div class="characters-area">
          <div class="characters-stage">
            <PeekCharacters
              :is-typing="isTyping"
              :show-password="showPassword"
              :password-length="form.password.length"
              :is-password-guard-mode="isPasswordGuardMode"
            />
          </div>
        </div>

        <div class="left-footer">
          <a href="#" class="footer-link">Privacy Policy</a>
          <a href="#" class="footer-link">Terms of Service</a>
        </div>

        <button type="button" class="check-fab" aria-label="Complete">
          <LucideIcon
            name="Check"
            class="check-icon"
            aria-hidden="true"
            :stroke-width="2"
          />
        </button>

        <div class="decor-blur decor-blur-one" />
        <div class="decor-blur decor-blur-two" />
      </section>

      <section class="right-panel">
        <div class="form-wrapper">
          <div class="mobile-logo">
            <div class="mobile-logo-icon">
              <img
                src="/favicon.ico"
                alt="Mobile Logo"
                class="mobile-logo-svg"
              />
            </div>
            <span>爆款杀手🥷</span>
          </div>

          <div class="form-header">
            <h1 class="form-title">Welcome back</h1>
            <p class="form-subtitle">Sign in to continue to your workspace.</p>
          </div>

          <form class="form" @submit.prevent="handleSubmit">
            <div class="field-label">账号</div>
            <div class="input-wrap">
              <input
                v-model="form.login"
                type="text"
                autocomplete="username"
                placeholder="请输入账号"
                class="text-input"
                @focus="isTyping = true"
                @blur="isTyping = false"
              />
            </div>

            <div class="field-label">密码</div>
            <div class="input-wrap">
              <input
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="请输入密码"
                class="text-input"
                @focus="passwordFocused = true"
                @blur="passwordFocused = false"
              />
              <button
                type="button"
                class="eye-toggle"
                @click="showPassword = !showPassword"
              >
                <LucideIcon
                  v-if="showPassword"
                  name="EyeOff"
                  class="eye-icon"
                  aria-hidden="true"
                  :stroke-width="2"
                />
                <LucideIcon
                  v-else
                  name="Eye"
                  class="eye-icon"
                  aria-hidden="true"
                  :stroke-width="2"
                />
              </button>
            </div>

            <div class="field-label">验证码</div>
            <div class="input-wrap captcha-wrap">
              <input
                v-model="captchaCode"
                type="text"
                autocomplete="off"
                inputmode="text"
                placeholder="请输入验证码"
                class="text-input"
              />
              <button
                type="button"
                class="captcha-image-button"
                :disabled="captcha.loading.value || captcha.verifying.value"
                @click="loadCaptcha"
              >
                <img
                  v-if="captcha.captchaImage.value"
                  :src="captcha.captchaImage.value"
                  alt="Captcha image"
                  class="captcha-image"
                />
                <span v-else class="captcha-placeholder">
                  {{
                    captcha.loading.value ? "Loading..." : "Click to refresh"
                  }}
                </span>
              </button>
            </div>

            <p v-if="captcha.error.value" class="captcha-hint">
              {{ captcha.error.value }}
            </p>

            <div class="form-meta">
              <label class="remember-box">
                <input
                  v-model="form.remember"
                  type="checkbox"
                  class="remember-input"
                />
                <span>记住我</span>
              </label>
            </div>

            <p v-if="error" class="feedback error-box">{{ error }}</p>
            <p v-if="successMessage" class="feedback success-box">
              {{ successMessage }}
            </p>
            <button type="submit" class="submit-btn" :disabled="isBusy">
              {{ isBusy ? "登录中.." : "登录" }}
            </button>
          </form>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped lang="scss">
.login-page {
  min-height: 100vh;
  background: #ffffff;
}

.login-container {
  width: 100%;
  max-width: none;
  min-height: 100vh;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: 50% 50%;

  @media (max-width: 1024px) {
    grid-template-columns: 1fr;
  }
}

.left-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  overflow: hidden;
  padding: 48px 48px 32px;
  background:
    radial-gradient(circle at top, rgba(255, 255, 255, 0.18), transparent 34%),
    linear-gradient(180deg, #959dac 0%, #6f7889 100%);

  @media (max-width: 1024px) {
    display: none;
  }

  .left-top {
    position: relative;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 12px;
    color: #fff;

    .brand-mark {
      display: flex;
      height: 32px;
      width: 32px;
      align-items: center;
      justify-content: center;
      border-radius: 10px;
      backdrop-filter: blur(8px);

      &-inner {
        display: flex;
        height: 32px;
        width: 32px;
        align-items: center;
        justify-content: center;
        border-radius: 999px;

        .brand-icon {
          width: 32px;
          height: 32px;
          fill: white;
        }
      }
    }

    .brand-name {
      font-size: 20px;
      font-weight: 600;
      letter-spacing: -0.02em;
    }
  }

  .characters-area {
    position: relative;
    z-index: 20;
    display: flex;
    flex: 1;
    align-items: flex-end;
    justify-content: flex-start;
    min-height: 500px;
    padding-bottom: 0;
    overflow: visible;

    .characters-stage {
      display: flex;
      align-items: flex-end;
      justify-content: flex-start;
      width: 100%;
      height: 100%;

      :deep(.characters-root) {
        transform: scale(1);
        transform-origin: left bottom;
      }
    }
  }

  .left-footer {
    position: relative;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 32px;
    color: rgba(71, 80, 98, 0.6);
    font-size: 14px;

    .footer-link {
      color: inherit;
      text-decoration: none;
      transition: color 0.2s ease;

      &:hover {
        color: white;
      }
    }
  }

  .check-fab {
    position: absolute;
    right: 48px;
    bottom: 32px;
    z-index: 30;
    display: flex;
    height: 48px;
    width: 48px;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 999px;
    background: #22c55e;
    box-shadow: 0 8px 16px rgba(34, 197, 94, 0.2);
    cursor: pointer;

    .check-icon {
      width: 24px;
      height: 24px;
      color: white;
    }
  }

  .decor-blur {
    position: absolute;
    border-radius: 999px;
    filter: blur(90px);
    pointer-events: none;

    &-one {
      top: 18%;
      right: 8%;
      width: 360px;
      height: 360px;
      background: rgba(255, 255, 255, 0.12);
    }

    &-two {
      left: 10%;
      bottom: 24%;
      width: 460px;
      height: 460px;
      background: rgba(119, 128, 145, 0.26);
    }
  }
}

.right-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 48px;
  background: #ffffff;

  @media (max-width: 1024px) {
    padding: 32px 24px;
  }

  .form-wrapper {
    width: 100%;
    max-width: 420px;

    @media (max-width: 1024px) {
      max-width: 400px;
      padding: 0;
    }
  }

  .mobile-logo {
    display: none;
    align-items: center;
    justify-content: center;
    gap: 10px;
    margin-bottom: 24px;
    font-size: 18px;
    font-weight: 700;
    color: #0f172a;

    @media (max-width: 1024px) {
      display: flex;
    }

    &-icon {
      display: flex;
      width: 32px;
      height: 32px;
      align-items: center;
      justify-content: center;
      border-radius: 12px;

      .mobile-logo-svg {
        width: 32px;
        height: 32px;
        fill: white;
      }
    }
  }

  .form-header {
    text-align: center;

    .form-title {
      margin: 0;
      color: #030712;
      font-size: 32px;
      font-weight: 700;
      line-height: 1.2;
      letter-spacing: -0.02em;

      @media (max-width: 1024px) {
        font-size: 28px;
      }
    }

    .form-subtitle {
      margin: 8px 0 0;
      color: #70819f;
      font-size: 16px;
      line-height: 1.45;

      @media (max-width: 1024px) {
        font-size: 15px;
      }
    }
  }

  .form {
    margin-top: 40px;

    .field-label {
      margin-bottom: 8px;
      color: #111827;
      font-size: 14px;
      font-weight: 600;
    }

    .input-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
      height: 48px;
      margin-bottom: 24px;
      padding: 0 16px;
      border-radius: 999px;
      border: 1px solid #e3e8f2;
      background: #ffffff;
      transition:
        border-color 0.2s ease,
        box-shadow 0.2s ease,
        background 0.2s ease;

      &:focus-within {
        border-color: #cdd8ee;
        background: white;
        box-shadow: 0 6px 16px rgba(34, 48, 73, 0.06);
      }

      .text-input {
        width: 100%;
        border: 0;
        background: transparent;
        color: #0f172a;
        font-size: 14px;
        outline: none;

        &::placeholder {
          color: #9ca3af;
        }
      }

      .eye-toggle {
        border: 0;
        background: transparent;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #9ca3af;
        cursor: pointer;
        padding: 0;

        .eye-icon {
          width: 20px;
          height: 20px;
        }
      }
    }

    .form-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin: 0 0 24px;
      color: #4b5563;
      font-size: 14px;

      .remember-box {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;

        .remember-input {
          width: 16px;
          height: 16px;
          accent-color: #4f46e5;
          border-radius: 4px;
          border: 1px solid #d1d5db;
          outline: none;
          cursor: pointer;
        }
      }

      .forgot-link {
        color: #4f46e5;
        font-weight: 500;
        text-decoration: none;

        &:hover {
          text-decoration: underline;
        }
      }
    }

    .captcha-wrap {
      overflow: hidden;

      .text-input {
        min-width: 0;
      }

      .captcha-image-button {
        flex: 0 0 132px;
        display: flex;
        align-items: center;
        justify-content: center;
        align-self: stretch;
        margin-right: -16px;
        padding: 0 16px;
        border: 0;
        cursor: pointer;
        transition:
          opacity 0.2s ease,
          background-color 0.2s ease;

        &:disabled {
          cursor: not-allowed;
          opacity: 0.72;
        }

        .captcha-image {
          display: block;
          width: 100%;
          height: 100%;
          object-fit: contain;
        }

        .captcha-placeholder {
          color: #6b7280;
          font-size: 12px;
          line-height: 1.4;
          text-align: center;
        }

        @media (max-width: 640px) {
          flex-basis: 120px;
        }
      }
    }

    .captcha-hint {
      margin: 0 0 16px;
      color: #6b7280;
      font-size: 13px;
      line-height: 1.5;
    }

    .feedback {
      margin: 0 0 16px;
      padding: 12px 14px;
      border-radius: 12px;
      font-size: 13px;
      line-height: 1.6;

      &.error-box {
        color: #b91c1c;
        background: #fff1f2;
        border: 1px solid #fecdd3;
      }

      &.success-box {
        color: #047857;
        background: #ecfdf5;
        border: 1px solid #a7f3d0;
      }
    }

    .submit-btn,
    .google-btn {
      width: 100%;
      height: 48px;
      border-radius: 999px;
      border: 1px solid #e3e8f2;
      font-size: 16px;
      font-weight: 600;
      transition: all 0.2s ease;
    }

    .submit-btn {
      background: #ffffff;
      color: #111827;
      cursor: pointer;

      &:hover:not(:disabled) {
        background: #f9fafb;
      }

      &:disabled {
        opacity: 0.7;
        cursor: not-allowed;
      }
    }

    .google-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      margin-top: 16px;
      background: white;
      color: #111827;
      cursor: pointer;

      &:hover {
        background: #f9fafb;
      }

      .google-icon {
        width: 18px;
        height: 18px;
      }
    }

    .signup-hint {
      margin: 32px 0 0;
      text-align: center;
      color: #6b7280;
      font-size: 14px;

      .signup-link {
        color: #111827;
        font-weight: 600;
        text-decoration: none;

        &:hover {
          text-decoration: underline;
        }
      }
    }
  }
}
</style>
