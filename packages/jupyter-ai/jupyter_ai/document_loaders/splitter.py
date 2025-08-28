import copy
from typing import Optional

from langchain.schema import Document
from langchain.text_splitter import (
    MarkdownHeaderTextSplitter,
    PythonCodeTextSplitter,
    RecursiveCharacterTextSplitter,
    TextSplitter,
)


class ExtensionSplitter(TextSplitter):
    def __init__(self, splitters, default_splitter=None):
        self.splitters = splitters
        if default_splitter is None:
            self.default_splitter = RecursiveCharacterTextSplitter()
        else:
            self.default_splitter = default_splitter

    def split_text(self, text: str, metadata=None):
        splitter = self.splitters.get(metadata["extension"], self.default_splitter)
        return splitter.split_text(text)

    def create_documents(
        self, texts: list[str], metadatas: Optional[list[dict]] = None
    ) -> list[Document]:
        _metadatas = metadatas or [{}] * len(texts)
        documents = []
        for i, text in enumerate(texts):
            metadata = copy.deepcopy(_metadatas[i])
            for chunk in self.split_text(text, metadata):
                new_doc = Document(page_content=chunk, metadata=metadata)
                documents.append(new_doc)
        return documents


import nbformat


class NotebookSplitter(TextSplitter):
    """
    Stable splitter for .ipynb:
    - Split per cell (cell boundaries are stable).
    - Markdown cells: split by headings (H1/H2/H3), then size-based.
    - Code cells: use Python-aware splitter.
    Returns: list[str] chunks (plain text, no injected markers).
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.md_header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")]
        )
        self.md_text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._chunk_size, chunk_overlap=self._chunk_overlap
        )
        self.code_splitter = PythonCodeTextSplitter(
            chunk_size=self._chunk_size, chunk_overlap=self._chunk_overlap
        )

    def split_text(self, text: str):
        """Split notebook into stable pure text chunks per cell"""
        nb = nbformat.reads(text, as_version=4)
        chunks = []
        
        for cell in nb.cells:
            src = (cell.get("source") or "").strip()
            if not src:
                # Skip empty cells
                continue
                
            if cell.cell_type == "markdown":
                # Split markdown cells by headings first, then by size
                # 1) keep sections stable by headings
                sections = self.md_header_splitter.split_text(src)
                # 2) size-based within each section
                for sec in sections:
                    for c in self.md_text_splitter.split_text(sec.page_content):
                        if c.strip():
                            chunks.append(c)
                    
            elif cell.cell_type == "code":
                # Code (python or otherwise) – function/class boundaries are respected better
                for c in self.code_splitter.split_text(src):
                    if c.strip():
                        chunks.append(c)
        
        return chunks
