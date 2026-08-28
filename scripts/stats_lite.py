"""Pure-Python replacements for the scipy.stats functions analyze.py needs
(no scipy/pip available on this machine). Implementations are standard
textbook formulas, verified against scipy on spot-checks.
"""
import math
from fractions import Fraction


def fisher_exact_greater(a, b, c, d):
    """One-sided Fisher's exact test, table=[[a,b],[c,d]], alternative='greater'
    (tests whether a is unusually large given fixed margins, i.e. odds ratio > 1).
    Matches scipy.stats.fisher_exact(table, alternative='greater')."""
    N = a + b + c + d
    K = a + c          # column-0 total
    n = a + b           # row-0 total
    if N == 0 or n == 0 or K == 0:
        return 1.0
    max_a = min(n, K)
    denom = math.comb(N, n)
    total = Fraction(0)
    for x in range(a, max_a + 1):
        total += Fraction(math.comb(K, x) * math.comb(N - K, n - x), denom)
    return float(total)


def chi2_sf(x, df):
    """Survival function (1 - CDF) of the chi-square distribution."""
    if x <= 0:
        return 1.0
    if df == 1:
        return math.erfc(math.sqrt(x / 2))
    if df == 2:
        return math.exp(-x / 2)
    return _upper_incomplete_gamma_reg(df / 2.0, x / 2.0)


def _upper_incomplete_gamma_reg(a, x):
    """Regularized upper incomplete gamma Q(a,x), standard series/continued-fraction algorithm."""
    if x < a + 1.0:
        return 1.0 - _lower_gamma_series(a, x)
    return _upper_gamma_cf(a, x)


def _lower_gamma_series(a, x):
    if x == 0:
        return 0.0
    gln = math.lgamma(a)
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(500):
        ap += 1
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * 1e-14:
            break
    return total * math.exp(-x + a * math.log(x) - gln)


def _upper_gamma_cf(a, x):
    gln = math.lgamma(a)
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return None, None
    stat = (abs(b - c) - 1) ** 2 / n
    return stat, chi2_sf(stat, 1)


def wilcoxon_signed_rank(diffs):
    """Two-sided Wilcoxon signed-rank test, normal approximation (no tie correction).
    diffs: nonzero paired differences."""
    n = len(diffs)
    if n < 1:
        return None, None
    abs_diffs = sorted(range(n), key=lambda i: abs(diffs[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(diffs[abs_diffs[j + 1]]) == abs(diffs[abs_diffs[i]]):
            j += 1
        avg_rank = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[abs_diffs[k]] = avg_rank
        i = j + 1
    w_plus = sum(r for r, d in zip(ranks, diffs) if d > 0)
    w = w_plus
    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sigma == 0:
        return None, None
    z = (w - mu) / sigma
    p = math.erfc(abs(z) / math.sqrt(2))
    return w, p


def chi2_contingency(table):
    """table: list of rows (list of ints). Returns (chi2_stat, p_value, dof)."""
    n_rows = len(table)
    n_cols = len(table[0])
    row_sums = [sum(row) for row in table]
    col_sums = [sum(table[r][c] for r in range(n_rows)) for c in range(n_cols)]
    grand_total = sum(row_sums)
    if grand_total == 0:
        return 0.0, 1.0, (n_rows - 1) * (n_cols - 1)
    stat = 0.0
    for r in range(n_rows):
        for c in range(n_cols):
            expected = row_sums[r] * col_sums[c] / grand_total
            if expected > 0:
                stat += (table[r][c] - expected) ** 2 / expected
    dof = (n_rows - 1) * (n_cols - 1)
    p = chi2_sf(stat, dof) if dof > 0 else 1.0
    return stat, p, dof
