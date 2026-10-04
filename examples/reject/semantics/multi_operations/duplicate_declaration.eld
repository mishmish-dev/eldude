module examples::reject::multi_operations::duplicate_declaration;
effect Multi {tail read(x:Int)->Int; once /*error*/read()->Unit;}
pub fn main()->Int {
    42
}
