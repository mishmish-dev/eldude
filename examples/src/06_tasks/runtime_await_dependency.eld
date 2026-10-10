module examples::tasks::runtime_await_dependency;

import task::{yield};

pub fn main() ->{suspend} Int {
    taskgroup {
        let first = spawn {
            yield();
            40
        };
        let second = spawn {
            (await first) + 2
        };
        await second
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
