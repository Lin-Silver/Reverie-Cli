pub const VERSION: &str = env!("CARGO_PKG_VERSION");
pub const PRODUCT_NAME: &str = "Reverie Cli";

pub fn version_line() -> String {
    format!("{PRODUCT_NAME} v{VERSION}")
}
