import os
import json
import re
import csv
from validator import ScheduleValidator

# Dynamically generate paths for the gpt6 outputs
LLM_FILES = []
# Easy: easy_1 to easy_5
LLM_FILES.extend([f"outputs/gpt6/easy_{i}" for i in range(1, 6)])
# Medium: medium_1 to medium_5
LLM_FILES.extend([f"outputs/gpt6/medium_{i}" for i in range(1, 6)])
# Hard: hard_1 to hard_14
LLM_FILES.extend([f"outputs/gpt6/hard_{i}" for i in range(1, 15)])

def get_instance_path(run_dir: str) -> tuple[str, str]:
    """Extracts the instance name and builds the path based on the new input_first structure."""
    basename = os.path.basename(run_dir) # e.g., "easy_1", "hard_14"
    
    match = re.match(r"^(easy|medium|hard)_(\d+)$", basename)
    if not match:
        raise ValueError(f"Could not parse instance name from directory: {basename}")
    
    level = match.group(1)
    num = int(match.group(2))
    num_str = f"{num:03d}"
    
    # Hard instances are named hard_001.json (no 'input_' prefix)
    if level == "hard":
        instance_name = f"hard_{num_str}"
        return os.path.join("instances/input_first", level, f"{instance_name}.json"), instance_name
    # Easy/Medium instances are named input_easy_001.json
    else:
        instance_name = f"input_{level}_{num_str}"
        return os.path.join("instances/input_first", level, f"{instance_name}.json"), instance_name

def main():
    summary_data = []
    
    print(f"{'Instance':<20} | {'Feasible?':<10} | {'HH (S/T)':<9} | {'Reqs (S/T)':<10} | {'Priority':<8} | {'Travel':<8} | {'Violations'}")
    print("-" * 95)

    for run_dir in LLM_FILES:
        if not os.path.exists(run_dir):
            print(f"Directory not found: {run_dir}")
            continue

        try:
            basename = os.path.basename(run_dir)
            instance_path, instance_name = get_instance_path(run_dir)
            
            # Look for the schedule in the directory. It's usually named {basename}.json or parsed.json
            schedule_path = os.path.join(run_dir, f"{basename}.json")
            if not os.path.exists(schedule_path):
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
    csv_path = os.path.join(reports_dir, "llm_validation_summary.csv")
    if summary_data:
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=summary_data[0].keys())
            writer.writeheader()
            writer.writerows(summary_data)
        print(f"\n✅ Batch complete. Summary saved to {csv_path}")

if __name__ == "__main__":
    main()