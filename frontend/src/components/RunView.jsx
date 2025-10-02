import React, { useEffect, useRef, useState } from "react";
import {
  executeRun,
  exportRunLogsCSV,
  getRun,
  getRunConfig,
  getRunLogs,
  updateRunConfig,
} from "../api.js";
import ConfigurationModal from "./ConfigurationModal.jsx";

// Configuration summary component (minimized)
function ConfigSummary({ config }) {
  const agentPoolCount = Object.keys(config.AGENT_POOLS || {}).length;
  const taskSettingsCount = Object.keys(config.TASK_SETTINGS || {}).length;

  return (
    <div className="grid grid-cols-2 gap-4 text-sm">
      <div className="bg-white p-3 rounded border">
        <div className="text-gray-500 text-xs uppercase tracking-wide">
          Agent Pools
        </div>
        <div className="text-lg font-semibold text-gray-900">
          {agentPoolCount}
        </div>
        <div className="text-xs text-gray-500">
          {Object.entries(config.AGENT_POOLS || {}).map(
            ([principal, pools]) => (
              <div key={principal}>
                {principal}: {pools.length} pool(s)
              </div>
            )
          )}
        </div>
      </div>

      <div className="bg-white p-3 rounded border">
        <div className="text-gray-500 text-xs uppercase tracking-wide">
          Task Settings
        </div>
        <div className="text-lg font-semibold text-gray-900">
          {taskSettingsCount}
        </div>
        <div className="text-xs text-gray-500">
          {Object.entries(config.TASK_SETTINGS || {})
            .slice(0, 2)
            .map(([task, [agent, duration]]) => {
              // Convert days to appropriate display unit
              let displayValue, unit;
              if (duration >= 1) {
                displayValue = duration;
                unit = duration === 1 ? "day" : "days";
              } else if (duration >= 1 / 24) {
                displayValue = Math.round(duration * 24 * 10) / 10;
                unit = displayValue === 1 ? "hour" : "hours";
              } else {
                displayValue = Math.round(duration * 24 * 60);
                unit = displayValue === 1 ? "minute" : "minutes";
              }

              return (
                <div key={task}>
                  {task}: {displayValue} {unit}
                </div>
              );
            })}
          {taskSettingsCount > 2 && (
            <div>... and {taskSettingsCount - 2} more</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function RunView({ runId, onRunUpdated, updateKey }) {
  const [run, setRun] = useState(null);
  const [config, setConfig] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [maxRounds, setMaxRounds] = useState(200);
  const [executionStartTime, setExecutionStartTime] = useState(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [virtualTimeStatus, setVirtualTimeStatus] = useState(null);

  // Log viewer state
  const [filterAgent, setFilterAgent] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  // Single dropdown for log filter mode
  // Modes: all, only_time, only_resource, only_both, hide_time, hide_resource, hide_both, business_protocol
  const [logFilterMode, setLogFilterMode] = useState("all");
  const logViewerRef = useRef(null);

  // Collapsible state for config and execution sections
  const [configCollapsed, setConfigCollapsed] = useState(false);
  const [executionCollapsed, setExecutionCollapsed] = useState(false);
  // Track if user manually toggled collapse (prevents auto-collapse override)
  const userToggledConfig = useRef(false);
  const userToggledExecution = useRef(false);

  // Auto-collapse when running, unless user manually toggled
  useEffect(() => {
    if (running) {
      if (!userToggledConfig.current) setConfigCollapsed(true);
      if (!userToggledExecution.current) setExecutionCollapsed(true);
    } else {
      if (!userToggledConfig.current) setConfigCollapsed(false);
      if (!userToggledExecution.current) setExecutionCollapsed(false);
    }
  }, [running]);

  // Load run data
  useEffect(() => {
    if (runId) {
      loadRun();
    }
  }, [runId, updateKey]);

  // Auto-scroll logs to bottom only when new logs are added
  const prevLogsLengthRef = useRef(0);
  useEffect(() => {
    if (logViewerRef.current && logs.length > prevLogsLengthRef.current) {
      // Only scroll if new logs are added
      logViewerRef.current.scrollTop = logViewerRef.current.scrollHeight;
    }
    prevLogsLengthRef.current = logs.length;
  }, [logs]);

  // Timer for running simulation
  useEffect(() => {
    let timer;
    if (running && executionStartTime) {
      timer = setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - executionStartTime) / 1000));
      }, 1000);
    } else {
      setElapsedTime(0);
    }
    return () => clearInterval(timer);
  }, [running, executionStartTime]);

  // Poll virtual time status when running
  useEffect(() => {
    let statusTimer;
    if (running && runId) {
      const fetchStatus = async () => {
        try {
          const response = await fetch(
            `http://localhost:8080/runs/${runId}/status`
          );
          if (response.ok) {
            const statusData = await response.json();
            setVirtualTimeStatus(statusData.virtual_time_status);
            // Update maxRounds if it's available from the run
            if (statusData.max_rounds) {
              setMaxRounds(statusData.max_rounds);
            }
          }
        } catch (err) {
          console.warn("Failed to fetch virtual time status:", err);
        }
      };

      // Fetch immediately and then every 2 seconds
      fetchStatus();
      statusTimer = setInterval(fetchStatus, 2000);
    } else {
      setVirtualTimeStatus(null);
    }

    return () => clearInterval(statusTimer);
  }, [running, runId]);

  const loadRun = async () => {
    try {
      setLoading(true);
      const runData = await getRun(runId);
      setRun(runData);
      onRunUpdated(runData);

      // Update running state based on fetched runData
      setRunning(runData.status === "running");

      // Load config if available
      if (runData.has_config) {
        try {
          const configResponse = await getRunConfig(runId);
          setConfig(configResponse.config);
        } catch (err) {
          console.warn("Could not load config:", err);
        }
      }

      // Load logs if completed, failed, or timed out
      if (
        runData.status === "complete" ||
        runData.status === "failed" ||
        runData.status === "timed_out"
      ) {
        try {
          const logsData = await getRunLogs(runId);
          setLogs(logsData.logs || []);
        } catch (err) {
          console.warn("Could not load logs:", err);
        }
      }
    } catch (err) {
      console.error("Failed to load run:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteRun = async () => {
    if (running || run?.status === "running") return;

    setRunning(true);
    setExecutionStartTime(Date.now());
    setElapsedTime(0);
    try {
      await executeRun(runId, {
        max_rounds: maxRounds,
      });
      // No more polling here, WebSocket will trigger updates
    } catch (err) {
      console.error("Failed to execute run:", err);
      alert("Failed to execute run: " + err.message);
    }
  };

  const handleConfigSave = async (newConfig) => {
    try {
      await updateRunConfig(runId, newConfig);

      // Reload the config to get the updated version
      const configResponse = await getRunConfig(runId);
      setConfig(configResponse.config);

      setShowConfigModal(false);
      alert("Configuration updated successfully!");
    } catch (err) {
      console.error("Failed to update config:", err);
      alert("Failed to update configuration: " + err.message);
    }
  };

  const handleDuplicateRun = async () => {
    if (!config) {
      alert("Configuration is not loaded yet. Please wait and try again.");
      return;
    }

    try {
      const newRunDescription = prompt(
        `Enter a description for the new run (a copy of the configuration from this run will be used):`,
        `Duplicate of ${run.run_id}`
      );

      if (!newRunDescription) {
        return; // User cancelled the prompt
      }

      // Pass the current config when creating the new run.
      const response = await fetch(
        `http://localhost:8080/simulations/${run.simulation_id}/runs`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            description: newRunDescription,
            config: config,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          `Failed to create duplicate run: ${
            errorData.detail || response.statusText
          }`
        );
      }

      const newRun = await response.json();

      alert(
        `Created duplicate run: ${newRun.run_id}. You can find it in the runs list.`
      );

      // Notify parent to refresh run list
      if (onRunUpdated) {
        onRunUpdated();
      }
    } catch (err) {
      console.error("Failed to duplicate run:", err);
      alert(err.message);
    }
  };

  const handleCopyLogs = () => {
    if (logs.length === 0) {
      alert("No logs to copy.");
      return;
    }

    // Format logs into a readable plain text format
    const logText = logs
      .map((log) => {
        const meta = [
          `[${log.timestamp}]`,
          `[${log.agent}]`,
          log.order_id ? `[Order: ${log.order_id}]` : "",
          log.task_id ? `[Task: ${log.task_id}]` : "",
        ]
          .filter(Boolean)
          .join(" ");

        // Indent subsequent lines of a multi-line message for readability
        const message = log.message.replace(/\\n/g, "\\n    ");

        return `${meta} - ${message}`;
      })
      .join("\\n");

    navigator.clipboard
      .writeText(logText)
      .then(() => {
        alert("Logs copied to clipboard!");
      })
      .catch((err) => {
        console.error("Failed to copy logs:", err);
        alert("Failed to copy logs. See console for details.");
      });
  };

  const handleExportCSV = async () => {
    try {
      const response = await exportRunLogsCSV(runId);
      if (response.success) {
        const blob = new Blob([response.csv_data], { type: "text/csv" });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `run_${runId}_logs.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
      } else {
        alert("Failed to export logs to CSV.");
      }
    } catch (err) {
      console.error("Failed to export logs to CSV:", err);
      alert("Failed to export logs to CSV. See console for details.");
    }
  };

  // Smart detection of business vs resource agents
  const getAgentCategories = () => {
    const agentStats = {};

    logs.forEach((log) => {
      const agent = log.agent.toLowerCase();
      if (!agentStats[agent]) {
        agentStats[agent] = {
          businessKeywords: 0,
          resourceKeywords: 0,
          timeKeywords: 0,
          totalLogs: 0,
        };
      }

      const message = log.message.toLowerCase();
      agentStats[agent].totalLogs++;

      // Business protocol indicators
      if (
        message.includes("sent") ||
        message.includes("enactment finished") ||
        message.includes("marketorder") ||
        message.includes("retailorder") ||
        message.includes("orderrequest") ||
        message.includes("orderresponse")
      ) {
        agentStats[agent].businessKeywords++;
      }

      // Resource management indicators
      if (
        message.includes("givetask") ||
        message.includes("completetask") ||
        message.includes("scheduled task")
      ) {
        agentStats[agent].resourceKeywords++;
      }

      // Time management indicators
      if (
        message.includes("timeupdate") ||
        message.includes("passivate") ||
        message.includes("hold") ||
        message.includes("timeservice")
      ) {
        agentStats[agent].timeKeywords++;
      }
    });

    const businessAgents = [];
    const resourceAgents = [];
    const timeAgents = [];

    Object.entries(agentStats).forEach(([agent, stats]) => {
      const businessRatio = stats.businessKeywords / stats.totalLogs;
      const resourceRatio = stats.resourceKeywords / stats.totalLogs;
      const timeRatio = stats.timeKeywords / stats.totalLogs;

      // Smart categorization based on log content patterns
      if (businessRatio > 0.1 && agent.startsWith("ra_") === false) {
        businessAgents.push(agent);
      } else if (resourceRatio > 0.1 || agent.startsWith("ra_")) {
        resourceAgents.push(agent);
      } else if (timeRatio > 0.3 || agent.includes("timeservice")) {
        timeAgents.push(agent);
      } else if (!agent.startsWith("ra_") && !agent.includes("timeservice")) {
        // Default: non-RA, non-TimeService agents are likely business agents
        businessAgents.push(agent);
      }
    });

    return { businessAgents, resourceAgents, timeAgents };
  };

  const handleExportBusinessCSV = async () => {
    try {
      const csvData = await exportRunLogsCSV(runId);

      // Download CSV file
      const blob = new Blob([csvData], { type: "text/csv" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `run_${runId}_business_protocol.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();

      alert("Business protocol logs exported successfully for Disco analysis.");
    } catch (err) {
      console.error("Failed to export business protocol logs:", err);
      alert(
        "Failed to export business protocol logs. See console for details."
      );
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading run...</p>
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="text-center text-gray-500 mt-20">
        <p>Run not found</p>
      </div>
    );
  }

  const getStatusBadge = (status) => {
    const colors = {
      created: "bg-blue-100 text-blue-800",
      configured: "bg-green-100 text-green-800",
      running: "bg-yellow-100 text-yellow-800",
      complete: "bg-green-100 text-green-800",
      failed: "bg-red-100 text-red-800",
      timed_out: "bg-orange-100 text-orange-800",
    };

    return (
      <span
        className={`px-2 py-1 rounded-full text-xs font-medium ${
          colors[status] || "bg-gray-100 text-gray-800"
        }`}
      >
        {status}
      </span>
    );
  };

  const canExecute = run.status === "configured" && !running;
  const canEditConfig = run.status === "configured" && !running;
  const isRunning = run.status === "running" || running;

  const uniqueAgents = [...new Set(logs.map((log) => log.agent))];

  const filteredLogs = logs.filter((log) => {
    const agentMatch = filterAgent === "all" || log.agent === filterAgent;
    const searchTermMatch = log.message
      .toLowerCase()
      .includes(searchTerm.toLowerCase());

    // Time management filter
    const timeManagementKeywords = [
      "self reminder",
      "passiv",
      "hold",
      "timeservice",
      "timeupdate",
      "virtual time",
      "initiator",
      "specific time",
      "round",
      "participating agents",
      "next action",
      "starting",
      "debug",
      "ending",
      "identified",
    ];
    const isTimeManagementLog = timeManagementKeywords.some((keyword) =>
      log.message.toLowerCase().includes(keyword.toLowerCase())
    );
    // Resource management filter
    const resourceManagementKeywords = [
      "givetask",
      "completetask",
      "scheduled task",
    ];
    const isResourceManagementLog = resourceManagementKeywords.some((keyword) =>
      log.message.toLowerCase().includes(keyword)
    );

    // Single dropdown filter logic
    let logFilterMatch = true;
    switch (logFilterMode) {
      case "all":
        logFilterMatch = true;
        break;
      case "only_time":
        logFilterMatch = isTimeManagementLog;
        break;
      case "only_resource":
        logFilterMatch = isResourceManagementLog;
        break;
      case "only_both":
        logFilterMatch = isTimeManagementLog && isResourceManagementLog;
        break;
      case "hide_time":
        logFilterMatch = !isTimeManagementLog;
        break;
      case "hide_resource":
        logFilterMatch = !isResourceManagementLog;
        break;
      case "hide_both":
        logFilterMatch = !isTimeManagementLog && !isResourceManagementLog;
        break;
      case "business_protocol":
        // Show only business protocol logs using smart detection
        const { businessAgents: smartBusinessAgents } = getAgentCategories();
        const isSmartBusinessAgent = smartBusinessAgents.includes(
          log.agent.toLowerCase()
        );
        const message = log.message.toLowerCase();
        const isImportantLog =
          message.includes("sent") ||
          message.includes("enactment finished") ||
          message.includes("marketorder") ||
          message.includes("retailorder") ||
          message.includes("orderrequest") ||
          message.includes("orderresponse");
        logFilterMatch =
          isSmartBusinessAgent &&
          isImportantLog &&
          !isTimeManagementLog &&
          !isResourceManagementLog;
        break;
      default:
        logFilterMatch = true;
    }

    // Only show logs that pass all filters
    return agentMatch && searchTermMatch && logFilterMatch;
  });

  const firstLog = logs.length > 0 ? logs[0] : null;
  const lastLog = logs.length > 0 ? logs[logs.length - 1] : null;

  return (
    <div className="max-w-none mx-4 lg:mx-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-2xl font-bold text-gray-900">Run {run.run_id}</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDuplicateRun}
              className="px-3 py-1 text-sm bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
            >
              Duplicate
            </button>
            {getStatusBadge(run.status)}
          </div>
        </div>

        {run.description && <p className="text-gray-600">{run.description}</p>}

        <div className="flex items-center gap-4 text-sm text-gray-500 mt-2">
          <span>Simulation: {run.simulation_id}</span>
          <span>Created: {new Date(run.created_at).toLocaleString()}</span>
          {run.execution_time && (
            <span>Executed in: {run.execution_time}s</span>
          )}
        </div>
      </div>

      {/* Configuration Display (Minimized) */}
      {config && (
        <div className="bg-white rounded-lg shadow mb-6">
          <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-gray-900">
                Configuration
              </h2>
              <button
                onClick={() => {
                  setConfigCollapsed((prev) => !prev);
                  userToggledConfig.current = true;
                }}
                className="ml-2 px-2 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
              >
                {configCollapsed ? "Show" : "Hide"}
              </button>
            </div>
            {canEditConfig && !configCollapsed && (
              <button
                onClick={() => setShowConfigModal(true)}
                className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Configure
              </button>
            )}
            {!canEditConfig && !configCollapsed && (
              <span className="text-xs text-gray-500">
                🔒{" "}
                {run.status === "running"
                  ? "Locked during execution"
                  : "Locked after execution"}
              </span>
            )}
          </div>

          {!configCollapsed && (
            <div className="p-6 bg-gray-50">
              <ConfigSummary config={config} />
            </div>
          )}
        </div>
      )}

      {/* Execution Section */}
      <div className="bg-white rounded-lg shadow mb-6">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-gray-900">Execute Run</h2>
            <button
              onClick={() => {
                setExecutionCollapsed((prev) => !prev);
                userToggledExecution.current = true;
              }}
              className="ml-2 px-2 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
            >
              {executionCollapsed ? "Show" : "Hide"}
            </button>
          </div>
        </div>

        {!executionCollapsed && (
          <div className="p-6">
            <div className="space-y-4">
              {/* Max Rounds Setting */}
              <div className="flex items-center gap-4">
                <label className="text-sm font-medium text-gray-700">
                  Max Rounds:
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={maxRounds}
                    onChange={(e) =>
                      setMaxRounds(parseInt(e.target.value) || 200)
                    }
                    disabled={isRunning}
                    min="1"
                    max="1000"
                    className="w-20 px-3 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                  />
                  <span className="text-sm text-gray-700">rounds</span>
                </div>
                <span className="text-xs text-gray-500">
                  Number of virtual time rounds to simulate (1-1000 rounds)
                </span>
              </div>

              {/* Execute Button and Status */}
              <div className="flex items-center gap-4">
                <button
                  onClick={handleExecuteRun}
                  disabled={!canExecute}
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                >
                  {running ? "Running..." : "Execute Run"}
                </button>

                {/* Virtual Time Progress and Timer */}
                {running && (
                  <div className="flex items-center gap-3 flex-grow justify-end">
                    {/* Virtual Time Display */}
                    {virtualTimeStatus && (
                      <div className="flex items-center gap-3">
                        <div className="text-sm font-mono text-gray-600">
                          Round {virtualTimeStatus.current_round}/
                          {virtualTimeStatus.max_rounds}
                        </div>
                        <div className="w-40 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                            style={{
                              width: `${virtualTimeStatus.progress_percentage}%`,
                            }}
                          ></div>
                        </div>
                        <div className="text-sm text-gray-500">
                          {virtualTimeStatus.progress_percentage.toFixed(1)}%
                        </div>
                      </div>
                    )}

                    {/* Fallback: show elapsed time if no virtual time status */}
                    {!virtualTimeStatus && (
                      <div className="flex items-center gap-3">
                        <div className="text-sm font-mono text-gray-600">
                          {new Date(elapsedTime * 1000)
                            .toISOString()
                            .substr(14, 5)}
                        </div>
                        <div className="w-40 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="bg-yellow-500 h-2 rounded-full"
                            style={{
                              width: `${Math.min(
                                100,
                                (elapsedTime / 30) * 100
                              )}%`,
                            }}
                          ></div>
                        </div>
                        <div className="text-sm text-gray-500">Starting...</div>
                      </div>
                    )}
                  </div>
                )}

                {/* Spacer to keep rounds input on the right */}
                {!running && <div className="flex-grow"></div>}

                {run.status === "failed" && run.error_message && (
                  <div className="text-sm text-red-600">
                    Error: {run.error_message}
                  </div>
                )}
              </div>

              {run.error_message && (
                <div className="mt-4 p-4 bg-red-50 text-red-700 rounded-lg border border-red-200">
                  <p className="font-semibold">Error Details:</p>
                  <pre className="text-xs whitespace-pre-wrap">
                    {run.error_message}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Virtual Time Status Section */}
      {virtualTimeStatus && running && (
        <div className="bg-white rounded-lg shadow mb-6">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">
              Virtual Time Progress
            </h2>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-blue-50 p-4 rounded-lg">
                <div className="text-sm text-blue-600 font-medium">
                  Current Round
                </div>
                <div className="text-2xl font-bold text-blue-900">
                  {virtualTimeStatus.current_round}
                </div>
                <div className="text-sm text-blue-600">
                  of {virtualTimeStatus.max_rounds}
                </div>
              </div>

              <div className="bg-green-50 p-4 rounded-lg">
                <div className="text-sm text-green-600 font-medium">
                  Progress
                </div>
                <div className="text-2xl font-bold text-green-900">
                  {virtualTimeStatus.progress_percentage.toFixed(1)}%
                </div>
                <div className="text-sm text-green-600">Complete</div>
              </div>

              <div className="bg-purple-50 p-4 rounded-lg">
                <div className="text-sm text-purple-600 font-medium">
                  Virtual Time
                </div>
                <div className="text-2xl font-bold text-purple-900">
                  {Math.floor(virtualTimeStatus.current_virtual_time)}
                </div>
                <div className="text-sm text-purple-600">Days</div>
              </div>

              <div className="bg-orange-50 p-4 rounded-lg">
                <div className="text-sm text-orange-600 font-medium">
                  Active Agents
                </div>
                <div className="text-2xl font-bold text-orange-900">
                  {Object.keys(virtualTimeStatus.agent_activity || {}).length}
                </div>
                <div className="text-sm text-orange-600">Logging</div>
              </div>
            </div>

            {/* Agent Activity */}
            {virtualTimeStatus.agent_activity &&
              Object.keys(virtualTimeStatus.agent_activity).length > 0 && (
                <div className="mt-6">
                  <h3 className="text-sm font-medium text-gray-700 mb-3">
                    Agent Activity
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                    {Object.entries(virtualTimeStatus.agent_activity).map(
                      ([agent, count]) => (
                        <div
                          key={agent}
                          className="bg-gray-50 px-3 py-2 rounded text-sm"
                        >
                          <div className="font-medium">{agent}</div>
                          <div className="text-gray-600">{count} messages</div>
                        </div>
                      )
                    )}
                  </div>
                </div>
              )}

            {/* Recent Activity */}
            {virtualTimeStatus.recent_activity &&
              virtualTimeStatus.recent_activity.length > 0 && (
                <div className="mt-6">
                  <h3 className="text-sm font-medium text-gray-700 mb-3">
                    Recent Activity
                  </h3>
                  <div className="bg-gray-50 p-3 rounded font-mono text-xs">
                    {virtualTimeStatus.recent_activity
                      .slice(0, 3)
                      .map((activity, idx) => (
                        <div key={idx} className="text-gray-700">
                          {activity}
                        </div>
                      ))}
                  </div>
                </div>
              )}
          </div>
        </div>
      )}

      {/* Logs Section */}
      {logs.length > 0 && (
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <div className="flex justify-between items-center">
              <div className="flex items-center space-x-4">
                <h2 className="text-lg font-semibold text-gray-900">Logs</h2>
                <span className="text-sm text-gray-500">
                  (Showing {filteredLogs.length} of {logs.length} entries)
                </span>
              </div>
              <div className="flex items-center space-x-4">
                <select
                  value={filterAgent}
                  onChange={(e) => setFilterAgent(e.target.value)}
                  className="px-3 py-1 border border-gray-300 rounded text-sm"
                >
                  <option value="all">All Agents</option>
                  {uniqueAgents.map((agent) => (
                    <option key={agent} value={agent}>
                      {agent}
                    </option>
                  ))}
                </select>
                <input
                  type="text"
                  placeholder="Search logs..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="px-3 py-1 border border-gray-300 rounded text-sm"
                />
                {/* Single dropdown for log filter mode */}
                <label className="flex items-center space-x-2 text-sm text-gray-700">
                  <span>Log filter:</span>
                  <select
                    value={logFilterMode}
                    onChange={(e) => setLogFilterMode(e.target.value)}
                    className="px-2 py-1 border border-gray-300 rounded text-sm"
                  >
                    <option value="all">Show all logs</option>
                    <option value="only_time">Only time management</option>
                    <option value="only_resource">
                      Only resource management
                    </option>
                    <option value="only_both">
                      Only time & resource management
                    </option>
                    <option value="hide_time">Hide time management</option>
                    <option value="hide_resource">
                      Hide resource management
                    </option>
                    <option value="hide_both">Hide both</option>
                  </select>
                </label>
                <button
                  onClick={handleCopyLogs}
                  className="px-3 py-1 text-sm bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                >
                  Copy Logs
                </button>
                <div className="flex space-x-2">
                  <button
                    onClick={handleExportBusinessCSV}
                    className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700 font-medium"
                    title="Export only business protocol logs for Disco analysis"
                  >
                    📊 Export Business Protocol
                  </button>
                  <button
                    onClick={handleExportCSV}
                    className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                    title="Export all filtered logs (backend processed)"
                  >
                    📄 Export All Logs
                  </button>
                </div>
              </div>
            </div>
            {firstLog && lastLog && (
              <div className="mt-2 pt-2 border-t border-gray-100 text-sm text-gray-600 font-mono">
                <span>First Log: {firstLog.timestamp}</span>
                <span className="mx-2 text-gray-400">|</span>
                <span>Last Log: {lastLog.timestamp}</span>
              </div>
            )}
          </div>

          <div
            ref={logViewerRef}
            className="p-6 h-96 overflow-y-auto font-mono text-xs bg-gray-900 text-white"
          >
            {filteredLogs.length > 0 ? (
              filteredLogs.map((log, index) => (
                <div key={index} className="flex items-start gap-3">
                  <span className="text-gray-500 w-40 shrink-0 text-right">
                    {log.timestamp}
                  </span>
                  <span className="text-blue-400 w-40 shrink-0">
                    [{log.agent}]
                  </span>
                  <span className="flex-1 whitespace-pre-wrap ml-auto">
                    {log.message}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-gray-500">No logs match your criteria.</div>
            )}
          </div>
        </div>
      )}

      {/* Configuration Modal */}
      <ConfigurationModal
        isOpen={showConfigModal}
        onClose={() => setShowConfigModal(false)}
        config={config}
        onSave={handleConfigSave}
      />
    </div>
  );
}
