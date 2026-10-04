module examples::reject::multi_operations::argument_abandonment;
import eldude::fixture::{acquire, close};
effect Multi {tail read(x:Int)->Int; once step()->Unit; affine stop(x:Int)->Unit;}
import eldude::fixture::{yield};
pub fn main()->Int {
    handle {let file=acquire(); !Multi::read({/*error*/yield(); 42}); close(file); 42} with handler Multi {read(x)=>x; step()=>resume(()); stop(x)=>x;}
}
