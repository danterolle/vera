from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit


class CatalogParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None and self.row is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


class PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "header", "footer", "form", "noscript"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "h1", "h2", "li", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "header", "footer", "form", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def content(self) -> str:
        return "\n".join(
            line for part in "".join(self.parts).splitlines()
            if (line := " ".join(part.split()))
        )[:5000]


class SearchLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag != "a" or not {"result__a", "result__url"}.intersection(classes):
            return
        url = urljoin("https://duckduckgo.com/", attributes.get("href") or "")
        parsed = urlsplit(url)
        target = parse_qs(parsed.query).get("uddg", [url])[0]
        if target not in self.urls:
            self.urls.append(target)
