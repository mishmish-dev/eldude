module collections::dyn_array;

import collections::list::{List};
import core::option::{Option};

// Root mutable owner in @r; Discard exactly when its elements are Discard.
pub affine struct DynArray<T, @r>;

impl<T, @r> DynArray<T, @r> {
    pub fn new() ->{state<@r>} DynArray<T, @r>;
    pub fn length(view self) ->{state<@r>} Nat;
    pub fn push(mut self, value: T) ->{state<@r>} Unit;
    pub fn pop(mut self) ->{state<@r>} Option<T>;
    // Result retains the whole owner summary unless T is provably capture-free.
    pub fn freeze(self) ->{state<@r>} List<T>;
}
