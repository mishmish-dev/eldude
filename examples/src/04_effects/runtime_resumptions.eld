module examples::effects::runtime_resumptions;

effect Step {
    tail pulse() -> Unit;
    once tick() -> Unit;
}

fn count(n: Int) ->{Step, diverge} Int {
    if n == 0 {
        0
    } else {
        !Step::pulse();
        !Step::tick();
        count(n - 1)
    }
}

pub fn main() ->{diverge} Int {
    handle {
        count(2048)
    } with handler Step {
        pulse() => ();
        tick() => resume(()) + 1;
    }
}

pub fn verify() ->{diverge} Int {
    if main() == 2048 {
        0
    } else {
        1
    }
}
