import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";

class ProjectScopeManager {
  constructor() {
    this.projectId = "";
    this.generation = 0;
    this.controller = new AbortController();
  }

  begin(projectId) {
    this.controller.abort(new DOMException("Project scope changed", "AbortError"));
    if (appState.wsConn) {
      appState.wsConn.close();
      appState.wsConn = null;
    }
    this.projectId = String(projectId || "");
    this.generation += 1;
    this.controller = new AbortController();
    appState.currentProjectId = this.projectId || null;
    appState.currentProject = null;
    appState.currentProjectClasses = [];
    appState.trainingStatus = null;
    appState.models = [];
    appState.inferenceModels = [];
    appState.inferenceJobs = [];
    appState.inferenceJobsProjectId = "";
    appState.inferenceJobsLoading = false;
    appState.inferenceLastResult = null;
    appState.inferenceRunning = false;
    eventBus.emit("project-scope-changed", this.capture());
    return this.capture();
  }

  clear() {
    return this.begin("");
  }

  capture() {
    return { projectId: this.projectId, generation: this.generation, signal: this.controller.signal };
  }

  isCurrent(scope) {
    return Boolean(scope) && !scope.signal?.aborted && scope.projectId === this.projectId && scope.generation === this.generation;
  }

  assertCurrent(scope) {
    if (!this.isCurrent(scope)) throw new DOMException("Stale project request", "AbortError");
  }
}

export const projectScope = new ProjectScopeManager();
