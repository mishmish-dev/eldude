module capture_row_duplicate;
import eldude::fixture::{File,acquire,close};
fn repeat<..C>(f:fn()->Unit captures {..C})->Unit where ..C:Dup {f();f();}
pub fn main()->Int {let file=acquire();repeat(fn(){close(file);});42}
