module examples::values::variant_field_order;

effect Echo {
    tail get(value: Int) -> Int;
}

enum Pair {
    P {
        x: Int,
        y: Int
    }
}

pub fn main() -> Int {
    handle {
        let pair = Pair::P { y: !Echo::get(2), x: !Echo::get(1) };
        match pair {
            case Pair::P { x, y } => x * 10 + y;
        }
    } with handler Echo {
        get(value) => value;
    }
}

pub fn verify() -> Int {
    if main() == 12 {
        0
    } else {
        1
    }
}
