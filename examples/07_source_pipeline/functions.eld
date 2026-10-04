module examples::source_pipeline::functions;

pub fn main() -> Int {
    let answer = 42;
    let callback = fn(value: Int) => answer;
    apply(callback, 0)
}

fn apply(callback: fn(Int) -> Int, value: Int) -> Int {
    callback(value)
}
