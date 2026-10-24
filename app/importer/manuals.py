"""Split Markdown manuals into sections for keyword search.

Each `##` and `###` heading starts a new chunk. A chunk's title keeps its
parent heading ("Troubleshooting > Leaks") so search results and citations
make sense on their own. Small, focused chunks matter: the AI prompt only gets
the few best-matching sections, not whole manuals, which keeps calls cheap.
"""

from dataclasses import dataclass


@dataclass
class Section:
    title: str
    content: str


def split_markdown(text: str) -> list[Section]:
    sections: list[Section] = []
    h2 = ""
    title = "Introduction"  # text before the first ## heading
    lines: list[str] = []

    def flush():
        body = "\n".join(lines).strip()
        if title and body:
            sections.append(Section(title, body))

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            h2 = line[3:].strip()
            title, lines = h2, []
        elif line.startswith("### "):
            flush()
            sub = line[4:].strip()
            title, lines = (f"{h2} > {sub}" if h2 else sub), []
        elif line.startswith("# "):
            continue  # document title; the product already identifies the manual
        else:
            lines.append(line)
    flush()
    return sections
