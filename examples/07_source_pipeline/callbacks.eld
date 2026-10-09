module examples::source_pipeline::callbacks;

effect Read {
    tail value() -> Int;
}

fn read() ->{Read} Int {
    !Read::value()
}

pub fn main() -> Int {
    handle {
        let fixed = fn() => !outer::value();
        let ambient = fn() => read();
        handle {
            fixed();
            ambient()
        } with inner = handler Read {
            value() => 20;
        }
    } with outer = handler Read {
        value() => 10;
    }
}
