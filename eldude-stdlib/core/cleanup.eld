module core::cleanup;

pub intrinsic trait Cleanup<!e> {
    fn cleanup(self) ->{| e} Unit;
}
