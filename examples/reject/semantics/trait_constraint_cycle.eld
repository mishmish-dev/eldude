module trait_constraint_cycle;
trait Read {fn read(view self)->Int;}
struct Box<T> {item:T}
impl<T> Read for Box<T> where Box<T>:Read {fn read(view self)->Int {42}}
pub fn main()->Int {42}
