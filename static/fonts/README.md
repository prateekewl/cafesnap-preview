# Bundled fonts

## Noto Sans JP (Regular, Bold)

`NotoSansJP-Regular.ttf` and `NotoSansJP-Bold.ttf` are used by
`pdf_receipt.py` to render the customer-facing booking receipt so that
Japanese customer names (kanji / hiragana / katakana) display as the
correct glyphs instead of empty boxes (tofu). The bot books under the
customer's real name, and many customers have Japanese names.

These are static TrueType instances (weight 400 and 700) derived from
the official Google Fonts "Noto Sans JP" variable font, then subset to
Latin + Latin-1 + Latin Extended A/B + general punctuation + currency
symbols + the full Japanese set (Hiragana, Katakana, Katakana Phonetic
Extensions, CJK Symbols and Punctuation, CJK Unified Ideographs and
Extension A, CJK Compatibility Ideographs, Halfwidth/Fullwidth Forms).
This keeps every realistic Japanese name renderable while keeping the
embedded files at a sensible size.

### License

Noto Sans JP is licensed under the SIL Open Font License, Version 1.1
(OFL-1.1), which permits bundling, embedding in documents (the PDF
receipt), and redistribution. The full license text is in `OFL.txt`.

- Upstream: https://fonts.google.com/noto/specimen/Noto+Sans+JP
- Source project: https://github.com/notofonts/noto-cjk
- Copyright: Copyright The Noto Project Authors
  (https://github.com/notofonts/noto-cjk)
