module examples::source_pipeline::tail_output;

effect Read {
    tail value() -> Int;
}

pub fn main() -> Unit {
    handle {
        !Read::value();
    } with read = handler Read {
        value() => 40;
    }
}
