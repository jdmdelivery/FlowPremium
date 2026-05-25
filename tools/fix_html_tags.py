import pathlib

BAD_OPEN = "<motion"
BAD_CLOSE = "</motion>"
GOOD_CLOSE = "</" + "d" + "i" + "v" + ">"

root = pathlib.Path(__file__).resolve().parent.parent
for path in root.rglob("*.html"):
    text = path.read_text(encoding="utf-8")
    fixed = text.replace(BAD_OPEN, "<div").replace(BAD_CLOSE, GOOD_CLOSE)
    if fixed != text:
        path.write_text(fixed, encoding="utf-8")
        print("fixed:", path)
