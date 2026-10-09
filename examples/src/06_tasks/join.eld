module examples::tasks::join;

pub fn main() ->{suspend} Int {
    taskgroup {
        let left = spawn 19;
        let right = spawn 23;
        (await left) + (await right)
    }
}

pub fn verify() ->{suspend} Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
