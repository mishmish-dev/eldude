module state::ref;

// Aliasable cells hold only capture-free, discardable payload types.
pub struct Ref<T, @r> where T: CaptureFree + Discard;

impl<T, @r> Ref<T, @r> where T: CaptureFree + Discard {
    pub fn new(value: T) ->{state<@r>} Ref<T, @r>;
    pub fn get(self) ->{state<@r>} T where T: Dup;
    pub fn replace(self, value: T) ->{state<@r>} T;

    pub fn set(self, value: T) ->{state<@r>} Unit {
        self.replace(value);
    }
}
