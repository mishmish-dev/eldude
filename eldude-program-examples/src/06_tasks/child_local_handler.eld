module examples::tasks::child_local_handler;

effect Read {
    tail value() -> Int;
}

pub fn main() ->{suspend} Int {
    taskgroup {
        let child = spawn handle {
            !Read::value() == 21
        } with handler Read {
            value() => 21;
            return flag => if flag {
                42
            } else {
                0
            };
        };
        await child
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
