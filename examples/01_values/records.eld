module examples::values::records;

struct Point {
    x: Int,
    y: Int
}

pub fn main() -> Int {
    let point = Point { x: 4, y: 5 };
    point.x + point.y
}
