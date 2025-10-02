const BASE_URL = "http://localhost:8080";

// ============================================================================
// SIMULATION APIs
// ============================================================================

export async function createSimulation(payload) {
  const res = await fetch(`${BASE_URL}/simulations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function listSimulations() {
  const res = await fetch(`${BASE_URL}/simulations`);
  return res.json();
}


// ============================================================================
// RUN APIs
// ============================================================================

export async function createRun(simulationId, payload = {}) {
  const res = await fetch(`${BASE_URL}/simulations/${simulationId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function getRun(runId) {
  const res = await fetch(`${BASE_URL}/runs/${runId}`);
  return res.json();
}

export async function getRunConfig(runId) {
  const res = await fetch(`${BASE_URL}/runs/${runId}/config`);
  return res.json();
}

export async function updateRunConfig(runId, configPatch) {
  const res = await fetch(`${BASE_URL}/runs/${runId}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(configPatch),
  });
  return res.json();
}

export async function executeRun(runId, opts) {
  const res = await fetch(`${BASE_URL}/runs/${runId}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  return res.json();
}

export async function getRunLogs(runId) {
  const res = await fetch(`${BASE_URL}/runs/${runId}/logs`);
  return res.json();
}

export async function exportRunLogsCSV(runId) {
  const res = await fetch(`${BASE_URL}/runs/${runId}/export/csv`);
  return res.text();
}

export function connectWebSocket(onMessageCallback) {
  const ws = new WebSocket(`ws://localhost:8080/ws`);

  ws.onopen = () => {
    // WebSocket connected
  };

  ws.onmessage = (event) => {
    onMessageCallback(JSON.parse(event.data));
  };

  ws.onclose = () => {
    // WebSocket disconnected
  };

  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
  };

  return ws;
}
