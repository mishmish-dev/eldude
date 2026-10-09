module examples::reject::multi_operations::unknown_forward;

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

pub fn main() -> Int {
    handle {
        42
    } with handler Multi {
        forward /*error*/ unknown;
        forward ..;
    }
}
