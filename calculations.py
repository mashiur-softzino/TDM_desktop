"""
PK Calculations for Therapeutic Drug Monitoring
Mycophenolic Acid (MPA) and other immunosuppressants

AUC method: Linear-Up / Log-Down (mixed trapezoidal) — FDA/EMA standard
LSS regression equations: Le Meur et al., Transplantation 2003
"""

import numpy as np
from scipy.stats import linregress


def canonical_drug_name(drug: str) -> str:
    text = (drug or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in {"MPA", "MYCOPHENOLATE", "MYCOPHENOLIC ACID"}:
        return "MPA"
    if upper in {"TAC", "TACROLIMUS"}:
        return "TAC"
    if upper in {"CSA", "CYCLOSPORINE"}:
        return "CsA"
    if upper == "SIROLIMUS":
        return "Sirolimus"
    return text


THERAPEUTIC_RANGES = {
    'MPA': {
        'range': (30, 60),
        'unit': 'mg·h/L',
        'label': 'AUC₀₋₁₂',
        'description': 'AUC 30–60 mg·h/L (Mycophenolic Acid)',
    },
    'TAC': {
        'range': (5, 15),
        'unit': 'ng/mL',
        'label': 'Trough',
        'description': 'Trough 5–15 ng/mL (Tacrolimus)',
    },
    'CsA': {
        'range': (100, 400),
        'unit': 'ng/mL',
        'label': 'Trough / C₂',
        'description': 'Trough 100–400 ng/mL (Cyclosporine)',
    },
    'Sirolimus': {
        'range': (4, 12),
        'unit': 'ng/mL',
        'label': 'Trough',
        'description': 'Trough 4–12 ng/mL (Sirolimus)',
    },
}


# ─────────────────────────────────────────────────────────────────
# Published LSS regression equations for MPA AUC₀₋₁₂ estimation
# Source: Pawinski et al., Ther Drug Monit 2002
#         Le Meur Y et al., Transplantation 2003
#         van Hest RM et al., Clin Pharmacokinet 2006
# ─────────────────────────────────────────────────────────────────
LSS_EQUATIONS = {
    # Key: (CNI, n_points) → (label, intercept, {time: coefficient}, r2, reference)
    # Only MPA is active. Others kept for future use when more drugs are added.
    ('MPA', 3): {
        'label': '3-point (C₀, C₀.₅, C₂) — MPA AUC₀₋₁₂',
        'intercept': 7.75,
        'coefficients': {0.0: 6.49, 0.5: 0.76, 2.0: 2.43},
        'r2': None,
        'reference': 'Pawinski et al., Ther Drug Monit 2002',
    },
    # ('TAC', 4): {
    #     'label': '4-point (C₀, C₀.₅, C₁, C₂) — Le Meur 2003 [Tac]',
    #     'intercept': 5.85,
    #     'coefficients': {0.0: 2.50, 0.5: 0.64, 1.0: 3.53, 2.0: 1.43},
    #     'r2': 0.94,
    #     'reference': 'Le Meur Y et al. Transplantation 2003',
    # },
    # ('CsA', 4): {
    #     'label': '4-point (C₀, C₀.₅, C₁, C₂) — Le Meur 2003 [CsA]',
    #     'intercept': 11.11,
    #     'coefficients': {0.0: 1.78, 0.5: 0.68, 1.0: 2.86, 2.0: 1.13},
    #     'r2': 0.93,
    #     'reference': 'Le Meur Y et al. Transplantation 2003',
    # },
    # ('TAC', 3): {
    #     'label': '3-point (C₀, C₁, C₂) — Le Meur 2003 [Tac]',
    #     'intercept': 7.38,
    #     'coefficients': {0.0: 3.97, 1.0: 3.88, 2.0: 2.02},
    #     'r2': 0.92,
    #     'reference': 'Le Meur Y et al. Transplantation 2003',
    # },
    # ('ANY', 4): {
    #     'label': '4-point (C₀, C₁, C₂, C₄) — van Hest 2006',
    #     'intercept': 2.2,
    #     'coefficients': {0.0: 2.7, 1.0: 4.5, 2.0: 2.4, 4.0: 4.3},
    #     'r2': 0.93,
    #     'reference': 'van Hest RM et al. Clin Pharmacokinet 2006',
    # },
}


def mixed_trapezoidal_auc(times, concentrations):
    """
    AUC using Linear-Up / Log-Down mixed trapezoidal rule (FDA standard).
    - Rising segments (Cᵢ₊₁ ≥ Cᵢ): linear trapezoid
    - Falling segments (Cᵢ₊₁ < Cᵢ): log-linear trapezoid
    """
    times = np.array(times, dtype=float)
    concs = np.array(concentrations, dtype=float)
    auc = 0.0
    segments = []
    for i in range(1, len(times)):
        dt = times[i] - times[i - 1]
        c0, c1 = concs[i - 1], concs[i]
        area = 0.0
        if c1 >= c0:
            # Rising or flat → linear trapezoid
            area = dt * (c0 + c1) / 2.0
        else:
            # Falling → log-linear trapezoid
            if c1 > 0 and c0 > 0:
                area = dt * (c0 - c1) / np.log(c0 / c1)
            else:
                # Fallback to linear if concentration hits zero
                area = dt * (c0 + c1) / 2.0
        auc += area
    return auc


def estimate_lambda_z(times, concentrations, n_points=3):
    """
    Estimate terminal elimination rate constant (λz) using
    log-linear regression on the last n_points data points.
    Returns (lambda_z, r_squared) or (None, None) if cannot estimate.
    """
    times = np.array(times, dtype=float)
    concs = np.array(concentrations, dtype=float)

    idx = concs > 0
    valid_times = times[idx]
    valid_concs = concs[idx]

    use_n = min(n_points, len(valid_times))
    if use_n < 2:
        return None, None

    t_term = valid_times[-use_n:]
    c_term = valid_concs[-use_n:]

    log_c = np.log(c_term)
    slope, intercept, r_value, p_value, std_err = linregress(t_term, log_c)

    if slope >= 0:
        return None, None

    return -slope, r_value ** 2


def calculate_auc_full(times, concentrations, dose_interval=12.0):
    """
    Full AUC calculation using Linear-Up / Log-Down trapezoidal rule
    with terminal extrapolation to the full dosing interval.

    times          : list/array including trough (t=0)
    concentrations : matching list/array (μg/mL for MPA)
    dose_interval  : dosing interval in hours (default 12)

    Returns dict with:
      auc_0_last  : AUC from 0 to last observed time point
      auc_0_12    : AUC extrapolated to full dosing interval
      lambda_z    : terminal elimination rate constant (h⁻¹)
      t_half      : terminal half-life (h)
      r_squared   : r² of terminal log-linear fit
      t_last      : last observed time point (h)
      c_trough    : trough (pre-dose) concentration
      c_last      : last observed concentration
    """
    times = np.array(times, dtype=float)
    concs = np.array(concentrations, dtype=float)

    t_last = times[-1]
    c_last = float(concs[-1])

    auc_0_last = mixed_trapezoidal_auc(times, concs)

    lambda_z, r_sq = estimate_lambda_z(times, concs, n_points=3)

    auc_0_interval = None
    t_half = None

    if lambda_z is not None and lambda_z > 0:
        t_half = np.log(2) / lambda_z
        remaining = dose_interval - t_last
        if remaining > 0:
            auc_last_12 = (c_last / lambda_z) * (1 - np.exp(-lambda_z * remaining))
            auc_0_interval = auc_0_last + auc_last_12
        else:
            auc_0_interval = auc_0_last

    return {
        'auc_0_last': round(auc_0_last, 3),
        'auc_0_12': round(auc_0_interval, 3) if auc_0_interval is not None else round(auc_0_last, 3),
        'lambda_z': round(lambda_z, 4) if lambda_z is not None else None,
        't_half': round(t_half, 2) if t_half is not None else None,
        'r_squared': round(r_sq, 4) if r_sq is not None else None,
        't_last': float(t_last),
        'c_trough': float(concs[0]),
        'c_last': c_last,
    }


def calculate_lss_auc(times, concentrations, cni='TAC'):
    """
    Calculate AUC₀₋₁₂ using published LSS regression equations (Le Meur 2003).
    Finds the best matching equation based on CNI and available time points.

    times          : list of time points (must include 0 for trough)
    concentrations : matching concentration values
    cni            : 'TAC' or 'CsA' (determines which equation to use)

    Returns dict or None if no matching equation found.
    """
    cni = canonical_drug_name(cni)
    time_conc = dict(zip(times, concentrations))

    # Try to find matching equation
    candidates = []

    for key, eq in LSS_EQUATIONS.items():
        eq_cni, n = key
        if eq_cni not in (cni, 'ANY'):
            continue
        required_times = set(eq['coefficients'].keys())
        available_times = set(round(t, 1) for t in time_conc.keys())
        if required_times.issubset(available_times):
            candidates.append((n, eq, required_times))

    if not candidates:
        return None

    # Use the equation with the most time points
    candidates.sort(key=lambda x: x[0], reverse=True)
    n, eq, req_times = candidates[0]

    auc = eq['intercept']
    for t_req, coef in eq['coefficients'].items():
        matched_t = min(time_conc.keys(), key=lambda t: abs(t - t_req))
        auc += coef * time_conc[matched_t]

    return {
        'auc_lss': round(auc, 3),
        'equation_label': eq['label'],
        'r2': eq['r2'],
        'reference': eq['reference'],
    }


def interpret_result(drug, auc_0_12):
    """Return interpretation string and (low, high) range."""
    drug = canonical_drug_name(drug)
    info = THERAPEUTIC_RANGES.get(drug)
    if not info:
        return 'N/A', None
    low, high = info['range']
    if auc_0_12 < low:
        return 'Low', (low, high)
    elif auc_0_12 > high:
        return 'High', (low, high)
    else:
        return 'Therapeutic', (low, high)
