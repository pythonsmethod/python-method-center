# -*- coding: utf-8 -*-
# normalization_module.py - Phase 5.1 Canonical Analysis Normalization Layer
# Deterministic, auditable, medically-safe normalization of OCR-extracted biomarker data.
# NO diagnosis. NO interpretation. NO AI inference. Pure structural normalization.
#
# Pipeline position:
#   upload → OCR → extraction → [THIS MODULE] → continuity → escalation
#
# Output schema per biomarker:
# {
#   "canonical_name": str,      # stable snake_case key
#   "original_name": str,       # raw string as seen in OCR
#   "value": float | None,      # parsed numeric value
#   "unit": str | None,         # unified SI/standard unit string
#   "reference_range": {        # parsed reference range
#     "min": float | None,
#     "max": float | None,
#     "text": str               # original range text preserved
#   },
#   "date": str | None,         # ISO 8601: YYYY-MM-DD
#   "source_upload_id": str,    # upload identifier for multi-upload reconciliation
#   "confidence": float         # 0.0-1.0 normalization confidence score
# }

import re
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

log = logging.getLogger('normalization_module')

# ============================================================
# VERSION
# ============================================================
NORMALIZATION_VERSION = '5.1.0'

# ============================================================
# CANONICAL BIOMARKER MAP
# Maps every known alias → canonical snake_case key
# Sources: Russian clinical lab forms, international standard names,
# common OCR variants, abbreviations.
# ============================================================

BIOMARKER_ALIASES: Dict[str, str] = {
    # ─── C-Reactive Protein ───
    'crp':                          'c_reactive_protein',
    'с-реактивный белок':           'c_reactive_protein',
    'с реактивный белок':           'c_reactive_protein',
    'срб':                          'c_reactive_protein',
    'c-reactive protein':           'c_reactive_protein',
    'c reactive protein':           'c_reactive_protein',
    'hs-crp':                       'c_reactive_protein_high_sensitivity',
    'hscrp':                        'c_reactive_protein_high_sensitivity',
    'high-sensitivity crp':         'c_reactive_protein_high_sensitivity',
    'high sensitivity crp':         'c_reactive_protein_high_sensitivity',
    'вч-срб':                       'c_reactive_protein_high_sensitivity',
    'вч срб':                       'c_reactive_protein_high_sensitivity',

    # ─── Hemoglobin ───
    'hb':                           'hemoglobin',
    'hgb':                          'hemoglobin',
    'гемоглобин':                   'hemoglobin',
    'hemoglobin':                   'hemoglobin',

    # ─── Glycated Hemoglobin ───
    'hba1c':                        'hba1c',
    'hb a1c':                       'hba1c',
    'glycated hemoglobin':          'hba1c',
    'glycosylated hemoglobin':      'hba1c',
    'гликированный гемоглобин':     'hba1c',
    'гликозилированный гемоглобин': 'hba1c',

    # ─── Leukocytes / WBC ───
    'wbc':                          'leukocytes',
    'white blood cells':            'leukocytes',
    'white blood count':            'leukocytes',
    'лейкоциты':                    'leukocytes',
    'leukocytes':                   'leukocytes',
    'лейк':                         'leukocytes',

    # ─── Erythrocytes / RBC ───
    'rbc':                          'erythrocytes',
    'red blood cells':              'erythrocytes',
    'red blood count':              'erythrocytes',
    'эритроциты':                   'erythrocytes',
    'erythrocytes':                 'erythrocytes',
    'эр':                           'erythrocytes',

    # ─── Platelets ───
    'plt':                          'platelets',
    'thrombocytes':                 'platelets',
    'тромбоциты':                   'platelets',
    'platelets':                    'platelets',

    # ─── Glucose ───
    'glucose':                      'glucose',
    'глюкоза':                      'glucose',
    'сахар':                        'glucose',
    'glu':                          'glucose',
    'blood sugar':                  'glucose',

    # ─── Cholesterol ───
    'total cholesterol':            'cholesterol_total',
    'cholesterol':                  'cholesterol_total',
    'общий холестерин':             'cholesterol_total',
    'холестерин':                   'cholesterol_total',
    'chol':                         'cholesterol_total',

    # ─── LDL ───
    'ldl':                          'cholesterol_ldl',
    'ldl cholesterol':              'cholesterol_ldl',
    'ldl-c':                        'cholesterol_ldl',
    'лпнп':                         'cholesterol_ldl',
    'холестерин лпнп':              'cholesterol_ldl',

    # ─── HDL ───
    'hdl':                          'cholesterol_hdl',
    'hdl cholesterol':              'cholesterol_hdl',
    'hdl-c':                        'cholesterol_hdl',
    'лпвп':                         'cholesterol_hdl',
    'холестерин лпвп':              'cholesterol_hdl',

    # ─── Triglycerides ───
    'triglycerides':                'triglycerides',
    'trig':                         'triglycerides',
    'tg':                           'triglycerides',
    'триглицериды':                 'triglycerides',
    'тг':                           'triglycerides',

    # ─── ALT (Alanine Aminotransferase) ───
    'alt':                          'alt',
    'alat':                         'alt',
    'аланинаминотрансфераза':       'alt',
    'алат':                         'alt',
    'alanine aminotransferase':     'alt',
    'alanine transaminase':         'alt',

    # ─── AST (Aspartate Aminotransferase) ───
    'ast':                          'ast',
    'asat':                         'ast',
    'аспартатаминотрансфераза':     'ast',
    'асат':                         'ast',
    'aspartate aminotransferase':   'ast',
    'aspartate transaminase':       'ast',

    # ─── Creatinine ───
    'creatinine':                   'creatinine',
    'cr':                           'creatinine',
    'креатинин':                    'creatinine',
    'crea':                         'creatinine',

    # ─── Urea / BUN ───
    'urea':                         'urea',
    'bun':                          'urea',
    'мочевина':                     'urea',
    'blood urea nitrogen':          'urea',

    # ─── Uric Acid ───
    'uric acid':                    'uric_acid',
    'мочевая кислота':              'uric_acid',
    'ua':                           'uric_acid',

    # ─── Bilirubin ───
    'total bilirubin':              'bilirubin_total',
    'bilirubin total':              'bilirubin_total',
    'общий билирубин':              'bilirubin_total',
    'билирубин общий':              'bilirubin_total',
    'direct bilirubin':             'bilirubin_direct',
    'bilirubin direct':             'bilirubin_direct',
    'прямой билирубин':             'bilirubin_direct',
    'билирубин прямой':             'bilirubin_direct',

    # ─── Ferritin ───
    'ferritin':                     'ferritin',
    'ферритин':                     'ferritin',

    # ─── Iron ───
    'iron':                         'iron',
    'serum iron':                   'iron',
    'железо':                       'iron',
    'железо сывороточное':          'iron',
    'fe':                           'iron',

    # ─── Vitamin D ───
    'vitamin d':                    'vitamin_d',
    'vitamin d3':                   'vitamin_d',
    '25-oh vitamin d':              'vitamin_d',
    '25-hydroxyvitamin d':          'vitamin_d',
    'витамин д':                    'vitamin_d',
    'витамин d':                    'vitamin_d',
    '25(oh)d':                      'vitamin_d',

    # ─── Vitamin B12 ───
    'vitamin b12':                  'vitamin_b12',
    'b12':                          'vitamin_b12',
    'cobalamin':                    'vitamin_b12',
    'витамин б12':                  'vitamin_b12',
    'витамин b12':                  'vitamin_b12',
    'цианокобаламин':               'vitamin_b12',

    # ─── Thyroid (TSH) ───
    'tsh':                          'tsh',
    'thyroid stimulating hormone':  'tsh',
    'тиреотропный гормон':          'tsh',
    'ттг':                          'tsh',

    # ─── Thyroid (T4 free) ───
    'free t4':                      't4_free',
    'ft4':                          't4_free',
    't4 free':                      't4_free',
    'свободный т4':                 't4_free',
    'т4 свободный':                 't4_free',

    # ─── PSA ───
    'psa':                          'psa',
    'prostate specific antigen':    'psa',
    'пса':                          'psa',

    # ─── CEA (Carcinoembryonic Antigen) ───
    'cea':                          'cea',
    'carcinoembryonic antigen':     'cea',
    'рэа':                          'cea',
    'раково-эмбриональный антиген': 'cea',

    # ─── CA 125 ───
    'ca 125':                       'ca_125',
    'ca-125':                       'ca_125',
    'ca125':                        'ca_125',

    # ─── CA 19-9 ───
    'ca 19-9':                      'ca_19_9',
    'ca-19-9':                      'ca_19_9',
    'ca19-9':                       'ca_19_9',
    'ca199':                        'ca_19_9',

    # ─── AFP ───
    'afp':                          'afp',
    'alpha-fetoprotein':            'afp',
    'альфа-фетопротеин':            'afp',
    'афп':                          'afp',

    # ─── INR / Prothrombin ───
    'inr':                          'inr',
    'мно':                          'inr',
    'prothrombin':                  'prothrombin_time',
    'протромбин':                   'prothrombin_time',
    'pt':                           'prothrombin_time',

    # ─── ESR (Erythrocyte Sedimentation Rate) ───
    'esr':                          'esr',
    'сое':                          'esr',
    'соэ':                          'esr',
    'erythrocyte sedimentation rate': 'esr',
    'sed rate':                     'esr',

    # ─── Lymphocytes ───
    'lymphocytes':                  'lymphocytes',
    'лимфоциты':                    'lymphocytes',
    'lymphs':                       'lymphocytes',

    # ─── Neutrophils ───
    'neutrophils':                  'neutrophils',
    'нейтрофилы':                   'neutrophils',
    'neut':                         'neutrophils',

    # ─── Albumin ───
    'albumin':                      'albumin',
    'альбумин':                     'albumin',
    'alb':                          'albumin',

    # ─── Total Protein ───
    'total protein':                'protein_total',
    'protein total':                'protein_total',
    'общий белок':                  'protein_total',
    'белок общий':                  'protein_total',
}

# ============================================================
# UNIT NORMALIZATION MAP
# Maps raw OCR unit strings → canonical unit
# ============================================================

UNIT_ALIASES: Dict[str, str] = {
    # Concentration — mass/volume
    'mg/l':     'mg/L',
    'мг/л':     'mg/L',
    'mg per l': 'mg/L',
    'mg/dl':    'mg/dL',
    'мг/дл':    'mg/dL',
    'mg per dl':'mg/dL',
    'g/l':      'g/L',
    'г/л':      'g/L',
    'g/dl':     'g/dL',
    'г/дл':     'g/dL',
    'ug/l':     'µg/L',
    'мкг/л':    'µg/L',
    'ng/ml':    'ng/mL',
    'нг/мл':    'ng/mL',
    'pg/ml':    'pg/mL',
    'пг/мл':    'pg/mL',
    'ug/ml':    'µg/mL',
    'мкг/мл':   'µg/mL',
    'nmol/l':   'nmol/L',
    'нмоль/л':  'nmol/L',
    'pmol/l':   'pmol/L',
    'пмоль/л':  'pmol/L',
    'umol/l':   'µmol/L',
    'мкмоль/л': 'µmol/L',
    'mmol/l':   'mmol/L',
    'ммоль/л':  'mmol/L',
    'iu/l':     'IU/L',
    'ед/л':     'IU/L',
    'u/l':      'IU/L',
    'ме/л':     'IU/L',
    'iu/ml':    'IU/mL',
    'ед/мл':    'IU/mL',
    'me/ml':    'IU/mL',
    # Cell counts
    '10^9/l':   '10⁹/L',
    '10^9/л':   '10⁹/L',
    'x10^9/l':  '10⁹/L',
    '10е9/л':   '10⁹/L',
    '*10^9/l':  '10⁹/L',
    '10^12/l':  '10¹²/L',
    '10^12/л':  '10¹²/L',
    'x10^12/l': '10¹²/L',
    # Percentage
    '%':        '%',
    'процент':  '%',
    # Time
    'mm/hr':    'mm/h',
    'мм/ч':     'mm/h',
    'mm/h':     'mm/h',
    'sec':      's',
    'с':        's',
    's':        's',
    # Other
    'miu/ml':   'mIU/mL',
    'мме/мл':   'mIU/mL',
    'u/ml':     'IU/mL',
}

# ============================================================
# DATE NORMALIZATION
# Converts all date formats → ISO 8601 (YYYY-MM-DD)
# ============================================================

# Month name maps (Russian + English)
_MONTH_MAP: Dict[str, int] = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'june': 6, 'july': 7, 'august': 8, 'september': 9,
    'october': 10, 'november': 11, 'december': 12,
    'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4,
    'май': 5, 'июн': 6, 'июл': 7, 'авг': 8,
    'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12,
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
    'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
    'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
}


def normalize_date(raw: str) -> Optional[str]:
    """
    Convert any date string to ISO 8601 (YYYY-MM-DD).
    Returns None if parsing fails.
    Handles: DD.MM.YYYY, DD/MM/YY, MM/DD/YY, YYYY-MM-DD,
             "01 мая 2026", "May 1, 2026", "2-digit year" expansion.
    """
    if not raw:
        return None
    raw = raw.strip()

    # Already ISO
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', raw)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime('%Y-%m-%d')
        except ValueError:
            pass

    # DD.MM.YYYY or DD.MM.YY
    m = re.match(r'^(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})$', raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y = 2000 + y if y <= 50 else 1900 + y
        try:
            return datetime(y, mo, d).strftime('%Y-%m-%d')
        except ValueError:
            pass

    # "01 мая 2026" or "May 1, 2026" or "1 May 2026"
    m = re.match(
        r'^(\d{1,2})\s+([а-яёa-z]+)\.?\s+(\d{4})$',
        raw.lower(), re.IGNORECASE
    )
    if m:
        d = int(m.group(1))
        month_str = m.group(2).lower()
        y = int(m.group(3))
        mo = _MONTH_MAP.get(month_str)
        if mo:
            try:
                return datetime(y, mo, d).strftime('%Y-%m-%d')
            except ValueError:
                pass

    # "May 1, 2026" or "May 01 2026"
    m = re.match(
        r'^([а-яёa-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})$',
        raw.lower(), re.IGNORECASE
    )
    if m:
        month_str = m.group(1).lower()
        d = int(m.group(2))
        y = int(m.group(3))
        mo = _MONTH_MAP.get(month_str)
        if mo:
            try:
                return datetime(y, mo, d).strftime('%Y-%m-%d')
            except ValueError:
                pass

    return None


# ============================================================
# VALUE NORMALIZATION
# Parses numeric values from OCR strings
# ============================================================

def normalize_value(raw: str) -> Optional[float]:
    """
    Parse numeric value from OCR string.
    Handles: "7,2" "7.2" "~7.2" "<7.2" ">7.2" "7.2*" "7 2" "7,200"
    Returns None if no valid number found.
    """
    if not raw:
        return None
    raw = str(raw).strip()
    # Remove non-numeric prefixes/suffixes but keep decimal separators
    cleaned = re.sub(r'[~<>*!↑↓H\s]', '', raw)
    # Replace comma decimal separator (European format) with dot
    # But only if comma is used as decimal (not thousands): "7,2" → "7.2"
    # "7,200" → "7200" (thousands separator)
    if re.match(r'^\d+,\d{1,2}$', cleaned):
        cleaned = cleaned.replace(',', '.')
    else:
        cleaned = cleaned.replace(',', '')
    # Extract first valid float/int
    m = re.search(r'\d+\.?\d*', cleaned)
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            pass
    return None


# ============================================================
# UNIT NORMALIZATION
# ============================================================

def normalize_unit(raw: str) -> Optional[str]:
    """
    Normalize unit string to canonical form.
    Returns canonical unit or raw (lowercased) if not found in map.
    """
    if not raw:
        return None
    key = raw.strip().lower()
    return UNIT_ALIASES.get(key, raw.strip() or None)


# ============================================================
# REFERENCE RANGE NORMALIZATION
# ============================================================

def normalize_reference_range(raw: str) -> Dict[str, Any]:
    """
    Parse reference range from OCR string.
    Input formats:
      "0-5"      → {min: 0, max: 5}
      "<5"       → {min: None, max: 5}
      ">0.5"     → {min: 0.5, max: None}
      "0.0-5.0"  → {min: 0.0, max: 5.0}
      "normal under 5" → {min: None, max: 5}
      "до 5"     → {min: None, max: 5}
      "от 0 до 5" → {min: 0, max: 5}
    Always preserves original text.
    """
    result: Dict[str, Any] = {'min': None, 'max': None, 'text': (raw or '').strip()}
    if not raw:
        return result

    r = raw.strip().lower()

    # "X-Y" or "X–Y" range
    m = re.match(r'^([\d.,]+)\s*[-–—]\s*([\d.,]+)$', r)
    if m:
        result['min'] = normalize_value(m.group(1))
        result['max'] = normalize_value(m.group(2))
        return result

    # "<X" or "до X" or "normal under X" (upper bound only)
    m = re.match(r'^[<≤]?\s*(?:до|under|less than|не более|below)?\s*([\d.,]+)$', r)
    if m and ('до' in r or '<' in raw or 'under' in r or 'less' in r or 'не более' in r or 'below' in r):
        result['max'] = normalize_value(m.group(1))
        return result
    # standalone upper bound "<5"
    m2 = re.match(r'^[<≤]([\d.,]+)$', raw.strip())
    if m2:
        result['max'] = normalize_value(m2.group(1))
        return result

    # ">X" or "от X" (lower bound only)
    m = re.match(r'^[>≥]?\s*(?:от|more than|более|above)?\s*([\d.,]+)$', r)
    if m and ('>' in raw or 'от' in r or 'more' in r or 'более' in r or 'above' in r):
        result['min'] = normalize_value(m.group(1))
        return result
    m2 = re.match(r'^[>≥]([\d.,]+)$', raw.strip())
    if m2:
        result['min'] = normalize_value(m2.group(1))
        return result

    # "от X до Y"
    m = re.match(r'от\s*([\d.,]+)\s*до\s*([\d.,]+)', r)
    if m:
        result['min'] = normalize_value(m.group(1))
        result['max'] = normalize_value(m.group(2))
        return result

    # "X to Y"
    m = re.match(r'([\d.,]+)\s+to\s+([\d.,]+)', r)
    if m:
        result['min'] = normalize_value(m.group(1))
        result['max'] = normalize_value(m.group(2))
        return result

    return result


# ============================================================
# BIOMARKER NAME NORMALIZATION
# ============================================================

def normalize_biomarker_name(raw: str) -> Dict[str, Any]:
    """
    Map raw OCR biomarker name to canonical form.
    Returns: {canonical_name: str, original_name: str, confidence: float}
    """
    if not raw:
        return {'canonical_name': None, 'original_name': raw, 'confidence': 0.0}

    original = raw.strip()
    key = original.lower().strip()

    # Direct lookup
    canonical = BIOMARKER_ALIASES.get(key)
    if canonical:
        return {'canonical_name': canonical, 'original_name': original, 'confidence': 1.0}

    # Fuzzy: try removing punctuation and extra spaces
    key_clean = re.sub(r'[\s\-\.]+', ' ', key).strip()
    canonical = BIOMARKER_ALIASES.get(key_clean)
    if canonical:
        return {'canonical_name': canonical, 'original_name': original, 'confidence': 0.95}

    # Partial: check if any known alias is a substring match
    for alias, canon in BIOMARKER_ALIASES.items():
        if alias in key_clean or key_clean in alias:
            if len(alias) >= 3:
                return {'canonical_name': canon, 'original_name': original, 'confidence': 0.70}

    # Unknown: return snake_case conversion of raw
    fallback = re.sub(r'[^a-zа-яё0-9]+', '_', key_clean, flags=re.IGNORECASE).strip('_')
    return {'canonical_name': fallback or 'unknown', 'original_name': original, 'confidence': 0.30}


# ============================================================
# LINE-LEVEL BIOMARKER EXTRACTION
# Parses individual lines from OCR text
# ============================================================

# Patterns for biomarker line extraction
# Typical formats:
# "Гемоглобин    140    г/л    120-160"
# "CRP: 7.2 mg/L (ref: 0-5)"
# "Hemoglobin 14.0 g/dL 12.0-16.0"
_BIOMARKER_LINE_PATTERNS = [
    # "Name: value unit ref"
    re.compile(
        r'^(?P<name>[A-Za-zА-Яа-яёЁ][\w\s\-\.()]{1,50}?)'
        r'[:\s]+(?P<value>[~<>≤≥]?[\d,\.]+[*↑↓H]?)'
        r'(?:\s+(?P<unit>[a-zA-Zµ%/\^0-9⁹¹²]+))?'
        r'(?:[\s(ref:)*(Ref)*(норма)*(нормa)]*(?P<ref>[\d.,]+\s*[-–—to]\s*[\d.,]+|[<>≤≥][\d.,]+|до\s+[\d.,]+))?',
        re.IGNORECASE
    ),
]


def extract_biomarkers_from_text(
    ocr_text: str,
    source_upload_id: str = '',
    upload_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Extract and normalize all biomarker readings from raw OCR text.
    
    Returns list of normalized biomarker dicts conforming to the canonical schema.
    Safe: never raises, always returns list (may be empty).
    Never interprets values — only structures them.
    """
    results: List[Dict[str, Any]] = []
    if not ocr_text:
        return results

    lines = ocr_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        for pattern in _BIOMARKER_LINE_PATTERNS:
            try:
                m = pattern.match(line)
                if not m:
                    continue

                raw_name  = (m.group('name') or '').strip()
                raw_value = (m.group('value') or '').strip()
                raw_unit  = m.lastindex and m.groupdict().get('unit') or ''
                raw_ref   = m.lastindex and m.groupdict().get('ref') or ''

                if not raw_name or not raw_value:
                    continue

                name_result = normalize_biomarker_name(raw_name)
                if name_result['confidence'] < 0.30:
                    # Too uncertain to include — skip
                    continue

                parsed_value = normalize_value(raw_value)
                if parsed_value is None:
                    continue

                ref_range = normalize_reference_range(raw_ref or '')
                unit = normalize_unit(raw_unit or '')

                # Confidence: combine name confidence with parse success indicators
                confidence = round(
                    name_result['confidence'] *
                    (0.9 if unit else 0.7) *
                    (0.95 if ref_range['min'] is not None or ref_range['max'] is not None else 0.8),
                    3
                )

                entry: Dict[str, Any] = {
                    'canonical_name':   name_result['canonical_name'],
                    'original_name':    name_result['original_name'],
                    'value':            parsed_value,
                    'unit':             unit,
                    'reference_range':  ref_range,
                    'date':             upload_date or datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    'source_upload_id': source_upload_id,
                    'confidence':       confidence,
                }
                results.append(entry)
                break  # one match per line is sufficient

            except Exception as exc:
                log.warning('[NORM] line_parse_error line=%.60s err=%s', line, exc)
                continue

    log.info('[NORM] extract_complete upload_id=%s lines=%d biomarkers=%d',
             source_upload_id, len(lines), len(results))
    return results


# ============================================================
# UPLOAD DATE EXTRACTION
# Tries to find a date in the OCR text header area
# ============================================================

def extract_upload_date(ocr_text: str) -> Optional[str]:
    """
    Scan the first 500 chars of OCR text for a recognizable date.
    Returns ISO 8601 date string or None.
    """
    if not ocr_text:
        return None
    header = ocr_text[:500]

    # ISO dates
    m = re.search(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', header)
    if m:
        result = normalize_date(m.group(0))
        if result:
            return result

    # DD.MM.YYYY
    m = re.search(r'\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b', header)
    if m:
        result = normalize_date(m.group(0))
        if result:
            return result

    # Verbal dates
    m = re.search(
        r'\b(\d{1,2})\s+([а-яёa-z]{3,12})\.?\s+(\d{4})\b',
        header, re.IGNORECASE
    )
    if m:
        result = normalize_date(m.group(0))
        if result:
            return result

    return None


# ============================================================
# MULTI-UPLOAD RECONCILIATION
# Merges biomarkers from multiple uploads by canonical_name + date
# ============================================================

def reconcile_biomarker_uploads(
    uploads: List[List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """
    Merge biomarker lists from multiple uploads.
    For same canonical_name + date: keep entry with highest confidence.
    Produces a deduplicated, date-sorted list.

    Input: list of biomarker lists (one per upload)
    Output: merged, deduplicated, sorted list
    """
    merged: Dict[str, Dict[str, Any]] = {}

    for upload_list in uploads:
        for entry in upload_list:
            key = f"{entry.get('canonical_name', 'unknown')}|{entry.get('date', 'unknown')}"
            existing = merged.get(key)
            if existing is None or entry.get('confidence', 0) > existing.get('confidence', 0):
                merged[key] = entry

    result = list(merged.values())
    # Sort by date descending, then by canonical_name
    result.sort(key=lambda x: (x.get('date') or '', x.get('canonical_name') or ''))
    return result


# ============================================================
# MAIN PUBLIC API
# ============================================================

def normalize_ocr_result(
    ocr_result: dict,
    source_upload_id: str = '',
) -> Dict[str, Any]:
    """
    Top-level normalization entry point.
    Takes raw ocr_result dict from image_pipeline.extract_content()
    Returns enriched normalization package added to the existing dict.

    Input: ocr_result = {text, confidence, success, ...}
    Output: ocr_result with added 'normalized' key:
    {
        'normalized': {
            'version': str,
            'biomarkers': [...],     # list of canonical biomarker dicts
            'upload_date': str|None, # extracted date from OCR text
            'biomarker_count': int,
            'normalization_ok': bool,
        }
    }

    SAFE: never raises. Failures are logged and 'normalization_ok' = False.
    """
    result_package: Dict[str, Any] = {
        'version': NORMALIZATION_VERSION,
        'biomarkers': [],
        'upload_date': None,
        'biomarker_count': 0,
        'normalization_ok': False,
    }

    try:
        ocr_text = ocr_result.get('text', '') or ''
        if not ocr_text.strip():
            log.info('[NORM] normalize_skipped reason=empty_text upload_id=%s', source_upload_id)
            ocr_result['normalized'] = result_package
            return ocr_result

        upload_date = extract_upload_date(ocr_text)
        biomarkers  = extract_biomarkers_from_text(
            ocr_text=ocr_text,
            source_upload_id=source_upload_id,
            upload_date=upload_date,
        )

        result_package.update({
            'biomarkers':      biomarkers,
            'upload_date':     upload_date,
            'biomarker_count': len(biomarkers),
            'normalization_ok': True,
        })

        log.info('[NORM] normalize_complete upload_id=%s date=%s biomarkers=%d',
                 source_upload_id, upload_date, len(biomarkers))

    except Exception as exc:
        log.error('[NORM] normalize_error upload_id=%s err=%s', source_upload_id, exc)
        result_package['normalization_ok'] = False

    ocr_result['normalized'] = result_package
    return ocr_result


# ============================================================
# CHRONOLOGY VERSION
# ============================================================
CHRONOLOGY_VERSION = '5.1.2'

# ============================================================
# CHRONOLOGY MERGE — Phase 5.1 Step 2
# Merges multiple upload biomarker lists into a structured
# chronological patient analysis timeline.
# Deterministic. Auditable. No diagnosis. No AI inference.
# ============================================================


def build_chronology(
    normalized_uploads_history: List[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """
    Merge multiple upload biomarker lists into one structured chronological timeline.

    Input:
        normalized_uploads_history: list of biomarker lists.
            Each inner list = normalized['biomarkers'] from one upload session.

    Output schema:
    {
        "chronology_version": str,
        "uploads_count": int,
        "biomarkers_count": int,
        "dates": [
            {
                "date": str | None,
                "source_upload_ids": [str],
                "biomarkers": [...]
            }
        ],
        "repeated_biomarkers": {
            "canonical_name": [
                {"date": str, "value": float|None, "unit": str|None,
                 "source_upload_id": str, "confidence": float|None}
            ]
        },
        "missing_dates": [str],
        "low_confidence_items": [...]
    }

    SAFE: never raises. Failures are logged and empty structure returned.
    """
    chronology: Dict[str, Any] = {
        'chronology_version': CHRONOLOGY_VERSION,
        'uploads_count': 0,
        'biomarkers_count': 0,
        'dates': [],
        'repeated_biomarkers': {},
        'missing_dates': [],
        'low_confidence_items': [],
    }

    try:
        if not normalized_uploads_history:
            log.info('[CHRONOLOGY] build_chronology called with empty uploads history')
            return chronology

        upload_count = len(normalized_uploads_history)
        chronology['uploads_count'] = upload_count
        log.info('[CHRONOLOGY] build_chronology start uploads=%d', upload_count)

        # Step 1: Flatten all biomarkers from all uploads
        all_biomarkers: List[Dict[str, Any]] = []
        for upload_list in normalized_uploads_history:
            if isinstance(upload_list, list):
                all_biomarkers.extend(upload_list)

        chronology['biomarkers_count'] = len(all_biomarkers)

        # Step 2: Collect low-confidence items (confidence < 0.7)
        LOW_CONFIDENCE_THRESHOLD = 0.7
        chronology['low_confidence_items'] = [
            b for b in all_biomarkers
            if (b.get('confidence') or 0) < LOW_CONFIDENCE_THRESHOLD
        ]

        # Step 3: Collect source_upload_ids where date could not be extracted
        missing_upload_ids: set = set()
        for b in all_biomarkers:
            if not b.get('date'):
                sid = b.get('source_upload_id', '')
                if sid:
                    missing_upload_ids.add(sid)
        chronology['missing_dates'] = sorted(missing_upload_ids)

        # Step 4: Group biomarkers by date key
        date_groups: Dict[str, List[Dict[str, Any]]] = {}
        date_upload_ids: Dict[str, set] = {}

        for b in all_biomarkers:
            date_key = b.get('date') or '__no_date__'
            if date_key not in date_groups:
                date_groups[date_key] = []
                date_upload_ids[date_key] = set()
            date_groups[date_key].append(b)
            sid = b.get('source_upload_id', '')
            if sid:
                date_upload_ids[date_key].add(sid)

        # Step 5: Within each date group, deduplicate by canonical_name
        # Same canonical_name + date → keep highest confidence entry
        def _dedup_by_name(
            biomarker_list: List[Dict[str, Any]],
        ) -> List[Dict[str, Any]]:
            best: Dict[str, Dict[str, Any]] = {}
            for b in biomarker_list:
                name = b.get('canonical_name', 'unknown')
                existing_conf = best[name].get('confidence', 0) if name in best else -1
                if existing_conf < (b.get('confidence') or 0):
                    best[name] = b
            return sorted(
                best.values(),
                key=lambda x: x.get('canonical_name') or '',
            )

        # Step 6: Build sorted dates list (known dates asc, then unknowns)
        sorted_date_keys = sorted(
            date_groups.keys(),
            key=lambda d: (d == '__no_date__', d),
        )

        dates_list = []
        for date_key in sorted_date_keys:
            biomarkers_for_date = _dedup_by_name(date_groups[date_key])
            upload_ids_for_date = sorted(date_upload_ids.get(date_key, set()))
            dates_list.append({
                'date': date_key if date_key != '__no_date__' else None,
                'source_upload_ids': upload_ids_for_date,
                'biomarkers': biomarkers_for_date,
            })

        chronology['dates'] = dates_list

        # Step 7: Build repeated_biomarkers map
        # Canonical names that appear across multiple date entries → repeated
        name_appearances: Dict[str, List[Dict[str, Any]]] = {}
        for date_entry in dates_list:
            for b in date_entry['biomarkers']:
                cname = b.get('canonical_name', 'unknown')
                if cname not in name_appearances:
                    name_appearances[cname] = []
                name_appearances[cname].append({
                    'date': b.get('date'),
                    'value': b.get('value'),
                    'unit': b.get('unit'),
                    'source_upload_id': b.get('source_upload_id', ''),
                    'confidence': b.get('confidence'),
                })

        # Only include names that appear more than once (tracked across dates)
        chronology['repeated_biomarkers'] = {
            cname: appearances
            for cname, appearances in name_appearances.items()
            if len(appearances) > 1
        }

        log.info(
            '[CHRONOLOGY] build_chronology complete '
            'dates=%d biomarkers=%d repeated=%d low_conf=%d missing_date_uploads=%d',
            len(dates_list),
            chronology['biomarkers_count'],
            len(chronology['repeated_biomarkers']),
            len(chronology['low_confidence_items']),
            len(chronology['missing_dates']),
        )

    except Exception as e:
        log.error('[CHRONOLOGY] build_chronology failed: %s', e, exc_info=True)

    return chronology
