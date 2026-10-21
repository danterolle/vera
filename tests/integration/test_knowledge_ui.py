from html.parser import HTMLParser

from vera.interfaces.assets import load_asset, load_graph_page


class PageElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = {}
        self.header_ids = set()
        self.toolbar_ids = set()
        self.links = []
        self.in_header = False
        self.in_toolbar = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "header":
            self.in_header = True
        if attributes.get("class") == "view-toolbar":
            self.in_toolbar = True
        if tag == "a":
            self.links.append(attributes.get("href"))
        if "id" in attributes:
            self.ids[attributes["id"]] = tag, attributes
            if self.in_header:
                self.header_ids.add(attributes["id"])
            if self.in_toolbar:
                self.toolbar_ids.add(attributes["id"])

    def handle_endtag(self, tag):
        if tag == "header":
            self.in_header = False
        if tag == "div" and self.in_toolbar:
            self.in_toolbar = False


def test_knowledge_page_exposes_search_graph_and_detail_controls():
    response = load_graph_page(knowledge=True)
    page = PageElements()
    page.feed(response.body.decode())

    assert response.status_code == 200
    assert page.ids["entity"][1]["role"] == "combobox"
    assert page.ids["entity"][1]["aria-controls"] == "suggestions"
    assert page.ids["filters"][1]["role"] == "search"
    assert page.ids["suggestions"][1]["role"] == "listbox"
    assert {"filters", "entity", "suggestions", "search-feedback"} <= page.header_ids
    assert {"limit", "overview", "provenance"} <= page.toolbar_ids
    assert "/graph" in page.links
    assert page.ids["graph"][1]["role"] == "group"
    assert page.ids["graph"][1]["aria-describedby"] == "graph-help"
    assert page.ids["status"][1]["role"] == "status"
    for identifier in ("overview", "provenance", "zoom-in", "zoom-out", "fit-graph",
                       "concept-list", "details", "back-to-graph"):
        assert identifier in page.ids


def test_knowledge_assets_are_available_and_render_graph_text_safely():
    for asset in ("knowledge.js", "knowledge-renderer.js", "knowledge-inspector.js",
                  "knowledge-layout.js", "knowledge.css"):
        assert load_asset(asset).status_code == 200

    for asset in ("knowledge.js", "knowledge-renderer.js", "knowledge-inspector.js"):
        source = load_asset(asset).body.decode()
        assert "innerHTML" not in source
        assert "textContent" in source


def test_knowledge_search_keeps_keyboard_navigation_and_mobile_layout():
    script = load_asset("knowledge.js").body.decode()
    stylesheet = load_asset("knowledge.css").body.decode()

    for key in ("ArrowDown", "ArrowUp", "Enter", "Escape", "aria-activedescendant"):
        assert key in script
    assert ".search-box:focus-within input" in stylesheet
    assert '#suggestions [aria-selected="true"]' in stylesheet
    assert "@media (max-width: 650px)" in stylesheet
