module reject::source_pipeline::tail_resume;

effect Read {
    tail value() -> Int;
}

pub fn main() -> Int {
    handle {
        !Read::value()
    } with handler Read {
        value() => resume(40);
    }
}
