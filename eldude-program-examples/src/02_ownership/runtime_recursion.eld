module examples::ownership::runtime_recursion;

fn count(n: Int) ->{diverge} Int {
    if n == 0 {
        0
    } else {
        count(n - 1) + 1
    }
}

pub fn main() ->{diverge} Int {
    count(2048)
}

pub fn verify() ->{diverge} Int {
    if main() == 2048 {
        0
    } else {
        1
    }
}
