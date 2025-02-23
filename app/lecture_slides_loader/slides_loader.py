import os
import re
from typing import (
    Callable,
    List,
)

from docling.datamodel.base_models import (
    InputFormat
)
from docling.document_converter import (
    DocumentConverter,
    PowerpointFormatOption
)
from docling.pipeline.simple_pipeline import SimplePipeline
from langchain_core.documents import Document

from .utils import (
    split_markdown_by_section,
    create_chunks,
)

class LectureSlidesLoader:
    def __init__(self):
        self.doc_converter = DocumentConverter(
            allowed_formats=[
                InputFormat.PPTX,
            ],
            format_options={
                InputFormat.PPTX: PowerpointFormatOption(
                    pipeline_cls=SimplePipeline
                ),
            }
        )


    def load_and_split_ppt(
        self,
        file_path: str,
        max_tokens: int,
        max_depth: int = 3,
        model_name: str="text-embedding-3-small",
        split_large_section_mode: Callable[[str], List[str]] = lambda text: text.split("\n\n"),
    )->List[Document]:
        """
        Split a markdown into sub-docs based on sections.
        """
        # I am assuming the format of file name
        filename = os.path.splitext(os.path.basename(file_path))[0]
        match = re.match(r"(\d+)\s*-\s*(.+)", filename)
        lecture_number = match.group(1)
        lecture_title = match.group(2)

        conversion_res = self.doc_converter.convert(file_path)
        md_text = conversion_res.document.export_to_markdown(
            image_placeholder="",
        )
        md_sections = split_markdown_by_section(
            markdown_text=md_text,
            max_depth=max_depth,
            include_title=True,
        )
        chunks = create_chunks(
            markdown_sections=md_sections,
            max_tokens=max_tokens,
            model_name=model_name,
            split_large_section_mode=split_large_section_mode,
        )
        for i in range(len(chunks)):
            chunks[i].metadata['chunk_idx'] = i
            chunks[i].metadata["filepath"] = file_path
            chunks[i].metadata["lecture_number"] = lecture_number
            chunks[i].metadata["lecture_title"] = lecture_title
        return chunks
