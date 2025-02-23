import re
from typing import (
    Callable,
    Dict,
    List,
    Tuple,
)

from langchain_core.documents import Document
import tiktoken

def count_num_tokens(
    text: str,
    model_name: str = "text-embedding-3-small",
) -> int:
    """
    Count number of token in a given text.
    """
    encoder = tiktoken.encoding_for_model(model_name)
    encodings = encoder.encode(text)
    return len(encodings)

def split_markdown_by_section(
    markdown_text: str,
    max_depth: int,
    include_title: bool = True,
) -> List[Document]:
    """
    Splits a Markdown document into sections represented as Document objects.
    If no headings are found, treats the entire text as one section.
    """
    heading_pattern = re.compile(r"^(#+)\s+.*", flags=re.MULTILINE)
    documents = []
    stack = []

    matches = list(heading_pattern.finditer(markdown_text))

    # If no headings are found, treat the whole markdown as a single section
    if not matches:
        return [
            Document(
                page_content=markdown_text.strip(),
                metadata={
                    "level": 0,
                    "section": "Whole Document",
                },
            )
        ]

    for match in matches:
        level = len(match.group(1))
        title_start = match.start()
        title_end = match.end()

        if level > max_depth:
            continue

        section_title = markdown_text[title_start:title_end].strip()

        metadata = {
            "level": level, "section": section_title}

        if stack:
            prev_section = stack[-1]
            prev_section_content = markdown_text[prev_section["start"]:title_start].rstrip()
            documents.append(
                Document(
                    page_content=prev_section_content,
                    metadata=prev_section["metadata"]
                )
            )

        while stack and stack[-1]["metadata"]["level"] >= level:
            stack.pop()

        stack.append({"metadata": metadata, "start": title_start if include_title else title_end})

    if stack:
        last_section = stack[-1]
        last_section_content = markdown_text[last_section["start"]:].rstrip()
        documents.append(
            Document(
                page_content=last_section_content,
                metadata=last_section["metadata"]
            )
        )
    return documents


def handle_large_section(
    section: Document,
    max_tokens: int,
    model_name: str,
    split_mode: Callable[[str], List[str]] = lambda text: text.split("\n\n")
) -> List[Tuple[Document, int]]:
    """
    Handle a single section that is larger than token threshold.

    Args:
        section (Document): The section to be split.
        max_tokens (int): Max token threshold.
        model_name (str): The model name used for token counting.
        split_mode (Callable[[str], List[str]]): A function used to split the section

    Returns:
        List[Tuple[Document, int]]: List[[Smaller Doc, num tokens]]
    """
    sub_sections = []
    units = split_mode(section.page_content)
    current_unit_group = []
    current_token_count = 0

    def create_sub_section():
        """Helper to create and append a sub-section."""
        sub_section_content = "\n\n".join(current_unit_group)
        sub_sections.append(
            (
                Document(
                    page_content=sub_section_content,
                    metadata={
                        "sections": [f"{section.metadata['section']} - Part {len(sub_sections) + 1}"]
                    },
                ),
                current_token_count,
            )
        )

    for unit in units:
        unit_tokens = count_num_tokens(unit, model_name=model_name)
        if current_token_count + unit_tokens > max_tokens:
            create_sub_section()
            current_unit_group = []
            current_token_count = 0

        current_unit_group.append(unit)
        current_token_count += unit_tokens

    # Add the last sub-section if it exists
    if current_unit_group:
        create_sub_section()

    return sub_sections

def create_chunks(
    markdown_sections: List[Document],
    max_tokens: int,
    model_name: str="text-embedding-3-small",
    split_large_section_mode: Callable[[str], List[str]] = lambda text: text.split("\n\n"),
) -> List[Document]:
    """
    Join markdown sections into documents till threshold is hit.

    Args:
        split_large_section_mode: A function used to split a single section that's larger than token threshold.
    Returns:
        List[Document]: A list of Document objects, each containing a combined set of sections.
    """
    grouped_documents = []
    current_group_content = []
    current_section_titles = []
    current_token_count = 0

    def finalize_group():
        """Finalize the current group and append it to the grouped documents."""
        nonlocal current_group_content, current_section_titles, current_token_count
        if current_group_content:
            grouped_documents.append(
                Document(
                    page_content="\n\n".join(current_group_content),
                    metadata={
                        "sections": current_section_titles
                    },
                )
            )
            current_group_content = []
            current_section_titles = []
            current_token_count = 0

    for section in markdown_sections:
        section_tokens = count_num_tokens(section.page_content, model_name=model_name)

        # Handle large sections
        if section_tokens > max_tokens:
            sub_sections = handle_large_section(
                section=section,
                max_tokens=max_tokens,
                model_name=model_name,
                split_mode=split_large_section_mode,
            )
            for sub_section, sub_section_tokens in sub_sections:
                if current_token_count + sub_section_tokens <= max_tokens:
                    # Merge with current group
                    current_group_content.append(sub_section.page_content)
                    current_section_titles.extend(sub_section.metadata["sections"])
                    current_token_count += sub_section_tokens
                else:
                    # Finalize the current group
                    finalize_group()
                    # Start a new group with the current sub-section
                    current_group_content = [sub_section.page_content]
                    current_section_titles = sub_section.metadata["sections"]
                    current_token_count = sub_section_tokens
            continue

        # Check if adding this section exceeds the max token limit
        if current_token_count + section_tokens > max_tokens:
            finalize_group()

        # Add the current section to the group
        current_group_content.append(section.page_content)
        current_section_titles.append(section.metadata["section"])
        current_token_count += section_tokens

    # Finalize the last group if it has content
    finalize_group()

    return grouped_documents
