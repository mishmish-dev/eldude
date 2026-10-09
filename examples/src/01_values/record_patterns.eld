module examples::values::record_patterns;

struct Point {
    x: Int,
    y: Int
}

struct Flagged {
    enabled: Bool,
    point: Point
}

struct Empty {}

fn sum(point: Point) -> Int {
    match point {
        case Point { y, x } => x + y;
    }
}

pub fn main() -> Int {
    let empty = Empty {};
    let zero = match empty {
        case Empty {} => 0;
    };
    let flagged = Flagged { enabled: true, point: Point { x: 19, y: 23 } };
    match flagged {
        case Flagged { point, enabled: false } => zero;
        case Flagged { enabled: true, point } => sum(point);
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
