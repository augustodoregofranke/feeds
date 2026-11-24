#!/usr/bin/env python3
"""Filtered YouTube channel feeds: keep only videos whose title matches a regex.

Each entry in FEEDS becomes <name>.xml. Stdlib only.
"""
import re, sys, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent

# name -> (channel_id, title regex)
FEEDS = {
    "bt0": ("UCru2m14K8eZgtl2uu4XjaJw", r"ironman|trein"),
}

NS = {"a": "http://www.w3.org/2005/Atom"}
for prefix, uri in {"": NS["a"], "yt": "http://www.youtube.com/xml/schemas/2015",
                    "media": "http://search.yahoo.com/mrss/"}.items():
    ET.register_namespace(prefix, uri)


def build(name, channel_id, pattern):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    root = ET.fromstring(urllib.request.urlopen(req, timeout=25).read())
    rx = re.compile(pattern, re.I)
    entries = root.findall("a:entry", NS)
    kept = 0
    for e in entries:
        if rx.search(e.findtext("a:title", "", NS)):
            kept += 1
        else:
            root.remove(e)
    title = root.find("a:title", NS)
    title.text = f"{title.text} ({pattern})"
    ET.ElementTree(root).write(HERE / f"{name}.xml", encoding="utf-8",
                               xml_declaration=True)
    print(f"{name}: {kept}/{len(entries)} videos match /{pattern}/i")


if __name__ == "__main__":
    failed = False
    for name, (cid, pat) in FEEDS.items():
        try:
            build(name, cid, pat)
        except Exception as e:
            print(f"{name}: error {e}")
            failed = True
    sys.exit(1 if failed else 0)
