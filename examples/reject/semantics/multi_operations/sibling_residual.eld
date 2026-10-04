module examples::reject::multi_operations::sibling_residual;
import eldude::fixture::{acquire, close};
effect Multi {tail read(x:Int)->Int; once first()->Unit; once second()->Unit; affine stop(x:Int)->Unit;}
effect Escape {affine leave()->Unit;}
pub fn main()->Int {
    handle {handle {!Multi::first(); !Multi::second(); !Multi::read(42)} with handler Multi {read(x)=>x; first()=>{let local=acquire(); let answer=/*error*/resume(()); close(local); answer}; second()=>{let answer=resume(()); !Escape::leave(); answer}; stop(x)=>x;}} with handler Escape {leave()=>7;}
}
