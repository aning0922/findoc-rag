# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportOptionalMemberAccess=false
import pdfplumber
import pymupdf

path, pno = "data/京东方A 2025年报.pdf", 29
with pdfplumber.open(path) as pdf:
    print("pdfplumber: ", pdf.pages[pno].extract_tables())
with pymupdf.open(path) as doc:
    for t in doc[pno].find_tables().tables:
        print("pymupdf: ", t.extract())
