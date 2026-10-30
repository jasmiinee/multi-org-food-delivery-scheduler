import pandas as pd
import numpy as np
import os

def load_and_clean_data():
    # Load the CSVs
    llm_df = pd.read_csv('reports/llm_validation_summary.csv')
    solver_df = pd.read_csv('reports/solver_validation_summary.csv')
    
    # Standardise instance names (e.g., input_easy_001 -> easy_001)
    llm_df['instance'] = llm_df['instance'].str.replace('input_', '', regex=False)
    solver_df['instance'] = solver_df['instance'].str.replace('input_', '', regex=False)
    
    # Merge on instance
    merged = pd.merge(llm_df, solver_df, on='instance', suffixes=('_llm', '_solver'))
    
    # Parse boolean feasibility
    merged['is_feasible_llm'] = merged['is_feasible_llm'].astype(str).str.upper() == 'TRUE'
    merged['is_feasible_solver'] = merged['is_feasible_solver'].astype(str).str.upper() == 'TRUE'
    
    # Parse "Served/Total" strings into numeric columns
    def parse_ratio(val, index):
        if pd.isna(val) or '-' in str(val): return np.nan
        parts = str(val).split('/')
        if len(parts) == 2: return float(parts[index])
        return np.nan

    for prefix in ['llm', 'solver']:
        merged[f'hh_s_{prefix}'] = merged[f'households_served_{prefix}'].apply(lambda x: parse_ratio(x, 0))
        merged[f'hh_t_{prefix}'] = merged[f'households_served_{prefix}'].apply(lambda x: parse_ratio(x, 1))
        merged[f'reqs_s_{prefix}'] = merged[f'requests_fulfilled_{prefix}'].apply(lambda x: parse_ratio(x, 0))
        merged[f'reqs_t_{prefix}'] = merged[f'requests_fulfilled_{prefix}'].apply(lambda x: parse_ratio(x, 1))
        merged[f'priority_{prefix}'] = pd.to_numeric(merged[f'priority_weight_{prefix}'], errors='coerce')
        merged[f'travel_{prefix}'] = pd.to_numeric(merged[f'mean_travel_minutes_{prefix}'], errors='coerce')

    return merged

def format_diff(val, is_float=False):
    """Helper to format differences: standardises 0 and adds +/- for others"""
    if not isinstance(val, (int, float, np.integer, np.floating)): 
        return val
    if val == 0:
        return "0.00" if is_float else "0"
    return f"{val:+.2f}" if is_float else f"{int(val):+}"

def generate_table1_detailed(df):
    """Table 1: Comparison of Direct LLM and CP-SAT Solver on All Instances"""
    rows = []
    for _, r in df.iterrows():
        inst = r['instance']
        
        # 1. Validity
        rows.append({
            "Instance": inst, "Metric": "Validity",
            "CP-SAT": "Yes" if r['is_feasible_solver'] else "No",
            "Direct LLM": "Yes" if r['is_feasible_llm'] else "No",
            "Difference": "–" if r['is_feasible_solver'] == r['is_feasible_llm'] else "Mismatch"
        })
        
        # 2. Households
        hh_sol = r['households_served_solver'] if pd.notna(r['hh_s_solver']) else "-"
        hh_llm = r['households_served_llm'] if pd.notna(r['hh_s_llm']) else "-"
        hh_diff = (r['hh_s_llm'] - r['hh_s_solver']) if pd.notna(r['hh_s_llm']) and pd.notna(r['hh_s_solver']) else "-"
        rows.append({
            "Instance": "", "Metric": "Households served",
            "CP-SAT": hh_sol, "Direct LLM": hh_llm,
            "Difference": format_diff(hh_diff)
        })
        
        # 3. Priority Weight
        pr_sol = r['priority_solver'] if pd.notna(r['priority_solver']) else "-"
        pr_llm = r['priority_llm'] if pd.notna(r['priority_llm']) else "-"
        pr_diff = (r['priority_llm'] - r['priority_solver']) if pd.notna(r['priority_llm']) and pd.notna(r['priority_solver']) else "-"
        rows.append({
            "Instance": "", "Metric": "Priority weight",
            "CP-SAT": int(pr_sol) if pr_sol != "-" else "-", 
            "Direct LLM": int(pr_llm) if pr_llm != "-" else "-",
            "Difference": format_diff(pr_diff)
        })
        
        # 4. Requests Fulfilled
        rq_sol = r['requests_fulfilled_solver'] if pd.notna(r['reqs_s_solver']) else "-"
        rq_llm = r['requests_fulfilled_llm'] if pd.notna(r['reqs_s_llm']) else "-"
        rq_diff = (r['reqs_s_llm'] - r['reqs_s_solver']) if pd.notna(r['reqs_s_llm']) and pd.notna(r['reqs_s_solver']) else "-"
        rows.append({
            "Instance": "", "Metric": "Requests fulfilled",
            "CP-SAT": rq_sol, "Direct LLM": rq_llm,
            "Difference": format_diff(rq_diff)
        })
        
        # 5. Travel Time
        tr_sol = round(r['travel_solver'], 2) if pd.notna(r['travel_solver']) else "-"
        tr_llm = round(r['travel_llm'], 2) if pd.notna(r['travel_llm']) else "-"
        tr_diff = round(r['travel_llm'] - r['travel_solver'], 2) if pd.notna(r['travel_llm']) and pd.notna(r['travel_solver']) else "-"
        rows.append({
            "Instance": "", "Metric": "Mean travel (min)",
            "CP-SAT": tr_sol, "Direct LLM": tr_llm,
            "Difference": format_diff(tr_diff, is_float=True)
        })
        
    table1 = pd.DataFrame(rows)
    table1.to_csv('reports/table1_detailed_comparison.csv', index=False)
    print("✅ Table 1 generated.")

def generate_table2_aggregate(df):
    """Table 2: Aggregate Performance Comparison"""
    llm_feas = df['is_feasible_llm'].sum()
    sol_feas = df['is_feasible_solver'].sum()
    total = len(df)
    
    table2 = pd.DataFrame([
        {"Metric": "Feasibility rate (%)", "Direct LLM": f"{(llm_feas/total)*100:.1f}%", "CP-SAT": f"{(sol_feas/total)*100:.1f}%"},
        {"Metric": "Average households served", "Direct LLM": round(df['hh_s_llm'].mean(), 2), "CP-SAT": round(df['hh_s_solver'].mean(), 2)},
        {"Metric": "Average priority weight", "Direct LLM": round(df['priority_llm'].mean(), 2), "CP-SAT": round(df['priority_solver'].mean(), 2)},
        {"Metric": "Average requests fulfilled", "Direct LLM": round(df['reqs_s_llm'].mean(), 2), "CP-SAT": round(df['reqs_s_solver'].mean(), 2)},
        {"Metric": "Average travel time (min)", "Direct LLM": round(df['travel_llm'].mean(), 2), "CP-SAT": round(df['travel_solver'].mean(), 2)},
    ])
    table2.to_csv('reports/table2_aggregate_comparison.csv', index=False)
    print("✅ Table 2 generated.")

def generate_table3_violations(df):
    """Table 3: Constraint violation analysis for Direct LLM"""
    invalid_llm = df[df['is_feasible_llm'] == False]
    total_invalid = len(invalid_llm)
    
    taxonomy = [
        ("Organisation eligibility", "WRONG_ORGANISATION", "Requests must be served by vehicles and volunteers belonging to the same organisation."),
        ("Routing", "ROUTE_ERROR", "Each vehicle must complete a single trip starting and ending at its home depot."),
        ("Timing", "TIME_PROPAGATION", "Service times must account for travel time, service duration and waiting."),
        ("Time windows", "TIME_WINDOW", "Each delivery must start within its specified time window."),
        ("Shifts", "SHIFT", "The entire trip, from loading to return, must fall within every team member's shift."),
        ("Assistant assignment", "ASSISTANT_DOUBLE_BOOKED", "Each assistant can be assigned to at most one vehicle."),
        ("Seat capacity", "SEAT_CAPACITY", "The driver and assistants must not exceed the vehicle's seating capacity."),
        ("Vehicle capacity", "AMBIENT_CAPACITY, CHILLED_CAPACITY", "Ambient and chilled loads must not exceed their respective vehicle capacities."),
        ("Specialised needs", "TRAINING", "At least one team member must be trained when serving a household requiring specialised assistance."),
        ("Other / Objective", "OBJECTIVE_MISMATCH, OTHER, PARSE_ERROR, SCHEMA_ERROR, UNKNOWN_ID", "Reported metrics do not match the physical route, or output format was invalid.")
    ]
    
    rows = []
    for name, codes_str, desc in taxonomy:
        target_codes = [c.strip() for c in codes_str.split(',')]
        count = 0
        for _, row in invalid_llm.iterrows():
            row_codes = [c.strip() for c in str(row['violation_codes_llm']).split(',')]
            if any(tc in row_codes for tc in target_codes):
                count += 1
                
        pct = f"{(count / total_invalid * 100):.1f}%" if total_invalid > 0 else "0.0%"
        rows.append({
            "Constraint": name,
            "Constraint description": desc,
            "Number of violations": count,
            "Percentage of invalid schedules affected": pct
        })
        
    table3 = pd.DataFrame(rows)
    table3.to_csv('reports/table3_violation_analysis.csv', index=False)
    print("✅ Table 3 generated.")

def generate_table4_scaling(df):
    """Table 4: Scaling degradation by difficulty"""
    df['difficulty'] = df['instance'].apply(lambda x: x.split('_')[0])
    
    rows = []
    for diff in ['easy', 'medium', 'hard']:
        subset = df[df['difficulty'] == diff]
        if subset.empty: continue
        
        total = len(subset)
        sol_feas = subset['is_feasible_solver'].sum()
        llm_feas = subset['is_feasible_llm'].sum()
        
        sol_cov = round((subset['hh_s_solver'] / subset['hh_t_solver'] * 100).mean(), 1)
        llm_cov = round((subset['hh_s_llm'] / subset['hh_t_llm'] * 100).mean(), 1)
        
        rows.append({
            "Difficulty": f"{diff.capitalize()} ({total})",
            "Feasible (CP-SAT)": f"{sol_feas}/{total} ({sol_feas/total*100:.0f}%)",
            "Feasible (LLM)": f"{llm_feas}/{total} ({llm_feas/total*100:.0f}%)",
            "Avg. HH coverage (CP-SAT)": f"{sol_cov}%",
            "Avg. HH coverage (LLM)": f"{llm_cov}%"
        })
        
    table4 = pd.DataFrame(rows)
    table4.to_csv('reports/table4_scaling_degradation.csv', index=False)
    print("✅ Table 4 generated.")

if __name__ == "__main__":
    os.makedirs('reports', exist_ok=True)
    print("Loading and standardising data...")
    merged_data = load_and_clean_data()
    
    print("Generating tables...")
    generate_table1_detailed(merged_data)
    generate_table2_aggregate(merged_data)
    generate_table3_violations(merged_data)
    generate_table4_scaling(merged_data)
    print("\nAll tables saved to the 'reports/' folder!")