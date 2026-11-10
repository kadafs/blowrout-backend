import os
import json
import re
from collections import Counter

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'basketball')

def normalize_name(name):
    if not name:
        return ""
    n = name.lower().strip()
    # Normalize Roman numerals to Arabic digits
    n = re.sub(r'\bii\b', '2', n)
    n = re.sub(r'\biii\b', '3', n)
    n = re.sub(r'\biv\b', '4', n)
    n = re.sub(r'\bi\b', '1', n)
    # Remove punctuation
    n = re.sub(r'[.,/()\'"\[\]]', ' ', n)
    return ' '.join(n.split())

def generate_team_keys(team_name):
    keys = set()
    raw = team_name.lower().strip()
    keys.add(raw)
    
    norm = normalize_name(raw)
    keys.add(norm)
    
    # Roman numeral equivalents
    r2 = re.sub(r'\b2\b', 'ii', norm)
    keys.add(r2)
    r3 = re.sub(r'\b3\b', 'iii', norm)
    keys.add(r3)
    
    # Hyphenated variants (e.g. "Jurbarkas-Karys" -> "jurbarkas", "jurbarkas karys")
    if '-' in raw:
        parts = raw.split('-')
        p0 = parts[0].strip()
        keys.add(p0)
        keys.add(normalize_name(p0))
        keys.add(' '.join(parts).strip())
        keys.add(normalize_name(' '.join(parts).strip()))
        
    # Strip common suffixes/prefixes
    tokens = norm.split()
    STOP_WORDS = {'bc', 'bk', 'sk', 'fc', 'ac', 'sc', 'club', 'basket', 'basketball', 'w', '(w)', 'women'}
    cleaned_tokens = [w for w in tokens if w not in STOP_WORDS]
    if cleaned_tokens:
        keys.add(' '.join(cleaned_tokens))
        
    return keys

def load_sdi_index(custom_path=None):
    """
    Load Star Dependency Index (SDI) team records into a normalized lookup index.
    """
    sdi_path = custom_path or os.path.join(DATA_DIR, 'team_sdi.json')
    if not os.path.exists(sdi_path):
        alt_path = os.path.join(os.path.dirname(DATA_DIR), 'team_sdi.json')
        if os.path.exists(alt_path):
            sdi_path = alt_path
        else:
            return {}
    try:
        with open(sdi_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        index = {}
        teams = data.get('teams', [])

        # Build index mapping multiple variants to each team
        for t in teams:
            t_name = t.get('team', '')
            if not t_name:
                continue
            for k in generate_team_keys(t_name):
                if k not in index:
                    index[k] = t

        # Index 2-word phrases (bigrams) that uniquely identify a team
        bigram_counts = Counter()
        for t in teams:
            t_name = t.get('team', '')
            norm = normalize_name(t_name)
            words = norm.split()
            for i in range(len(words) - 1):
                bg = f"{words[i]} {words[i+1]}"
                bigram_counts[bg] += 1
        unique_bigrams = {bg for bg, count in bigram_counts.items() if count == 1}
        for t in teams:
            t_name = t.get('team', '')
            norm = normalize_name(t_name)
            words = norm.split()
            for i in range(len(words) - 1):
                bg = f"{words[i]} {words[i+1]}"
                if bg in unique_bigrams and bg not in index:
                    index[bg] = t

        # Also index unique single words (>= 5 chars) if they only appear in 1 team
        word_counts = Counter()
        for t in teams:
            t_name = t.get('team', '')
            norm = normalize_name(t_name)
            for w in norm.split():
                if len(w) >= 5 and w not in {'basket', 'basketball', 'athletic', 'united', 'sport', 'sports'}:
                    word_counts[w] += 1
                    
        unique_words = {w for w, count in word_counts.items() if count == 1}
        for t in teams:
            t_name = t.get('team', '')
            norm = normalize_name(t_name)
            for w in norm.split():
                if w in unique_words and w not in index:
                    index[w] = t

        return index
    except Exception:
        return {}

def get_sdi_record(team_name, sdi_index):
    """
    Retrieve SDI record for a team using normalized variants or unique keyword/bigram matching.
    """
    if not team_name or not sdi_index:
        return None
        
    for k in generate_team_keys(team_name):
        if k in sdi_index:
            rec = sdi_index[k]
            # Guard against single-word key matching a multi-word foreign team (e.g. "brescia" -> "Germani Brescia")
            rec_words = [w for w in normalize_name(rec.get("team", "")).split() 
                         if w not in {'bc', 'bk', 'sk', 'fc', 'ac', 'sc', 'club', 'basket', 'basketball', 'w', 'women'}]
            if len(k.split()) == 1 and len(rec_words) > 1 and k != rec_words[0]:
                continue
            return rec

    # Try unique bigram (2-word) matching
    norm = normalize_name(team_name)
    words = norm.split()
    for i in range(len(words) - 1):
        bg = f"{words[i]} {words[i+1]}"
        if bg in sdi_index:
            return sdi_index[bg]

    # Try unique significant word lookup ONLY if input has multiple words
    # (prevents single-word college/city names like 'Brescia' from grabbing foreign multi-word pro teams like 'Germani Brescia')
    if len(words) > 1:
        for w in words:
            if len(w) >= 5 and w in sdi_index:
                rec = sdi_index[w]
                rec_words = [x for x in normalize_name(rec.get("team", "")).split() 
                             if x not in {'bc', 'bk', 'sk', 'fc', 'ac', 'sc', 'club', 'basket', 'basketball', 'w', 'women'}]
                if set(words) & set(rec_words):
                    return rec

    return None
