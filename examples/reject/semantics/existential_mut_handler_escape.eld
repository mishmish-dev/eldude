module existential_mut_handler_escape;
import collections::dyn_array::{DynArray};
import state::ref::{Ref};
effect Stop {affine stop()->Unit;}
trait Read {fn read(view self)->Int;}
struct Holder<@r> {cell:Ref<Int,@r>}
impl<@r> Read for Holder<@r> {fn read(view self)->Int {42}}
trait Store<@r> {fn store(mut self,value:any Read+Discard)->{state<@r>,Stop}Unit;fn len(view self)->{state<@r>}Nat;}
impl<@r> Store<@r> for DynArray<any Read+Discard,@r> {
    fn store(mut self,value:any Read+Discard)->{state<@r>,Stop}Unit {mut self.push(value);!Stop::stop();}
    fn len(view self)->{state<@r>}Nat {view self.length()}
}
pub fn main()->Nat {region outer {
    let values:DynArray<any Read+Discard,@outer> = DynArray::new();
    let owner:any Store<@outer>+Discard=values;
    region inner {
        let cell:Ref<Int,@inner> = Ref::new(0);
        let item:any Read+Discard=Holder{cell:cell};
        handle {mut owner.store(item)} with handler Stop {stop()=>();return x=>x;};
    };
    view owner.len()
}}
