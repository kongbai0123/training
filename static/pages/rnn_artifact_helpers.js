export const RNN_ARTIFACT_PRIORITY = [
  "best.pt",
  "last.pt",
  "best.json",
  "last.json",
  "metrics.json",
  "results.csv",
  "run_summary.json",
  "feature_schema.json",
  "normalization_stats.json",
  "label_encoder.json",
  "model_metadata.json",
  "artifact_manifest.json"
];

export function sortRnnArtifacts(artifacts = []) {
  return [...(Array.isArray(artifacts) ? artifacts : [])].sort((a, b) => {
    const ai = RNN_ARTIFACT_PRIORITY.indexOf(a?.filename);
    const bi = RNN_ARTIFACT_PRIORITY.indexOf(b?.filename);
    const priorityDelta = (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    if (priorityDelta !== 0) return priorityDelta;
    return String(a?.filename || "").localeCompare(String(b?.filename || ""));
  });
}

export function formatRnnArtifactSize(size) {
  if (size === undefined || size === null) return "--";
  const bytes = Number(size);
  if (!Number.isFinite(bytes)) return "--";
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export function buildRnnArtifactDownloadUrl({ projectId, runId, filename, relPath } = {}) {
  const safeFilename = filename || "artifact";
  const safeRelPath = relPath || safeFilename;
  if (!projectId || !runId) return "";
  return `/api/projects/${encodeURIComponent(projectId)}/train/runs/${encodeURIComponent(runId)}/artifacts/download/${encodeURIComponent(safeFilename)}?path=${encodeURIComponent(safeRelPath)}`;
}

export function buildRnnArtifactViewModels({ artifacts = [], projectId = "", runId = "" } = {}) {
  return sortRnnArtifacts(artifacts).map((artifact) => {
    const filename = artifact?.filename || "artifact";
    const relPath = artifact?.rel_path || filename;
    return {
      filename,
      relPath,
      sizeLabel: formatRnnArtifactSize(artifact?.size),
      downloadUrl: buildRnnArtifactDownloadUrl({
        projectId,
        runId,
        filename,
        relPath
      })
    };
  });
}

export function buildRnnArtifactListViewModel({ artifacts = [], projectId = "", runId = "" } = {}) {
  const rows = buildRnnArtifactViewModels({ artifacts, projectId, runId });
  const hasArtifacts = Boolean(runId) && rows.length > 0;
  return {
    hasArtifacts,
    emptyMessage: hasArtifacts ? "" : "No artifacts.",
    rows
  };
}
