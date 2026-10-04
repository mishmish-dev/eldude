module examples::reject::multi_operations::frame_transfer;
import eldude::fixture::{acquire, close};
effect Multi {tail read(x:Int)->Int; once step()->Unit; affine stop(x:Int)->Unit;}
pub fn main()->Int {
    let frame=acquire(); handle {!Multi::step(); !Multi::read(42)} with handler Multi {read(x)=>x; step()=>{resume(()); close(/*error*/frame); 42}; stop(x)=>{close(frame); x};return x=>{close(frame); x};}
}
