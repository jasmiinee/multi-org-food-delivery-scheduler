import os
import json
import re
import csv
from validator import ScheduleValidator

# Combined V2 and V2.1 directories
CODEX_FILES = [
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
    "outputs/codex_v2/input_hard_010_20261023T075259Z_3ca631e0",
    
    # V2.1 Directories
    "outputs/codex_v2.1/hard_1",
    "outputs/codex_v2.1/hard_2",
    "outputs/codex_v2.1/hard_3",
    "outputs/codex_v2.1/hard_4"
]

def get_instance_path(run_dir: str) -> tuple[str, str]:
    """Extracts the instance name and builds the path for V2 and V2.1."""
    basename = os.path.basename(run_dir)
    
    # V2.1 Logic (e.g., hard_1)
    if "v2.1" in run_dir:
        # Check inside the directory hard_1/hard_1.json
        possible_paths = [
            os.path.join("instances/v2.1/hard", basename, f"{basename}.json"),
            os.path.join("instances/v2.1/hard", f"{basename}.json"),
            os.path.join("instances/v2.1", f"{basename}.json")
        ]
        for p in possible_paths:
            if os.path.exists(p) and os.path.isfile(p):
                return p, basename
        return possible_paths[0], basename

    # V2 Logic
    else:
        match = re.match(r"^(?:input_)?(easy|medium|hard)_(\d{3})_", basename)
        if not match:
            raise ValueError(f"Could not parse instance name from directory: {basename}")
        level = match.group(1)
        instance_name = f"input_{level}_{match.group(2)}"
        return os.path.join("instances/input_first", level, f"{instance_name}.json"), instance_name

def main():
    summary_data = []
    
    print(f"{'Instance':<20} | {'Feasible?':<10} | {'HH (S/T)':<9} | {'Reqs (S/T)':<10} | {'Priority':<8} | {'Travel':<8} | {'Violations'}")
    print("-" * 95)

    for run_dir in CODEX_FILES:
        if not os.path.exists(run_dir):
            print(f"Directory not found: {run_dir}")
            continue

        try:
            basename = os.path.basename(run_dir)
            instance_path, instance_name = get_instance_path(run_dir)
            
            # V2.1 saves schedule as hard_1.json, V2 saves as parsed.json
            if "v2.1" in run_dir:
                schedule_path = os.path.join(run_dir, f"{basename}.json")
            else:
                schedule_path = os.path.join(run_dir, "parsed.json")
                
            validation_out_path = os.path.join(run_dir, "validation.json")

            if not os.path.exists(instance_path):
                print(f"❌ Instance file missing for {instance_name} at {instance_path}")
                continue

            with open(instance_path, 'r') as f:
                instance_data = json.load(f)
            
            total_hh = len(instance_data.get('households', []))
            total_reqs = len(instance_data.get('requests', []))

            if not os.path.exists(schedule_path):
                report = {
                    "is_feasible": False,
                    "violations": [{"code": "PARSE_ERROR", "message": f"Schedule not found at {schedule_path}"}],
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

    # Save to a single combined CSV
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)
    csv_path = os.path.join(reports_dir, "codex_validation_summary.csv")
    if summary_data:
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=summary_data[0].keys())
            writer.writeheader()
            writer.writerows(summary_data)
        print(f"\n✅ Batch complete. Summary saved to {csv_path}")

if __name__ == "__main__":
    main()