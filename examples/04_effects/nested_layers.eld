module examples::effects::nested_layers;

effect Read {
    tail value() -> Int;
}

pub fn main() -> Int {
    handle {
        handle {
            !Read::value()
        } with handler Read {
            value() => !outer::value() + 2;
        }
    } with outer = handler Read {
        value() => 40;
    }
}
