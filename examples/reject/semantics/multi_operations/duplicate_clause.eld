module examples::reject::multi_operations::duplicate_clause;

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

pub fn main() -> Int {
    handle {
        42
    } with handler Multi {
        read(x) => x;
        step() => resume(());
        stop(x) => x; /*error*/
        read(x) => x;
    }
}
