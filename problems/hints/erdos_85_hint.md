# C4-Minimum-Degree: Bounded-Drop Notes

This note summarizes a clean, self-contained argument for a bounded-drop
statement for the function `f(n)` defined as:

> `f(n)` is the smallest integer such that every graph on `n` vertices with
> minimum degree at least `f(n)` contains a 4-cycle (`C4`).

Define

```
g(n) = max { delta(G) : |V(G)| = n and G is C4-free }.
```

Then `f(n) = g(n) + 1`.

We prove that for all `m > n >= 5`,

```
f(m) >= f(n) - 3,
```

and we explain why the same method cannot give a global constant `2`.

---

## 1) Universal upper bound

In any `C4`-free graph on `n` vertices, each ordered pair of distinct vertices
is the endpoint of at most one length-2 path. Therefore:

```
sum_v d(v)(d(v) - 1) <= n(n - 1).
```

If the minimum degree is `d`, then:

```
d(d - 1) <= n - 1.
```

Define

```
U(n) = floor( (1 + sqrt(4n - 3)) / 2 ).
```

Then

```
g(n) <= U(n), and f(n) <= U(n) + 1.
```

---

## 2) A large C4-free construction

Let `PG(2, q)` be the projective plane over `F_q` with

```
n_q = q^2 + q + 1
```

points. The orthogonal polarity graph `G_q` has:

- vertices = points of `PG(2, q)`;
- two distinct points adjacent iff one lies on the polar line of the other.

Any two vertices have at most one common neighbor, so `G_q` is `C4`-free, and
each vertex has degree `q` or `q + 1`. Hence

```
delta(G_q) = q, so g(n_q) >= q.
```

---

## 3) Two disjoint conics for all `q >= 3`

We build a large deletion set `S` whose intersection with any line is small.

### Lemma (two disjoint conics)

For every prime power `q >= 3`, there exist two disjoint nondegenerate conics
in `PG(2, q)`. Consequently, there exists a set `S` with

```
|S| = 2(q + 1)
```

and every line meets `S` in at most 4 points.

### Proof sketch

Pick an anisotropic quadratic form `B(x, y)`:

- If `q` is odd, choose a nonsquare `d` and let `B(x, y) = x^2 - d y^2`.
- If `q` is even, choose `a` with `Tr(a) = 1` and let
  `B(x, y) = x^2 + x y + a y^2`.

In both cases `B(x, y) = 0` implies `x = y = 0`.

For any nonzero `k`, define the conic

```
C_k: B(x, y) = k z^2.
```

Each `C_k` is nondegenerate (so any line meets it in at most 2 points), and
if `k != k'` then `C_k` and `C_k'` are disjoint. Thus

```
S = C_k union C_k'
```

has size `2(q + 1)` and intersects any line in at most 4 points.

---

## 4) Deleting S drops degree by at most 4

In the polarity graph, the neighbors of a vertex are exactly the points on its
polar line. If a set `S` meets every line in at most 4 points, deleting any
subset of `S` removes at most 4 neighbors from every vertex.

Therefore, for each

```
n in [ n_q - 2(q + 1), n_q ],
```

there exists a `C4`-free graph with

```
delta >= q - 4,
so g(n) >= q - 4.
```

---

## 5) Upgrade to a uniform bound (c = 3)

For any `n >= 5`, choose `q` with

```
n in [ n_q - 2(q + 1), n_q ].
```

Then

```
n >= q^2 - q - 1,
so U(n) >= q - 1.
```

Combined with the construction, this yields

```
g(n) >= q - 4 >= U(n) - 3,
so f(n) = g(n) + 1 >= U(n) - 2.
```

Since `U` is nondecreasing,

```
f(m) >= U(m) - 2 >= U(n) - 2 >= f(n) - 3
```

for all `m > n >= 5`.

---

## 6) Why c = 2 fails for this method

To improve to `c = 2` using the same strategy, one would need a set

```
|S| = 2(q + 1)
```

that meets every line in at most **2** points. Such a set is a `2`-arc.

But for odd `q`, the largest `2`-arc in `PG(2, q)` has size `q + 1` (a conic).
So a size `2(q + 1)` set with at most 2 points per line does not exist.

Therefore this polarity-graph deletion method cannot yield a global constant
`c = 2`. New constructions would be required.

---

## 7) Even-q note

For even `q`, there exist `2`-arcs of size `2(q + 1)` (Denniston arcs), which
do give a local `c = 2` bound on intervals

```
[ n_q - 2(q + 1), n_q ].
```

These intervals do not cover all `n`, so this does not give a global `c = 2`.

---

## Summary

- The construction via polarity graphs and two disjoint conics gives a **global**
  bounded-drop statement with constant **3**:

```
f(m) >= f(n) - 3 for all m > n >= 5.
```

- The same method cannot give `c = 2` for all `n` because large `2`-arcs do not
  exist in `PG(2, q)` when `q` is odd.
