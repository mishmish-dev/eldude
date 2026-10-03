module examples::values::closures;

pub fn main() -> Int {
    let offset = 2;
    let add = fn(value: Int) => value + offset;
    add(18) + add(20)
}
