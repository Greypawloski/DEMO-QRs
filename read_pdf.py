"""Run this on PythonAnywhere to show the raw PDF text so we can build the right parser.
   cd ~/DEMO-QRs && python read_pdf.py
"""
import sys

PDF = "tennis_strings_chart.pdf"

# Try pdfplumber first (best for tables), fall back to PyPDF2
try:
    import pdfplumber
    with pdfplumber.open(PDF) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"\n{'='*60}\nPAGE {i+1}\n{'='*60}")
            # Try extracting as a table first
            tables = page.extract_tables()
            if tables:
                for t, table in enumerate(tables):
                    print(f"\n--- Table {t+1} ---")
                    for row in table:
                        print(row)
            else:
                print(page.extract_text())
except ImportError:
    try:
        import PyPDF2
        with open(PDF, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for i, page in enumerate(reader.pages):
                print(f"\n{'='*60}\nPAGE {i+1}\n{'='*60}")
                print(page.extract_text())
    except ImportError:
        print("Neither pdfplumber nor PyPDF2 is installed.")
        print("Run:  pip install pdfplumber")
        sys.exit(1)
