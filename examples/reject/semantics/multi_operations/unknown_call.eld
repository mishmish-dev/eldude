module examples::reject::multi_operations::unknown_call;
effect Multi {tail read(x:Int)->Int; once step()->Unit; affine stop(x:Int)->Unit;}
pub fn main()->Int {
    !/*error*/Multi::unknown()
}
