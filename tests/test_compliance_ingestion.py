"""Tests du chunking et du chargement de corpus — purs, AUCUN appel réseau/DB/embedding."""

import json

from app.modules.compliance import ingestion

TEXTE = """## Article 9 — Liste des mentions obligatoires
1. Conformément aux articles 10 à 35, les mentions suivantes sont obligatoires.

## Annexe II — Substances ou produits provoquant des allergies ou intolérances
1. Céréales contenant du gluten.
2. Crustacés et produits à base de crustacés.
"""


def test_chunking_par_article_garde_la_reference():
    chunks = ingestion.split_into_chunks(TEXTE)
    assert [c["ref_article"] for c in chunks] == ["Article 9", "Annexe II"]
    # le contenu garde le titre complet (contexte pour l'embedding) et le texte exact
    assert chunks[0]["contenu"].startswith("Article 9 — Liste des mentions obligatoires")
    assert "mentions suivantes sont obligatoires" in chunks[0]["contenu"]
    assert "Céréales contenant du gluten" in chunks[1]["contenu"]


def test_section_vide_ignoree():
    assert ingestion.split_into_chunks(
        "## Article 1 — Objet\n\n## Article 2 — Définitions\ncorps"
    ) == [{"ref_article": "Article 2", "contenu": "Article 2 — Définitions\n\ncorps"}]


def test_sous_decoupage_article_long_avec_references_precises():
    paragraphes = "\n\n".join(f"{n}. " + f"Contenu du paragraphe {n}. " * 60 for n in range(1, 9))
    texte = f"## Article 30 — Contenu de la déclaration nutritionnelle\n{paragraphes}\n"
    chunks = ingestion.split_into_chunks(texte)
    assert len(chunks) > 1  # sous-découpé
    for chunk in chunks:
        # chaque sous-chunk garde une référence PRÉCISE (« Article 30 §1–§2 »)
        assert chunk["ref_article"].startswith("Article 30 §")
        assert len(chunk["contenu"]) <= ingestion.MAX_CHUNK_CHARS
        # le titre de l'article est répété en tête de chaque sous-chunk (contexte)
        assert chunk["contenu"].startswith("Article 30 — Contenu")
    # les références couvrent les 8 paragraphes sans trou (le §1 est dans le premier, §8 dans le dernier)
    assert "§1" in chunks[0]["ref_article"] and "§8" in chunks[-1]["ref_article"]


def test_section_longue_sans_paragraphes_numerotes():
    texte = "## Annexe IV — Définition de la hauteur de x\n" + ("ligne de texte\n\n" * 400)
    chunks = ingestion.split_into_chunks(texte)
    assert len(chunks) > 1
    assert all(c["ref_article"].startswith("Annexe IV (partie ") for c in chunks)


def test_load_corpus_ignore_les_dossiers_sans_texte(tmp_path):
    # dossier avec meta mais sans .md (cas actuel : en attente du texte officiel)
    folder = tmp_path / "inco"
    folder.mkdir()
    (folder / "meta.json").write_text(
        json.dumps({"titre": "INCO", "source_celex": "02011R1169"}), encoding="utf-8"
    )
    assert ingestion.load_corpus(tmp_path) == []
    # puis le texte arrive
    (folder / "inco.md").write_text(TEXTE, encoding="utf-8")
    documents = ingestion.load_corpus(tmp_path)
    assert len(documents) == 1
    assert documents[0]["meta"]["source_celex"] == "02011R1169"
    assert len(documents[0]["chunks"]) == 2


# HTML synthétique reproduisant la structure du consolidé EUR-Lex (marqueurs ▼,
# notes de bas de page, pagination) — le vrai fichier sera déposé par l'utilisateur.
HTML = """<html><head><title>x</title><script>var x=1;</script></head><body>
<p>02011R1169 — FR — 01.04.2025 — 008.001 — 12</p>
<p>▼B</p>
<p>vu le traité sur le fonctionnement de l'Union européenne, considérant ce qui suit…</p>
<p>Article 1</p><p>Objet et champ d'application</p><p>1. Le présent règlement…</p>
<p>Article 9</p>
<p>Liste des mentions obligatoires</p>
<p>1. Conformément aux articles 10 à 35, les mentions suivantes sont obligatoires :</p>
<p>a) la dénomination de la denrée alimentaire;</p>
<p>▼M5</p>
<p>( 1 ) JO L 304 du 22.11.2011, p. 18.</p>
<p>Article 10</p><p>Mentions complémentaires</p><p>1. Hors curation.</p>
<p>ANNEXE II</p>
<p>SUBSTANCES OU PRODUITS PROVOQUANT DES ALLERGIES OU INTOLÉRANCES</p>
<p>1. Céréales contenant du gluten, à savoir :</p>
</body></html>"""


def test_extraction_html_nettoie_et_cure():
    markdown = ingestion.extract_markdown_from_html(HTML)
    # curation : l'article 9 et l'annexe II sont là, l'article 1 et 10 (hors plan) non,
    # le préambule/considérants non plus
    assert "## Article 9 — Liste des mentions obligatoires" in markdown
    assert "## Annexe II — SUBSTANCES OU PRODUITS" in markdown
    assert "Article 1" not in markdown.replace("Article 10", "").replace("articles 10", "")
    assert "Mentions complémentaires" not in markdown
    assert "considérant" not in markdown
    # bruit EUR-Lex retiré : marqueurs de consolidation, notes, pagination, scripts
    assert "▼" not in markdown and "JO L 304" not in markdown
    assert "02011R1169 —" not in markdown and "var x" not in markdown
    # le texte réglementaire, lui, est intact
    assert "a) la dénomination de la denrée alimentaire;" in markdown
    assert "Céréales contenant du gluten" in markdown


def test_extraction_html_puis_chunking_bout_en_bout():
    markdown = ingestion.extract_markdown_from_html(HTML)
    chunks = ingestion.split_into_chunks(markdown)
    assert [c["ref_article"] for c in chunks] == ["Article 9", "Annexe II"]


# --- Nettoyage Lot 2 : marqueurs retirés, fragments fusionnés, jamais de contenu perdu ---


def test_clean_retire_les_marqueurs_de_rectificatif_en_gardant_le_texte():
    lines = ingestion.clean_lines(["►C1 matières grasses ◄", "▼M5 dont:", "texte ————— suite"])
    assert lines == ["matières grasses", "dont:", "texte suite"]


def test_clean_fusionne_les_marqueurs_de_liste_orphelins():
    lines = ingestion.clean_lines(
        ["a)", "les définitions de «denrée alimentaire»", "b)", "autre point"]
    )
    assert lines == ["a) les définitions de «denrée alimentaire»", "b) autre point"]


def test_clean_fusionne_les_unites_du_tableau_nutritionnel():
    lines = ingestion.clean_lines(["énergie", "kJ/kcal", "matières grasses", "g", "glucides", "g"])
    assert lines == ["énergie — kJ/kcal", "matières grasses — g", "glucides — g"]


def test_clean_retire_les_renvois_de_notes_espaces_seulement():
    # « ( 1 ) » (format EUR-Lex espacé) part ; « (1) » collé et « paragraphe 1 » restent
    lines = ingestion.clean_lines(
        [
            "visés à l'article 9 ( 1 ) du règlement",
            "le paragraphe 1, point c) s'applique",
            "au sens du point (1)",
        ]
    )
    assert lines[0] == "visés à l'article 9 du règlement"
    assert lines[1] == "le paragraphe 1, point c) s'applique"
    assert lines[2] == "au sens du point (1)"


def test_clean_ne_supprime_jamais_de_contenu():
    # tout le texte réglementaire d'entrée se retrouve en sortie (fusionné, jamais perdu)
    entree = ["a)", "céréales contenant du gluten", "12)", "lupin et produits à base de lupin", "g"]
    sortie = " ".join(ingestion.clean_lines(entree))
    for fragment in (
        "céréales contenant du gluten",
        "lupin et produits à base de lupin",
        "a)",
        "12)",
    ):
        assert fragment in sortie


def test_extraction_reelle_sans_artefacts():
    """Sur le vrai corpus déposé : plus aucun marqueur ni cellule-unité isolée."""
    import pathlib

    html_path = pathlib.Path("data/corpus/inco/inco.html")
    if not html_path.exists():
        import pytest

        pytest.skip("corpus non déposé dans cet environnement")
    markdown = ingestion.extract_markdown_from_html(
        html_path.read_text(encoding="utf-8", errors="replace")
    )
    assert "▼" not in markdown and "►" not in markdown and "◄" not in markdown
    assert "—————" not in markdown
    import re

    assert not re.search(r"^\w{1,3}$", markdown, re.M), "cellule isolée résiduelle"
    assert not re.search(r"\( \d+ \)", markdown), "renvoi de note résiduel"
    # le contenu réglementaire clé est intact
    assert "Céréales contenant du gluten" in markdown
    assert "matières grasses — g" in markdown  # unités fusionnées, pas perdues


def test_format_pgvector():
    literal = ingestion.to_pgvector([0.25, -1.0, 0.5])
    assert literal.startswith("[") and literal.endswith("]")
    assert literal.count(",") == 2
    assert "-1.0" in literal
