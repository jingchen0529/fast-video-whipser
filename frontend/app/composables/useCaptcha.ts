interface CaptchaPayload {
  captcha_id: string;
  captcha_type: string;
  captcha_image: string;
  expires_in_seconds: number;
}

interface CaptchaVerifyPayload {
  captcha_id: string;
  verified: boolean;
}

export function useCaptcha() {
  const api = useApi();

  const captchaId = ref("");
  const captchaImage = ref("");
  const captchaType = ref("svg");
  const expiresInSeconds = ref(0);
  const loading = ref(false);
  const verifying = ref(false);
  const error = ref<string | null>(null);

  async function refreshCaptcha() {
    loading.value = true;
    error.value = null;

    try {
      const data = await api.get<CaptchaPayload>("/common/captcha");
      captchaId.value = data.captcha_id;
      captchaImage.value = data.captcha_image;
      captchaType.value = data.captcha_type;
      expiresInSeconds.value = data.expires_in_seconds;
      return data;
    } catch (requestError) {
      captchaId.value = "";
      captchaImage.value = "";
      error.value = api.normalizeError(requestError);
      throw requestError;
    } finally {
      loading.value = false;
    }
  }

  async function verifyCaptcha(captchaCode: string) {
    const normalizedCode = captchaCode.trim();

    if (!captchaId.value) {
      throw createError({
        statusCode: 400,
        statusMessage: "Captcha is not ready.",
      });
    }

    verifying.value = true;
    error.value = null;

    try {
      const data = await api.post<CaptchaVerifyPayload>("/common/captcha/verify", {
        captcha_id: captchaId.value,
        captcha_code: normalizedCode,
      });
      return data.verified;
    } catch (requestError) {
      error.value = api.normalizeError(requestError);
      throw requestError;
    } finally {
      verifying.value = false;
    }
  }

  return {
    captchaId,
    captchaImage,
    captchaType,
    expiresInSeconds,
    loading,
    verifying,
    error,
    refreshCaptcha,
    verifyCaptcha,
  };
}
