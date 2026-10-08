module existential_hidden_prerequisite;
trait Read {fn read(view self)->Int where Self:Dup;}
struct A {} impl Read for A {fn read(view self)->Int {42}}
pub fn main()->Int {let a:any Read+Discard=A{};view a.read()}
