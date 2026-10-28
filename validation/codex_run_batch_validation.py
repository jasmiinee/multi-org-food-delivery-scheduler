import os
import json
import re
import csv
from validator import ScheduleValidator

# List of directories
CODEX_FILES = [
    # V1 Directories (Easy, Hard, Medium)
    "outputs/codex/easy_001_20261020T140256Z_7f9b9b28",
    "outputs/codex/easy_002_20261020T140532Z_f3eb35c7",
    "outputs/codex/easy_003_20261020T140620Z_63a371d7",
    "outputs/codex/easy_004_20261020T140744Z_ef1bb522",
    "outputs/codex/easy_005_20261020T140817Z_49a3f4dd",
    "outputs/codex/hard_001_20261020T141733Z_c5914643",
    "outputs/codex/hard_002_20261020T141914Z_a8c21404",
    "outputs/codex/hard_003_20261020T142059Z_33c89f9a",
    "outputs/codex/hard_004_20261020T142223Z_3456e03a",
    "outputs/codex/hard_005_20261020T142419Z_6702bbf7",
    "outputs/codex/medium_001_20261020T140906Z_95d7a92d",
    "outputs/codex/medium_002_20261020T141038Z_2f15097b",
    "outputs/codex/medium_003_20261020T141201Z_bea485ea",
    "outputs/codex/medium_004_20261020T141430Z_e92dce6b",
    "outputs/codex/medium_005_20261020T141551Z_386a4890",
    
    # V2 Directories
    "outputs/codex_v2/input_hard_001_20261023T071519Z_dc9d20f9",
    "outputs/codex_v2/input_hard_002_20261023T071913Z_7a678e5c",
    "outputs/codex_v2/input_hard_003_20261023T072515Z_bf59fdd3",
    "outputs/codex_v2/input_hard_004_20261023T072915Z_54017428",
    "outputs/codex_v2/input_hard_005_20261023T073327Z_47d6caaf",
    "outputs/codex_v2/input_hard_006_20261023T073904Z_1853a67b",
    "outputs/codex_v2/input_hard_007_20261023T074330Z_6b5d4f38",
    "outputs/codex_v2/input_hard_008_20261023T074641Z_44092f98",
    "outputs/codex_v2/input_hard_009_20261023T074928Z_dda3ef0e",
    "outputs/codex_v2/input_hard_010_20261023T075259Z_3ca631e0"
]

def get_instance_path(run_dir: str) -> str:
    """Extracts the instance name and builds the path for both V1 and V2."""
    basename = os.path.basename(run_dir)
    
    # Regex updated to handle optional 'input_' prefix
    match = re.match(r"^(?:input_)?(easy|medium|hard)_(\d{3})_", basename)
    if not match:
        raise ValueError(f"Could not parse instance name from directory: {basename}")
    
    level = match.group(1)
    
    if basename.startswith("input_"):
        # V2 Logic
        instance_name = f"input_{level}_{match.group(2)}"
        return os.path.join("instances/input_first", level, f"{instance_name}.json"), instance_name
    else:
        # V1 Logic
        instance_name = f"{level}_{match.group(2)}"
        return os.path.join("instances/benchmark", level, f"{instance_name}.json"), instance_name

def main():
    summary_data = []
    
    print(f"{'Instance':<20} | {'Feasible?':<10} | {'HH (S/T)':<9} | {'Reqs (S/T)':<10} | {'Priority':<8} | {'Travel':<8} | {'Violations'}")
    print("-" * 95)

    for run_dir in CODEX_FILES:
        if not os.path.exists(run_dir):
            print(f"Directory not found: {run_dir}")
            continue

        try:
            instance_path, instance_name = get_instance_path(run_dir)
            schedule_path = os.path.join(run_dir, "parsed.json")
            validation_out_path = os.path.join(run_dir, "validation.json")

            with open(instance_path, 'r') as f:
                instance_data = json.load(f)
            
            total_hh = len(instance_data.get('households', []))
            total_reqs = len(instance_data.get('requests', []))

            if not os.path.exists(schedule_path):
                report = {
                    "is_feasible": False,
                    "violations": [{"code": "PARSE_ERROR", "message": "parsed.json not found. LLM failed to output valid JSON."}],
                    "recomputed_metrics": {},
                    "claimed_metrics": {}
                }
                served_hh_display = "-"
                served_reqs_display = "-"
                priority = "-"
                travel = "-"
            else:
                with open(schedule_path, 'r') as f:
                    schedule_data = json.load(f)

                validator = ScheduleValidator(instance_data, schedule_data)
                report = validator.validate()

                metrics = report.get("recomputed_metrics", {})
                served_hh = metrics.get("households_served", "-")
                served_reqs = metrics.get("requests_fulfilled", "-")
                priority = metrics.get("priority_weight", "-")
                travel = metrics.get("mean_travel_minutes", "-")

                # Format as Served/Total
                served_hh_display = f"{served_hh}/{total_hh}" if served_hh != "-" else "-"
                served_reqs_display = f"{served_reqs}/{total_reqs}" if served_reqs != "-" else "-"

            with open(validation_out_path, 'w') as f:
                json.dump(report, f, indent=2)

            is_feasible = report["is_feasible"]
            violations = len(report["violations"])

            feasible_str = "YES" if is_feasible else "NO"
            print(f"{instance_name:<20} | {feasible_str:<10} | {served_hh_display:<9} | {served_reqs_display:<10} | {str(priority):<8} | {str(travel):<8} | {violations}")

            summary_data.append({
                "instance": instance_name,
                "is_feasible": is_feasible,
                "households_served": served_hh_display,
                "requests_fulfilled": served_reqs_display,
                "priority_weight": priority,
                "mean_travel_minutes": travel,
                "num_violations": violations,
                "violation_codes": ",".join([v["code"] for v in report["violations"]])
            })

        except Exception as e:
            print(f"Error processing {run_dir}: {e}")

    # Updated to save in a centralized output path
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)
    csv_path = os.path.join(reports_dir, "codex_validation_summary.csv")
    if summary_data:
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=summary_data[0].keys())
            writer.writeheader()
            writer.writerows(summary_data)
        print(f"\nBatch complete. Summary saved to {csv_path}")

if __name__ == "__main__":
    main()