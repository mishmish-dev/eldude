module reject::source_pipeline::wrong_operation_result;

effect Read {
    tail value() -> Int;
}

pub fn main() -> Int {
    handle {
        !Read::value()
    } with handler Read {
        value() => ();
    }
}
