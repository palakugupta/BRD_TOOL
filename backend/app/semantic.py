from functools import lru_cache
from typing import List, Tuple

from sentence_transformers import SentenceTransformer, util
import torch


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """
    Shared SBERT model.
    Cached so it loads only once per process.
    """
    return SentenceTransformer("all-MiniLM-L6-v2")


def embed_sentences(sentences: List[str]) -> torch.Tensor:
    """
    Returns a tensor of shape (n_sentences, dim).
    """
    if not sentences:
        return torch.empty((0, 384))
    model = get_model()
    return model.encode(sentences, convert_to_tensor=True, show_progress_bar=False)


def most_similar(
    query_emb: torch.Tensor,
    candidate_embs: torch.Tensor,
    top_k: int = 3,
) -> List[Tuple[int, float]]:
    """
    Return list of (index, similarity) for top_k most similar candidates.
    """
    if candidate_embs.size(0) == 0:
        return []
    sims = util.cos_sim(query_emb, candidate_embs)[0]
    values, indices = torch.topk(sims, k=min(top_k, len(sims)))
    return [(int(idx), float(val)) for idx, val in zip(indices, values)]