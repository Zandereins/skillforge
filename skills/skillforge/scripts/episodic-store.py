#!/usr/bin/env python3
from __future__ import annotations
"""SkillForge Episodic Memory — Cross-Session Learning Store

Lightweight semantic search over past skill improvements.
Remembers: "Last time with a similar skill, strategy X failed because Y."

Eliminates cold-start. Enables transfer-learning between skills.
Compound knowledge over weeks.

Usage:
    python3 episodic-store.py --store --skill NAME --strategy STR --outcome keep --delta 3.5 --learning "..."
    python3 episodic-store.py --recall "trigger accuracy low" --top-k 5
    python3 episodic-store.py --synthesize "trigger accuracy"
    python3 episodic-store.py --test
    python3 episodic-store.py --stats
"""

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


EPISODES_PATH = Path.home() / ".skillforge" / "meta" / "episodes.jsonl"
MAX_EPISODES = 10_000
CONSOLIDATION_BATCH = 1000
MAX_FILE_SIZE = 10_000_000  # 10 MB


# --- Tokenizer (reuses scorer patterns) ---

STOPWORDS = {
    "this", "that", "with", "from", "have", "will", "been", "were", "they",
    "their", "them", "what", "when", "where", "which", "about", "into",
    "your", "some", "than", "then", "also", "just", "more", "very", "here",
    "there", "each", "like", "help", "want", "need", "using", "used",
    "uses", "does", "doing", "done", "should", "could", "would", "please",
    "really", "actually", "currently", "basically", "think", "know",
    "sure", "well", "okay", "look", "show", "tell",
}


def _tokenize(text: str) -> list[str]:
    """Extract meaningful words (4+ chars, not stopwords)."""
    words = re.findall(r"\b[a-z]{4,}\b", text.lower())
    return [w for w in words if w not in STOPWORDS]


# --- TF-IDF Engine ---

class TFIDFIndex:
    """Lightweight TF-IDF index for episode recall."""

    def __init__(self, documents: list[dict]):
        """Build index from episode documents.

        Each document must have a 'text' field for indexing.
        """
        self.documents = documents
        self.n_docs = len(documents)
        self.doc_freq: Counter = Counter()
        self.doc_vectors: list[dict[str, float]] = []

        # Build document frequency
        for doc in documents:
            tokens = set(_tokenize(doc.get("text", "")))
            for token in tokens:
                self.doc_freq[token] += 1

        # Build TF-IDF vectors
        for doc in documents:
            tokens = _tokenize(doc.get("text", ""))
            tf: Counter = Counter(tokens)
            vector = {}
            for term, count in tf.items():
                tf_val = count / max(len(tokens), 1)
                idf_val = math.log(self.n_docs / (self.doc_freq[term] + 1)) + 1
                vector[term] = tf_val * idf_val
            self.doc_vectors.append(vector)

    def search(self, query: str, top_k: int = 5) -> list[tuple[int, float]]:
        """Search index with query string.

        Returns list of (doc_index, similarity_score) tuples, sorted by score.
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        query_tf: Counter = Counter(query_tokens)
        query_vector = {}
        for term, count in query_tf.items():
            tf_val = count / len(query_tokens)
            idf_val = math.log(self.n_docs / (self.doc_freq.get(term, 0) + 1)) + 1
            query_vector[term] = tf_val * idf_val

        # Cosine similarity against each document
        results = []
        for i, doc_vec in enumerate(self.doc_vectors):
            common = set(query_vector.keys()) & set(doc_vec.keys())
            if not common:
                continue
            dot = sum(query_vector[t] * doc_vec[t] for t in common)
            norm_q = math.sqrt(sum(v ** 2 for v in query_vector.values()))
            norm_d = math.sqrt(sum(v ** 2 for v in doc_vec.values()))
            if norm_q > 0 and norm_d > 0:
                sim = dot / (norm_q * norm_d)
                results.append((i, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


# --- Episode Store ---

def _load_episodes() -> list[dict]:
    """Load all episodes from JSONL file."""
    if not EPISODES_PATH.exists():
        return []
    if EPISODES_PATH.stat().st_size > MAX_FILE_SIZE:
        print(f"Warning: episodes file exceeds {MAX_FILE_SIZE} bytes", file=sys.stderr)
        return []

    episodes = []
    with open(EPISODES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    episodes.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return episodes


def _save_episode(episode: dict) -> None:
    """Append a single episode to the store."""
    EPISODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EPISODES_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(episode) + "\n")


def _episode_text(ep: dict) -> str:
    """Build searchable text from episode fields."""
    parts = [
        ep.get("skill", ""),
        ep.get("domain", ""),
        ep.get("strategy", ""),
        ep.get("outcome", ""),
        ep.get("learning", ""),
        ep.get("context", ""),
    ]
    return " ".join(p for p in parts if p)


def store_episode(
    skill: str,
    strategy: str,
    outcome: str,
    delta: float,
    learning: str,
    domain: str = "unknown",
    context: str = "",
) -> dict:
    """Store a new learning episode.

    Args:
        skill: Skill name
        strategy: Strategy type used
        outcome: "keep" or "discard"
        delta: Score change
        learning: What was learned (1-2 sentences)
        domain: Skill domain
        context: Additional context

    Returns:
        The stored episode dict
    """
    episode = {
        "skill": skill,
        "domain": domain,
        "strategy": strategy,
        "outcome": outcome,
        "delta": round(delta, 2),
        "learning": learning,
        "context": context,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    episode["text"] = _episode_text(episode)
    _save_episode(episode)

    # Check size cap
    _enforce_size_cap()

    return episode


def recall(query: str, top_k: int = 5) -> list[dict]:
    """Recall relevant past episodes using semantic search.

    Args:
        query: Natural language query (e.g., "trigger accuracy low")
        top_k: Number of results to return

    Returns:
        List of episode dicts with added 'relevance' score
    """
    episodes = _load_episodes()
    if not episodes:
        return []

    # Build text field if missing
    for ep in episodes:
        if "text" not in ep:
            ep["text"] = _episode_text(ep)

    index = TFIDFIndex(episodes)
    results = index.search(query, top_k=top_k)

    recalled = []
    for doc_idx, score in results:
        ep = episodes[doc_idx].copy()
        ep["relevance"] = round(score, 3)
        # Remove internal text field from output
        ep.pop("text", None)
        recalled.append(ep)

    return recalled


def synthesize(query: str, top_k: int = 5) -> str:
    """Synthesize relevant episodes into a 3-5 line summary.

    Args:
        query: What to synthesize about
        top_k: How many episodes to consider

    Returns:
        Summary string
    """
    episodes = recall(query, top_k=top_k)
    if not episodes:
        return "No relevant episodes found."

    # Group by outcome
    keeps = [ep for ep in episodes if ep.get("outcome") == "keep"]
    discards = [ep for ep in episodes if ep.get("outcome") == "discard"]

    lines = []
    lines.append(f"Based on {len(episodes)} relevant past episodes:")

    if keeps:
        strategies = set(ep.get("strategy", "?") for ep in keeps)
        avg_delta = sum(ep.get("delta", 0) for ep in keeps) / len(keeps)
        lines.append(f"  Successful strategies: {', '.join(strategies)} (avg delta: {avg_delta:+.1f})")

    if discards:
        strategies = set(ep.get("strategy", "?") for ep in discards)
        learnings = [ep.get("learning", "") for ep in discards if ep.get("learning")]
        lines.append(f"  Failed strategies: {', '.join(strategies)}")
        if learnings:
            lines.append(f"  Key lesson: {learnings[0][:100]}")

    # Top learning
    all_learnings = [ep.get("learning", "") for ep in episodes if ep.get("learning")]
    if all_learnings:
        lines.append(f"  Most relevant: {all_learnings[0][:120]}")

    return "\n".join(lines)


def _enforce_size_cap() -> None:
    """Consolidate oldest episodes when exceeding MAX_EPISODES."""
    episodes = _load_episodes()
    if len(episodes) <= MAX_EPISODES:
        return

    # Split: keep recent, consolidate oldest
    old = episodes[:CONSOLIDATION_BATCH]
    keep = episodes[CONSOLIDATION_BATCH:]

    # Consolidate old episodes: group by (domain, strategy, outcome)
    groups: dict[tuple, list] = defaultdict(list)
    for ep in old:
        key = (ep.get("domain", "?"), ep.get("strategy", "?"), ep.get("outcome", "?"))
        groups[key].append(ep)

    consolidated = []
    for (domain, strategy, outcome), eps in groups.items():
        avg_delta = sum(ep.get("delta", 0) for ep in eps) / len(eps)
        learnings = [ep.get("learning", "") for ep in eps if ep.get("learning")]
        # Pick most informative learning (longest)
        best_learning = max(learnings, key=len) if learnings else ""
        consolidated.append({
            "skill": "consolidated",
            "domain": domain,
            "strategy": strategy,
            "outcome": outcome,
            "delta": round(avg_delta, 2),
            "learning": f"[{len(eps)} episodes] {best_learning[:200]}",
            "context": f"Consolidated from {len(eps)} episodes",
            "timestamp": eps[-1].get("timestamp", ""),
            "text": _episode_text({"domain": domain, "strategy": strategy,
                                    "outcome": outcome, "learning": best_learning}),
        })

    # Atomic rewrite: write to temp file then rename (crash-safe on POSIX)
    all_episodes = consolidated + keep
    EPISODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = EPISODES_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for ep in all_episodes:
            f.write(json.dumps(ep) + "\n")
    tmp_path.replace(EPISODES_PATH)

    print(f"Consolidated {len(old)} old episodes into {len(consolidated)}", file=sys.stderr)


def get_stats() -> dict:
    """Get episode store statistics."""
    episodes = _load_episodes()
    if not episodes:
        return {"total": 0, "domains": {}, "strategies": {}, "outcomes": {}}

    domains: Counter = Counter()
    strategies: Counter = Counter()
    outcomes: Counter = Counter()

    for ep in episodes:
        domains[ep.get("domain", "unknown")] += 1
        strategies[ep.get("strategy", "unknown")] += 1
        outcomes[ep.get("outcome", "unknown")] += 1

    return {
        "total": len(episodes),
        "domains": dict(domains.most_common()),
        "strategies": dict(strategies.most_common()),
        "outcomes": dict(outcomes.most_common()),
    }


def _run_self_test() -> bool:
    """Run store/recall roundtrip test."""
    import tempfile
    global EPISODES_PATH

    # Save original path
    orig_path = EPISODES_PATH

    try:
        # Use temp file
        tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w")
        tmp.close()
        EPISODES_PATH = Path(tmp.name)

        # Store test episodes
        store_episode("test-skill", "trigger_expansion", "keep", 5.0,
                       "Adding synonyms improved trigger accuracy significantly",
                       domain="skill", context="test context")
        store_episode("test-skill", "noise_reduction", "discard", -1.0,
                       "Removing hedge words reduced clarity score",
                       domain="skill", context="test context 2")
        store_episode("other-skill", "example_addition", "keep", 3.0,
                       "Adding before/after examples helped output quality",
                       domain="testing", context="test context 3")

        # Test recall
        results = recall("trigger accuracy improvement", top_k=3)
        assert len(results) > 0, "Recall returned no results"
        assert results[0].get("relevance", 0) > 0, "No relevance score"

        # Test synthesize
        summary = synthesize("trigger improvement")
        assert "Based on" in summary, f"Bad synthesis: {summary}"

        # Test stats
        stats = get_stats()
        assert stats["total"] == 3, f"Expected 3 episodes, got {stats['total']}"

        # Cleanup temp
        EPISODES_PATH.unlink(missing_ok=True)
        print("All episodic-store tests passed!", file=sys.stderr)
        return True

    except Exception as e:
        print(f"Self-test FAILED: {e}", file=sys.stderr)
        return False

    finally:
        EPISODES_PATH = orig_path


def main():
    parser = argparse.ArgumentParser(description="SkillForge Episodic Memory Store")
    parser.add_argument("--store", action="store_true", help="Store a new episode")
    parser.add_argument("--recall", type=str, help="Recall episodes matching query")
    parser.add_argument("--synthesize", type=str, help="Synthesize episodes into summary")
    parser.add_argument("--test", action="store_true", help="Run self-test")
    parser.add_argument("--stats", action="store_true", help="Show store statistics")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Store args
    parser.add_argument("--skill", default="unknown", help="Skill name")
    parser.add_argument("--strategy", default="unknown", help="Strategy used")
    parser.add_argument("--outcome", default="keep", help="Outcome: keep/discard")
    parser.add_argument("--delta", type=float, default=0.0, help="Score delta")
    parser.add_argument("--learning", default="", help="What was learned")
    parser.add_argument("--domain", default="unknown", help="Skill domain")
    parser.add_argument("--context", default="", help="Additional context")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results")

    args = parser.parse_args()

    if args.test:
        success = _run_self_test()
        sys.exit(0 if success else 1)

    if args.store:
        ep = store_episode(
            skill=args.skill,
            strategy=args.strategy,
            outcome=args.outcome,
            delta=args.delta,
            learning=args.learning,
            domain=args.domain,
            context=args.context,
        )
        if args.json:
            print(json.dumps(ep, indent=2))
        else:
            print(f"Stored episode: {ep['skill']} / {ep['strategy']} → {ep['outcome']} ({ep['delta']:+.1f})")

    elif args.recall:
        results = recall(args.recall, top_k=args.top_k)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                print("No relevant episodes found.")
            else:
                for i, ep in enumerate(results, 1):
                    print(f"  #{i} [{ep.get('relevance', 0):.3f}] {ep.get('skill', '?')} / "
                          f"{ep.get('strategy', '?')} → {ep.get('outcome', '?')} ({ep.get('delta', 0):+.1f})")
                    if ep.get("learning"):
                        print(f"      {ep['learning'][:80]}")

    elif args.synthesize:
        summary = synthesize(args.synthesize, top_k=args.top_k)
        if args.json:
            print(json.dumps({"synthesis": summary}, indent=2))
        else:
            print(summary)

    elif args.stats:
        stats = get_stats()
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(f"Episodes: {stats['total']}")
            print(f"Domains: {stats['domains']}")
            print(f"Strategies: {stats['strategies']}")
            print(f"Outcomes: {stats['outcomes']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
