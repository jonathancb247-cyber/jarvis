const state = {
  health: null,
  devices: [],
  selectedDeviceId: null,
  selectedDetail: null,
  selectedCapabilities: [],
  selectedState: null,
  isRefreshing: false,
  commandHistory: [],
  pollTimer: null,
};

const API_TIMEOUT_MS = 4500;
const POLL_INTERVAL_MS = 5000;

document.addEventListener("DOMContentLoaded", () => {
  bindNavigation();
  bindRefresh();
  bindSearch();
  bindCommandForm();
  refreshAll();
  startPolling();
});

window.addEventListener("beforeunload", () => {
  stopPolling();
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopPolling();
  } else {
    startPolling();
  }
});

const api = {
  getHealth: () => requestJson("/api/v1/health"),
  getDevices: () => requestJson("/api/v1/devices"),
  getDevice: (id) => requestJson(`/api/v1/devices/${encodeURIComponent(validateDeviceId(id))}`),
  getCapabilities: (id) => requestJson(`/api/v1/devices/${encodeURIComponent(validateDeviceId(id))}/capabilities`),
  getState: (id) => requestJson(`/api/v1/devices/${encodeURIComponent(validateDeviceId(id))}/state`),
  sendCommand: (input) => requestJson("/api/v1/commands", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input }),
  }),
};

async function requestJson(path, options = {}) {
  if (!path.startsWith("/api/v1/")) {
    throw new Error("Invalid API path");
  }
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      credentials: "same-origin",
    });
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("Unexpected API response");
    }
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(safeApiMessage(payload));
    }
    return payload;
  } finally {
    window.clearTimeout(timeout);
  }
}

function bindNavigation() {
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.viewTarget));
  });
}

function bindRefresh() {
  element("refreshButton").addEventListener("click", () => refreshAll());
  element("autoRefreshToggle").addEventListener("change", () => {
    if (element("autoRefreshToggle").checked) {
      startPolling();
    } else {
      stopPolling();
    }
  });
}

function bindSearch() {
  element("deviceSearch").addEventListener("input", () => renderDevices());
}

function bindCommandForm() {
  element("commandForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const command = element("commandInput").value.trim();
    if (command) {
      sendCommand(command);
    }
  });
}

function showView(viewName) {
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-visible", view.id === `${viewName}View`);
  });
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.viewTarget === viewName);
  });
}

async function refreshAll() {
  if (state.isRefreshing) {
    return;
  }
  state.isRefreshing = true;
  setConnection("loading", "Loading");
  try {
    const [health, devicesPayload] = await Promise.all([api.getHealth(), api.getDevices()]);
    state.health = health;
    state.devices = Array.isArray(devicesPayload.devices) ? devicesPayload.devices : [];
    renderOverview();
    renderDevices();
    if (state.selectedDeviceId) {
      await loadDeviceDetail(state.selectedDeviceId, false);
    }
    element("lastRefresh").textContent = `Last refresh: ${new Date().toLocaleTimeString()}`;
    setConnection("connected", "Connected");
  } catch (error) {
    setConnection("disconnected", "Disconnected");
    showCommandResult(`API connection failed: ${safeErrorText(error)}`, false);
  } finally {
    state.isRefreshing = false;
  }
}

async function loadDeviceDetail(deviceId, switchView = true) {
  try {
    validateDeviceId(deviceId);
    const [detail, capabilities, deviceState] = await Promise.all([
      api.getDevice(deviceId),
      api.getCapabilities(deviceId),
      api.getState(deviceId),
    ]);
    state.selectedDeviceId = deviceId;
    state.selectedDetail = detail;
    state.selectedCapabilities = Array.isArray(capabilities.capabilities) ? capabilities.capabilities : [];
    state.selectedState = deviceState;
    renderDetail();
    if (switchView) {
      showView("detail");
    }
  } catch (error) {
    showCommandResult(`Device detail failed: ${safeErrorText(error)}`, false);
  }
}

function renderOverview() {
  const health = state.health || {};
  element("runtimeStatus").textContent = health.status || "unknown";
  element("prototypeLabel").textContent = health.prototype || "Prototype unknown";
  element("deviceCount").textContent = String(state.devices.length);
  element("persistenceStatus").textContent = health.persistence_enabled ? "Persistence enabled" : "Persistence disabled";
  element("knownCount").textContent = String(countStatus("known"));
  element("staleCount").textContent = String(countStatus("stale"));
  element("unknownCount").textContent = String(countStatus("unknown"));
}

function renderDevices() {
  const list = element("deviceList");
  clear(list);
  const query = element("deviceSearch").value.trim().toLowerCase();
  const devices = state.devices.filter((device) => {
    const haystack = `${device.device_id || ""} ${device.name || ""} ${device.type || ""}`.toLowerCase();
    return haystack.includes(query);
  });
  element("emptyDevices").hidden = devices.length !== 0;
  devices.forEach((device) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "device-card";
    card.addEventListener("click", () => loadDeviceDetail(device.device_id));

    const title = document.createElement("span");
    title.className = "device-title";
    appendText(title, "strong", device.name || device.device_id || "Unnamed device");
    appendText(title, "span", device.device_id || "unknown id", "muted");

    const type = document.createElement("span");
    type.textContent = device.type || "unknown";

    const status = statusBadge(device.status, device.is_current);
    card.append(title, type, status);
    list.appendChild(card);
  });
}

function renderDetail() {
  const container = element("deviceDetail");
  clear(container);
  const detail = state.selectedDetail;
  const deviceState = state.selectedState || {};
  if (!detail) {
    appendText(container, "p", "Choose a device to inspect capabilities and state.", "muted");
    return;
  }
  element("detailTitle").textContent = detail.name || detail.device_id || "Device Detail";

  const grid = document.createElement("div");
  grid.className = "detail-grid";
  const info = panel("Device");
  appendKeyValue(info, "ID", detail.device_id);
  appendKeyValue(info, "Type", detail.type);
  appendKeyValue(info, "Status", detail.status);
  appendKeyValue(info, "Current", detail.is_current ? "yes" : "no");

  const semantic = panel("Semantic State");
  appendKeyValue(semantic, "Updated", deviceState.updated_at || detail.updated_at || "unknown");
  appendText(semantic, "p", "Stale means the last persisted state and does not confirm current device availability.", "muted");
  const properties = deviceState.semantic_properties || detail.semantic_properties || {};
  Object.keys(properties).sort().forEach((key) => appendKeyValue(semantic, key, String(properties[key])));
  if (Object.keys(properties).length === 0) {
    appendText(semantic, "p", "No semantic properties.", "muted");
  }

  grid.append(info, semantic);
  container.appendChild(grid);

  const caps = document.createElement("div");
  caps.className = "capability-list";
  state.selectedCapabilities.forEach((capability) => {
    caps.appendChild(renderCapability(capability, detail.device_id));
  });
  if (state.selectedCapabilities.length === 0) {
    appendText(caps, "p", "No formal capabilities.", "muted");
  }
  container.appendChild(caps);
}

function renderCapability(capability, deviceId) {
  const card = document.createElement("article");
  card.className = "capability-card";
  appendText(card, "h3", capability.name || "Unnamed capability");
  appendText(card, "p", `Kind: ${capability.kind || "unknown"}`, "muted");
  appendText(card, "p", `Parameters: ${describeParameters(capability.parameters)}`, "muted");
  const actions = document.createElement("div");
  actions.className = "capability-actions";
  controlsForCapability(capability, deviceId).forEach((control) => actions.appendChild(control));
  card.appendChild(actions);
  return card;
}

function controlsForCapability(capability, deviceId) {
  const controls = [];
  if (capability.kind === "action" && capability.name === "power.switch" && hasStateParameter(capability)) {
    controls.push(commandButton("Turn on", buildCapabilityCommand(deviceId, capability, "true"), true));
    controls.push(commandButton("Turn off", buildCapabilityCommand(deviceId, capability, "false"), true));
    return controls;
  }
  if (capability.kind === "reading") {
    controls.push(commandButton("Read", buildCapabilityCommand(deviceId, capability), false));
    return controls;
  }
  controls.push(templateButton("Copy template", `device apply ${deviceId} ${capability.name}`));
  return controls;
}

function buildCapabilityCommand(deviceId, capability, stateValue) {
  validateDeviceId(deviceId);
  if (capability.kind === "reading") {
    return `device read ${deviceId} ${capability.name}`;
  }
  if (capability.name === "power.switch") {
    return `device apply ${deviceId} ${capability.name} state=${stateValue}`;
  }
  return `device apply ${deviceId} ${capability.name}`;
}

function commandButton(label, command, requiresConfirmation) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = requiresConfirmation ? "button" : "button button-secondary";
  button.textContent = label;
  button.addEventListener("click", () => {
    if (requiresConfirmation && !window.confirm(`Send command: ${command}`)) {
      return;
    }
    element("commandInput").value = command;
    sendCommand(command);
  });
  return button;
}

function templateButton(label, command) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "button button-secondary";
  button.textContent = label;
  button.addEventListener("click", () => {
    element("commandInput").value = command;
    showView("console");
  });
  return button;
}

async function sendCommand(command) {
  if (command.includes("\n") || command.includes("\r")) {
    showCommandResult("Only one canonical command is allowed.", false);
    return;
  }
  const button = element("sendCommandButton");
  button.disabled = true;
  showCommandResult(`Sending: ${command}`, true);
  try {
    const result = await api.sendCommand(command);
    addHistory(command, result.success);
    showCommandResult(result.message || "Command completed.", Boolean(result.success));
    await refreshAll();
  } catch (error) {
    addHistory(command, false);
    showCommandResult(`Command failed: ${safeErrorText(error)}`, false);
  } finally {
    button.disabled = false;
  }
}

function startPolling() {
  if (!element("autoRefreshToggle").checked || state.pollTimer || document.hidden) {
    return;
  }
  state.pollTimer = window.setInterval(() => refreshAll(), POLL_INTERVAL_MS);
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function countStatus(status) {
  return state.devices.filter((device) => device.status === status).length;
}

function setConnection(kind, text) {
  const status = element("connectionStatus");
  status.className = `connection-badge ${kind}`;
  status.textContent = text;
}

function statusBadge(status, isCurrent) {
  const badge = document.createElement("span");
  badge.className = `status-badge ${status || "unknown"}`;
  badge.textContent = `${status || "unknown"} · ${isCurrent ? "current" : "not current"}`;
  return badge;
}

function panel(title) {
  const wrapper = document.createElement("div");
  wrapper.className = "info-panel";
  appendText(wrapper, "h3", title);
  return wrapper;
}

function appendKeyValue(parent, key, value) {
  const row = document.createElement("p");
  const label = document.createElement("strong");
  label.textContent = `${key}: `;
  row.appendChild(label);
  row.appendChild(document.createTextNode(value || "unknown"));
  parent.appendChild(row);
}

function appendText(parent, tag, text, className) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  node.textContent = text;
  parent.appendChild(node);
  return node;
}

function clear(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function element(id) {
  return document.getElementById(id);
}

function describeParameters(parameters) {
  const entries = Object.entries(parameters || {});
  if (entries.length === 0) {
    return "none";
  }
  return entries.map(([name, descriptor]) => {
    const required = descriptor && descriptor.required ? "required" : "optional";
    const type = descriptor && descriptor.type ? descriptor.type : "unknown";
    return `${name} (${type}, ${required})`;
  }).join(", ");
}

function hasStateParameter(capability) {
  return Boolean(capability.parameters && capability.parameters.state && capability.parameters.state.required);
}

function addHistory(command, success) {
  state.commandHistory.unshift({ command, success });
  state.commandHistory = state.commandHistory.slice(0, 6);
  const list = element("commandHistory");
  clear(list);
  state.commandHistory.forEach((item) => {
    const row = document.createElement("li");
    row.textContent = `${item.success ? "OK" : "Failed"} — ${item.command}`;
    list.appendChild(row);
  });
}

function showCommandResult(message, success) {
  const panelNode = element("commandResult");
  panelNode.textContent = message;
  panelNode.classList.toggle("status-badge", false);
  panelNode.style.borderColor = success ? "rgba(34, 197, 94, 0.55)" : "rgba(239, 68, 68, 0.65)";
}

function validateDeviceId(deviceId) {
  if (typeof deviceId !== "string" || !/^[A-Za-z0-9_.-]{1,128}$/.test(deviceId)) {
    throw new Error("Invalid device id");
  }
  return deviceId;
}

function safeApiMessage(payload) {
  if (payload && typeof payload.message === "string") {
    return payload.message;
  }
  if (payload && typeof payload.error === "string") {
    return payload.error;
  }
  return "API request failed";
}

function safeErrorText(error) {
  if (error && typeof error.message === "string") {
    return error.message.slice(0, 160);
  }
  return "Request failed";
}
