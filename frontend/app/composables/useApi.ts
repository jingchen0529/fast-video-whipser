import type { ApiErrorResponse, ApiResponse } from "@/types/api";

interface ApiFetchError {
  data?: Partial<ApiErrorResponse>;
  statusCode?: number;
  statusMessage?: string;
  message?: string;
}

export function useApi() {
  const { $api } = useNuxtApp();
  type ApiClient = typeof $api;
  type ApiRequestOptions = NonNullable<Parameters<ApiClient>[1]>;

  const request = <T>(url: string, options?: ApiRequestOptions) =>
    $api<ApiResponse<T>>(url, options);

  const requestData = async <T>(url: string, options?: ApiRequestOptions) => {
    const response = await request<T>(url, options);
    return response.data;
  };

  const get = <T>(url: string, options?: ApiRequestOptions) =>
    requestData<T>(url, { ...options, method: "get" });

  const post = <T>(
    url: string,
    body?: ApiRequestOptions["body"],
    options?: ApiRequestOptions,
  ) =>
    requestData<T>(url, { ...options, method: "post", body });

  const patch = <T>(
    url: string,
    body?: ApiRequestOptions["body"],
    options?: ApiRequestOptions,
  ) =>
    requestData<T>(url, { ...options, method: "patch", body });

  const put = <T>(
    url: string,
    body?: ApiRequestOptions["body"],
    options?: ApiRequestOptions,
  ) =>
    requestData<T>(url, { ...options, method: "put", body });

  const del = <T>(url: string, options?: ApiRequestOptions) =>
    requestData<T>(url, { ...options, method: "delete" });

  const normalizeError = (error: unknown) => {
    const apiError = error as ApiFetchError | undefined;
    return (
      apiError?.data?.message ||
      apiError?.statusMessage ||
      apiError?.message ||
      "Request failed."
    );
  };

  return {
    client: $api,
    request,
    requestData,
    get,
    post,
    patch,
    put,
    delete: del,
    normalizeError,
  };
}
