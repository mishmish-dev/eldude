module examples::reject::multi_operations::call_arity;

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

pub fn main() -> Int {
    handle { /*error*/
        !Multi::read()
    } with handler Multi {
        read(x) => x;
        step() => resume(());
        stop(x) => x;
    }
}
