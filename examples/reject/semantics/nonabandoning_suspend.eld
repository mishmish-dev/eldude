module nonabandoning_suspend;
import eldude::fixture::{yield};
fn call<!e>(f:fn()->{|e}Int)->{|e}Int where e:NonAbandoning {f()}
pub fn main()->Int {call(fn(){yield();42})}
