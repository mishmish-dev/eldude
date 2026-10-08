module mut_root_effect;
import collections::dyn_array::{DynArray};
fn noop<@r>(mut values:DynArray<Int,@r>)->Unit {}
fn caller<@r>(values:DynArray<Int,@r>)->Unit {noop(mut values);}
pub fn main()->Int {42}
