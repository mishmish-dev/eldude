module examples::reject::multi_operations::opaque_affine_family;
import eldude::fixture::{acquire, close};
effect Multi {tail read(x:Int)->Int; once step()->Unit; affine stop(x:Int)->Unit;}
fn opaque()->{Multi}Int {!Multi::read(42)}
pub fn main()->Int {
    handle {let file=acquire(); let answer=/*error*/opaque(); close(file); answer} with handler Multi {read(x)=>x; step()=>resume(()); stop(x)=>x;}
}
