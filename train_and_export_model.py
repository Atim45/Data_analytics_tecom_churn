"""
Train and export the telecom churn model pipeline.

Runs the full notebook end-to-end (EDA -> feature engineering -> balancing
experiment -> model bake-off -> Optuna tuning -> final evaluation), then
saves the fitted pipeline and a metadata file that reflects the metrics
actually computed in that run.

Requires: etl/data/telecom_churn.csv (not committed to git; place your
raw dataset there before running).
"""

import json
import re
import sys
import os
import subprocess

NOTEBOOK_PATH = "telecom_churn_analysis.ipynb"
RUN_SCRIPT_PATH = "run_notebook.py"
OUTPUT_LOG_PATH = "notebook_execution_output.txt"
MODEL_OUTPUT_PATH = os.path.join("app", "telecom_churn_pipeline.joblib")
METADATA_OUTPUT_PATH = "model_metadata.json"

# Appended to the end of the extracted notebook code. Everything here runs
# in the SAME process/namespace as the executed notebook cells, so it can
# see df, final_pipeline, X_train, X_test, y_test, y_pred, y_prob, study,
# best_params, feature_cols, categorical_cols, numerical_cols, preprocessor
# -- all defined earlier in the notebook. This is the step that was
# previously missing entirely: nothing in the original notebook or driver
# script ever called joblib.dump() or wrote model_metadata.json.
EXPORT_BLOCK = '''

# ==========================================
# Export block (appended by train_and_export_model.py)
# ==========================================
import joblib as _joblib
import json as _json
import os as _os
from datetime import datetime as _datetime
from sklearn.metrics import (
    accuracy_score as _accuracy_score,
    precision_score as _precision_score,
    recall_score as _recall_score,
    f1_score as _f1_score,
    roc_auc_score as _roc_auc_score,
)

_os.makedirs("app", exist_ok=True)

# 1. Save the fitted pipeline (preprocessor + sampler + tuned classifier)
_joblib.dump(final_pipeline, r"''' + MODEL_OUTPUT_PATH + '''")

# 2. Recompute metrics fresh, from the actual fitted pipeline on the actual
#    held-out test set, instead of hand-typing numbers into a JSON file.
_test_metrics = {
    "accuracy": round(_accuracy_score(y_test, y_pred), 4),
    "f1_score_churn": round(_f1_score(y_test, y_pred, pos_label=1), 4),
    "precision_churn": round(_precision_score(y_test, y_pred, pos_label=1, zero_division=0), 4),
    "recall_churn": round(_recall_score(y_test, y_pred, pos_label=1, zero_division=0), 4),
    "roc_auc": round(_roc_auc_score(y_test, y_prob), 4),
}

_metadata = {
    "model_name": "LightGBM Telecom Churn Classifier",
    "model_version": "1.0.0",
    "model_file": "telecom_churn_pipeline.joblib",
    "created_at": _datetime.now().strftime("%Y-%m-%d"),
    "framework": "LightGBM",
    "optimal_threshold": 0.5,
    "threshold_metric": "default (0.5) -- re-tune on this run's PR curve before deploying",
    "dataset": {
        "total_samples": int(len(df)),
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "churn_rate": round(float(df["churn"].mean()), 4),
        "retained_count": int((df["churn"] == 0).sum()),
        "churned_count": int((df["churn"] == 1).sum()),
    },
    "hyperparameters": best_params,
    "test_metrics": _test_metrics,
    "features": list(feature_cols),
    "telecom_partners": sorted(df["telecom_partner"].unique().tolist()),
    "genders": sorted(df["gender"].unique().tolist()),
    "description": (
        "LightGBM pipeline trained on Indian telecom customer churn dataset. "
        "Metadata generated automatically from this training run -- "
        "test_metrics reflect the actual held-out performance of the "
        "model_file saved alongside this JSON."
    ),
}

with open(r"''' + METADATA_OUTPUT_PATH + '''", "w", encoding="utf-8") as _f:
    _json.dump(_metadata, _f, indent=2)

print("[SUCCESS] Model exported to " + r"''' + MODEL_OUTPUT_PATH + '''")
print("[SUCCESS] Metadata written to " + r"''' + METADATA_OUTPUT_PATH + '''")
print("[REAL TEST METRICS]", _test_metrics)
'''


def run_notebook_code():
    if not os.path.exists(NOTEBOOK_PATH):
        print(f"[ERROR] Notebook not found at '{NOTEBOOK_PATH}'. "
              f"Check the filename -- it must match exactly (no double extension).")
        sys.exit(1)

    with open(NOTEBOOK_PATH, "r", encoding="utf-8") as f:
        nb = json.load(f)

    code_cells = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            code_cells.append("".join(cell.get("source", [])))

    # Combine code cells into a single execution block
    full_code = "\n\n# ==========================================\n\n".join(code_cells)

    # Force Agg backend to prevent figure popups blocking execution
    full_code = "import matplotlib\nmatplotlib.use('Agg')\n" + full_code

    # Append the export block so the run actually produces artifacts
    full_code = full_code + EXPORT_BLOCK

    # Save code to run_notebook.py
    with open(RUN_SCRIPT_PATH, "w", encoding="utf-8") as f:
        f.write(full_code)

    print("Code extracted. Running execution of the full notebook code...")

    result = subprocess.run(
        [sys.executable, RUN_SCRIPT_PATH],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    with open(OUTPUT_LOG_PATH, "w", encoding="utf-8") as out:
        out.write("=== STDOUT ===\n")
        out.write(result.stdout)
        out.write("\n=== STDERR ===\n")
        out.write(result.stderr)

    print("Execution complete. Output saved to " + OUTPUT_LOG_PATH)
    print(result.stdout[-1500:])  # Print the end of stdout

    if result.returncode != 0:
        print(f"Error occurred. Exit code: {result.returncode}")
        print(result.stderr[-1500:])
        sys.exit(result.returncode)

    if not os.path.exists(MODEL_OUTPUT_PATH) or not os.path.exists(METADATA_OUTPUT_PATH):
        print("[ERROR] Run finished but expected output files were not created. "
              "Check " + OUTPUT_LOG_PATH + " for details.")
        sys.exit(1)


if __name__ == "__main__":
    run_notebook_code()
