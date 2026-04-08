import { toast } from "vue-sonner";

/**
 * 格式化并显示 API 错误信息
 * @param api useApi 返回的实例对象
 * @param error 捕获的错误对象
 * @param fallback 默认的错误提示文字
 */
export const notifyError = (api: any, error: unknown, fallback: string) => {
  const message = api.normalizeError(error);
  toast.error(message === "Request failed." ? fallback : message);
};

/**
 * 日期时间格式化 (yyyy/MM/dd HH:mm)
 * @param value ISO 日期字符串
 * @returns 格式化后的本地化字符串
 */
export const formatDateTime = (value?: string | null) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};
