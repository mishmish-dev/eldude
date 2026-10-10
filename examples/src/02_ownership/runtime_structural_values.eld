module examples::ownership::runtime_structural_values;

enum Chain {
    End,
    Link(Int, Chain)
}

fn build(n: Int) ->{diverge} Chain {
    if n == 0 {
        Chain::End
    } else {
        Chain::Link(1, build(n - 1))
    }
}

fn sum(chain: Chain) -> Int {
    match chain {
        case Chain::End => 0;
        case Chain::Link(head, tail) => head + sum(tail);
    }
}

pub fn main() ->{diverge} Int {
    sum(build(2048))
}

pub fn verify() ->{diverge} Int {
    if main() == 2048 {
        0
    } else {
        1
    }
}
