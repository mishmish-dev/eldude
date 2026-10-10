module examples::tasks::runtime_nested_groups;

fn descend(n: Int) ->{suspend, diverge} Int {
    taskgroup {
        if n == 0 {
            42
        } else {
            let child = spawn descend(n - 1);
            await child
        }
    }
}

pub fn main() ->{suspend, diverge} Int {
    descend(2048)
}

pub fn verify() ->{suspend, diverge} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
