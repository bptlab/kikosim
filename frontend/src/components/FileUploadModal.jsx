import React, { useState } from "react";
import { createSimulation } from "../api.js";

export default function FileUploadModal({
  isOpen,
  onClose,
  onSimulationCreated,
}) {
  const [files, setFiles] = useState({
    bspl: null,
    agents: [],
  });
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  const handleBsplUpload = (event) => {
    const file = event.target.files[0];
    if (file) {
      setFiles((prev) => ({ ...prev, bspl: file }));
    }
  };

  const handleAgentUpload = (event) => {
    const newFiles = Array.from(event.target.files);
    setFiles((prev) => ({
      ...prev,
      agents: [...prev.agents, ...newFiles],
    }));
  };

  const removeAgentFile = (index) => {
    setFiles((prev) => ({
      ...prev,
      agents: prev.agents.filter((_, i) => i !== index),
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!files.bspl || files.agents.length === 0) {
      setError("Please upload both a BSPL file and at least one agent file");
      return;
    }

    setCreating(true);
    setError(null);

    try {
      // Read file contents
      const bsplContent = await readFileContent(files.bspl);
      const agentContents = {};

      for (const agentFile of files.agents) {
        const content = await readFileContent(agentFile);
        agentContents[agentFile.name] = content;
      }

      // Create simulation (but don't auto-configure)
      const sim = await createSimulation({
        agent_files: agentContents,
        bspl_content: bsplContent,
        bspl_filename: files.bspl.name,
        description:
          description || `Simulation with ${files.agents.length} agents`,
      });

      // Just pass the created simulation (status: "created")
      onSimulationCreated(sim);

      // Reset form and close
      setFiles({ bspl: null, agents: [] });
      setDescription("");
      onClose();
    } catch (err) {
      console.error("Failed to create simulation:", err);
      setError(
        "Failed to create simulation: " + (err.message || "Unknown error")
      );
    } finally {
      setCreating(false);
    }
  };

  const readFileContent = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target.result);
      reader.onerror = (e) => reject(e);
      reader.readAsText(file);
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">
            Create New Simulation
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-md p-3">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Description (optional)
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g., Supply chain simulation with 2 agents"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* BSPL File Upload */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              BSPL Protocol File *
            </label>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-4">
              {files.bspl ? (
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <svg
                      className="w-5 h-5 text-blue-500 mr-2"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                    <span className="text-sm text-gray-700">
                      {files.bspl.name}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      setFiles((prev) => ({ ...prev, bspl: null }))
                    }
                    className="text-red-500 hover:text-red-700"
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <div className="text-center">
                  <input
                    type="file"
                    accept=".bspl"
                    onChange={handleBsplUpload}
                    className="hidden"
                    id="bspl-upload"
                  />
                  <label htmlFor="bspl-upload" className="cursor-pointer">
                    <svg
                      className="w-8 h-8 text-gray-400 mx-auto mb-2"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                      />
                    </svg>
                    <p className="text-sm text-gray-600">
                      Click to upload BSPL file
                    </p>
                    <p className="text-xs text-gray-500">.bspl files only</p>
                  </label>
                </div>
              )}
            </div>
          </div>

          {/* Agent Files Upload */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Agent Files * (Python files)
            </label>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-4">
              {files.agents.length > 0 && (
                <div className="mb-3 space-y-2">
                  {files.agents.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between bg-gray-50 px-3 py-2 rounded"
                    >
                      <div className="flex items-center">
                        <svg
                          className="w-4 h-4 text-green-500 mr-2"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                          />
                        </svg>
                        <span className="text-sm text-gray-700">
                          {file.name}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeAgentFile(index)}
                        className="text-red-500 hover:text-red-700 text-sm"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="text-center">
                <input
                  type="file"
                  accept=".py"
                  multiple
                  onChange={handleAgentUpload}
                  className="hidden"
                  id="agent-upload"
                />
                <label htmlFor="agent-upload" className="cursor-pointer">
                  <svg
                    className="w-8 h-8 text-gray-400 mx-auto mb-2"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                    />
                  </svg>
                  <p className="text-sm text-gray-600">
                    {files.agents.length > 0
                      ? "Add more agent files"
                      : "Click to upload agent files"}
                  </p>
                  <p className="text-xs text-gray-500">
                    .py files only, select multiple
                  </p>
                </label>
              </div>
            </div>
          </div>

          {/* Submit Buttons */}
          <div className="flex justify-end space-x-3">
            <button
              type="button"
              onClick={onClose}
              disabled={creating}
              className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={creating || !files.bspl || files.agents.length === 0}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {creating ? (
                <span className="flex items-center">
                  <svg
                    className="w-4 h-4 mr-2 animate-spin"
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
                  Creating...
                </span>
              ) : (
                "Create Simulation"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
