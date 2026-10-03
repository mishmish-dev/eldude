module state::ref;

// Aliasable cell; construction/writes enforce the region retention horizon.
pub struct Ref<T, @r> where T: Discard;

impl<T, @r> Ref<T, @r> where T: Discard {
    pub fn new(value: T) ->{state<@r>} Ref<T, @r>;
    pub fn get(self) ->{state<@r>} T where T: Dup;
    pub fn replace(self, value: T) ->{state<@r>} T;

    pub fn set(self, value: T) ->{state<@r>} Unit {
        self.replace(value);
    }
}
