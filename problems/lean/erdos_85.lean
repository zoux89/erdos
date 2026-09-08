/-
Erdős Problem 85

Let f(n) be the smallest integer for which every graph on n vertices with
minimal degree ≥ f(n) contains a C_4 (4-cycle).

Is it true that, for all large n, f(n + 1) ≥ f(n)?

Reference: https://www.erdosproblems.com/85
-/

import Mathlib

open Classical SimpleGraph Finset Filter

namespace Erdos85

/--
f(n) is the smallest minimum degree k such that every simple graph on n vertices
with minimum degree ≥ k contains a 4-cycle as a subgraph.
-/
noncomputable def f (n : ℕ) : ℕ :=
  sInf {k : ℕ | ∀ (G : SimpleGraph (Fin n)), G.minDegree ≥ k → (cycleGraph 4) ⊑ G}

/--
The conjecture: f is eventually non-decreasing.
For all sufficiently large n, f(n) ≤ f(n + 1).
-/
theorem erdos_85 : ∀ᶠ n in atTop, f n ≤ f (n + 1) := by
  sorry

end Erdos85
