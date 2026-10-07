module generic_argument_kind;
fn call<@r>(f:fn()->Int captures {@r})->Int {f()}
pub fn main()->Int {call::<Int>(fn(){42})}
