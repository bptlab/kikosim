import React, { useEffect, useState } from "react";

export default function ConfigurationModal({
  isOpen,
  onClose,
  config,
  onSave,
}) {
  const [step, setStep] = useState(1);
  const [agentPools, setAgentPools] = useState({});
  const [taskSettings, setTaskSettings] = useState({});
  const [taskToAgentMapping, setTaskToAgentMapping] = useState({});

  // Initialize from existing config
  useEffect(() => {
    if (config && isOpen) {
      // Step 1: Keep AGENT_POOLS in count format (don't expand to individual agents)
      const pools = {};
      Object.entries(config.AGENT_POOLS || {}).forEach(
        ([principal, poolList]) => {
          const agentCounts = {};
          poolList.forEach((poolObj) => {
            Object.entries(poolObj).forEach(([agentType, count]) => {
              agentCounts[agentType] = count;
            });
          });
          pools[principal] = agentCounts;
        }
      );
      setAgentPools(pools);

      // Step 2: Copy task settings
      setTaskSettings(config.TASK_SETTINGS || {});

      // Step 3: Store task-to-agent mapping if available
      const mapping = config.TASK_TO_AGENT || {};
      setTaskToAgentMapping(mapping);

      // Step 4: Apply smart defaults for task settings if not already configured
      if (config.TASK_SETTINGS && mapping && Object.keys(mapping).length > 0) {
        const updatedTaskSettings = { ...config.TASK_SETTINGS };
        let hasChanges = false;

        Object.keys(config.TASK_SETTINGS).forEach((taskName) => {
          const [currentAgent, duration] = config.TASK_SETTINGS[taskName];
          const businessAgent = mapping[taskName];

          // If task is not assigned to any agent, apply smart default
          if (!currentAgent && businessAgent) {
            const recommendedAgent = `${businessAgent}RA`;
            updatedTaskSettings[taskName] = [recommendedAgent, duration || 1];
            hasChanges = true;
          }
        });

        if (hasChanges) {
          setTaskSettings(updatedTaskSettings);
        }
      }
    }
  }, [config, isOpen]);

  const businessAgents = Object.keys(agentPools);

  // Time conversion utilities
  const convertToDays = (value, unit) => {
    const conversions = {
      minutes: value / (24 * 60),
      hours: value / 24,
      days: value,
    };
    return conversions[unit] || value;
  };

  const convertFromDays = (days, unit) => {
    const conversions = {
      minutes: days * 24 * 60,
      hours: days * 24,
      days: days,
    };
    return conversions[unit] || days;
  };

  const getDisplayValue = (taskName) => {
    const setting = taskSettings[taskName];
    if (!setting)
      return { mean: 1, stdDev: 0, unit: "days", useDistribution: false };

    // Support both old format [agent, duration] and new format [agent, mean, stdDev]
    let meanDaysValue, stdDevDaysValue;
    if (setting.length === 2) {
      meanDaysValue = setting[1] || 1;
      stdDevDaysValue = 0;
    } else if (setting.length === 3) {
      meanDaysValue = setting[1] || 1;
      stdDevDaysValue = setting[2] || 0;
    } else {
      meanDaysValue = 1;
      stdDevDaysValue = 0;
    }

    const useDistribution = stdDevDaysValue > 0;

    // Auto-select best unit for display based on mean
    let unit, meanValue, stdDevValue;
    if (meanDaysValue >= 1) {
      unit = "days";
      meanValue = meanDaysValue;
      stdDevValue = stdDevDaysValue;
    } else if (meanDaysValue >= 1 / 24) {
      unit = "hours";
      meanValue = Math.round(meanDaysValue * 24 * 10) / 10;
      stdDevValue = Math.round(stdDevDaysValue * 24 * 10) / 10;
    } else {
      unit = "minutes";
      meanValue = Math.round(meanDaysValue * 24 * 60);
      stdDevValue = Math.round(stdDevDaysValue * 24 * 60);
    }

    return { mean: meanValue, stdDev: stdDevValue, unit, useDistribution };
  };

  // Simplified agent pool management - only need basic count updates

  // Step 2: Task Settings Management
  const getAllResourceAgents = () => {
    const allAgents = [];
    Object.values(agentPools).forEach((agentCounts) => {
      Object.keys(agentCounts).forEach((agentType) => {
        if (!allAgents.includes(agentType)) {
          allAgents.push(agentType);
        }
      });
    });
    return allAgents.sort();
  };

  const updateTaskSetting = (taskName, field, value) => {
    setTaskSettings((prev) => {
      const currentSetting = prev[taskName] || [
        getAllResourceAgents()[0],
        1,
        0,
      ];
      const currentAgent = currentSetting[0];
      const currentMeanDays = currentSetting[1] || 1;
      const currentStdDevDays = currentSetting[2] || 0;

      if (field === "agent") {
        return {
          ...prev,
          [taskName]: [value, currentMeanDays, currentStdDevDays],
        };
      } else if (field === "mean") {
        const { unit } = getDisplayValue(taskName);
        const meanDays = convertToDays(parseFloat(value) || 1, unit);
        return {
          ...prev,
          [taskName]: [currentAgent, meanDays, currentStdDevDays],
        };
      } else if (field === "stdDev") {
        const { unit } = getDisplayValue(taskName);
        const stdDevDays = convertToDays(parseFloat(value) || 0, unit);
        return {
          ...prev,
          [taskName]: [currentAgent, currentMeanDays, stdDevDays],
        };
      } else if (field === "unit") {
        // Convert current values to new unit, then back to days
        const { mean: currentMean, stdDev: currentStdDev } =
          getDisplayValue(taskName);
        const meanDays = convertToDays(currentMean, value);
        const stdDevDays = convertToDays(currentStdDev, value);
        return {
          ...prev,
          [taskName]: [currentAgent, meanDays, stdDevDays],
        };
      } else if (field === "useDistribution") {
        if (value) {
          // Enable distribution: suggest default std dev as mean/3 (ensuring μ - 2σ > 0)
          const suggestedStdDev = Math.max(0.1, currentMeanDays / 3);
          return {
            ...prev,
            [taskName]: [currentAgent, currentMeanDays, suggestedStdDev],
          };
        } else {
          // Disable distribution: set std dev to 0
          return {
            ...prev,
            [taskName]: [currentAgent, currentMeanDays, 0],
          };
        }
      }

      return prev;
    });
  };

  // Helper functions for task grouping and smart defaults
  const getTasksByBusinessAgent = () => {
    const grouped = {};

    // Group tasks by their business agent
    Object.keys(taskSettings).forEach((taskName) => {
      const businessAgent = taskToAgentMapping[taskName];
      if (businessAgent) {
        if (!grouped[businessAgent]) {
          grouped[businessAgent] = [];
        }
        grouped[businessAgent].push(taskName);
      } else {
        // Fallback: put ungrouped tasks under "Unknown"
        if (!grouped["Unknown"]) {
          grouped["Unknown"] = [];
        }
        grouped["Unknown"].push(taskName);
      }
    });

    // Convert to array of [businessAgent, tasks] pairs, sorted
    return Object.entries(grouped).sort(([a], [b]) => {
      if (a === "Unknown") return 1; // Put "Unknown" last
      if (b === "Unknown") return -1;
      return a.localeCompare(b);
    });
  };

  const getRecommendedAgent = (taskName) => {
    const businessAgent = taskToAgentMapping[taskName];
    if (!businessAgent) return null;

    // Default to the primary resource agent for this business agent
    const resourceAgentCounts = agentPools[businessAgent] || {};
    const agentTypes = Object.keys(resourceAgentCounts);

    if (agentTypes.length > 0) {
      // Return the first available agent type, or the one with highest count
      const sorted = Object.entries(resourceAgentCounts).sort(
        (a, b) => b[1] - a[1]
      );
      return sorted[0]?.[0] || `${businessAgent}RA`;
    }

    return `${businessAgent}RA`; // Fallback to conventional naming
  };

  // Convert back to backend format
  const convertToBackendFormat = () => {
    // Ensure all business agents have at least their main resource agent
    const backendPools = {};
    Object.keys(agentPools).forEach((principal) => {
      const mainAgentType = `${principal}RA`;
      const agentCounts = agentPools[principal] || {};

      // Ensure the main agent type exists with at least count 1
      if (!agentCounts[mainAgentType]) {
        agentCounts[mainAgentType] = 1;
      }

      backendPools[principal] = [agentCounts];
    });

    return {
      agent_pools: backendPools,
      task_settings: taskSettings,
    };
  };

  const handleSave = () => {
    const backendConfig = convertToBackendFormat();
    onSave(backendConfig);
  };

  const handleNext = () => {
    if (step === 1) {
      setStep(2);
    } else {
      handleSave();
    }
  };

  const handleBack = () => {
    setStep(1);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-gray-900">
            Configure Resources - Step {step} of 2
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

        {/* Progress indicator */}
        <div className="flex items-center mb-6">
          <div
            className={`flex items-center ${
              step >= 1 ? "text-blue-600" : "text-gray-400"
            }`}
          >
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium ${
                step >= 1 ? "bg-blue-600" : "bg-gray-400"
              }`}
            >
              1
            </div>
            <span className="ml-2 font-medium">Agent Pools</span>
          </div>

          <div
            className={`flex-1 h-1 mx-4 ${
              step >= 2 ? "bg-blue-600" : "bg-gray-300"
            }`}
          ></div>

          <div
            className={`flex items-center ${
              step >= 2 ? "text-blue-600" : "text-gray-400"
            }`}
          >
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium ${
                step >= 2 ? "bg-blue-600" : "bg-gray-400"
              }`}
            >
              2
            </div>
            <span className="ml-2 font-medium">Task Settings</span>
          </div>
        </div>

        {/* Step 1: Agent Pools - Simple + On-Demand Creation */}
        {step === 1 && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                Resource Agent Configuration
              </h3>
              <p className="text-sm text-gray-600 mb-4">
                Configure different types of resource agents and how many of
                each type to create.
              </p>
            </div>

            <div className="space-y-4">
              {businessAgents.map((principal) => {
                const agentTypes = Object.entries(agentPools[principal] || {});

                return (
                  <div key={principal} className="bg-gray-50 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="font-medium text-gray-900">
                        {principal} Business Agent
                      </h4>
                      <button
                        onClick={() => {
                          const agentName = prompt(
                            `Enter name for new ${principal} resource agent:`,
                            `${principal}Shipper`
                          );
                          if (agentName && agentName.trim()) {
                            const cleanName = agentName.trim();
                            setAgentPools((prev) => ({
                              ...prev,
                              [principal]: {
                                ...prev[principal],
                                [cleanName]: 1,
                              },
                            }));
                          }
                        }}
                        className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                        title="Add a new type of resource agent"
                      >
                        + Add Agent Type
                      </button>
                    </div>

                    <div className="space-y-2">
                      {agentTypes.length > 0 ? (
                        agentTypes.map(([agentType, count]) => (
                          <div
                            key={`${principal}-${agentType}`}
                            className="bg-white rounded border p-3"
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-3">
                                <span className="font-mono text-sm font-medium text-gray-900">
                                  {agentType}
                                </span>
                              </div>

                              <div className="flex items-center gap-2">
                                <label className="text-sm font-medium text-gray-700">
                                  Count:
                                </label>
                                <input
                                  type="number"
                                  min="1"
                                  max="10"
                                  value={count}
                                  onChange={(e) => {
                                    const newCount = Math.max(
                                      1,
                                      parseInt(e.target.value) || 1
                                    );
                                    setAgentPools((prev) => ({
                                      ...prev,
                                      [principal]: {
                                        ...prev[principal],
                                        [agentType]: newCount,
                                      },
                                    }));
                                  }}
                                  className="w-16 px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-center"
                                />

                                {agentTypes.length > 1 && (
                                  <button
                                    onClick={() => {
                                      setAgentPools((prev) => {
                                        const updated = { ...prev };
                                        const principalAgents = {
                                          ...updated[principal],
                                        };
                                        delete principalAgents[agentType];
                                        updated[principal] = principalAgents;
                                        return updated;
                                      });
                                    }}
                                    className="p-1 text-red-600 hover:text-red-800"
                                    title="Remove this agent type"
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
                                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                                      />
                                    </svg>
                                  </button>
                                )}
                              </div>
                            </div>

                            <div className="text-xs text-gray-500 mt-2">
                              Will create {count} instance
                              {count !== 1 ? "s" : ""} of {agentType}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="bg-white rounded border p-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <span className="font-mono text-sm font-medium text-gray-900">
                                {principal}RA
                              </span>
                            </div>

                            <div className="flex items-center gap-2">
                              <label className="text-sm font-medium text-gray-700">
                                Count:
                              </label>
                              <input
                                type="number"
                                min="1"
                                max="10"
                                value={1}
                                onChange={(e) => {
                                  const newCount = Math.max(
                                    1,
                                    parseInt(e.target.value) || 1
                                  );
                                  setAgentPools((prev) => ({
                                    ...prev,
                                    [principal]: {
                                      [`${principal}RA`]: newCount,
                                    },
                                  }));
                                }}
                                className="w-16 px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-center"
                              />
                            </div>
                          </div>

                          <div className="text-xs text-gray-500 mt-2">
                            Will create 1 instance of {principal}RA
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {businessAgents.length === 0 && (
              <div className="text-center py-8">
                <p className="text-gray-500">
                  No business agents found in configuration.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Step 2: Task Settings - Simplified */}
        {step === 2 && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                Task Assignment & Timing
              </h3>
              <p className="text-sm text-gray-600 mb-4">
                Configure how tasks are assigned to resource agents and their
                execution duration.
              </p>
            </div>

            <div className="space-y-4">
              {getTasksByBusinessAgent().map(([businessAgent, tasks]) => (
                <div key={businessAgent} className="bg-gray-50 rounded-lg p-4">
                  <h4 className="font-medium text-gray-900 mb-3 flex items-center">
                    <span className="w-3 h-3 bg-blue-500 rounded-full mr-2"></span>
                    {businessAgent} Business Agent Tasks
                  </h4>

                  <div className="space-y-3">
                    {tasks.map((taskName, taskIndex) => {
                      const [currentAgent, duration] = taskSettings[
                        taskName
                      ] || ["", 1];
                      const recommendedAgent = getRecommendedAgent(taskName);
                      const taskBusinessAgent = taskToAgentMapping[taskName];

                      // Simplified cross-assignment check
                      const isCrossAssignment =
                        currentAgent &&
                        taskBusinessAgent &&
                        !Object.keys(
                          agentPools[taskBusinessAgent] || {}
                        ).includes(currentAgent);

                      return (
                        <div
                          key={`${businessAgent}-${taskIndex}`}
                          className="bg-white rounded border p-3"
                        >
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            <div className="flex items-center">
                              <span className="font-mono text-sm font-medium text-gray-900">
                                {taskName}
                              </span>
                              {isCrossAssignment && (
                                <span
                                  className="ml-2 text-xs text-orange-600"
                                  title="Cross-business-agent assignment"
                                >
                                  ⚠️
                                </span>
                              )}
                            </div>

                            <div className="flex gap-2">
                              <select
                                value={currentAgent || ""}
                                onChange={(e) =>
                                  updateTaskSetting(
                                    taskName,
                                    "agent",
                                    e.target.value
                                  )
                                }
                                className="flex-1 px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                              >
                                <option value="">
                                  Select resource agent...
                                </option>
                                {getAllResourceAgents().map((agent) => (
                                  <option key={agent} value={agent}>
                                    {agent}
                                  </option>
                                ))}
                              </select>
                            </div>

                            <div className="space-y-2">
                              {/* Duration Mode Toggle */}
                              <div className="flex items-center gap-2">
                                <label className="flex items-center cursor-pointer">
                                  <input
                                    type="checkbox"
                                    checked={
                                      getDisplayValue(taskName).useDistribution
                                    }
                                    onChange={(e) =>
                                      updateTaskSetting(
                                        taskName,
                                        "useDistribution",
                                        e.target.checked
                                      )
                                    }
                                    className="mr-2"
                                  />
                                  <span className="text-sm text-gray-700">
                                    Variable duration (normal distribution)
                                  </span>
                                </label>
                              </div>

                              {/* Duration Inputs */}
                              <div className="flex items-center gap-2">
                                <div className="flex items-center gap-1">
                                  <label className="text-xs text-gray-600 w-8">
                                    {getDisplayValue(taskName).useDistribution
                                      ? "Mean:"
                                      : "Duration:"}
                                  </label>
                                  <input
                                    type="number"
                                    value={getDisplayValue(taskName).mean}
                                    onChange={(e) =>
                                      updateTaskSetting(
                                        taskName,
                                        "mean",
                                        e.target.value
                                      )
                                    }
                                    min="0.1"
                                    step="0.1"
                                    className="w-16 px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                  />
                                </div>

                                {getDisplayValue(taskName).useDistribution && (
                                  <div className="flex items-center gap-1">
                                    <label className="text-xs text-gray-600">
                                      ±
                                    </label>
                                    <input
                                      type="number"
                                      value={getDisplayValue(taskName).stdDev}
                                      onChange={(e) =>
                                        updateTaskSetting(
                                          taskName,
                                          "stdDev",
                                          e.target.value
                                        )
                                      }
                                      min="0"
                                      step="0.1"
                                      className="w-16 px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    />
                                  </div>
                                )}

                                <select
                                  value={getDisplayValue(taskName).unit}
                                  onChange={(e) =>
                                    updateTaskSetting(
                                      taskName,
                                      "unit",
                                      e.target.value
                                    )
                                  }
                                  className="px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                >
                                  <option value="minutes">min</option>
                                  <option value="hours">hr</option>
                                  <option value="days">days</option>
                                </select>
                              </div>

                              {/* Distribution Preview */}
                              {getDisplayValue(taskName).useDistribution && (
                                <div className="text-xs text-gray-500">
                                  Range:{" "}
                                  {(
                                    getDisplayValue(taskName).mean -
                                    2 * getDisplayValue(taskName).stdDev
                                  ).toFixed(1)}{" "}
                                  -{" "}
                                  {(
                                    getDisplayValue(taskName).mean +
                                    2 * getDisplayValue(taskName).stdDev
                                  ).toFixed(1)}{" "}
                                  {getDisplayValue(taskName).unit} (95% of
                                  samples)
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              {Object.keys(taskSettings).length === 0 && (
                <div className="text-center py-8">
                  <p className="text-gray-500">
                    No tasks found in configuration.
                  </p>
                </div>
              )}
            </div>

            {/* Summary */}
            <div className="bg-blue-50 rounded-lg p-4">
              <h4 className="font-medium text-blue-900 mb-2">
                Configuration Summary
              </h4>
              <div className="text-sm text-blue-800">
                <p>
                  <strong>Business Agents:</strong> {businessAgents.join(", ")}
                </p>
                <p>
                  <strong>Resource Agents:</strong>{" "}
                  {getAllResourceAgents().join(", ")}
                </p>
                <p>
                  <strong>Tasks Configured:</strong>{" "}
                  {Object.keys(taskSettings).length}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Navigation Buttons */}
        <div className="flex justify-between mt-8">
          <div>
            {step === 2 && (
              <button
                onClick={handleBack}
                className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                Back
              </button>
            )}
          </div>

          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300"
            >
              Cancel
            </button>
            <button
              onClick={handleNext}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              {step === 1 ? "Next: Task Settings" : "Save Configuration"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
