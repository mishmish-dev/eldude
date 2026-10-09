module examples::reject::numeric_recursion_without_diverge;

// This terminates mathematically, but arithmetic results are not stored subterms.
// Its contract must admit diverge under the initial conservative rules.
fn gcd(a: Nat, b: Nat) -> Nat {
    if b == 0nat {
        a
    } else {
        gcd(b, a % b)
    }
}
