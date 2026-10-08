module projection_prerequisite;
trait Output {type Item;fn read(view self)->Int;}
struct Box<T> {value:T}
impl<T> Output for Box<T> where T::Item:Dup {type Item=Int;fn read(view self)->Int {42}}
pub fn main()->Int {42}
