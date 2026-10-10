module examples::reject::multi_operations::incomplete;

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

pub fn main() -> Int {
    handle {
        42
    } with handler /*error*/ Multi {
        read(x) => x;
        step() => resume(());
    }
}
