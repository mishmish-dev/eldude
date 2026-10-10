module examples::tasks::runtime_yields;

import task::{yield};
import state::ref::{Ref};

fn work<@r>(count: Ref<Int, @r>, n: Int) ->{state<@r>, suspend, diverge} Unit {
    if n != 0 {
        yield();
        count.replace(count.get() + 1);
        work(count, n - 1);
    }
}

pub fn main() ->{suspend, diverge} Int {
    region r {
        let count: Ref<Int, @r> = Ref::new(0);
        taskgroup {
            spawn work(count, 2048);
            spawn work(count, 2048);
        };
        count.get()
    }
}

pub fn verify() ->{suspend, diverge} Int {
    if main() == 4096 {
        0
    } else {
        1
    }
}
