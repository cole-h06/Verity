import pdfplumber
import re

# find first numeric occurrence in a string
NUM_RE = re.compile(r"([-+]?\d+(\.\d+)?)")

def parse_pdf_specs(pdf_path: str):
    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for raw_line in text.split("\n"):
                line = raw_line.strip()

                # Skip empty or obvious headers
                if not line:
                    continue
                if line.isupper() and len(line) < 40:
                    continue
                if len(line) < 6:
                    continue

                # Look for first numeric value in the line
                match = NUM_RE.search(line)
                if not match:
                    continue

                idx = match.start()

                attribute = line[:idx].strip()
                value = line[idx:].strip()

                # Filter junk lines
                if not attribute:
                    continue
                if len(attribute) > 100:
                    continue

                rows.append({
                    "attribute_raw": attribute,
                    "value_raw": value
                })

    return rows