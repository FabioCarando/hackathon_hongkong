"""TF-IDF search over every readable document (char n-grams, so Chinese works)."""

from sklearn.feature_extraction.text import TfidfVectorizer

from app.core import indexer, reader

# fold common traditional characters to simplified so 銀行 finds 银行 (and vice versa)
T2S = str.maketrans(
    "銀帳號發貨價約單額費匯戶變賬導錢會計貿許證書關聯係與為業",
    "银帐号发货价约单额费汇户变账导钱会计贸许证书关联系与为业",
)


def _fold(s: str) -> str:
    return s.lower().translate(T2S)


def _corpus() -> list[tuple[str, int, str]]:
    out = []
    for f in indexer.load():
        if not reader.can_read(f.path):
            continue
        rr = reader.read(f.path, ocr=False)  # scans only once OCR'd (cached)
        out += [(f.path, p.page, p.text) for p in rr.pages if p.text.strip()]
    return out


def search(query: str, k: int = 8) -> list[dict]:
    corpus = _corpus()
    if not corpus or not query.strip():
        return []
    texts = [_fold(f"{path} {text}") for path, _, text in corpus]
    q = _fold(query.strip())
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True)
    m = vec.fit_transform(texts)
    scores = (m @ vec.transform([q]).T).toarray().ravel()
    # exact phrase / every-word matches rank first
    words = q.split()
    for i, t in enumerate(texts):
        if q in _fold(corpus[i][0]):  # file name match: "lease" -> the lease contracts
            scores[i] += 0.5
        if q in t:
            scores[i] += 1.0
        elif words and all(w in t for w in words):
            scores[i] += 0.5
    out = []
    for i in scores.argsort()[::-1][:k]:
        if scores[i] <= 0.05:
            break
        path, page, text = corpus[i]
        flat = " ".join(text.split())
        pos = max(0, max((_fold(flat).find(w) for w in words), default=0) - 60)
        out.append(
            dict(path=path, page=page, score=float(scores[i]), snippet=flat[pos : pos + 200])
        )
    return out
