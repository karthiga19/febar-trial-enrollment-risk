"""Render deck/*.md (slides separated by '---') to a 16:9 PDF via headless Chrome."""
import markdown, pathlib, subprocess, sys
root = pathlib.Path(__file__).resolve().parents[1]
src = root / "deck/FEBAR_Trial_Enrollment_Risk_Deck.md"
slides = [s.strip() for s in src.read_text().split("\n---\n") if s.strip()]
css = """@page { size: 13.333in 7.5in; margin: 0; }
body { margin: 0; font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; color: #1b2a33; }
.slide { width: 13.333in; height: 7.5in; box-sizing: border-box; padding: 0.55in 0.75in; page-break-after: always; position: relative; overflow: hidden; }
.slide:first-child { background: #0b2026; color: #fff; display: flex; flex-direction: column; justify-content: center; }
.slide:first-child h1 { font-size: 40pt; color: #fff; } .slide:first-child h3 { color: #40d1f5; font-weight: 500; }
h1 { font-size: 26pt; margin: 0 0 .25in; } h2 { font-size: 24pt; margin: 0 0 .2in; color: #0b2026; border-bottom: 3px solid #eb1600; padding-bottom: 6px; }
h3 { font-size: 15pt; margin: .1in 0; } p, li { font-size: 13.5pt; line-height: 1.4; } li { margin: 3px 0; }
table { border-collapse: collapse; width: 100%; font-size: 12pt; margin: 8px 0; } th { background: #0b2026; color: #fff; text-align: left; }
th, td { padding: 6px 9px; border-bottom: 1px solid #d5dde2; } tr:nth-child(even) td { background: #f3f6f8; }
blockquote { border-left: 4px solid #40d1f5; margin: 10px 0; padding: 4px 14px; background: #f3fbfe; } blockquote p { font-size: 13pt; }
pre { background: #f3f6f8; padding: 12px; font-size: 11pt; border-radius: 6px; white-space: pre-wrap; }
strong { color: #b81200; } th strong { color: #40d1f5; } .slide:first-child strong { color: #fff; }
.foot { position: absolute; bottom: .25in; right: .5in; font-size: 9pt; color: #7a8a94; }"""
body = "".join(f'<section class="slide">{markdown.markdown(s, extensions=["tables", "fenced_code"])}<div class="foot">Meridian Therapeutics (fictional) · Trial Enrollment Risk Cockpit · {i+1}/{len(slides)}</div></section>' for i, s in enumerate(slides))
html = root / "deck/deck.html"; html.write_text(f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>")
pdf = root / "deck/FEBAR_Trial_Enrollment_Risk_Deck.pdf"
chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", html.as_uri()], check=True, capture_output=True)
print(pdf, pdf.stat().st_size, "bytes,", len(slides), "slides")
