## Vital Extractor – Monitor OCR Demo

This mini‑project extracts medical vital signs from bedside monitor screenshots
using **PaddleOCR** and **OpenCV**, and returns a structured JSON object.

### Features

- **Preprocessing**: grayscale, contrast enhancement, adaptive thresholding.
- **OCR**: PaddleOCR for robust multi‑style text detection.
- **Keyword‑based mapping**: finds values using nearby labels, not fixed positions.
- **Handles common OCR mistakes** such as `O`→`0` or `B`→`8`.

### Installation

From the project root:

```bash
pip install -r requirements.txt
```

> On some systems PaddleOCR/PaddlePaddle may require additional
> runtime libraries. See the official PaddleOCR installation guide
> if you encounter issues.

### Running the extractor

Basic usage from the command line:

```bash
python -m vital_extractor.main --image path/to/monitor.png --pretty
```

Example JSON output:

  ```json
  {
    "heart_rate": 72,
    "blood_pressure": "127/80",
    "spo2": 97,
    "respiration": 20,
    "temperature": 36.7
  }
```

### Example test helper (Python)

You can also call the extractor directly from Python using the
`example_test` helper:

```python
from vital_extractor.extractor import example_test

example_test("path/to/monitor.png")
```

This will print the extracted vitals and return them as a Python dictionary.

