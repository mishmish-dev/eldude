module reject::source_pipeline::same_family;

effect Read {
    tail value() -> Int;
}

pub fn main() -> Int {
    handle {
        !Read::value()
    } with handler Read {
        value() => !Read::value();
    }
}
