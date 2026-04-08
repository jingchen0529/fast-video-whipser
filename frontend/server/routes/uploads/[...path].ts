import { getRequestURL, proxyRequest } from "h3";

export default defineEventHandler((event) => {
  const runtimeConfig = useRuntimeConfig(event);
  const path = String(event.context.params?.path || "").replace(/^\/+/, "");
  const baseUrl = String(runtimeConfig.apiBase).replace(/\/$/, "");
  const target = `${baseUrl}/uploads/${path}`;

  return proxyRequest(event, target);
});
