# V1 evaluation protocol

The V1 protocol evaluates synthetic PDFs at finding, page, and document units. Ground truth is generated independently by `synth.deed_gen`; predictions come from the scan pipeline. A box is a true positive only when category matches and IoU meets the configured threshold. Missing OCR or model dependencies produce `N/A`, never substitute values.
