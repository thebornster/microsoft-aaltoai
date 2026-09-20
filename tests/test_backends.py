import pathlib

import pytest

from gateway import backends


def test_search_supplier_docs_reads_the_pdf_not_the_txt(tmp_path, monkeypatch):
    txt_path = backends.DEMO_DIR / "bulletin_A19.txt"
    moved = tmp_path / "bulletin_A19.txt.moved"
    txt_path.rename(moved)
    try:
        result = backends.search_supplier_docs({})
    finally:
        moved.rename(txt_path)

    assert result["document_id"] == "bulletin_A19.pdf"
    assert "SERVICE NOTE" in result["text"]
    assert "operator IDs" in result["text"]


def test_search_supplier_docs_text_matches_pdf_extraction():
    result = backends.search_supplier_docs({})
    import pypdf

    reader = pypdf.PdfReader(backends.DEMO_DIR / "bulletin_A19.pdf")
    expected = "\n".join(page.extract_text() for page in reader.pages)
    assert result["text"] == expected
