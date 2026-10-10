module examples::effects::forwarding;

effect Read {
    tail value() -> Int;
    tail extra() -> Int;
}

pub fn main() -> Int {
    handle {
        handle {
            !Read::value() + !Read::extra()
        } with handler Read {
            extra() => 2;
            forward value;
        }
    } with handler Read {
        value() => 40;
        extra() => 0;
    }
}

pub fn verify() -> Int {
    if main() == 42 {
        0
    } else {
        1
    }
}
