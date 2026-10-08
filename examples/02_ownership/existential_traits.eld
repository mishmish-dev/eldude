module existential_traits;
trait First {fn first(view self)->Int;}
trait Second {fn second(view self)->Int;}
struct A {}
impl First for A {fn first(view self)->Int {20}}
impl Second for A {fn second(view self)->Int {22}}
pub fn main()->Int {
    let both:any First+Second+First+Discard=A{};
    let first=view both.first();
    let second=view both.second();
    let weak:any First+Discard=both;
    let ignored=view weak.first();
    first+second
}
