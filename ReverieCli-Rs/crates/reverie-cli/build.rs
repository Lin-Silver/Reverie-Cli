fn main() {
    #[cfg(windows)]
    {
        let icon = "../../Reverie-Rs.ico";
        if std::path::Path::new(icon).exists() {
            let mut res = winres::WindowsResource::new();
            res.set_icon(icon);
            let _ = res.compile();
        }
    }
}
