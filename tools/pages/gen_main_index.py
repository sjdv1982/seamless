"""Generate docs/main/index.md (the documentation home page) from README.md.

The page is the README, adapted for the site, followed by the table of
contents in docs/main-index-toc.md:

- Links to the documentation site or to files under docs/main/ become
  relative links, so they stay inside the site.
- Paragraphs that point to the site home (e.g. "the documentation is at
  https://sjdv1982.github.io/seamless/") are dropped; the first one is
  replaced by SITE_LEADIN, which points to the table of contents.
- Other relative links are made absolute GitHub URLs, because the README's
  repo-relative paths do not exist inside the site.

Usage: gen_main_index.py [ROOT_DIR]
"""

import re
import sys
from pathlib import Path

SITE = "https://sjdv1982.github.io/seamless/"
GITHUB_BLOB = "https://github.com/sjdv1982/seamless/blob/main/"
DOCS_MAIN_URLS = (
    "https://github.com/sjdv1982/seamless/blob/main/docs/main/",
    "https://raw.githubusercontent.com/sjdv1982/seamless/main/docs/main/",
)
# Replaces the dropped paragraph(s) that point to the site home: on the site
# itself, the reader needs a pointer to the table of contents instead.
SITE_LEADIN = (
    "These pages cover the Python and command-line faces: getting started, "
    "caching, cluster setup, remote execution, compiled transformers and the "
    "reference API. See [In this documentation](#in-this-documentation) below "
    "for the full list."
)
HEADER = (
    "<!-- Generated from README.md by tools/pages/gen_main_index.py. "
    "Do not edit; edit README.md or docs/main-index-toc.md instead. -->\n\n"
)

LINK_RE = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))|<(https?://[^>]+)>")


def rewrite_url(url: str) -> str:
    if url.startswith(SITE):
        rest = url[len(SITE):]
        if not rest:
            return url
        return re.sub(r"\.html(?=$|#)", ".md", rest)
    for prefix in DOCS_MAIN_URLS:
        if url.startswith(prefix):
            return url[len(prefix):]
    if re.match(r"^[a-z]+:|^#", url):
        return url
    return GITHUB_BLOB + url.lstrip("./")


def points_to_site_home(paragraph: str) -> bool:
    urls = re.findall(r"https?://[^\s)>*]+", paragraph)
    return any(u.rstrip("/") + "/" == SITE for u in urls)


def adapt(readme: str) -> str:
    def repl(m):
        if m.group(4) is not None:
            return "<" + rewrite_url(m.group(4)) + ">"
        return m.group(1) + rewrite_url(m.group(2)) + m.group(3)

    out_paragraphs = []
    in_code = False
    leadin_done = False
    for para in re.split(r"\n{2,}", readme):
        n_fences = sum(
            1 for line in para.splitlines() if line.lstrip().startswith("```")
        )
        touches_code = in_code or n_fences > 0
        if n_fences % 2:
            in_code = not in_code
        # Leave (parts of) fenced code blocks untouched
        if touches_code:
            out_paragraphs.append(para)
            continue
        if points_to_site_home(para):
            if not leadin_done:
                out_paragraphs.append(SITE_LEADIN)
                leadin_done = True
            continue
        out_paragraphs.append(LINK_RE.sub(repl, para))
    return "\n\n".join(out_paragraphs).rstrip() + "\n"


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parents[2])
    readme = (root / "README.md").read_text()
    toc = (root / "docs" / "main-index-toc.md").read_text()
    page = HEADER + adapt(readme) + "\n---\n\n" + toc.rstrip() + "\n"
    (root / "docs" / "main" / "index.md").write_text(page)
    print("Generated docs/main/index.md from README.md")


if __name__ == "__main__":
    main()
