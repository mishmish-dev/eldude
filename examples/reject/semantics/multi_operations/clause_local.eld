module examples::reject::multi_operations::clause_local;
import eldude::fixture::{acquire, close};
effect Multi {tail read(x:Int)->Int; once step()->Unit; affine stop(x:Int)->Unit;}
pub fn main()->Int {
    handle {!Multi::step(); 42} with handler Multi {read(x)=>x; step()=>{/*error*/let local=acquire(); resume(())}; stop(x)=>x;}
}
