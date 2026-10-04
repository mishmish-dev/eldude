module examples::reject::multi_operations::post_resume_outward;
import eldude::fixture::{acquire, close};
effect Multi {tail read(x:Int)->Int; once step()->Unit; affine stop(x:Int)->Unit;}
effect Escape {affine leave()->Unit;}
pub fn main()->Int {
    handle {let outside=acquire(); let answer=handle {!Multi::step(); 42} with handler Multi {read(x)=>x; step()=>{let answer=resume(()); /*error*/!Escape::leave(); answer}; stop(x)=>x;}; close(outside); answer} with handler Escape {leave()=>7;}
}
