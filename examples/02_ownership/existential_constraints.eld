module existential_constraints;
trait Read<T> where T:Dup {fn read(view self,x:T)->Int where Self:Dup;}
struct A {} impl Read<Int> for A where A:Dup {fn read(view self,x:Int)->Int {x}}
pub fn main()->Int {let a:any Read<Int>+Dup+Discard=A{};view a.read(42)}
