"""
Make sure we built the page correctly and that it displays all the expected
information and sections.
This function should be called on a fully-built site but **before**
deploying it into production.
"""


import os
from bs4 import BeautifulSoup


def _parse_html_for_check(path):
    with open(path, "r") as html:
        return BeautifulSoup(html, "html.parser")


def main():
    workdir = os.path.dirname(os.path.realpath(__file__))

    # Test that we successfully generated the page with all sponsors
    classes = ["sponsor", "card"]
    path = os.path.join(workdir, "_build/production/all/index.html")
    soup = _parse_html_for_check(path)
    sponsors = soup.body.find_all("div", attrs={"class": classes})
    assert len(sponsors) > 100

    # Test that some of those sponsors are not active
    inactive = [x for x in sponsors if "muted" in x.attrs["class"]]
    assert len(inactive) > 30
    assert len(inactive) < 150

    # Test that we successfully generated the page with active sponsors
    path = os.path.join(workdir, "_build/production/active/index.html")
    soup = _parse_html_for_check(path)
    active = soup.body.find_all("div", attrs={"class": classes})
    assert len(active) > 20
    assert len(active) + len(inactive) == len(sponsors)

    # Test that we successfully generated the page with sponsors divided by
    # their groups of interests
    path = os.path.join(workdir, "_build/production/interests/index.html")
    soup = _parse_html_for_check(path)
    toc = soup.body.find("ul", attrs={"id": "toc"}).find_all("li")
    assert len(toc) > 30
    headings = soup.body.find_all("h2")
    assert len(headings) == len(toc)
    sponsors = soup.body.find_all("div", attrs={"class": classes})
    assert len(sponsors) > 50

    # Test that we successfully generated the page with sponsors divided by
    # their native languages
    path = os.path.join(workdir, "_build/production/languages/index.html")
    soup = _parse_html_for_check(path)
    toc = soup.body.find("ul", attrs={"id": "toc"}).find_all("li")
    assert len(toc) > 10
    headings = soup.body.find_all("h2")
    assert len(headings) == len(toc)
    sponsors = soup.body.find_all("div", attrs={"class": classes})
    assert len(sponsors) > 30


if __name__ == "__main__":
    main()
