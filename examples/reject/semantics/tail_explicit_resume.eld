module examples::reject::tail_explicit_resume;

effect Read { tail value() -> Int; }

pub fn main() -> Int {
    handle { !Read::value() } with handler Read {
        // Tail clauses return the operation result; explicit resume is forbidden.
        value() => resume(42);
    }
}
