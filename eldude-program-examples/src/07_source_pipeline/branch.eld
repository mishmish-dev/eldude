module examples::source_pipeline::branch;

pub fn main() -> Int {
    if true {
        42
    } else {
        0
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
