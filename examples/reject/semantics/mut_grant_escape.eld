module mut_grant_escape;
import collections::dyn_array::{DynArray};
fn escape<@r>(mut values:DynArray<Int,@r>)->fn()->{state<@r>}Unit captures {@r} {fn(){mut values.push(42);}}
pub fn main()->Int {42}
