import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from itantra_ai.priority.priority_engine import PriorityEngine
from itantra_ai.priority.adaptive_priority_engine import AdaptivePriorityEngine

def show(label, semantic_dict):
    print(f"\n=== {label} ===")
    print("Message:", semantic_dict)

    old = PriorityEngine.assign_priorities(semantic_dict)
    print("OLD (fixed by field name):")
    for tier in ["P0", "P1", "P2", "P3"]:
        if old[tier]:
            print(f"  {tier}: {old[tier]}")

    print("NEW (adaptive, context-sensitive):")
    for row in AdaptivePriorityEngine.explain(semantic_dict):
        print(f"  {row['field']:<10} = {str(row['value']):<18} "
              f"base={row['base_score']:>3} value_mod={row['value_modifier']:>+3} "
              f"ctx_mod={row['context_modifier']:>+3}  -> score={row['final_score']:>3}  tier={row['tier']}")


# Case 1: routine status check-in - LOCATION should stay low priority
show("Routine check-in", {
    "TEAM": "ENGINEER", "LOCATION": "HQ", "STATUS": "ARRIVED"
})

# Case 2: evacuation order - LOCATION should escalate to P0 even though
# it's the same field type as case 1's LOCATION
show("Critical evacuation order", {
    "ACTION": "EVACUATE", "URGENCY": "CRITICAL",
    "LOCATION": "POWER_PLANT", "QUANTITY": "12"
})

# Case 3: same field (LOCATION), different value/context -> different tier
# This is the exact limitation we discussed: old engine always gives
# LOCATION = P1 no matter what. New engine differentiates.
print("\n=== Direct comparison: same field, different context ===")
msg_a = {"ACTION": "REPORT", "LOCATION": "HQ"}
msg_b = {"ACTION": "EVACUATE", "URGENCY": "HIGH", "LOCATION": "SECTOR_4"}
for label, msg in [("routine report at HQ", msg_a), ("urgent evacuation at Sector 4", msg_b)]:
    old_tier = PriorityEngine.get_priority_level("LOCATION")
    new_scores = AdaptivePriorityEngine.score_fields(msg)
    from itantra_ai.priority.adaptive_priority_engine import _score_to_tier
    print(f"  [{label}] OLD tier for LOCATION: {old_tier} (always fixed)  "
          f"NEW tier for LOCATION: {_score_to_tier(new_scores['LOCATION'])} "
          f"(score={new_scores['LOCATION']})")
