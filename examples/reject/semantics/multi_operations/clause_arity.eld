module examples::reject::multi_operations::clause_arity;

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

pub fn main() -> Int {
    handle {
        42
    } with handler Multi { /*error*/
        read() => 42;
        step() => resume(());
        stop(x) => x;
    }
}
