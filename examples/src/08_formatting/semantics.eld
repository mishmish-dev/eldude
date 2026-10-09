// Field evaluation follows source order, even when field names are out of order.
module examples::formatting::semantics;

effect Echo {
    tail echo(value: Int) -> Int;
}

struct Pair {
    first: Int,
    second: Int
}

pub fn main() -> Int {
    handle {
        handle {
            let pair = Pair { second: !Echo::echo(1), first: !Echo::echo(2) };
            // Parentheses and comparison brackets have different roles from type arguments.
            if pair.first > pair.second {
                (pair.first * 10 + pair.second) * 2
            } else {
                0
            }
        } with handler Echo {
            forward echo;
        }
    } with handler Echo {
        echo(value) => value;
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
