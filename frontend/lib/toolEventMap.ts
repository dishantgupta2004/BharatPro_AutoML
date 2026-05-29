/** Maps internal MCP tool names → user-facing labels. Used by ToolProgressBanner, ToolCallCard, and useStreamingChat. */

export interface ToolMeta {
  label: string;
  done: string;
}

const MAP: Record<string, ToolMeta> = {
  ingest_dataset:                   { label: "Loading dataset",            done: "Dataset loaded" },
  validate_schema_with_pandera:     { label: "Validating data quality",    done: "Validation complete" },
  run_feature_engineering:          { label: "Engineering features",       done: "Features ready" },
  run_full_eda:                     { label: "Analyzing your data",        done: "Analysis complete" },
  run_parallel_bake_off:            { label: "Training candidate models",  done: "Best model selected" },
  trigger_hyperparameter_sweep:     { label: "Optimizing hyperparameters", done: "Optimization complete" },
  calculate_shap_values:            { label: "Computing explainability",   done: "Explanations ready" },
  generate_feature_importance_plot: { label: "Ranking feature importance", done: "Importance chart ready" },
  generate_jupyter_notebook:        { label: "Creating notebook",          done: "Notebook ready" },
  compile_pdf_report:               { label: "Preparing report",           done: "Report ready" },
  bundle_project_export:            { label: "Bundling project",           done: "Export ready" },
  list_uploaded_files:              { label: "Scanning your datasets",     done: "Datasets found" },
};

/** Returns the user-facing start label for a tool name, falling back to a generic string. */
export function getToolLabel(toolName: string): string {
  return MAP[toolName]?.label ?? "Processing";
}

/** Returns the user-facing completion label for a tool name. */
export function getToolDoneLabel(toolName: string): string {
  return MAP[toolName]?.done ?? "Done";
}
