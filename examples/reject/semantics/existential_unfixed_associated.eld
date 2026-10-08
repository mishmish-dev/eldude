module existential_unfixed_associated;
trait Read {type Item;fn read(view self)->Self::Item;}
struct A {} impl Read for A {type Item=Int;fn read(view self)->Int {42}}
pub fn main()->Int {let a:any Read+Discard=A{};view a.read()}
