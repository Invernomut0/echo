"""Cognitive Thermodynamics — Boltzmann framework for ECHO's plasticity.

Background
----------
An unexpected bridge connects Boltzmann autoregressive generators (used to
sample molecular configuration spaces) and emerging theories of artificial
self-consciousness: both explore a huge configuration space by evaluating an
"energy" or "credibility" for each state.  In statistical physics,
equilibrium distributions are given by:

    P(state) ∝ exp(−E(state) / kT)

where T is the temperature and E is the energy.  This paper applies the same
principle to ECHO's cognitive architecture.

Cognitive Free Energy (Friston-inspired)
-----------------------------------------
We define the **cognitive free energy**:

    F = U − T · S

where:
  - U  = internal energy  = Σᵢ (setpoint_i − drive_i)²
          drives far from their homeostatic targets → high disorder
  - S  = cognitive entropy = −Σⱼ p_j · log(p_j)
          Shannon entropy of the normalised agent-weight distribution
          high S → agents are equally weighted (exploratory)
          low S  → one agent dominates (specialised / rigid)
  - T  = temperature      = f(arousal, stability, cycle_age)
          high T (aroused, unstable) → bold exploration, accept surprises
          low T  (calm, stable)      → crystallise best configurations

Thermodynamic consolidation analogy
-------------------------------------
Memory consolidation is a "cooling" process:
  - During active interaction T is high → accept diverse memories (explore)
  - During sleep/consolidation T decreases → only coherent states survive
  - Final stable self-model = a free-energy minimum (ground state)

Boltzmann acceptance (Metropolis–Hastings criterion)
-----------------------------------------------------
For each proposed weight change δ:
  - If ΔF < 0 → always accept (improvement)
  - If ΔF > 0 → accept with probability exp(−ΔF / T)

This prevents the system from freezing in a local minimum (vs. greedy descent)
and mirrors the thermodynamic origin of robustness in physical systems.
"""

from __future__ import annotations

import math
import random
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from echo.core.types import MetaState

logger = logging.getLogger(__name__)

# ── Homeostatic setpoints ──────────────────────────────────────────────────────
# The "ground state" drive values toward which ECHO naturally gravitates.
DRIVE_SETPOINTS: dict[str, float] = {
    "coherence":   0.70,
    "curiosity":   0.60,
    "stability":   0.65,
    "competence":  0.65,
    "compression": 0.55,
}

# Base temperature — prevents the system from fully freezing even at rest
_BASE_TEMP: float = 0.05
# Maximum temperature (fully aroused, unstable state)
_MAX_TEMP: float  = 1.50
# Boltzmann constant for cognitive space (scales acceptance probability)
_K_COG: float = 1.0


# ── Core metric ───────────────────────────────────────────────────────────────

@dataclass
class ThermodynamicState:
    """Snapshot of ECHO's thermodynamic quantities at a given moment."""
    temperature: float        # T   ∈ [0, ∞)
    internal_energy: float    # U   ∈ [0, 1]  (normalised MSE from setpoints)
    entropy: float            # S   ∈ [0, ln(n_agents)]
    free_energy: float        # F = U − T·S
    drive_snapshot: dict[str, float] = field(default_factory=dict)
    weight_snapshot: dict[str, float] = field(default_factory=dict)


def compute_temperature(meta_state: "MetaState") -> float:
    """Derive cognitive temperature from the meta-state.

    T = base + arousal_component + instability_component

    High arousal + low stability → high T (plastic, exploratory).
    Low arousal + high stability → low T (rigid, conservative).
    """
    arousal   = meta_state.arousal                     # 0–1
    stability = meta_state.drives.stability            # 0–1

    # Instability drives temperature up — unstable systems need to explore
    instability = 1.0 - stability

    # Valence asymmetry: negative affect slightly raises temperature
    valence_penalty = max(0.0, -meta_state.emotional_valence) * 0.15

    T = _BASE_TEMP + arousal * 0.6 + instability * 0.5 + valence_penalty
    return min(_MAX_TEMP, max(_BASE_TEMP, T))


def compute_internal_energy(meta_state: "MetaState") -> float:
    """Measure cognitive dissonance as mean squared deviation from setpoints.

    U = (1/n) · Σᵢ (setpoint_i − drive_i)²

    U = 0 → all drives at homeostatic optimum (perfect cognitive health)
    U = 1 → all drives maximally displaced (severe cognitive distress)
    """
    drives = {
        "coherence":   meta_state.drives.coherence,
        "curiosity":   meta_state.drives.curiosity,
        "stability":   meta_state.drives.stability,
        "competence":  meta_state.drives.competence,
        "compression": meta_state.drives.compression,
    }
    mse = sum(
        (DRIVE_SETPOINTS[k] - v) ** 2
        for k, v in drives.items()
        if k in DRIVE_SETPOINTS
    ) / len(DRIVE_SETPOINTS)
    return round(mse, 6)


def compute_entropy(agent_weights: dict[str, float]) -> float:
    """Shannon entropy of the normalised agent-weight distribution.

    S = −Σⱼ p_j · log(p_j)   where p_j = w_j / Σ wₖ

    Maximum S = ln(n_agents) ≈ 1.946  for 7 agents (uniform distribution)
    Minimum S = 0  (one agent monopolises all weight)
    """
    if not agent_weights:
        return 0.0
    total = sum(agent_weights.values())
    if total <= 0:
        return 0.0
    probs = [w / total for w in agent_weights.values() if w > 0]
    return -sum(p * math.log(p) for p in probs)


def compute_free_energy(meta_state: "MetaState") -> float:
    """F = U − T·S (cognitive free energy).

    Minimising F simultaneously:
      1. Reduces cognitive dissonance (low U)
      2. Maintains appropriate diversity at the given temperature (maximise T·S)

    High F → system is in a high-energy, unstable configuration.
    Low F  → system has crystallised into a coherent, stable representation
             (not necessarily boring — at high T, stable = diverse).
    """
    T = compute_temperature(meta_state)
    U = compute_internal_energy(meta_state)
    S = compute_entropy(meta_state.agent_weights)
    F = U - T * S
    return round(F, 6)


def thermodynamic_snapshot(meta_state: "MetaState") -> ThermodynamicState:
    """Return a full thermodynamic snapshot for the given meta-state."""
    T = compute_temperature(meta_state)
    U = compute_internal_energy(meta_state)
    S = compute_entropy(meta_state.agent_weights)
    F = U - T * S
    return ThermodynamicState(
        temperature=round(T, 4),
        internal_energy=round(U, 6),
        entropy=round(S, 4),
        free_energy=round(F, 6),
        drive_snapshot={
            "coherence":   meta_state.drives.coherence,
            "curiosity":   meta_state.drives.curiosity,
            "stability":   meta_state.drives.stability,
            "competence":  meta_state.drives.competence,
            "compression": meta_state.drives.compression,
        },
        weight_snapshot=dict(meta_state.agent_weights),
    )


# ── Boltzmann / Metropolis acceptance ─────────────────────────────────────────

def boltzmann_accept(delta_free_energy: float, temperature: float) -> bool:
    """Metropolis–Hastings acceptance criterion.

    Accept a proposed weight change unconditionally if it reduces F (ΔF < 0).
    Accept it probabilistically if it increases F (ΔF > 0):

        P(accept) = exp(−ΔF / (k·T))

    This prevents the optimizer from getting stuck in a local minimum —
    analogous to how physical systems escape metastable configurations through
    thermal fluctuations.

    Args:
        delta_free_energy: F(proposed) − F(current)
        temperature:       current cognitive temperature T

    Returns:
        True if the change should be accepted.
    """
    if delta_free_energy <= 0:
        return True  # unconditional improvement
    if temperature <= 0:
        return False  # fully frozen — reject all worsening moves
    p = math.exp(-delta_free_energy / (_K_COG * temperature))
    accepted = random.random() < p
    if accepted:
        logger.debug(
            "Metropolis: accepted ΔF=%.4f at T=%.3f (p=%.3f)", delta_free_energy, temperature, p
        )
    return accepted


def boltzmann_softmax(
    scores: list[float], temperature: float
) -> list[float]:
    """Convert a list of free-energy scores to a Boltzmann probability distribution.

    p_i = exp(−score_i / T) / Σ_j exp(−score_j / T)

    Lower score (lower free energy) → higher probability.
    At T → ∞: uniform distribution (pure exploration)
    At T → 0:  all mass on the minimum (pure exploitation)

    Args:
        scores:      list of free-energy values (lower = better)
        temperature: cognitive temperature T

    Returns:
        Probability vector (sums to 1.0)
    """
    if temperature <= 1e-9:
        # Zero temperature: deterministic argmin
        min_idx = scores.index(min(scores))
        return [1.0 if i == min_idx else 0.0 for i in range(len(scores))]

    # Numerically stable softmax over −score / T
    logits = [-s / temperature for s in scores]
    max_l  = max(logits)
    exps   = [math.exp(l - max_l) for l in logits]
    total  = sum(exps)
    return [e / total for e in exps]


def boltzmann_sample(
    candidates: list,
    free_energies: list[float],
    temperature: float,
) -> object:
    """Sample one candidate proportionally to its Boltzmann weight.

    Replaces pure-greedy elitist selection with stochastic selection that
    preserves diversity at high temperature while converging to the optimum
    at low temperature.

    Args:
        candidates:    list of any objects to choose from
        free_energies: corresponding free-energy score for each candidate
        temperature:   cognitive temperature

    Returns:
        The selected candidate.
    """
    probs = boltzmann_softmax(free_energies, temperature)
    r = random.random()
    cumulative = 0.0
    for candidate, p in zip(candidates, probs):
        cumulative += p
        if r <= cumulative:
            return candidate
    return candidates[-1]  # fallback (floating-point edge case)
