use anyhow::Result;
use base64::{engine::general_purpose::STANDARD, Engine};
use qrcode::QrCode;
use image::{DynamicImage, ImageBuffer, Luma};
use std::io::Cursor;

/// Encode a URL into a QR code and return it as a base64-encoded PNG.
pub fn generate_qr_base64(url: &str) -> Result<String> {
    let code = QrCode::new(url.as_bytes())?;
    let image: ImageBuffer<Luma<u8>, Vec<u8>> = code.render::<Luma<u8>>().build();
    let dynamic = DynamicImage::ImageLuma8(image);

    let mut buf = Cursor::new(Vec::new());
    dynamic.write_to(&mut buf, image::ImageFormat::Png)?;
    Ok(STANDARD.encode(buf.into_inner()))
}
