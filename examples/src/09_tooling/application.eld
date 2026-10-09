module tooling_application;

pub fn start() -> Int {
    7
}

pub fn main() -> Int {
    start()
}

pub fn verify() -> Int {
    if main() == 7 {
        0
    } else {
        1
    }
}
