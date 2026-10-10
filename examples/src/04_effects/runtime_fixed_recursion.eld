module examples::effects::runtime_fixed_recursion;

effect Read {
    tail value() -> Int;
}

fn descend<
    !e,
    ..C
>(n: Int, read: fn() ->{| e} Int captures {..C}) ->{diverge | e} Int where ..C: Dup + Discard {
    handle {
        if n == 0 {
            read()
        } else {
            let current = fn() => !local::value();
            descend(n - 1, current)
        }
    } with local = handler Read {
        value() => n;
    }
}

pub fn main() ->{diverge} Int {
    descend(2048, fn() => 42) + 41
}

pub fn verify() ->{diverge} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
