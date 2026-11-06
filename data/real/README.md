# Real-world samples

These are the ZUGFeRD 2.x example invoices from [ZUGFeRD/corpus](https://github.com/ZUGFeRD/corpus) (folder `ZUGFeRDv2/correct`), licensed under Apache-2.0. `manifest.json` gives each file's source URL.

- `labels/<id>.xml` is the CII XML embedded in the original PDF. It is the ground truth.
- `labels/<id>.json` is that XML in the same label schema as the generated invoices (see `einvoice.labels.cii_to_label`).
- `pdf/` is not committed. Run `uv run einvoice testset real` to download it.

Our own real invoices never go here. If you have any, keep them in `data/private/`, which is gitignored, and report only counts.
