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

// --------- Channels ---------
export const listChannels = () => api.get("/channels").then((r) => r.data);
export const createChannel = (body) => api.post("/channels", body).then((r) => r.data);
export const updateChannel = (id, body) =>
  api.patch(`/channels/${id}`, body).then((r) => r.data);
export const deleteChannel = (id) =>
  api.delete(`/channels/${id}`).then((r) => r.data);

// --------- Repeater configs ---------
export const listRepeaterConfigs = () =>
  api.get("/repeater-configs").then((r) => r.data);
export const upsertRepeaterConfig = (repeaterId, body) =>
  api.put(`/repeater-configs/${repeaterId}`, body).then((r) => r.data);
export const deleteRepeaterConfig = (repeaterId) =>
  api.delete(`/repeater-configs/${repeaterId}`).then((r) => r.data);

// --------- Dispatcher ACL ---------
export const adminSetUserGroups = (id, allowed_group_ids) =>
  api.post(`/admin/users/${id}/groups`, { allowed_group_ids }).then((r) => r.data);

// --------- Shift log ---------
export const listShiftLog = (params = {}) =>
  api.get("/shift-log", { params }).then((r) => r.data);
export const shiftLogCsvUrl = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  const token = localStorage.getItem(TOKEN_KEY);
  return { url: `${API}/shift-log/export.csv${qs ? "?" + qs : ""}`, token };
};
export const clearShiftLog = () => api.delete("/shift-log").then((r) => r.data);

// --------- Radios / positions / packets ----------
export const fetchRadios = (opts = {}) => {
  const params = {};
  if (opts.groupId) params.group_id = opts.groupId;
  if (opts.channel) params.channel = opts.channel;
  return api.get("/radios", { params }).then((r) => r.data);
};
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

// ---- Auth ----
export const login = (email, password) =>
  api.post("/auth/login", { email, password }).then((r) => r.data);
export const register = (payload) =>
  api.post("/auth/register", payload).then((r) => r.data);
export const me = () => api.get("/auth/me").then((r) => r.data);

// ---- Admin ----
export const adminListUsers = () => api.get("/admin/users").then((r) => r.data);
export const adminApproveUser = (id) => api.post(`/admin/users/${id}/approve`).then((r) => r.data);
export const adminRejectUser = (id) => api.post(`/admin/users/${id}/reject`).then((r) => r.data);
export const adminSetRole = (id, role) => api.post(`/admin/users/${id}/role`, { role }).then((r) => r.data);
export const adminDeleteUser = (id) => api.delete(`/admin/users/${id}`).then((r) => r.data);

// ---- Geofences + alerts ----
export const listGeofences = () => api.get("/geofences").then((r) => r.data);
export const createGeofence = (body) => api.post("/geofences", body).then((r) => r.data);
export const deleteGeofence = (id) => api.delete(`/geofences/${id}`).then((r) => r.data);
export const listAlerts = (limit = 100) => api.get(`/alerts?limit=${limit}`).then((r) => r.data);
export const clearAlerts = () => api.delete("/alerts").then((r) => r.data);

// ---- Groups (talk groups) ----
export const listGroups = () => api.get("/groups").then((r) => r.data);
export const createGroup = (body) => api.post("/groups", body).then((r) => r.data);
export const updateGroup = (id, body) => api.patch(`/groups/${id}`, body).then((r) => r.data);
export const deleteGroup = (id) => api.delete(`/groups/${id}`).then((r) => r.data);

// ---- Messages ----
export const listMessages = (limit = 200) => api.get(`/messages?limit=${limit}`).then((r) => r.data);
export const sendMessage = (body) => api.post("/messages", body).then((r) => r.data);
export const simulateInboundMessage = (body) =>
  api.post("/messages/simulate-inbound", body).then((r) => r.data);

// ---- Voice ----
export const voiceStatus = () => api.get("/voice/status").then((r) => r.data);
export const voicePtt = (body) => api.post("/voice/ptt", body).then((r) => r.data);

// ---- Repeaters (MMDVMs) ----
export const listRepeaters = () => api.get("/repeaters").then((r) => r.data);

// ---- Emergencies ----
export const listEmergencies = (status = "active") =>
  api.get(`/emergencies?status_filter=${status}`).then((r) => r.data);
export const clearEmergency = (id) =>
  api.post(`/emergencies/${id}/clear`).then((r) => r.data);
export const simulateEmergency = (body) =>
  api.post("/emergencies/simulate", body).then((r) => r.data);

// ---- Situational awareness (admin CRUD) ----
export const listSituationalTokens = () =>
  api.get("/situational-tokens").then((r) => r.data);
export const createSituationalToken = (body) =>
  api.post("/situational-tokens", body).then((r) => r.data);
export const deleteSituationalToken = (id) =>
  api.delete(`/situational-tokens/${id}`).then((r) => r.data);

// ---- Situational awareness (public viewer, no auth) ----
export const fetchSituationalSnapshot = (token) =>
  axios.get(`${API}/situational/${token}/snapshot`).then((r) => r.data);
export const situationalWsUrl = (token) => {
  const url = new URL(BACKEND_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/api/situational/${token}/ws`;
  return url.toString();
};

// ---- Event overlays ----
export const listOverlays = (activeOnly = false) =>
  api
    .get(`/overlays${activeOnly ? "?active=true" : ""}`)
    .then((r) => r.data);
export const createOverlay = (name) =>
  api.post("/overlays", { name }).then((r) => r.data);
export const updateOverlay = (id, patch) =>
  api.patch(`/overlays/${id}`, patch).then((r) => r.data);
export const deleteOverlay = (id) =>
  api.delete(`/overlays/${id}`).then((r) => r.data);
export const replaceOverlayShapes = (id, shapes) =>
  api.put(`/overlays/${id}/shapes`, { shapes }).then((r) => r.data);
export const uploadOverlayImage = (id, form) =>
  api
    .post(`/overlays/${id}/images`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);
export const updateOverlayImage = (id, imageId, patch) =>
  api.patch(`/overlays/${id}/images/${imageId}`, patch).then((r) => r.data);
export const deleteOverlayImage = (id, imageId) =>
  api.delete(`/overlays/${id}/images/${imageId}`).then((r) => r.data);
export const uploadUrl = (relativePath) => {
  if (!relativePath) return "";
  if (relativePath.startsWith("http")) return relativePath;
  return `${BACKEND_URL}${relativePath}`;
};

export function apiErrorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (!detail) return err.message || "Something went wrong";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((d) => d.msg || JSON.stringify(d)).join(" · ");
  if (detail && typeof detail === "object" && detail.msg) return detail.msg;
  return JSON.stringify(detail);
}

export const getUpdateStatus = () => api.get("/admin/update/status").then((r) => r.data);
export const applyUpdate = () => api.post("/admin/update/apply").then((r) => r.data);
export const getUpdateJob = () => api.get("/admin/update/job").then((r) => r.data);

export const ackEmergency = (id) => api.post(`/emergencies/${id}/ack`).then((r) => r.data);
export const listGateways = () => api.get("/gateways").then((r) => r.data);
export const createGateway = (name) => api.post("/gateways", { name }).then((r) => r.data);
export const deleteGateway = (id) => api.delete(`/gateways/${id}`).then((r) => r.data);
export const voiceWsUrl = () => {
  const url = new URL(`${API}/voice/ws`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("token", localStorage.getItem(TOKEN_KEY) || "");
  return url.toString();
};
