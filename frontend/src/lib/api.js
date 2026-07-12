import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;
export const TOKEN_KEY = "dmr_token";

export const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const wsUrl = () => {
  const token = localStorage.getItem(TOKEN_KEY) || "";
  const url = new URL(BACKEND_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/api/ws";
  url.searchParams.set("token", token);
  return url.toString();
};

// --------- Radios / positions / packets ---------
export const fetchRadios = () => api.get("/radios").then((r) => r.data);
export const fetchStatus = () => api.get("/status").then((r) => r.data);
export const fetchPackets = (limit = 200) =>
  api.get(`/packets?limit=${limit}`).then((r) => r.data);
export const fetchPositions = (dmrId) =>
  api.get(`/radios/${dmrId}/positions`).then((r) => r.data);
export const injectPacket = (packet) =>
  api.post("/inject", packet).then((r) => r.data);
export const injectRawHex = (payload) =>
  api.post("/inject-raw", payload).then((r) => r.data);
export const clearAll = () => api.delete("/radios").then((r) => r.data);
export const updateRadio = (dmrId, meta) =>
  api.patch(`/radios/${dmrId}`, meta).then((r) => r.data);
export const deleteRadio = (dmrId) =>
  api.delete(`/radios/${dmrId}`).then((r) => r.data);

// --------- Auth ---------
export const login = (email, password) =>
  api.post("/auth/login", { email, password }).then((r) => r.data);
export const register = (payload) =>
  api.post("/auth/register", payload).then((r) => r.data);
export const me = () => api.get("/auth/me").then((r) => r.data);

// --------- Admin ---------
export const adminListUsers = () =>
  api.get("/admin/users").then((r) => r.data);
export const adminApproveUser = (id) =>
  api.post(`/admin/users/${id}/approve`).then((r) => r.data);
export const adminRejectUser = (id) =>
  api.post(`/admin/users/${id}/reject`).then((r) => r.data);
export const adminSetRole = (id, role) =>
  api.post(`/admin/users/${id}/role`, { role }).then((r) => r.data);
export const adminDeleteUser = (id) =>
  api.delete(`/admin/users/${id}`).then((r) => r.data);

// --------- Geofences + alerts ---------
export const listGeofences = () => api.get("/geofences").then((r) => r.data);
export const createGeofence = (body) =>
  api.post("/geofences", body).then((r) => r.data);
export const deleteGeofence = (id) =>
  api.delete(`/geofences/${id}`).then((r) => r.data);
export const listAlerts = (limit = 100) =>
  api.get(`/alerts?limit=${limit}`).then((r) => r.data);
export const clearAlerts = () => api.delete("/alerts").then((r) => r.data);

export function apiErrorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (!detail) return err.message || "Something went wrong";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((d) => d.msg || JSON.stringify(d)).join(" · ");
  if (detail && typeof detail === "object" && detail.msg) return detail.msg;
  return JSON.stringify(detail);
}
