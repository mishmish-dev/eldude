module examples::effects::once_handler;

effect Offset {
    once value() -> Int;
}

pub fn main() -> Int {
    handle {
        !Offset::value() + 1
    } with handler Offset {
        value() => {
            let completed = resume(40);
            completed + 1
        }
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
