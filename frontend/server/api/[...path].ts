import { getRequestURL, proxyRequest } from "h3";

export default defineEventHandler((event) => {
  const runtimeConfig = useRuntimeConfig(event);
  const path = String(event.context.params?.path || "").replace(/^\/+/, "");
  const baseUrl = String(runtimeConfig.apiBase).replace(/\/$/, "");
  const search = getRequestURL(event).search;
  // 前端统一请求 /api/...，这里转发到后端正式的 /api/... 路径。
  const target = `${baseUrl}/api/${path}${search}`;

  return proxyRequest(event, target);
});
