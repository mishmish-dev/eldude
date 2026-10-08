module trait_prerequisites;
trait Read {fn read(view self)->Int;}
trait Answer {type Item;fn answer(view self)->Self::Item;}
struct Leaf {}
struct Wrapper<T> {item:T}
impl Read for Leaf {fn read(view self)->Int {42}}
impl<T> Answer for Wrapper<T> where T:Read+Discard {
    type Item=Int;
    fn answer(view self)->Int {42}
}
fn inspect<T>(view item:Wrapper<T>)->Int where T:Read+Discard {view item.answer()}
pub fn main()->Int {let item=Wrapper{item:Leaf{}};inspect(view item)+normalized(view item)-42}
fn normalized<T>(view item:Wrapper<T>)->Wrapper<T>::Item
where Wrapper<T>:Answer, Wrapper<T>::Item=Int {42}
