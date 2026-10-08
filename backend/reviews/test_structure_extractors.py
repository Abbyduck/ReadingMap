"""Offline fixtures for Structure extraction: no Chrome/network required."""
import io
import unittest

from reviews.structure_extractors import PageSnapshot, extract_structure, extract_url_list
from reviews.structure_extractors.image import analyze_image


FLUBBY = [
    "Flubby Does Not Like Valentine's Day",
    "Flubby Does Not Like Snow",
    "Flubby Will Not Go to Sleep",
    "Flubby Will Not Take a Bath",
    "Flubby Is Not a Good Pet!",
    "Flubby Will Not Play with That",
]


def make_grid(titles, *, url_prefix="/books/", css="card"):
    return "".join(
        f'<article class="{css}"><a href="{url_prefix}{idx}/{title.lower().replace(" ", "-")}">'
        f'<img src="/covers/{idx}.jpg" alt="{title}"><span>{title}</span></a></article>'
        for idx, title in enumerate(titles, 1)
    )


class StructureExtractorTests(unittest.TestCase):
    BASE = "https://www.penguinrandomhouse.com/series/1LY/flubby/"

    def test_flubby_six_direct_members_and_excludes_related(self):
        # Representative offline fixture, not a saved copy of the publisher's live HTML.
        html = (
            "<main><h2>Flubby Series (6 Titles)</h2><div class='series-grid'>"
            + make_grid(FLUBBY)
            + "</div><h2>Other Series You Might Like</h2><div>"
            + make_grid(["Some Other Book", "Another Other Book"], css="recommendation")
            + "</div></main>"
        )
        result = extract_structure(PageSnapshot(self.BASE, "Flubby", html))
        self.assertEqual(result["declared_count"], 6)
        self.assertEqual(len(result["members"]), 6)
        self.assertEqual([member["title"] for member in result["members"]], FLUBBY)
        self.assertEqual(result["diagnostics"]["strategy"], "generic_dom")

    def test_scholastic_like_cards(self):
        html = '<h2>Frog and Dog Series (2 Books)</h2><div>' + make_grid(
            ["Frog and Dog", "Frog and Dog Go to School"], css="bookDetails") + "</div>"
        result = extract_structure(PageSnapshot("https://www.scholastic.com/books/frog-and-dog", "Frog and Dog", html))
        self.assertEqual(len(result["members"]), 2)

    def test_itemlist_only(self):
        html = '''<script type="application/ld+json">
        {"@type":"ItemList","numberOfItems":5,"itemListElement":[
          {"@type":"ListItem","position":1,"name":"First","url":"https://example.com/books/1"},
          {"@type":"ListItem","position":2,"name":"Second","url":"https://example.com/books/2"}
        ]}</script>'''
        result = extract_structure(PageSnapshot("https://example.com/series", "A Series", html))
        self.assertEqual(result["declared_count"], 5)
        self.assertEqual(result["members"][0]["position"], 1)
        self.assertEqual(len(result["members"]), 2)
        self.assertEqual(result["diagnostics"]["strategy"], "json_ld")

    def test_html_selection_uses_same_parser(self):
        html = "<div>" + make_grid(["Book One", "Book Two"]) + "</div>"
        result = extract_structure(PageSnapshot("https://example.com/series", "", ""), html_fragment=html)
        self.assertEqual(len(result["members"]), 2)

    def test_url_list_deduplicates_and_keeps_distinct_titles(self):
        urls = ["https://example.com/books/1", "https://example.com/books/2",
                "https://example.com/books/1"]
        result = extract_url_list(urls)
        self.assertEqual([m["url"] for m in result["members"]], urls[:2])
        self.assertIsNone(result["members"][0]["position"])

    def test_no_auto_relationship_for_unrelated_navigation(self):
        html = '<nav><a href="/books/x">Books</a><a href="/books/y">Shop</a></nav>'
        result = extract_structure(PageSnapshot("https://example.com/", "Home", html))
        self.assertEqual(result["members"], [])

    def test_declared_count_is_not_member_count(self):
        html = "<h2>A Series (36 Books)</h2><div>" + make_grid(["One", "Two"]) + "</div>"
        result = extract_structure(PageSnapshot("https://example.com/series", "A Series", html))
        self.assertEqual(result["declared_count"], 36)
        self.assertEqual(len(result["members"]), 2)

    def test_image_returns_review_candidates_not_catalog_covers(self):
        from PIL import Image, ImageDraw
        image = Image.new("RGB", (420, 190), "white")
        draw = ImageDraw.Draw(image)
        for left in (20, 145, 270):
            draw.rectangle((left, 15, left + 90, 150), fill=(55, 85, 135))
        buf = io.BytesIO()
        image.save(buf, "PNG")
        result = analyze_image(buf.getvalue())
        self.assertEqual(len(result["members"]), 3)
        self.assertTrue(all(row["image"].startswith("data:image/jpeg;base64,") for row in result["members"]))
