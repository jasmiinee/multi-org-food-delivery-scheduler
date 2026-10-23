import json
import math
from typing import Dict, List, Any, Tuple

class ScheduleValidator:
    def __init__(self, instance_data: dict, schedule_data: dict):
        self.instance = instance_data
        self.schedule = schedule_data
        self.violations = []
        
        self.req_dict = {r['id']: r for r in instance_data.get('requests', [])}
        self.hh_dict = {h['id']: h for h in instance_data.get('households', [])}
        self.veh_dict = {v['id']: v for v in instance_data.get('vehicles', [])}
        self.vol_dict = {v['id']: v for v in instance_data.get('volunteers', [])}
        self.org_dict = {o['id']: o for o in instance_data.get('organisations', [])}
        self.travel_times = instance_data.get('travel_times', {})
        self.service_minutes = instance_data.get('parameters', {}).get('service_minutes', 10)
        self.loading_minutes = instance_data.get('parameters', {}).get('loading_minutes', 5)
        
        # Get the duplicate policy from the instance parameters; default to 'alternatives' if not specified.
        self.duplicate_policy = instance_data.get('parameters', {}).get('duplicate_policy', 'alternatives')

    def add_violation(self, code: str, message: str):
        self.violations.append({"code": code, "message": message})

    def parse_time_str(self, t_str: str) -> int:
        """Converts 'HH:MM' to minutes from midnight."""
        try:
            h, m = map(int, t_str.split(':'))
            return h * 60 + m
        except Exception:
            return -1

    def get_shift_bounds(self, vol_id: str) -> Tuple[int, int]:
        """Helper to get the shift bounds of any volunteer (Driver or Assistant)."""
        vol = self.vol_dict.get(vol_id)
        if not vol: return 0, 1440
        
        shift_id = vol.get('shift_id')
        if not shift_id: return 0, 1440
        
        org = self.org_dict.get(vol['organisation'])
        if not org: return 0, 1440
        
        shift = next((s for s in org.get('shifts', []) if s['id'] == shift_id), None)
        if shift: return shift['start'], shift['end']
        
        return 0, 1440

    def validate(self) -> dict:
        # 1. Structural & Reference Checks
        self._check_references()
        if self.violations: # If references are totally broken, stop early
            return self._build_result()

        # 2. Request Status & Coverage Checks (C1)
        self._check_request_status()

        # 3. Vehicle, Routing, Timing, & Capacity Checks (C2-C9, C11)
        used_vehicles = self._check_vehicles_and_routes()

        # 4. Recalculate Metrics
        metrics = self._recalculate_metrics(used_vehicles)

        # 5. Objective Mismatch Check
        self._check_objective_mismatch(metrics)

        return self._build_result(metrics)

    def _check_references(self):
        # Check vehicles in output exist in instance
        for v_out in self.schedule.get('vehicles', []):
            v_id = v_out.get('vehicle')
            if v_id not in self.veh_dict:
                self.add_violation("UNKNOWN_ID", f"Vehicle {v_id} is not in the instance.")
                continue
            
            # Check driver
            driver_id = v_out.get('driver')
            if driver_id not in self.vol_dict:
                self.add_violation("UNKNOWN_ID", f"Driver {driver_id} is not in the instance.")
            elif self.vol_dict[driver_id]['vehicle_id'] != v_id:
                self.add_violation("WRONG_ORGANISATION", f"Driver {driver_id} does not own vehicle {v_id}.")

            # Check assistants
            for a_id in v_out.get('assistants', []):
                if a_id not in self.vol_dict:
                    self.add_violation("UNKNOWN_ID", f"Assistant {a_id} is not in the instance.")
                elif self.vol_dict[a_id]['role'] != 'assistant':
                    self.add_violation("OTHER", f"Volunteer {a_id} is not an assistant.")

            # Check requests
            for stop in v_out.get('route', []):
                r_id = stop.get('request')
                if r_id not in self.req_dict:
                    self.add_violation("UNKNOWN_ID", f"Request {r_id} is not in the instance.")
                
                hh_id = stop.get('household')
                if hh_id not in self.hh_dict:
                    self.add_violation("UNKNOWN_ID", f"Household {hh_id} in route is not in the instance.")
                
                if hh_id not in self.travel_times:
                    self.add_violation("UNKNOWN_ID", f"Household {hh_id} missing from travel_times matrix.")

    def _check_request_status(self):
        all_reqs = set(self.req_dict.keys())
        seen_reqs = set()
        fulfilled_counts = {}
        fulfilled_reqs = set()
        unserved_hhs = set()

        for status_obj in self.schedule.get('request_status', []):
            r_id = status_obj.get('request')
            status = status_obj.get('status')
            
            if r_id not in all_reqs:
                self.add_violation("UNKNOWN_ID", f"Request status refers to unknown request {r_id}.")
                continue
                
            if r_id in seen_reqs:
                self.add_violation("OTHER", f"Request {r_id} appears multiple times in request_status.")
            seen_reqs.add(r_id)

            if status == 'fulfilled':
                fulfilled_reqs.add(r_id) # Track them
                hh = self.req_dict[r_id]['household']
                fulfilled_counts[hh] = fulfilled_counts.get(hh, 0) + 1
            elif status not in ['covered_by_alternative', 'unserved']:
                self.add_violation("SCHEMA_ERROR", f"Invalid status '{status}' for request {r_id}.")

        # C1: Missing statuses
        missing = all_reqs - seen_reqs
        for m in missing:
            self.add_violation("MISSING_REQUEST_STATUS", f"Request {m} has no status in request_status.")

        # C1: Duplicate Service (Only enforced if policy is 'alternatives' i.e., V1)
        if self.duplicate_policy == 'alternatives':
            for hh, count in fulfilled_counts.items():
                if count > 1:
                    self.add_violation("DUPLICATE_SERVICE", f"Household {hh} is served {count} times.")

        # Cross-reference unserved_households list
        for uh in self.schedule.get('unserved_households', []):
            hh_id = uh.get('household')
            if hh_id not in self.hh_dict:
                self.add_violation("UNKNOWN_ID", f"Unserved list refers to unknown household {hh_id}.")
                continue
            unserved_hhs.add(hh_id)
            
            # If a household is in unserved list, it shouldn't have any fulfilled requests
            if hh_id in fulfilled_counts:
                self.add_violation("OTHER", f"Household {hh_id} is in unserved_households but has fulfilled requests.")

        # Ensure all fulfilled requests actually appear in a route
        routed_reqs = set()
        for v_out in self.schedule.get('vehicles', []):
            for stop in v_out.get('route', []):
                routed_reqs.add(stop.get('request'))

        for r_id in fulfilled_reqs:
            if r_id not in routed_reqs:
                self.add_violation("OTHER", f"Request {r_id} is marked fulfilled but never appears in any vehicle route.")

    def _check_vehicles_and_routes(self) -> set:
        used_vehicles = set()
        assistant_assignments = {}

        for v_out in self.schedule.get('vehicles', []):
            v_id = v_out.get('vehicle')
            if v_id not in self.veh_dict:
                continue
            
            veh = self.veh_dict[v_id]
            used_vehicles.add(v_id)
            
            # Team & Seats (C7, C8)
            driver_id = v_out.get('driver')
            assistants = v_out.get('assistants', [])
            
            if len(assistants) + 1 > veh['seats']:
                self.add_violation("SEAT_CAPACITY", f"Vehicle {v_id} requires {len(assistants)+1} seats, but has {veh['seats']}.")

            for a_id in assistants:
                if a_id in assistant_assignments:
                    self.add_violation("ASSISTANT_DOUBLE_BOOKED", f"Assistant {a_id} is assigned to multiple vehicles.")
                assistant_assignments[a_id] = v_id

                # C2 & C7: Own Organisation Only
                if a_id in self.vol_dict and self.vol_dict[a_id]['organisation'] != veh['organisation']:
                    self.add_violation("WRONG_ORGANISATION", f"Assistant {a_id} is from a different org than vehicle {v_id}.")

            # Timing & Routing (C3, C4, C5, C6, C9, C11)
            loading_start_str = v_out.get('loading_start', '00:00')
            departure_str = v_out.get('departure', '00:00')
            return_str = v_out.get('return', '00:00')
            
            loading = self.parse_time_str(loading_start_str)
            departure = self.parse_time_str(departure_str)
            ret = self.parse_time_str(return_str)

            if departure != loading + self.loading_minutes:
                self.add_violation("TIME_PROPAGATION", f"Vehicle {v_id} departure ({departure}) does not equal loading ({loading}) + {self.loading_minutes} mins.")

            # Route Traversal
            prev_loc = veh['home_depot']
            prev_time = departure
            total_ambient = 0
            total_chilled = 0
            has_trained = self.vol_dict.get(driver_id, {}).get('trained', False)
            for a_id in assistants:
                if self.vol_dict.get(a_id, {}).get('trained', False):
                    has_trained = True

            for i, stop in enumerate(v_out.get('route', [])):
                r_id = stop.get('request')
                hh_id = stop.get('household')
                s_start_str = stop.get('service_start', '00:00')
                s_start = self.parse_time_str(s_start_str)

                if r_id not in self.req_dict or hh_id not in self.travel_times:
                    continue
                
                req = self.req_dict[r_id]
                hh = self.hh_dict.get(hh_id, {})

                # C3: Consistency between route and request_status
                req_status_obj = next((s for s in self.schedule.get('request_status', []) if s['request'] == r_id), None)
                if req_status_obj and req_status_obj.get('status') != 'fulfilled':
                    self.add_violation("ROUTE_ERROR", f"Request {r_id} is in vehicle {v_id}'s route but status is '{req_status_obj.get('status')}'.")

                # C2: Organisation and Depot
                if req['organisation'] != veh['organisation']:
                    self.add_violation("WRONG_ORGANISATION", f"Vehicle {v_id} serves request {r_id} from a different org.")
                if req.get('depot') != veh['home_depot']:
                    self.add_violation("WRONG_ORGANISATION", f"Request {r_id} loads from depot {req.get('depot')}, but vehicle {v_id} home depot is {veh['home_depot']}.")

                # C11: Trained Volunteer
                if hh.get('needs_trained_volunteer') and not has_trained:
                    self.add_violation("TRAINING", f"Household {hh_id} needs trained volunteer, but vehicle {v_id} lacks one.")

                # C4: Time Propagation
                travel_time = self.travel_times.get(prev_loc, {}).get(hh_id, 0)
                earliest_arrival = prev_time + travel_time
                if s_start < earliest_arrival:
                    self.add_violation("TIME_PROPAGATION", f"Request {r_id} starts at {s_start_str}, but earliest possible is {earliest_arrival} mins.")

                # C5: Time Windows
                if s_start < req['window_start'] or s_start > req['window_end']:
                    self.add_violation("TIME_WINDOW", f"Request {r_id} starts at {s_start_str}, outside window [{req['window_start']}, {req['window_end']}].")

                # C9: Capacities
                total_ambient += req['ambient_crates']
                total_chilled += req['chilled_crates']

                # Prepare for next stop
                prev_loc = hh_id
                prev_time = s_start + self.service_minutes

            # C3 & C6: Check Return Time exactly matches the physical route
            travel_back = self.travel_times.get(prev_loc, {}).get(veh['home_depot'], 0)
            expected_return = prev_time + travel_back
            
            # Enforce exact return time (no extra padding allowed)
            if ret != expected_return:
                self.add_violation("TIME_PROPAGATION", f"Vehicle {v_id} reports return at {return_str} ({ret} mins), but physical route dictates return at {expected_return} mins.")

            # C6: SHIFTS (Check Driver AND all Assistants)
            d_start, d_end = self.get_shift_bounds(driver_id)
            if loading < d_start or ret > d_end:
                self.add_violation("SHIFT", f"Vehicle {v_id} trip ({loading}-{ret}) exceeds driver {driver_id}'s shift ({d_start}-{d_end}).")

            for a_id in assistants:
                a_start, a_end = self.get_shift_bounds(a_id)
                if loading < a_start or ret > a_end:
                    self.add_violation("SHIFT", f"Vehicle {v_id} trip ({loading}-{ret}) exceeds assistant {a_id}'s shift ({a_start}-{a_end}).")

            # C9: Final Capacity Checks
            if total_ambient > veh['ambient_capacity']:
                self.add_violation("AMBIENT_CAPACITY", f"Vehicle {v_id} has {total_ambient} ambient crates, max is {veh['ambient_capacity']}.")
            if total_chilled > veh['chilled_capacity']:
                self.add_violation("CHILLED_CAPACITY", f"Vehicle {v_id} has {total_chilled} chilled crates, max is {veh['chilled_capacity']}.")

        return used_vehicles

    def _recalculate_metrics(self, used_vehicles: set) -> dict:
        served_households = set()
        priority_weight = 0
        requests_fulfilled = 0 # V2 metric

        # Re-derive from request_status
        for status_obj in self.schedule.get('request_status', []):
            if status_obj.get('status') == 'fulfilled':
                requests_fulfilled += 1
                r_id = status_obj.get('request')
                if r_id in self.req_dict:
                    hh_id = self.req_dict[r_id]['household']
                    served_households.add(hh_id)

        for hh_id in served_households:
            if hh_id in self.hh_dict:
                priority_weight += self.hh_dict[hh_id]['priority']

        # Calculate exact travel time
        total_travel = 0
        for v_out in self.schedule.get('vehicles', []):
            v_id = v_out.get('vehicle')
            if v_id not in self.veh_dict:
                continue
            
            veh = self.veh_dict[v_id]
            prev_loc = veh['home_depot']
            
            for stop in v_out.get('route', []):
                hh_id = stop.get('household')
                if hh_id:
                    total_travel += self.travel_times.get(prev_loc, {}).get(hh_id, 0)
                    prev_loc = hh_id
            
            total_travel += self.travel_times.get(prev_loc, {}).get(veh['home_depot'], 0)

        mean_travel = (total_travel / len(used_vehicles)) if used_vehicles else 0.0

        return {
            "households_served": len(served_households),
            "requests_fulfilled": requests_fulfilled,
            "priority_weight": priority_weight,
            "mean_travel_minutes": round(mean_travel, 2),
            "vehicles_used": len(used_vehicles)
        }

    def _check_objective_mismatch(self, metrics: dict):
        claimed = self.schedule.get('objective', {})
        mismatch = False
        
        if claimed.get('households_served') != metrics['households_served']:
            mismatch = True
        if 'requests_fulfilled' in claimed and claimed.get('requests_fulfilled') != metrics['requests_fulfilled']:
            mismatch = True
        if claimed.get('priority_weight') != metrics['priority_weight']:
            mismatch = True
        if claimed.get('vehicles_used') != metrics['vehicles_used']:
            mismatch = True
        # Allow slight float tolerance for mean travel
        if abs(claimed.get('mean_travel_minutes', 0) - metrics['mean_travel_minutes']) > 0.1:
            mismatch = True

        if mismatch:
            self.add_violation("OBJECTIVE_MISMATCH", f"Claimed objective {claimed} does not match recomputed {metrics}.")

    def _build_result(self, metrics=None) -> dict:
        return {
            "is_feasible": len(self.violations) == 0,
            "violations": self.violations,
            "recomputed_metrics": metrics or {},
            "claimed_metrics": self.schedule.get('objective', {})
        }