from functools import lru_cache
from typing import List, Tuple, Optional

# Heavy ML deps are optional. The app should still run end-to-end (preview, rules,
# pattern detectors) even if these aren't installed.
try:
    from sentence_transformers import SentenceTransformer, util  # type: ignore
    import torch  # type: ignore
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore
    util = None  # type: ignore
    torch = None  # type: ignore


@lru_cache(maxsize=1)
def get_model() -> "SentenceTransformer":
    """
    Shared SBERT model.
    Cached so it loads only once per process.
    """
    if SentenceTransformer is None:
        raise RuntimeError(
            "Semantic model unavailable (install sentence-transformers and torch)."
        )
    return SentenceTransformer("all-MiniLM-L6-v2")


def embed_sentences(sentences: List[str]):
    """
    Returns a tensor of shape (n_sentences, dim).
    """
    if torch is None:
        return None
    if not sentences:
        return torch.empty((0, 384))
    model = get_model()
    return model.encode(sentences, convert_to_tensor=True, show_progress_bar=False)


def most_similar(
    query_emb,
    candidate_embs,
    top_k: int = 3,
) -> List[Tuple[int, float]]:
    """
    Return list of (index, similarity) for top_k most similar candidates.
    """
    if torch is None or util is None or query_emb is None or candidate_embs is None:
        return []
    if candidate_embs.size(0) == 0:
        return []
    sims = util.cos_sim(query_emb, candidate_embs)[0]
    values, indices = torch.topk(sims, k=min(top_k, len(sims)))
    return [(int(idx), float(val)) for idx, val in zip(indices, values)]