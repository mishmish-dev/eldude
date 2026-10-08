module mut_wrong_authority;
import collections::dyn_array::{DynArray};
fn update<@inner>(mut values:DynArray<Int,@inner>)->Unit {mut values.push(42);}
pub fn main()->Int {42}
