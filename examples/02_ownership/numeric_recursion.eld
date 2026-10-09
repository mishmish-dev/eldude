module examples::ownership::numeric_recursion;

// Numeric descent has no structural-subterm proof in the initial core.
fn gcd(a: Nat, b: Nat) ->{diverge} Nat {
    if b == 0nat {
        a
    } else {
        gcd(b, a % b)
    }
}

pub fn main() ->{diverge} Nat {
    gcd(48nat, 18nat)
}
