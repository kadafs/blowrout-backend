import os
import json
from collections import Counter

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'basketball')

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
        STOP_WORDS = {'de', 'del', 'la', 'le', 'los', 'las', 'el', 'en', 'of', 'and',
                      'the', 'bc', 'bk', 'sk', 'fc', 'ac', 'sc', 'club', 'basket',
                      'basketball', 'sport', 'sports'}

        teams = data.get('teams', [])
        first_word_counts = Counter(t['team'].lower().split()[0] for t in teams if t.get('team'))
        unique_first_words = {w for w, count in first_word_counts.items() if count == 1}

        word_counts = Counter()
        for t in teams:
            full_key = t['team'].lower()
            for word in full_key.split():
                if len(word) >= 4 and word not in STOP_WORDS:
                    word_counts[word] += 1
        unique_words = {w for w, count in word_counts.items() if count == 1}

        for t in teams:
            full_key = t['team'].lower()
            index[full_key] = t
            words = full_key.split()

            first_word = words[0]
            if first_word in unique_first_words and first_word not in index:
                index[first_word] = t

            for word in words:
                if len(word) >= 4 and word not in STOP_WORDS and word in unique_words:
                    if word not in index:
                        index[word] = t

        return index
    except Exception:
        return {}

def get_sdi_record(team_name, sdi_index):
    """
    Retrieve SDI record for a team using full name or unique keyword matching.
    """
    if not team_name or not sdi_index:
        return None
    t_lower = team_name.lower().strip()

    rec = sdi_index.get(t_lower)
    if rec:
        return rec

    words = t_lower.split()
    if t_lower.endswith(' w') or t_lower.endswith(' (w)'):
        rec = sdi_index.get(words[0] + ' w')
        if rec:
            return rec

    if len(words) == 1:
        rec = sdi_index.get(words[0])

    return rec
