"""Remove verified site boilerplate from this Penn State scrape.

Run: python clean_scrape.py multi_seed_scrape_data.json
Writes cleaned_scrape_data.json; never overwrites the input.
These rules target observed templates, not arbitrary websites. Unknown layouts
are preserved and flagged for review. Flattened text cannot recover lost links,
heading boundaries, or joined words; future scrapes should extract from HTML.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

PREFIX_ENDS = {
    'career.engr.psu.edu': 'ABET Data Connect ',
    'www.me.psu.edu': 'Quick Links Events Facebook Twitter ',
}
FOOTER_MARKERS = (
    'Connect with Us Communications Development and Alumni Relations Facilities Finance Human Resources',
    'Privacy and Legal Statements Accessibility University Hotlines Email Webmaster',
    'Privacy and Legal Statements University Hotlines Email Webmaster',
)


def clean_page(page):
    if not isinstance(page, dict):
        raise ValueError('Every page must be an object.')
    for field in ('url', 'title', 'content'):
        if not isinstance(page.get(field), str) or not page[field].strip():
            raise ValueError(f'Every page needs a nonempty {field}.')
    original = re.sub(r'\s+', ' ', page['content']).strip()
    text = original
    edits, warnings = [], []
    domain = urlsplit(page['url']).hostname
    marker = PREFIX_ENDS.get(domain)
    if marker:
        boundary = text.find(marker)
        # Require the observed navigation header too; otherwise leave unchanged.
        if boundary >= 0 and 'Search this site' in text[:boundary] and boundary < 8000:
            text = text[boundary + len(marker):].strip()
            edits.append('Removed repeated site navigation prefix')
        else:
            warnings.append('Expected navigation layout not recognized; review page')
    boundaries = [text.find(m) for m in FOOTER_MARKERS if m in text]
    if boundaries:
        text = text[:min(boundaries)].strip()
        edits.append('Removed repeated footer and site contact block')
    if not text:
        text = original
        edits = []
        warnings.append('Cleaning would remove all text; original retained')
    if 'Search this siteSearch Penn State' in text:
        warnings.append('Navigation text remains')
    result = dict(page)
    result['content'] = text
    result['cleaning'] = {
        'rules_version': 1,
        'original_content_sha256': hashlib.sha256(page['content'].encode()).hexdigest(),
        'original_words': len(original.split()), 'cleaned_words': len(text.split()),
        'changes': edits, 'warnings': warnings,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, default=Path('cleaned_scrape_data.json'))
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Keep the original scrape; choose a different output.')
    try:
        pages = json.loads(args.input.read_text(encoding='utf-8'))
        if not isinstance(pages, list) or not pages:
            raise ValueError('Expected a nonempty list of pages.')
        cleaned = [clean_page(page) for page in pages]
        args.output.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except (ValueError, OSError) as error:
        parser.exit(1, f'Error: {error}\n')
    before = sum(p['cleaning']['original_words'] for p in cleaned)
    after = sum(p['cleaning']['cleaned_words'] for p in cleaned)
    print(f'Pages: {len(cleaned)}; words before: {before}; words after: {after}')
    print(f'Saved {args.output}. Original scrape preserved.')
    for page in cleaned:
        for warning in page['cleaning']['warnings']:
            print(f'Review: {page["url"]}: {warning}')


if __name__ == '__main__':
    main()
