module forwarded_mut;
import collections::dyn_array::{DynArray};
fn append<@r>(mut values:DynArray<Int,@r>)->{state<@r>}Unit {mut values.push(42);}
fn forwarded<@r>(mut values:DynArray<Int,@r>)->{state<@r>}Unit {append(mut values);}
pub fn main()->Nat {region local {let values:DynArray<Int,@local> = DynArray::new();forwarded(mut values);view values.length()}}
