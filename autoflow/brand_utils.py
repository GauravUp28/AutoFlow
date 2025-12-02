import re

STOP_WORDS = {
    'create','make','build','setup','set','sign','signup','sign-up','signin','login','log','download','install','open','go','to','the','a','an','in','on','for','with','and','or','of','my','new','account','project','app','apps','how','do','i','website','site','task','filter','database','data','page','pages','guide','tutorial','help','docs','from','at','is','are','configure','change','add','edit','delete','remove','called','named','item','items'
}
# Common ecosystems treated as potential brands even if lowercase
COMMON_BRANDS = {'github','npm','pypi','python'}

def extract_brands(task: str, limit: int = 3):
    """Unified brand extractor.
    Signals:
    - Capitalized tokens (Proper nouns) => +2
    - Appears after prepositions (in|from|on|at) => +3 (captures lowercase like 'npm')
    - Known ecosystem keyword => +2.5
    Returns up to `limit` distinct lowercased brand candidates ordered by score.
    """
    if not task:
        return []
    caps = re.findall(r"\b([A-Z][A-Za-z0-9.+-]{1,})\b", task)
    after_in = re.findall(r"\b(?:in|from|on|at)\s+([A-Za-z][A-Za-z0-9.+-]{1,})", task, re.I)
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9._+-]{1,30}", task)
    scores = {}
    for t in tokens:
        tl = t.lower()
        if tl in STOP_WORDS or len(tl) < 2:
            continue
        s = 0.0
        if t in caps:
            s += 2.0
        if any(t.lower() == ai.lower() for ai in after_in):
            s += 3.0
        if tl in COMMON_BRANDS:
            s += 2.5
        if s > 0:
            # keep max score per token
            scores[tl] = max(scores.get(tl, 0.0), s)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [k for k,_ in ranked[:limit]]
