module nonabandoning_affine;

effect Stop {
    affine stop() -> Int;
}

fn call<!e>(f: fn() ->{| e} Int) ->{| e} Int where e: NonAbandoning {
    f()
}

pub fn main() -> Int {
    handle {
        call(fn() {
            !Stop::stop()
        })
    } with handler Stop {
        stop() => 42;
        return x => x;
    }
}
