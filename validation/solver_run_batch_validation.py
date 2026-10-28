import os
import json
import re
import csv
from validator import ScheduleValidator

SOLVER_FILES = [
    "outputs/solver/easy_001.json",
    "outputs/solver/easy_002.json",
    "outputs/solver/easy_003.json",
    "outputs/solver/easy_004.json",
    "outputs/solver/easy_005.json",
    "outputs/solver/hard_001.json",
    "outputs/solver/hard_002.json",
    "outputs/solver/hard_003.json",
    "outputs/solver/hard_004.json",
    "outputs/solver/hard_005.json",
    "outputs/solver/medium_001.json",
    "outputs/solver/medium_002.json",
    "outputs/solver/medium_003.json",
    "outputs/solver/medium_004.json",
    "outputs/solver/medium_005.json",
    "outputs/solver_v2/input_hard_001.json",
    "outputs/solver_v2/input_hard_002.json",
    "outputs/solver_v2/input_hard_003.json",
    "outputs/solver_v2/input_hard_004.json",
    "outputs/solver_v2/input_hard_005.json",
    "outputs/solver_v2/input_hard_006.json",
    "outputs/solver_v2/input_hard_007.json",
    "outputs/solver_v2/input_hard_008.json",
    "outputs/solver_v2/input_hard_009.json",
    "outputs/solver_v2/input_hard_010.json"
]

def get_instance_path(filepath: str) -> str:
    """Extracts the instance name and builds the path for both V1 and V2."""
    basename = os.path.basename(filepath).replace('.json', '')
    
    # Handle the example file specifically
    if basename == "final_proposal_example":
        return "instances/example/final_proposal_example.json", basename

    # Regex updated to handle optional 'input_' prefix and no trailing underscore
    match = re.match(r"^(?:input_)?(easy|medium|hard)_(\d{3})", basename)
    if not match:
        raise ValueError(f"Could not parse instance name from file: {basename}")
    
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

    for schedule_path in SOLVER_FILES:
        if not os.path.exists(schedule_path):
            print(f"File not found: {schedule_path}")
            continue

        try:
            instance_path, instance_name = get_instance_path(schedule_path)
            
            # For flat files, the output validation is just appended with _validation
            validation_out_path = schedule_path.replace('.json', '_validation.json')

            if not os.path.exists(instance_path):
                print(f"Instance file missing for {instance_name} at {instance_path}")
                continue

            with open(instance_path, 'r') as f:
                instance_data = json.load(f)
            
            total_hh = len(instance_data.get('households', []))
            total_reqs = len(instance_data.get('requests', []))

            with open(schedule_path, 'r') as f:
                schedule_data = json.load(f)

            validator = ScheduleValidator(instance_data, schedule_data)
            report = validator.validate()

            with open(validation_out_path, 'w') as f:
                json.dump(report, f, indent=2)

            is_feasible = report["is_feasible"]
            violations = len(report["violations"])
            metrics = report.get("recomputed_metrics", {})
            
            served_hh = metrics.get("households_served", "-")
            served_reqs = metrics.get("requests_fulfilled", "-")
            priority = metrics.get("priority_weight", "-")
            travel = metrics.get("mean_travel_minutes", "-")

            served_hh_display = f"{served_hh}/{total_hh}" if served_hh != "-" else "-"
            served_reqs_display = f"{served_reqs}/{total_reqs}" if served_reqs != "-" else "-"

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
            print(f"Error processing {schedule_path}: {e}")

    # Save to a separate CSV file so it doesn't overwrite the Codex summary
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)
    csv_path = os.path.join(reports_dir, "solver_validation_summary.csv")
    if summary_data:
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=summary_data[0].keys())
            writer.writeheader()
            writer.writerows(summary_data)
        print(f"\n✅ Batch complete. Summary saved to {csv_path}")

if __name__ == "__main__":
    main()