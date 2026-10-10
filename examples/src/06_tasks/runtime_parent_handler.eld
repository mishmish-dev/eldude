module examples::tasks::runtime_parent_handler;

effect Read {
    tail value() -> Int;
}

pub fn main() ->{suspend} Int {
    handle {
        taskgroup {
            let child = spawn 40;
            await child
        }
    } with handler Read {
        value() => 0;
        return result => result + 2;
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
