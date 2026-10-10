module collections::list;

import core::option::{Option};
import core::result::{Result};
import core::iter::{Iterator, Next};

// Opaque representation and bodyless methods are implementation contracts.
pub struct List<T>;

pub struct BoundsError { pub index: Int, pub length: Nat }

impl<T> List<T> {
    pub fn new() -> List<T>;
    pub fn length(view self) -> Nat;
    pub fn push(self, value: T) -> List<T>;

    pub fn get(view self, index: Int) -> Option<T>
    where T: Dup;

    pub fn remove(self, index: Int)
        -> Result<(T, List<T>), (BoundsError, List<T>)>;

    pub fn replace(self, index: Int, value: T)
        -> Result<(T, List<T>), (BoundsError, List<T>, T)>;

    pub fn with<R, !e, ..C>(
        view self,
        index: Int,
        inspect: fn(view T) ->{| e} R captures {..C},
    ) ->{| e} Option<R>
    where ..C: Discard;

    pub fn filter<..C>(
        self,
        predicate: fn(view T) -> Bool captures {..C},
    ) -> List<T>
    where T: Discard, ..C: Dup + Discard;

    pub fn partition<..C>(
        self,
        predicate: fn(view T) -> Bool captures {..C},
    ) -> (List<T>, List<T>)
    where ..C: Dup + Discard;
}

impl<T> Iterator for List<T> {
    type Item = T;
    fn next(self) -> Next<List<T>, T>;
}
