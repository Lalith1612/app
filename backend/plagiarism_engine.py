import os
from typing import Dict, List

import numpy as np


def _cosine_similarity_fallback(texts: List[str]) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    matrix = TfidfVectorizer(stop_words="english").fit_transform(texts)
    return cosine_similarity(matrix)


def calculate_plagiarism_flags(submissions: List[Dict]) -> Dict[str, Dict]:
    if len(submissions) < 2:
        return {
            item["id"]: {
                "plagiarism_score": 0.0,
                "plagiarism_flag": False,
                "plagiarism_matches": [],
            }
            for item in submissions
        }

    docs = ["\n".join(item.get("answers", {}).values()) for item in submissions]

    try:
        from sentence_transformers import SentenceTransformer

        model_name = os.environ.get("PLAGIARISM_MODEL", "all-MiniLM-L6-v2")
        model = SentenceTransformer(model_name)
        embeddings = model.encode(docs, normalize_embeddings=True)
        similarity = np.matmul(embeddings, embeddings.T)
    except Exception:
        similarity = _cosine_similarity_fallback(docs)

    threshold = float(os.environ.get("PLAGIARISM_THRESHOLD", "0.88"))
    plagiarism_map: Dict[str, Dict] = {}

    for i, source in enumerate(submissions):
        matches = []
        max_score = 0.0
        for j, target in enumerate(submissions):
            if i == j:
                continue
            score = float(similarity[i][j])
            if score > max_score:
                max_score = score
            if score >= threshold:
                matches.append(
                    {
                        "submission_id": target["id"],
                        "roll_number": target.get("roll_number", "UNKNOWN"),
                        "score": round(score, 4),
                    }
                )

        plagiarism_map[source["id"]] = {
            "plagiarism_score": round(max_score, 4),
            "plagiarism_flag": len(matches) > 0,
            "plagiarism_matches": matches,
        }

    return plagiarism_map
