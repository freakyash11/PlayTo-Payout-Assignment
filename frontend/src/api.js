import axios from "axios";

// Vite proxies /api → http://backend:8000, so no absolute URL is needed.
const api = axios.create({ baseURL: "/api/v1" });

// Inject X-Merchant-Id on every request when a merchant is selected.
// The interceptor reads from a module-level variable set by setMerchantId().
let _merchantId = null;
export const setMerchantId = (id) => { _merchantId = id; };

api.interceptors.request.use((config) => {
  if (_merchantId) config.headers["X-Merchant-Id"] = _merchantId;
  return config;
});

export default api;
