module examples::effects::generic_instances;

effect Read<T> { tail value() -> T; }

pub fn main() -> Int {
    handle {
        handle {
            if !Read::<Bool>::value() { !Read::<Int>::value() } else { 0 }
        } with handler Read<Bool> {
            value() => true;
        }
    } with handler Read<Int> {
        value() => 42;
    }
}
