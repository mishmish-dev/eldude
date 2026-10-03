module examples::reject::decreases_annotation;

// Symbolic termination measures are deferred; this is not current syntax.
fn countdown(n: Nat) -> Nat
decreases n {
    if n == 0nat { 0nat } else { countdown(n - 1nat) }
}
