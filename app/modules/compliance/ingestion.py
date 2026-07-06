"""Ingestion du corpus réglementaire : lecture, chunking par article, vectorisation, index.

STRATÉGIE DE CHUNKING — par unité citable, pas par taille :
- le texte est balisé par des titres « ## <Réf> — <Intitulé> » (un article, une annexe) ;
- un chunk = une unité juridiquement citable qui GARDE sa référence (« Article 9 »,
  « Annexe II ») : c'est ce qui permettra à M2-b de citer ses sources, et un découpage
  aveugle à N caractères séparerait par exemple les 14 allergènes de leur intitulé ;
- les unités trop longues (ex. déclaration nutritionnelle) sont sous-découpées sur leurs
  paragraphes numérotés, en visant TARGET_CHUNK_CHARS (ni dilution, ni miettes), et
  chaque sous-chunk garde une référence précise (« Article 30 §1–§3 »).

Le texte du corpus est le texte OFFICIEL déposé dans data/corpus/ (jamais reconstitué).
"""

import json
import re
from pathlib import Path

from lxml import html as lxml_html

CORPUS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "corpus"

# Plan de curation validé : les unités gardées (mentions obligatoires, allergènes,
# lisibilité, ingrédients, quantités, dates, conservation, origine, mode d'emploi,
# nutrition, définitions, responsabilités). Le reste (considérants, alcool,
# comitologie, transitoires, annexes techniques) est écarté.
CURATED_REFS = {
    "Article 2",
    "Article 8",
    "Article 9",
    "Article 12",
    "Article 13",
    "Article 17",
    "Article 18",
    "Article 21",
    "Article 22",
    "Article 23",
    "Article 24",
    "Article 25",
    "Article 26",
    "Article 27",
    "Article 29",
    "Article 30",
    "Article 31",
    "Article 32",
    "Article 33",
    "Article 34",
    "Article 35",
    "Annexe II",
    "Annexe IV",
    "Annexe X",
    "Annexe XV",
}

# Bruit EUR-Lex consolidé : marqueurs de version (▼B, ▼M5, ►C1…), notes « ( 1 ) JO L … »,
# lignes d'en-tête de pagination « 02011R1169 — FR — 01.04.2025 — 008.001 — 12 »
_NOISE_LINE = re.compile(
    r"^(?:[▼►]\s?[BMC]?\d*\s*$|\(\s?\d+\s?\)\s+JO\b.*|02011R1169\b.*—.*\d+\s*$)"
)
_ARTICLE_LINE = re.compile(r"^Article\s+(\d+)\s*(?:er)?\s*$")
_ANNEXE_LINE = re.compile(r"^ANNEXE\s+([IVXLC]+)\s*$")

# Au-delà : sous-découpage par paragraphes ; en dessous de MIN, on fusionne avec le suivant.
MAX_CHUNK_CHARS = 4000
TARGET_CHUNK_CHARS = 2500

_HEADING = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_PARAGRAPH_NUM = re.compile(r"^(\d+)\.\s", re.MULTILINE)


def _split_long_section(ref: str, body: str) -> list[dict]:
    """Sous-découpe une section longue sur ses paragraphes numérotés « 1. », « 2. »…

    Les paragraphes sont regroupés jusqu'à TARGET_CHUNK_CHARS ; chaque groupe garde
    une référence précise : « <ref> §2 » ou « <ref> §1–§3 ».
    """
    marks = list(_PARAGRAPH_NUM.finditer(body))
    if len(marks) < 2:  # pas de structure en paragraphes : découpage par blocs de lignes
        blocks, current = [], []
        for paragraph in re.split(r"\n\s*\n", body):
            current.append(paragraph)
            if sum(len(p) for p in current) >= TARGET_CHUNK_CHARS:
                blocks.append("\n\n".join(current))
                current = []
        if current:
            blocks.append("\n\n".join(current))
        return [
            {"ref_article": f"{ref} (partie {i})", "contenu": block.strip()}
            for i, block in enumerate(blocks, start=1)
        ]

    # (numéro de §, texte du §) — le préambule éventuel est rattaché au premier groupe
    paragraphs = []
    for index, mark in enumerate(marks):
        start = mark.start() if index > 0 else 0
        end = marks[index + 1].start() if index + 1 < len(marks) else len(body)
        paragraphs.append((int(mark.group(1)), body[start:end].strip()))

    chunks, group, group_start = [], [], None
    for num, text in paragraphs:
        group_start = num if group_start is None else group_start
        group.append((num, text))
        if sum(len(t) for _, t in group) >= TARGET_CHUNK_CHARS:
            ref_suffix = f"§{group_start}" if group_start == num else f"§{group_start}–§{num}"
            chunks.append(
                {
                    "ref_article": f"{ref} {ref_suffix}",
                    "contenu": "\n\n".join(t for _, t in group),
                }
            )
            group, group_start = [], None
    if group:
        last_num = group[-1][0]
        ref_suffix = f"§{group_start}" if group_start == last_num else f"§{group_start}–§{last_num}"
        chunks.append(
            {"ref_article": f"{ref} {ref_suffix}", "contenu": "\n\n".join(t for _, t in group)}
        )
    return chunks


def split_into_chunks(markdown_text: str) -> list[dict]:
    """Markdown balisé « ## Réf — Intitulé » → [{ref_article, contenu}] (contenu = titre + corps)."""
    chunks = []
    headings = list(_HEADING.finditer(markdown_text))
    for index, heading in enumerate(headings):
        title = heading.group(1).strip()
        # la référence citable = la partie avant le tiret long (« Article 9 — Liste… » → « Article 9 »)
        ref = title.split("—")[0].split(" - ")[0].strip()
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown_text)
        body = markdown_text[start:end].strip()
        if not body:
            continue
        content = f"{title}\n\n{body}"
        if len(content) <= MAX_CHUNK_CHARS:
            chunks.append({"ref_article": ref, "contenu": content})
        else:
            for sub in _split_long_section(ref, body):
                sub["contenu"] = f"{title}\n\n{sub['contenu']}"
                chunks.append(sub)
    return chunks


def html_to_lines(raw_html: str | bytes) -> list[str]:
    """HTML EUR-Lex → lignes de texte propres (balises, scripts et bruit retirés)."""
    if isinstance(raw_html, str):
        # lxml refuse les str porteuses d'une déclaration d'encodage : on repasse en bytes,
        # avec parseur UTF-8 explicite (nos bytes viennent toujours d'un ré-encodage UTF-8)
        raw_html = raw_html.encode("utf-8", errors="replace")
    tree = lxml_html.fromstring(raw_html, parser=lxml_html.HTMLParser(encoding="utf-8"))
    for node in tree.xpath("//script | //style | //head"):
        node.drop_tree()
    lines = []
    # blocs FEUILLES uniquement : un <td> contenant des <p> sortirait deux fois
    # (le td entier puis chaque p) et casserait l'ordre des sections
    blocks = tree.xpath(
        "//p[not(.//p)] | //h1 | //h2 | //h3 | //li[not(.//p or .//li)]"
        " | //td[not(.//p or .//div or .//table or .//li)]"
        " | //div[not(.//p or .//div or .//table or .//li or .//td)]"
    )
    for block in blocks:
        text = " ".join(block.text_content().split())
        if text and not _NOISE_LINE.match(text):
            lines.append(text)
    return lines


def extract_markdown_from_html(raw_html: str, curated_refs: set[str] | None = None) -> str:
    """HTML consolidé EUR-Lex → markdown balisé « ## Réf — Intitulé », curation appliquée.

    Détection des unités sur les lignes « Article N » / « ANNEXE X » (la ligne suivante
    est l'intitulé). Tout ce qui précède le premier article (visas, considérants) tombe,
    ainsi que les unités hors du plan de curation validé.
    """
    curated = CURATED_REFS if curated_refs is None else curated_refs
    lines = html_to_lines(raw_html)
    sections: list[tuple[str, str, list[str]]] = []  # (ref, intitulé, corps)
    current: tuple[str, str, list[str]] | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        article = _ARTICLE_LINE.match(line)
        annexe = _ANNEXE_LINE.match(line)
        if article or annexe:
            ref = f"Article {article.group(1)}" if article else f"Annexe {annexe.group(1)}"
            title = lines[index + 1].strip() if index + 1 < len(lines) else ""
            # l'intitulé est la ligne qui suit ; s'il ressemble déjà à du corps, pas d'intitulé
            has_title = bool(title) and not title[:1].isdigit() and len(title) < 200
            current = (ref, title if has_title else "", [])
            sections.append(current)
            index += 2 if has_title else 1
            continue
        if current is not None:
            current[2].append(line)
        index += 1

    parts = []
    for ref, title, body in sections:
        if ref not in curated or not body:
            continue
        heading = f"## {ref} — {title}" if title else f"## {ref}"
        parts.append(heading + "\n" + "\n\n".join(body))
    return "\n\n".join(parts)


def load_corpus(corpus_dir: Path | None = None) -> list[dict]:
    """Lit data/corpus/<slug>/ → [{meta, chunks}] ; ignore les dossiers sans texte déposé."""
    corpus_dir = corpus_dir or CORPUS_DIR
    documents = []
    if not corpus_dir.is_dir():
        return documents
    for folder in sorted(corpus_dir.iterdir()):
        meta_path = folder / "meta.json"
        if not folder.is_dir() or not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        # deux formats acceptés : Markdown déjà balisé, ou HTML brut EUR-Lex (extrait ici)
        parts = [path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.md"))]
        parts += [
            extract_markdown_from_html(path.read_text(encoding="utf-8", errors="replace"))
            for path in sorted(folder.glob("*.html"))
        ]
        chunks = split_into_chunks("\n\n".join(parts))
        if chunks:
            documents.append({"meta": meta, "chunks": chunks})
    return documents


def to_pgvector(vector: list[float]) -> str:
    """Format littéral pgvector ('[0.1,0.2,...]') pour le cast ::vector côté SQL."""
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
