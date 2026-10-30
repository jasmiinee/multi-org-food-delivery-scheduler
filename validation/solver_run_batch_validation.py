import os
import json
import re
import csv
from validator import ScheduleValidator

# Dynamically generate paths for the new solver outputs
SOLVER_FILES = []
# Easy: 001 to 005
SOLVER_FILES.extend([f"outputs/solver/easy/input_easy_{i:03d}.json" for i in range(1, 6)])
# Medium: 001 to 005
SOLVER_FILES.extend([f"outputs/solver/medium/input_medium_{i:03d}.json" for i in range(1, 6)])
# Hard: 001 to 014
SOLVER_FILES.extend([f"outputs/solver/hard/hard_{i:03d}.json" for i in range(1, 15)])

def get_instance_path(schedule_path: str) -> tuple[str, str]:
    """Extracts the instance name and builds the path from the new structure."""
    basename = os.path.basename(schedule_path).replace('.json', '')
    
    # The parent directory (easy, medium, hard) tells us the level
    level = os.path.basename(os.path.dirname(schedule_path))
    
    # The solver files match the instance names exactly (e.g., input_easy_001, hard_001)
    instance_name = basename
    instance_path = os.path.join("instances/input_first", level, f"{instance_name}.json")
    
    return instance_path, instance_name

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
            
            # Output validation file is saved next to the schedule
            validation_out_path = schedule_path.replace('.json', '_validation.json')

            if not os.path.exists(instance_path):
                print(f"❌ Instance file missing for {instance_name} at {instance_path}")
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

    # Save to the same solver CSV
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