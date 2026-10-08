module generic_alias;
trait Read {fn read(view self)->Int;}
struct Box<T> {value:T}
type Alias<T> = Box<T>;
impl Read for Alias<Int> {fn read(view self)->Int {self.value}}
pub fn main()->Int {let item:any Read+Discard=Box{value:42};view item.read()}
