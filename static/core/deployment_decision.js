import { escapeHtml } from "../utils.js";

export function buildDeploymentDecision(result = {}) {
  const recommendation = result.recommendation || {};
  const summary = result.summary || {};
  const warnings = [...new Set([...(summary.warnings || []), ...(recommendation.warnings || [])])];
  const bestOverall = recommendation.best_overall || "";
  const confidence = recommendation.confidence || "low";
  const metricCount = Object.keys(summary.best_by_metric || {}).length;
  const blockers = [];
  if (!bestOverall) blockers.push("No recommended run is available.");
  if (metricCount < 2) blockers.push("Metric coverage is too thin for a deployment decision.");
  const deployable = Boolean(bestOverall && blockers.length === 0);
  const reasons = [
    recommendation.reason || "Recommendation is based on best available run metrics.",
    metricCount ? `${metricCount} metric families are available for comparison.` : "",
  ].filter(Boolean);
  const risks = warnings.length
    ? warnings
    : ["Review edge cases and output comparison before release export."];
  const nextActions = deployable
    ? [
        { label: "Review output comparison", action: "output_compare" },
        { label: "Export comparison report", action: "export_report" }
      ]
    : [
        { label: "Run comparison", action: "run_compare" },
        { label: "Add completed runs", action: "add_runs" }
      ];

  return {
    recommendedModelId: bestOverall,
    confidence,
    deployable,
    blockers,
    reasons,
    risks,
    nextActions
  };
}

export function renderDeploymentDecisionCard(decision = {}) {
  const badgeClass = decision.deployable ? "badge-success" : "badge-warning";
  return `
    <div class="deployment-decision-card" data-ui-smoke="deployment-decision-card">
      <div class="deployment-decision-head">
        <div>
          <span>Deployment Decision</span>
          <strong>${escapeHtml(decision.deployable ? "Candidate ready" : "Review required")}</strong>
        </div>
        <span class="summary-badge ${badgeClass}">${escapeHtml(decision.confidence || "low")} confidence</span>
      </div>
      <div class="deployment-decision-target">
        <span>Recommended run</span>
        <code>${escapeHtml(decision.recommendedModelId || "--")}</code>
      </div>
      ${decision.blockers?.length ? `<div class="decision-list danger"><strong>Blockers</strong>${renderList(decision.blockers)}</div>` : ""}
      <div class="decision-list"><strong>Reasons</strong>${renderList(decision.reasons || [])}</div>
      <div class="decision-list warning"><strong>Risks</strong>${renderList(decision.risks || [])}</div>
      <div class="decision-actions">
        ${(decision.nextActions || []).map((item) => `<span class="badge badge-neutral">${escapeHtml(item.label)}</span>`).join("")}
      </div>
    </div>
  `;
}

function renderList(items = []) {
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>--</li>"}</ul>`;
}
