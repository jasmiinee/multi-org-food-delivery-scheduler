import pandas as pd
import numpy as np

def load_data():
    codex_df = pd.read_csv('reports/codex_validation_summary.csv')
    solver_df = pd.read_csv('reports/solver_validation_summary.csv')
    
    # Ensure boolean columns are actually booleans (sometimes read as strings)
    codex_df['is_feasible'] = codex_df['is_feasible'].astype(str).str.upper() == 'TRUE'
    solver_df['is_feasible'] = solver_df['is_feasible'].astype(str).str.upper() == 'TRUE'

    for df in [codex_df, solver_df]:
        df['mean_travel_minutes'] = pd.to_numeric(df['mean_travel_minutes'], errors='coerce')
        df['households_served'] = pd.to_numeric(df['households_served'], errors='coerce')
        df['priority_weight'] = pd.to_numeric(df['priority_weight'], errors='coerce')
        df['requests_fulfilled'] = pd.to_numeric(df['requests_fulfilled'], errors='coerce')
        
    return codex_df, solver_df

def generate_table1_divergent(codex_df, solver_df):
    """Table 1: Head-to-Head Optimality Gap (Only divergent cases)"""
    # Merge the two dataframes on the 'instance' column
    merged = pd.merge(codex_df, solver_df, on='instance', suffixes=('_codex', '_solver'))
    
    # Filter for divergent cases:
    # 1. Feasibility differs, OR 
    # 2. Households served differs, OR 
    # 3. Travel time differs by more than 0.1 mins
    div_mask = (
        (merged['is_feasible_codex'] != merged['is_feasible_solver']) |
        (merged['households_served_codex'] != merged['households_served_solver']) |
        (abs(merged['mean_travel_minutes_codex'] - merged['mean_travel_minutes_solver']) > 0.1)
    )
    divergent = merged[div_mask].copy()
    
    # Calculate Travel Gap (%)
    def calc_gap(row):
        c = row['mean_travel_minutes_codex']
        s = row['mean_travel_minutes_solver']
        # Handle N/A (like when Codex hit token limit)
        if pd.isna(c) or pd.isna(s): 
            return np.nan
        return round(((c - s) / s) * 100, 2)
        
    divergent['Travel Gap (%)'] = divergent.apply(calc_gap, axis=1)
    
    # Format the table
    table1 = divergent[[
        'instance', 
        'is_feasible_codex', 
        'is_feasible_solver', 
        'mean_travel_minutes_codex', 
        'mean_travel_minutes_solver', 
        'Travel Gap (%)'
    ]].rename(columns={
        'instance': 'Instance',
        'is_feasible_codex': 'Codex Feasible',
        'is_feasible_solver': 'Solver Feasible',
        'mean_travel_minutes_codex': 'Codex Travel',
        'mean_travel_minutes_solver': 'Solver Travel'
    })
    
    table1.to_csv('reports/table1_optimality_gap.csv', index=False)
    print("✅ Table 1 (Divergent Cases) saved to reports/table1_optimality_gap.csv")
    
def generate_table2_aggregate(codex_df, solver_df):
    """Table 2: Aggregate Metrics (No V1/V2 split)"""
    
    def get_metrics(df, method_name):
        total_instances = len(df)
        feasible_count = df['is_feasible'].sum()
        feasibility_rate = (feasible_count / total_instances) * 100
        
        # Only average over feasible instances for Travel & Households
        feasible_df = df[df['is_feasible'] == True]
        
        # Convert to numeric in case they read as strings, coerce errors to NaN
        avg_travel = pd.to_numeric(feasible_df['mean_travel_minutes'], errors='coerce').mean()
        avg_hh = pd.to_numeric(feasible_df['households_served'], errors='coerce').mean()
        
        return {
            'Method': method_name,
            'Feasibility Rate': f"{feasibility_rate:.1f}%",
            'Avg Travel Time': round(avg_travel, 2),
            'Avg Households Served': round(avg_hh, 2)
        }

    agg_data = [
        get_metrics(codex_df, 'Codex (Direct LLM)'),
        get_metrics(solver_df, 'Solver (CP-SAT)')
    ]
    
    table2 = pd.DataFrame(agg_data)
    
    table2.to_csv('reports/table2_aggregate_metrics.csv', index=False)
    print("✅ Table 2 (Aggregate Metrics) saved to reports/table2_aggregate_metrics.csv")

if __name__ == "__main__":
    import os
    os.makedirs('reports', exist_ok=True)
    
    print("Loading data...")
    codex_data, solver_data = load_data()
    
    print("Generating tables...")
    generate_table1_divergent(codex_data, solver_data)
    generate_table2_aggregate(codex_data, solver_data)