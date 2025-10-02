import React, { useState } from "react";
import { createRun } from "../api.js";
import FileUploadModal from "./FileUploadModal.jsx";

export default function Sidebar({
  simulations,
  selectedRunId,
  onSelectRun,
  onSimulationCreated,
  onRunCreated,
  loading,
  onRefresh,
}) {
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [expandedSimulations, setExpandedSimulations] = useState(new Set());
  const [creatingRuns, setCreatingRuns] = useState(new Set());
  const [isCollapsed, setIsCollapsed] = useState(false);

  const toggleSimulation = (simulationId) => {
    const newExpanded = new Set(expandedSimulations);
    if (newExpanded.has(simulationId)) {
      newExpanded.delete(simulationId);
    } else {
      newExpanded.add(simulationId);
    }
    setExpandedSimulations(newExpanded);
  };

  const handleCreateRun = async (simulationId) => {
    if (creatingRuns.has(simulationId)) return;

    const newCreating = new Set(creatingRuns);
    newCreating.add(simulationId);
    setCreatingRuns(newCreating);

    try {
      const run = await createRun(simulationId, {
        description: `Run ${new Date().toLocaleTimeString()}`,
      });

      onRunCreated(run);

      // Auto-expand the simulation to show the new run
      setExpandedSimulations((prev) => new Set([...prev, simulationId]));
    } catch (err) {
      console.error("Failed to create run:", err);
      alert("Failed to create run: " + err.message);
    } finally {
      const newCreating = new Set(creatingRuns);
      newCreating.delete(simulationId);
      setCreatingRuns(newCreating);
    }
  };

  const handleSimulationCreated = (newSim) => {
    onSimulationCreated(newSim);
    setShowUploadModal(false);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case "created":
        return "text-blue-600";
      case "configured":
        return "text-green-600";
      case "running":
        return "text-yellow-600";
      case "complete":
        return "text-green-700";
      case "failed":
        return "text-red-600";
      default:
        return "text-gray-600";
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case "created":
        return "📝";
      case "configured":
        return "⚙️";
      case "running":
        return "🏃";
      case "complete":
        return "✅";
      case "failed":
        return "❌";
      default:
        return "❓";
    }
  };

  return (
    <div
      className={`${
        isCollapsed ? "w-16" : "w-80"
      } bg-white border-r border-gray-200 flex flex-col transition-all duration-300`}
    >
      {/* Header */}
      <div
        className={`${
          isCollapsed ? "p-3" : "p-6"
        } border-b border-gray-200 flex items-center justify-between`}
      >
        {!isCollapsed && (
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <h1 className="text-xl font-bold text-gray-900">Simulations</h1>
              <div className="flex items-center gap-1">
                <button
                  onClick={onRefresh}
                  disabled={loading}
                  className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 disabled:opacity-50"
                  title="Refresh"
                >
                  <svg
                    className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                    />
                  </svg>
                </button>
                <button
                  onClick={() => setIsCollapsed(!isCollapsed)}
                  className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100"
                  title="Collapse sidebar"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M11 19l-7-7 7-7m8 14l-7-7 7-7"
                    />
                  </svg>
                </button>
              </div>
            </div>
            <p className="text-sm text-gray-500 mt-1">
              {simulations.length} simulation
              {simulations.length !== 1 ? "s" : ""}
            </p>
          </div>
        )}
        {isCollapsed && (
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-2 text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 mx-auto"
            title="Expand sidebar"
          >
            <svg
              className="w-4 h-4 transform rotate-180"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M11 19l-7-7 7-7m8 14l-7-7 7-7"
              />
            </svg>
          </button>
        )}
      </div>

      {/* Simulation List */}
      <div className={`flex-1 overflow-y-auto ${isCollapsed ? "hidden" : ""}`}>
        {simulations.map((sim) => (
          <div key={sim.simulation_id} className="border-b border-gray-100">
            {/* Simulation Header */}
            <div className="flex items-center p-3 hover:bg-gray-50">
              <button
                onClick={() => toggleSimulation(sim.simulation_id)}
                className="flex-1 flex items-center text-left"
              >
                <svg
                  className={`w-4 h-4 mr-2 transition-transform ${
                    expandedSimulations.has(sim.simulation_id)
                      ? "rotate-90"
                      : ""
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5l7 7-7 7"
                  />
                </svg>

                <div className="flex-1">
                  <div className="font-medium text-gray-900 truncate">
                    {sim.simulation_id}
                  </div>
                  <div className="text-xs text-gray-500">
                    {sim.agent_count} agents • {sim.run_count} runs
                  </div>
                  {sim.description && (
                    <div className="text-xs text-gray-500 truncate mt-1">
                      {sim.description}
                    </div>
                  )}
                </div>
              </button>

              <button
                onClick={() => handleCreateRun(sim.simulation_id)}
                disabled={creatingRuns.has(sim.simulation_id)}
                className="ml-2 p-1 text-blue-600 hover:text-blue-800 disabled:opacity-50"
                title="Create new run"
              >
                {creatingRuns.has(sim.simulation_id) ? (
                  <svg
                    className="w-4 h-4 animate-spin"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                    />
                  </svg>
                ) : (
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 4v16m8-8H4"
                    />
                  </svg>
                )}
              </button>
            </div>

            {/* Runs List (Collapsible) */}
            {expandedSimulations.has(sim.simulation_id) && (
              <div className="bg-gray-50">
                {sim.runs && sim.runs.length > 0 ? (
                  sim.runs.map((run) => (
                    <button
                      key={run.run_id}
                      onClick={() => onSelectRun(run.run_id)}
                      className={`w-full text-left p-3 pl-8 border-t border-gray-200 hover:bg-gray-100 transition-colors ${
                        selectedRunId === run.run_id
                          ? "bg-blue-50 border-l-4 border-l-blue-500"
                          : ""
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-gray-900 text-sm truncate">
                          {run.run_id}
                        </span>
                        <span className="text-lg">
                          {getStatusIcon(run.status)}
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-xs">
                        <span
                          className={`font-medium ${getStatusColor(
                            run.status
                          )}`}
                        >
                          {run.status}
                        </span>
                        {run.execution_time && (
                          <span className="text-gray-500">
                            {run.execution_time}s
                          </span>
                        )}
                      </div>

                      {run.description && (
                        <p className="text-xs text-gray-500 mt-1 truncate">
                          {run.description}
                        </p>
                      )}

                      <p className="text-xs text-gray-400 mt-1">
                        {new Date(run.created_at).toLocaleString()}
                      </p>
                    </button>
                  ))
                ) : (
                  <div className="p-3 pl-8 text-xs text-gray-500 italic border-t border-gray-200">
                    No runs yet
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* New Simulation Button */}
      <div
        className={`p-4 border-t border-gray-200 ${
          isCollapsed ? "hidden" : ""
        }`}
      >
        <button
          onClick={() => setShowUploadModal(true)}
          className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition-colors"
        >
          <span className="flex items-center justify-center">
            <svg
              className="w-4 h-4 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
            New Simulation
          </span>
        </button>
      </div>

      {/* File Upload Modal */}
      <FileUploadModal
        isOpen={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        onSimulationCreated={handleSimulationCreated}
      />
    </div>
  );
}
