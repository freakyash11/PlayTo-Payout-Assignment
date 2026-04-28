import axios from "axios";

// Use env var VITE_API_URL or fallback to localhost
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const api = axios.create({ baseURL: `${BASE_URL}/api/v1` });

// Inject X-Merchant-Id on every request when a merchant is selected.
// The interceptor reads from a module-level variable set by setMerchantId().
let _merchantId = null;
export const setMerchantId = (id) => { _merchantId = id; };

api.interceptors.request.use((config) => {
  if (_merchantId) config.headers["X-Merchant-Id"] = _merchantId;
  return config;
});

export default api;
