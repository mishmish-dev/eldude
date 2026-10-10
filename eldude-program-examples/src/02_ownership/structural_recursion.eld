module examples::ownership::structural_recursion;

enum Chain {
    End,
    Link(Int, Chain)
}

fn sum(chain: Chain) -> Int {
    match chain {
        case Chain::End => 0;
        case Chain::Link(head, tail) => head + sum(tail);
    }
}

pub fn main() -> Int {
    sum(Chain::Link(10, Chain::Link(32, Chain::End)))
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
