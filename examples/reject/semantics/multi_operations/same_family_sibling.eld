module examples::reject::multi_operations::same_family_sibling;

effect Multi {
    tail read(x: Int) -> Int;
    once step() -> Unit;
    affine stop(x: Int) -> Unit;
}

pub fn main() -> Int {
    handle {
        42
    } with handler Multi {
        read(x) => { /*error*/
            !Multi::step();
            x
        };
        step() => resume(());
        stop(x) => x;
    }
}
