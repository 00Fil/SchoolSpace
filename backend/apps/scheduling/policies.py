"""Versioned, configurable planning policies whose business choice is open (D03).

Nothing here is an approved centre policy: every default is marked
PENDING_APPROVAL ("da approvare") and is echoed in results as a warning.
Changing a definition requires a new version, never an in-place edit.
"""

FAIRNESS_POLICIES = {
    # D03: equity after coverage, per-student max relative deficit, minutes
    # per beneficiary (a pair counts two beneficiaries).  Da approvare.
    ("fairness-default", 1): {
        "policy_id": "fairness-default",
        "version": 1,
        "approval_status": "PENDING_APPROVAL",
        "measure": "MAX_RELATIVE_DEFICIT_PER_STUDENT",
        "scale": 1000,
        "beneficiary_counting": "MINUTES_PER_BENEFICIARY",
    }
}
# Paper vector; the position of F relative to coverage is a product decision (D03).
DEFAULT_OBJECTIVE_ORDER = ["P0", "P1", "P2", "F", "C", "R", "P", "G"]
OBJECTIVE_ORDER_STATUS = "PENDING_APPROVAL"


def fairness_policy(policy_id="fairness-default", version=1):
    try:
        return dict(FAIRNESS_POLICIES[(policy_id, version)])
    except KeyError:
        raise ValueError("Policy di equità sconosciuta: nuova versione da registrare")
