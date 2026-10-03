module examples::values::branches;

fn absolute(value: Int) -> Int {
    if value < 0 { -value } else { value }
}

pub fn main() -> Int {
    absolute(-7)
}
