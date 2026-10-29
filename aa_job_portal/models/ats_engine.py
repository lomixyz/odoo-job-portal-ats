# -*- coding: utf-8 -*-
"""ATS (Applicant Tracking System) compliance checker for résumés / CVs.

Pure-Python, no extra dependencies: PDF through pypdf / PyPDF2 (shipped with
Odoo), DOCX and ODT by reading their XML, TXT/RTF as text.

The checks follow the widely accepted rules for an ATS-compliant résumé:
  * a text-based PDF or DOCX file, readable by a parser, reasonably small,
    with a professional file name
  * contact details (name, e-mail, phone, profile link) in the body
  * standard section headings (Summary, Experience, Education, Skills, ...)
  * simple single-column layout: no tables, text boxes, columns, images or
    contact details hidden in headers/footers; standard fonts
  * concise content (1-2 pages), dated experience, bullet points, action verbs
    and quantified achievements, no unnecessary personal data
  * keywords that match the targeted job description
"""
import io
import re
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

try:  # Odoo 17 on Python >= 3.13 and recent environments
    import pypdf as _pdf
except ImportError:  # pragma: no cover - depends on the installed stack
    try:
        import PyPDF2 as _pdf
    except ImportError:
        _pdf = None

MAX_ANALYSE_SIZE = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------
SECTIONS = {
    'summary': ['summary', 'professional summary', 'career summary', 'profile', 'professional profile',
                'personal profile', 'objective', 'career objective', 'about me', 'executive summary',
                'الملخص', 'ملخص', 'نبذة', 'نبذة عني', 'الهدف الوظيفي', 'الملف الشخصي'],
    'experience': ['experience', 'work experience', 'professional experience', 'employment history',
                   'work history', 'career history', 'relevant experience', 'employment', 'experience summary',
                   'الخبرات', 'الخبرة', 'الخبرات العملية', 'الخبرة العملية', 'السجل الوظيفي'],
    'education': ['education', 'academic background', 'qualifications', 'academic qualifications',
                  'education and training', 'educational background', 'education & training',
                  'التعليم', 'المؤهلات', 'المؤهلات العلمية', 'التعليم والمؤهلات', 'المؤهل العلمي'],
    'skills': ['skills', 'technical skills', 'core competencies', 'key skills', 'competencies',
               'areas of expertise', 'expertise', 'core skills', 'skills & abilities', 'skills and abilities',
               'professional skills', 'المهارات', 'المهارات التقنية', 'المهارات الشخصية'],
    'extra': ['certifications', 'certificates', 'certification', 'licenses', 'licenses & certifications',
              'projects', 'key projects', 'languages', 'awards', 'achievements', 'publications',
              'volunteer', 'volunteering', 'training', 'courses', 'professional development',
              'الشهادات', 'الدورات', 'الدورات التدريبية', 'اللغات', 'المشاريع', 'الإنجازات'],
}

ACTION_VERBS = {
    'achieved', 'administered', 'analyzed', 'analysed', 'automated', 'built', 'championed', 'configured',
    'consolidated', 'coordinated', 'created', 'customized', 'customised', 'delivered', 'deployed',
    'designed', 'developed', 'directed', 'drove', 'enhanced', 'established', 'executed', 'expanded',
    'facilitated', 'generated', 'guided', 'headed', 'identified', 'implemented', 'improved', 'increased',
    'initiated', 'integrated', 'introduced', 'launched', 'led', 'maintained', 'managed', 'mentored',
    'migrated', 'negotiated', 'optimized', 'optimised', 'organized', 'organised', 'oversaw', 'planned',
    'produced', 'reduced', 'resolved', 'restructured', 'saved', 'spearheaded', 'streamlined',
    'supervised', 'supported', 'trained', 'transformed', 'upgraded', 'won', 'wrote',
}

STANDARD_FONTS = (
    'arial', 'calibri', 'cambria', 'garamond', 'georgia', 'helvetica', 'times', 'timesnewroman',
    'verdana', 'tahoma', 'trebuchet', 'bookantiqua', 'palatino', 'segoeui', 'aptos', 'liberation',
    'dejavu', 'opensans', 'roboto', 'lato', 'carlito', 'caladea', 'arimo', 'tinos', 'noto', 'sourcesans',
    'symbol', 'wingdings', 'courier', 'consolas', 'centurygothic', 'franklingothic', 'inter',
)

PERSONAL_DATA = [
    r'date of birth', r'\bd\.?o\.?b\b', r'birth ?date', r'\bage\s*[:\-]', r'marital status', r'\breligion\b',
    r'\bgender\s*[:\-]', r'passport (no|number)', r'\biqama\b', r'national id', r'تاريخ الميلاد',
    r'الحالة الاجتماعية', r'الديانة',
]

GENERIC_FILE_WORDS = {'document', 'doc', 'untitled', 'scan', 'scanned', 'image', 'img', 'file', 'new',
                      'copy', 'final', 'download', 'tmp', 'temp', 'test'}

STOPWORDS = set('''
a about above across after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing done down during each either else etc every few for
from further had has have having he her here hers him his how i if in into is it its itself just least
less let like made make many may me might more most must my no nor not of off on once only or other our
ours out over own per please same shall she should so some such than that the their theirs them then there
these they this those through to too under until up upon us very via was we well were what when where which
while who whom whose why will with within without would you your yours
ability able across apply applicant applicants applying candidate candidates company daily day description
duties ensure etc excellent experience experienced familiar good great help ideal include including job jobs
join knowledge level looking must new opportunity part per plus position positions preferred related
required requirement requirements responsibilities responsibility responsible role roles skill skills strong
successful team teams time understanding work working year years within across based key one two three
'''.split())

EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+(\.[\w-]+)+')
PHONE_RE = re.compile(r'(\+?\d[\d\s().\-]{7,}\d)')
URL_RE = re.compile(r'(linkedin\.com/|github\.com/|https?://|www\.)', re.I)
MONTHS = r'(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?'
DATE_RE = re.compile(
    r'(' + MONTHS + r'\s*\d{4})|(\b\d{1,2}[/.\-]\d{4}\b)|(\b(19|20)\d{2}\s*[-–—]\s*((19|20)\d{2}|present|current|now|today)\b)'
    r'|(\b(19|20)\d{2}\b)', re.I)
BULLET_RE = re.compile(r'^\s*([•●▪◦‣■□►▶✓✔\-–—*·\uf0b7\uf0a7\uf0d8\uf076]|\d{1,2}[.)])\s*')
QUANT_RE = re.compile(
    r'(\d+(\.\d+)?\s?%)|([$€£¥]\s?\d)|(\b(sar|usd|eur|aed|ريال)\s?\d)|(\d[\d,.]*\s?(k|m|million|billion|bn)\b)'
    r'|(\b\d[\d,]*\+?\s?(users|clients|customers|projects|employees|people|staff|stores|branches|companies|'
    r'modules|reports|orders|transactions|members|countries|sites|servers|hours|days|weeks|months)\b)', re.I)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z+#.\-]*[A-Za-z+#]|[A-Za-z]|[\u0600-\u06FF]{2,}")


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _extract_docx(raw):
    meta = {'tables': 0, 'images': 0, 'textboxes': 0, 'columns': 1, 'header_contact': False, 'fonts': set(),
            'pages': None}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        root = ET.fromstring(z.read('word/document.xml'))
        lines = []
        for el in root.iter():
            tag = _local(el.tag)
            if tag == 'tbl':
                meta['tables'] += 1
            elif tag in ('drawing', 'pict', 'imagedata'):
                meta['images'] += 1
            elif tag == 'txbxContent':
                meta['textboxes'] += 1
            elif tag == 'cols':
                for k, v in el.attrib.items():
                    if _local(k) == 'num' and v.isdigit():
                        meta['columns'] = max(meta['columns'], int(v))
            elif tag == 'rFonts':
                for k, v in el.attrib.items():
                    if _local(k) in ('ascii', 'hAnsi', 'cs'):
                        meta['fonts'].add(v)
            elif tag == 'lastRenderedPageBreak':
                meta['pages'] = (meta['pages'] or 1) + 1
        for p in root.iter():
            if _local(p.tag) != 'p':
                continue
            text = ''.join(t.text or '' for t in p.iter() if _local(t.tag) in ('t',))
            text = text.replace('\xa0', ' ')
            is_list = any(_local(x.tag) == 'numPr' for x in p.iter())
            if text.strip():
                lines.append(('• ' if is_list and not BULLET_RE.match(text) else '') + text)
        # headers / footers
        hf_text = ''
        for n in names:
            if re.match(r'word/(header|footer)\d*\.xml$', n):
                hroot = ET.fromstring(z.read(n))
                hf_text += ' '.join(t.text or '' for t in hroot.iter() if _local(t.tag) == 't') + ' '
                meta['images'] += sum(1 for x in hroot.iter() if _local(x.tag) in ('drawing', 'pict'))
        if EMAIL_RE.search(hf_text) or PHONE_RE.search(hf_text):
            meta['header_contact'] = True
        for n in ('word/styles.xml', 'word/theme/theme1.xml'):
            if n in names:
                sroot = ET.fromstring(z.read(n))
                for el in sroot.iter():
                    tag = _local(el.tag)
                    if tag == 'rFonts':
                        for k, v in el.attrib.items():
                            if _local(k) in ('ascii', 'hAnsi'):
                                meta['fonts'].add(v)
                    elif tag == 'latin' and n.endswith('theme1.xml'):
                        if el.attrib.get('typeface'):
                            meta['fonts'].add(el.attrib['typeface'])
        meta['media_files'] = sum(1 for n in names if n.startswith('word/media/'))
    return '\n'.join(lines), meta


def _extract_odt(raw):
    meta = {'tables': 0, 'images': 0, 'textboxes': 0, 'columns': 1, 'header_contact': False, 'fonts': set(),
            'pages': None}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root = ET.fromstring(z.read('content.xml'))
        lines = []
        for el in root.iter():
            tag = _local(el.tag)
            if tag == 'table':
                meta['tables'] += 1
            elif tag == 'image':
                meta['images'] += 1
            elif tag == 'text-box':
                meta['textboxes'] += 1
            elif tag == 'font-face':
                for k, v in el.attrib.items():
                    if _local(k) == 'name':
                        meta['fonts'].add(v)
            if tag in ('p', 'h'):
                text = ''.join(el.itertext()).strip()
                if text:
                    lines.append(text)
    return '\n'.join(lines), meta


def _clean_font(name):
    name = (name or '').lstrip('/')
    name = re.sub(r'^[A-Z]{6}\+', '', name)  # subset prefix
    name = re.split(r'[,\-]', name)[0]
    return name


def _extract_pdf(raw):
    meta = {'tables': None, 'images': 0, 'textboxes': None, 'columns': None, 'header_contact': None,
            'fonts': set(), 'pages': 0}
    if _pdf is None:
        raise ValueError('No PDF library available')
    Reader = getattr(_pdf, 'PdfReader', None) or getattr(_pdf, 'PdfFileReader')
    reader = Reader(io.BytesIO(raw), strict=False)
    if getattr(reader, 'is_encrypted', False) or getattr(reader, 'isEncrypted', False):
        try:
            reader.decrypt('')
        except Exception:
            raise ValueError('encrypted')
    pages = list(reader.pages)
    meta['pages'] = len(pages)
    chunks = []
    for page in pages:
        extract = getattr(page, 'extract_text', None) or getattr(page, 'extractText')
        try:
            chunks.append(extract() or '')
        except Exception:
            chunks.append('')
        try:
            res = page.get('/Resources') or {}
            res = res.get_object() if hasattr(res, 'get_object') else res
            fonts = res.get('/Font') or {}
            fonts = fonts.get_object() if hasattr(fonts, 'get_object') else fonts
            for ref in fonts.values():
                font = ref.get_object() if hasattr(ref, 'get_object') else ref
                meta['fonts'].add(_clean_font(str(font.get('/BaseFont', ''))))
            xobjs = res.get('/XObject') or {}
            xobjs = xobjs.get_object() if hasattr(xobjs, 'get_object') else xobjs
            for ref in xobjs.values():
                xo = ref.get_object() if hasattr(ref, 'get_object') else ref
                if str(xo.get('/Subtype')) == '/Image':
                    meta['images'] += 1
        except Exception:
            pass
    return '\n'.join(chunks), meta


def _extract_rtf(raw):
    text = raw.decode('latin-1', errors='ignore')
    text = re.sub(r'\\par[d]?', '\n', text)
    text = re.sub(r'\{\\\*[^{}]*\}', '', text)
    text = re.sub(r'\\[a-zA-Z]+-?\d* ?', '', text)
    text = re.sub(r'[{}]', '', text)
    return text, {'tables': None, 'images': 0, 'textboxes': None, 'columns': None, 'header_contact': None,
                  'fonts': set(), 'pages': None}


def extract(filename, raw):
    """Return (fmt, text, meta, error)."""
    ext = (filename or '').lower().rsplit('.', 1)[-1] if '.' in (filename or '') else ''
    try:
        if ext == 'pdf' or raw[:4] == b'%PDF':
            text, meta = _extract_pdf(raw)
            return 'pdf', text, meta, None
        if ext == 'docx':
            text, meta = _extract_docx(raw)
            return 'docx', text, meta, None
        if ext == 'odt':
            text, meta = _extract_odt(raw)
            return 'odt', text, meta, None
        if ext == 'rtf':
            text, meta = _extract_rtf(raw)
            return 'rtf', text, meta, None
        if ext == 'txt':
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                text = raw.decode('latin-1', errors='ignore')
            return 'txt', text, {'tables': 0, 'images': 0, 'textboxes': 0, 'columns': 1, 'header_contact': False,
                                 'fonts': set(), 'pages': None}, None
        return ext or 'unknown', '', {'fonts': set()}, 'unsupported'
    except Exception as e:  # corrupted / encrypted / unusual files
        return ext or 'unknown', '', {'fonts': set()}, str(e) or 'unreadable'


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------
def _norm(text):
    return re.sub(r'\s+', ' ', (text or '').lower())


def tokens(text):
    return [w.lower().strip('.-') for w in WORD_RE.findall(text or '')]


def job_keywords(title, description, limit=18):
    """Most relevant keywords of a job: title words + frequent description terms + frequent bigrams."""
    title_words = [w for w in tokens(title) if w not in STOPWORDS and len(w) > 1]
    desc_words = [w for w in tokens(description) if w not in STOPWORDS and len(w) > 2 and not w.isdigit()]
    counts = Counter(desc_words)
    bigrams = Counter(
        f'{a} {b}' for a, b in zip(desc_words, desc_words[1:]) if a != b)
    keywords = []
    for w in title_words:
        if w not in keywords:
            keywords.append(w)
    for bg, n in bigrams.most_common(6):
        if n >= 2 and bg not in keywords:
            keywords.append(bg)
    for w, n in counts.most_common(60):
        if len(keywords) >= limit:
            break
        if w not in keywords and not any(w in k.split() for k in keywords if ' ' in k and counts[w] <= 2):
            keywords.append(w)
    return keywords[:limit]


def keyword_match(cv_text, keywords):
    norm = ' ' + ' '.join(tokens(cv_text)) + ' '
    matched, missing = [], []
    for kw in keywords:
        (matched if f' {kw} ' in norm else missing).append(kw)
    score = round(100.0 * len(matched) / len(keywords)) if keywords else 0
    return score, matched, missing


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def _check(key, category, title, status, points, max_points, message, tip=''):
    return {'key': key, 'category': category, 'title': title, 'status': status,
            'points': points, 'max': max_points, 'message': message, 'tip': tip}


def _find_sections(lines):
    found = {}
    for line in lines:
        clean = re.sub(r'^[\W_]+|[\W_]+$', '', line.strip()).lower()
        clean = re.sub(r'\s+', ' ', clean)
        if not clean or len(clean.split()) > 5:
            continue
        for key, names in SECTIONS.items():
            if any(clean == n or clean.startswith(n + ' ') or clean.endswith(' ' + n) for n in names):
                found.setdefault(key, line.strip())
    return found


def analyse(filename, raw, candidate_name='', keywords=None):
    """Run every ATS check. Returns a dict ready to be stored."""
    size = len(raw or b'')
    fmt, text, meta, error = extract(filename, raw) if size <= MAX_ANALYSE_SIZE else (
        (filename or '').rsplit('.', 1)[-1].lower(), '', {'fonts': set()}, 'too_large')
    text = (text or '').replace('\r', '\n')
    lines = [l for l in (x.strip() for x in text.split('\n')) if l]
    words = tokens(text)
    word_count = len([w for w in text.split() if re.search(r'\w', w)])
    checks = []
    C_FILE, C_CONTACT, C_SECTIONS, C_LAYOUT, C_CONTENT = 'file', 'contact', 'sections', 'layout', 'content'

    # ---------------- File & format (20) ----------------
    if fmt in ('pdf', 'docx'):
        checks.append(_check('format', C_FILE, 'File format', 'pass', 6, 6, f'{fmt.upper()} is read by every major ATS.'))
    elif fmt in ('odt', 'txt', 'rtf'):
        checks.append(_check('format', C_FILE, 'File format', 'warn', 3, 6, f'{fmt.upper()} files are not accepted by every ATS.',
                             'Export your CV as a PDF (text-based) or DOCX file.'))
    else:
        checks.append(_check('format', C_FILE, 'File format', 'fail', 0, 6, f'{fmt.upper() or "This"} format cannot be parsed reliably.',
                             'Save your CV as a PDF (text-based) or DOCX file.'))

    if word_count >= 150:
        checks.append(_check('readable', C_FILE, 'Machine-readable text', 'pass', 10, 10,
                             f'{word_count} words could be extracted.'))
    elif word_count >= 50:
        checks.append(_check('readable', C_FILE, 'Machine-readable text', 'warn', 5, 10,
                             f'Only {word_count} words could be extracted.',
                             'Make sure the text is real text (not an image) and not inside shapes or text boxes.'))
    else:
        reason = 'The file looks like a scanned image or a design export.' if (fmt == 'pdf' and meta.get('images')) else \
            'Almost no text could be read from the file.'
        if error == 'encrypted':
            reason = 'The PDF is password-protected.'
        checks.append(_check('readable', C_FILE, 'Machine-readable text', 'fail', 0, 10, reason,
                             'Create the CV in Word/Google Docs and export it as PDF or DOCX — do not scan or photograph it.'))

    mb = size / (1024 * 1024.0)
    size_label = f'{mb:.1f} MB' if mb >= 1 else f'{max(1, round(size / 1024.0))} KB'
    if mb <= 2:
        checks.append(_check('size', C_FILE, 'File size', 'pass', 2, 2, f'{size_label}.'))
    elif mb <= 5:
        checks.append(_check('size', C_FILE, 'File size', 'warn', 1, 2, f'{mb:.1f} MB is larger than recommended.',
                             'Keep the file under 2 MB: remove images and compress the PDF.'))
    else:
        checks.append(_check('size', C_FILE, 'File size', 'fail', 0, 2, f'{mb:.1f} MB — many ATS reject large files.',
                             'Keep the file under 2 MB.'))

    stem = re.sub(r'\.[a-z0-9]+$', '', (filename or '').lower())
    stem_words = set(re.split(r'[\W_]+', stem)) - {''}
    name_words = {w for w in tokens(candidate_name) if len(w) > 1}
    if (stem_words & name_words) or (stem_words & {'cv', 'resume', 'résumé'}) and not (stem_words & GENERIC_FILE_WORDS):
        checks.append(_check('filename', C_FILE, 'File name', 'pass', 2, 2, f'"{filename}" is clear and professional.'))
    else:
        checks.append(_check('filename', C_FILE, 'File name', 'warn', 0, 2, f'"{filename}" does not identify you.',
                             'Name the file like "Firstname-Lastname-CV.pdf".'))

    # ---------------- Contact details (15) ----------------
    head = '\n'.join(lines[:25])
    email = EMAIL_RE.search(text)
    phone = None
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r'\D', '', m.group(1))
        if 9 <= len(digits) <= 15 and not re.fullmatch(r'(19|20)\d{2}(19|20)\d{2}', digits):
            phone = m
            break
    checks.append(_check('email', C_CONTACT, 'E-mail address', 'pass' if email else 'fail', 5 if email else 0, 5,
                         'Found in the CV.' if email else 'No e-mail address found in the CV text.',
                         '' if email else 'Add a professional e-mail address at the top of the CV (not in the header area).'))
    checks.append(_check('phone', C_CONTACT, 'Phone number', 'pass' if phone else 'fail', 5 if phone else 0, 5,
                         'Found in the CV.' if phone else 'No phone number found in the CV text.',
                         '' if phone else 'Add your mobile number with country code, e.g. +966 5x xxx xxxx.'))
    head_tokens = set(tokens(head))
    if name_words and len(name_words & head_tokens) >= min(2, len(name_words)):
        checks.append(_check('name', C_CONTACT, 'Your name at the top', 'pass', 3, 3, 'Your name appears at the top.'))
    elif name_words and name_words & set(words):
        checks.append(_check('name', C_CONTACT, 'Your name at the top', 'warn', 1, 3, 'Your name is not in the first lines.',
                             'Put your full name as the first line of the CV.'))
    else:
        checks.append(_check('name', C_CONTACT, 'Your name at the top', 'warn' if not name_words else 'fail', 1 if not name_words else 0, 3,
                             'Your name could not be found.', 'Put your full name as the first line of the CV.'))
    url = URL_RE.search(text)
    checks.append(_check('links', C_CONTACT, 'LinkedIn / portfolio link', 'pass' if url else 'warn', 2 if url else 0, 2,
                         'Profile link found.' if url else 'No LinkedIn or portfolio link.',
                         '' if url else 'Add your LinkedIn profile URL next to your contact details.'))

    # ---------------- Standard sections (25) ----------------
    found = _find_sections(lines)
    section_rules = [
        ('experience', 'Work Experience section', 8, 'fail',
         'Use a heading such as "Work Experience" or "Professional Experience".'),
        ('education', 'Education section', 6, 'fail', 'Add an "Education" section with degree, institution and year.'),
        ('skills', 'Skills section', 6, 'fail', 'Add a "Skills" section listing your hard skills as keywords.'),
        ('summary', 'Professional Summary', 3, 'warn', 'Start with a 2–3 line "Professional Summary".'),
        ('extra', 'Certifications / Projects / Languages', 2, 'warn',
         'Add "Certifications", "Projects" or "Languages" if relevant.'),
    ]
    for key, title, pts, missing_status, tip in section_rules:
        if key in found:
            checks.append(_check('sec_' + key, C_SECTIONS, title, 'pass', pts, pts, f'Heading found: "{found[key]}".'))
        else:
            checks.append(_check('sec_' + key, C_SECTIONS, title, missing_status, 0, pts,
                                 'No standard heading found — an ATS may not recognise this part.', tip))

    # ---------------- Layout & formatting (20) ----------------
    def layout_check(key, title, value, pts, ok_msg, bad_msg, tip, warn=False):
        if value is None:
            checks.append(_check(key, C_LAYOUT, title, 'pass', pts, pts, 'Not detected.'))
        elif value:
            checks.append(_check(key, C_LAYOUT, title, 'warn' if warn else 'fail', pts // 2 if warn else 0, pts, bad_msg, tip))
        else:
            checks.append(_check(key, C_LAYOUT, title, 'pass', pts, pts, ok_msg))

    layout_check('tables', 'No tables', meta.get('tables'), 5, 'No tables used.',
                 f"{meta.get('tables')} table(s) found — many ATS read tables in the wrong order.",
                 'Replace tables with plain paragraphs and bullet points.')
    images = meta.get('images') or meta.get('media_files')
    layout_check('images', 'No photo or graphics', images, 4, 'No images or photos.',
                 f'{images} image(s) found (photo, icons, logos or charts).',
                 'Remove the photo, icons and skill bars — an ATS cannot read them.', warn=True)
    complex_layout = None
    if meta.get('textboxes') is not None or meta.get('columns') is not None:
        complex_layout = (meta.get('textboxes') or 0) + (1 if (meta.get('columns') or 1) > 1 else 0)
    layout_check('columns', 'Single column, no text boxes', complex_layout, 4, 'Simple single-column layout.',
                 'Text boxes or multiple columns found.', 'Use a single-column layout without text boxes.')
    layout_check('header', 'Contact details in the body', meta.get('header_contact'), 3,
                 'Contact details are in the main body.', 'Contact details are placed in the page header/footer.',
                 'Many ATS skip headers and footers — move contact details into the body.')
    fonts = {f for f in meta.get('fonts') or set() if f}
    odd = sorted({f for f in fonts if not any(s in re.sub(r'[\s_]', '', f.lower()) for s in STANDARD_FONTS)
                  and not f.lower().startswith('+')})
    if not fonts:
        checks.append(_check('fonts', C_LAYOUT, 'Standard fonts', 'pass', 4, 4, 'Not detected.'))
    elif odd:
        checks.append(_check('fonts', C_LAYOUT, 'Standard fonts', 'warn', 2, 4, 'Non-standard font(s): ' + ', '.join(odd[:4]) + '.',
                             'Use Arial, Calibri, Cambria, Garamond, Georgia, Helvetica or Times New Roman.'))
    else:
        checks.append(_check('fonts', C_LAYOUT, 'Standard fonts', 'pass', 4, 4, 'Standard, ATS-safe fonts.'))

    # ---------------- Content quality (20) ----------------
    pages = meta.get('pages') or (max(1, round(word_count / 500.0)) if word_count else 0)
    if 350 <= word_count <= 1200 and pages <= 2:
        checks.append(_check('length', C_CONTENT, 'Length (1–2 pages)', 'pass', 4, 4, f'{word_count} words, about {pages} page(s).'))
    elif 200 <= word_count <= 1800 and pages <= 3:
        checks.append(_check('length', C_CONTENT, 'Length (1–2 pages)', 'warn', 2, 4, f'{word_count} words, about {pages} page(s).',
                             'Aim for 400–1,000 words on one or two pages.'))
    else:
        checks.append(_check('length', C_CONTENT, 'Length (1–2 pages)', 'fail', 0, 4, f'{word_count} words, about {pages} page(s).',
                             'Aim for 400–1,000 words on one or two pages.'))
    dates = len(DATE_RE.findall(text))
    checks.append(_check('dates', C_CONTENT, 'Dated experience', 'pass' if dates >= 3 else ('warn' if dates else 'fail'),
                         4 if dates >= 3 else (2 if dates else 0), 4,
                         f'{dates} date(s) found.' if dates else 'No dates found.',
                         '' if dates >= 3 else 'Give start and end dates for every role, e.g. "Jan 2022 – Present".'))
    bullets = sum(1 for l in lines if BULLET_RE.match(l) or (l.split() and l.split()[0].lower().strip(',.') in ACTION_VERBS))
    checks.append(_check('bullets', C_CONTENT, 'Bullet points', 'pass' if bullets >= 4 else ('warn' if bullets else 'fail'),
                         3 if bullets >= 4 else (1 if bullets else 0), 3, f'{bullets} bullet / achievement line(s).',
                         '' if bullets >= 4 else 'Describe each role with 3–6 simple bullet points (•).'))
    quant = sum(1 for l in lines if QUANT_RE.search(l))
    checks.append(_check('numbers', C_CONTENT, 'Quantified achievements', 'pass' if quant >= 3 else ('warn' if quant else 'fail'),
                         3 if quant >= 3 else (1 if quant else 0), 3, f'{quant} measurable result(s).',
                         '' if quant >= 3 else 'Add numbers: %, amounts, team size, users, time saved.'))
    verbs = sorted({w for w in words if w in ACTION_VERBS})
    checks.append(_check('verbs', C_CONTENT, 'Action verbs', 'pass' if len(verbs) >= 5 else ('warn' if verbs else 'fail'),
                         4 if len(verbs) >= 5 else (2 if verbs else 0), 4,
                         (f'{len(verbs)} found: ' + ', '.join(verbs[:6]) + ('…' if len(verbs) > 6 else '')) if verbs else 'No action verbs found.',
                         '' if len(verbs) >= 5 else 'Start bullets with verbs like Led, Implemented, Reduced, Delivered.'))
    lowered = _norm(text)
    personal = [p for p in PERSONAL_DATA if re.search(p, lowered)]
    checks.append(_check('personal', C_CONTENT, 'No unnecessary personal data', 'warn' if personal else 'pass',
                         0 if personal else 2, 2,
                         'Contains personal details such as date of birth, marital status or ID numbers.' if personal
                         else 'No unnecessary personal data.',
                         'Remove date of birth, marital status, religion and ID/passport numbers.' if personal else ''))

    score = sum(c['points'] for c in checks)
    max_score = sum(c['max'] for c in checks)
    score = round(100.0 * score / max_score) if max_score else 0
    if word_count < 50:
        # Nothing for an ATS to parse: the other checks are meaningless.
        score = min(score, 15)
    result = {
        'format': fmt,
        'error': error,
        'score': score,
        'grade': 'excellent' if score >= 85 else 'good' if score >= 70 else 'fair' if score >= 50 else 'poor',
        'word_count': word_count,
        'page_count': pages or 0,
        'checks': checks,
        'text': text[:60000],
    }
    if keywords:
        kscore, matched, missing = keyword_match(text, keywords)
        result.update(keyword_score=kscore, matched=matched, missing=missing)
    return result
