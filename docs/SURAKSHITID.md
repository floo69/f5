# SurakshitID extension

SurakshitID is an additional frontend mode alongside ThumbShield. It keeps the existing visual system and offers a local image workflow: camera/file input, ID-type selection, local OCR/detector suggestions blurred before review, manual masking, a tiled recipient/date/token watermark, flattened PNG export, a blur quality gate, and an export hash with an in-session comparison inspector.

## Safety boundary in this prototype

- Image bytes are sent only to the local API at the same machine for OCR and detector suggestions; the scan endpoint does not write them to disk. Camera captures and exported PNGs are canvas-generated, without original EXIF metadata or selectable PDF text layers.
- The local scanner uses Verhoeff-validated Aadhaar/VID detection, OCR pattern matches for PAN/passport/voter/driving-licence IDs, OpenCV QR detection, and the existing classical fingerprint detector. Results are suggestions, not certified detections; OCR pattern matching may miss or misread fields.
- Detected regions are pixel-blurred before review. Users can add regions and select pixel blur or solid black. Solid black is safer for high-risk numbers; blur can be reconstructed in some cases. Black-mask pixels are verified as zero before export.
- The tiled watermark measures text width to prevent collisions and repeats recipient/date/token text at alternating rows. A watermark can still be removed or altered with sufficiently capable editing. The inspector compares a suspected copy with the original retained in the active browser session and reports changed pixel bounds; this is not a portable signature and is lost when the session ends.
- The quality metric and OCR threshold reject some unreadable images, but do not establish that the document is safe or that every sensitive field was found. Users must inspect the whole document and mark missed regions.
- PDF selection is refused with a fail-closed message because this purpose-bound flow still lacks a verified local PDF raster path.
- Validity is printed as context; a downloaded PNG cannot enforce expiry or prevent copying.
