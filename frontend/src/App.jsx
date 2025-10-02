import React, { useEffect, useState } from "react";
import { connectWebSocket, listSimulations } from "./api.js";
import RunView from "./components/RunView.jsx";
import Sidebar from "./components/Sidebar.jsx";

export default function App() {
  const [simulations, setSimulations] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [runUpdateKey, setRunUpdateKey] = useState(0);

  // Load simulations on mount and connect to WebSocket
  useEffect(() => {
    // Initial load of simulations from the backend
    loadSimulations();

    // Establish WebSocket connection for real-time updates
    const ws = connectWebSocket((message) => {
      // On receiving a WebSocket message, refresh the list of simulations
      // and trigger a potential refresh of the currently viewed run.
      loadSimulations();
      setRunUpdateKey((k) => k + 1);
    });

    // Cleanup function to close WebSocket when component unmounts
    return () => {
      ws.close();
    };
  }, []); // Empty dependency array ensures this effect runs only once on mount

  // Function to fetch simulations from the backend
  const loadSimulations = async () => {
    try {
      setLoading(true); // Set loading state to true
      const data = await listSimulations(); // Fetch simulations
      setSimulations(data.simulations || []); // Update simulations state
    } catch (err) {
      console.error("Failed to load simulations:", err); // Log any errors
    } finally {
      setLoading(false); // Set loading state to false
    }
  };

  // Callback for when a new simulation is created
  const handleSimulationCreated = (newSim) => {
    setSimulations((prev) => [newSim, ...prev]); // Add new simulation to the list
    // No auto-selection; user needs to create a run for the new simulation
  };

  // Callback for when a new run is created
  const handleRunCreated = (newRun) => {
    loadSimulations(); // Refresh simulations to update run counts
    setSelectedRunId(newRun.run_id); // Auto-select the newly created run
  };

  // Callback for when a run is updated (e.g., status change)
  const handleRunUpdated = (updatedRun) => {
    loadSimulations(); // Refresh simulations to reflect updated run status
  };

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Sidebar component for navigation and simulation/run listing */}
      <Sidebar
        simulations={simulations}
        selectedRunId={selectedRunId}
        onSelectRun={setSelectedRunId}
        onSimulationCreated={handleSimulationCreated}
        onRunCreated={handleRunCreated}
        loading={loading}
        onRefresh={loadSimulations}
      />

      {/* Main content area */}
      <main className="flex-1 p-6">
        {selectedRunId ? (
          // If a run is selected, display the RunView component
          <RunView
            key={selectedRunId} // Key ensures component re-mounts when selectedRunId changes
            runId={selectedRunId}
            onRunUpdated={handleRunUpdated}
            updateKey={runUpdateKey} // Key to force refresh based on WebSocket updates
          />
        ) : (
          // Display a welcome message if no run is selected
          <div className="text-center text-gray-500 mt-20">
            <h2 className="text-xl font-semibold mb-2">Welcome to KikoSim!</h2>
            <p>
              Create a simulation, then create runs to configure and execute
              simulations.
            </p>
            <div className="mt-4 text-sm text-gray-400">
              <p>• Simulations store your agent files and protocols</p>
              <p>• Runs contain configuration and execution results</p>
              <p>
                • Create multiple runs per simulation to test different configs
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
