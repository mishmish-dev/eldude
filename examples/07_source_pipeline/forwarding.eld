module examples::source_pipeline::forwarding;
effect Read { tail value() -> Int; }

pub fn main() -> Int {
    handle {
        handle { !Read::value() } with inner = handler Read {
            forward value;
        }
    } with outer = handler Read {
        value() => 42;
    }
}
