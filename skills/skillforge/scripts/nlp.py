#!/usr/bin/env python3
"""SkillForge — Shared NLP Utilities

Centralized tokenizer, stemmer, stopwords, and synonym expansion.
Single source of truth — imported by score-skill.py, episodic-store.py, skill-mesh.py.
"""
from __future__ import annotations

import re

# --- Stopwords (truly generic function words only) ---
# IMPORTANT: Do NOT include domain-relevant terms here. Words like "skill",
# "code", "create" are meaningful in skill-improvement contexts.
STOPWORDS = {
    "this", "that", "with", "from", "have", "will", "been", "were", "they",
    "their", "them", "what", "when", "where", "which", "about", "into",
    "your", "some", "than", "then", "also", "just", "more", "very", "here",
    "there", "each", "like", "help", "want", "need", "using", "used",
    "uses", "does", "doing", "done", "should", "could", "would", "please",
    "really", "actually", "currently", "basically", "think", "know",
    "sure", "well", "okay", "look", "show", "tell",
}

RE_WORD_TOKEN = re.compile(r"\b[a-z]{4,}\b")


def stem(word: str) -> str:
    """Lightweight suffix-stripping stemmer for English skill terms."""
    for suffix, min_len in [
        ("ation", 6), ("ment", 5), ("ness", 5), ("tion", 5),
        ("sion", 5), ("able", 5), ("ible", 5), ("ying", 4),
        ("ling", 4), ("ting", 4), ("ning", 4),
        ("ing", 4), ("ring", 4), ("ied", 4), ("ies", 4), ("ous", 4),
        ("ive", 4), ("ize", 4), ("ise", 4), ("ate", 4),
        ("ful", 4), ("ely", 4), ("ally", 5), ("ly", 4),
        ("ed", 4), ("er", 4), ("es", 4), ("al", 4),
        ("s", 4),
    ]:
        if len(word) >= min_len and word.endswith(suffix):
            result = word[:-len(suffix)]
            if len(result) >= 3:
                return result
    return word


# --- Synonym expansion for trigger matching ---
_SYNONYM_GROUPS = {
    "improve": ["enhance", "optimize", "refine", "polish", "boost", "upgrade", "tune", "tweak"],
    "trigger": ["activate", "fire", "match", "invoke", "detect"],
    "audit": ["assess", "inspect", "review", "evaluate", "examine", "check"],
    "eval": ["test", "validate", "verify"],
    "iterate": ["grind", "loop", "repeat"],
    "efficiency": ["verbose", "bloated", "concise", "lean", "trim", "compact"],
}

SYNONYM_TABLE: dict[str, str] = {}
for _canonical, _synonyms in _SYNONYM_GROUPS.items():
    for _syn in _synonyms:
        SYNONYM_TABLE[_syn] = _canonical
    SYNONYM_TABLE[_canonical] = _canonical


def tokenize_meaningful(text: str, expand_reverse: bool = False) -> list[str]:
    """Extract meaningful words (4+ chars, not stopwords), with stemming + synonym expansion.

    expand_reverse=True: also expand canonical->all-synonyms (use for descriptions only).
    expand_reverse=False: only expand synonym->canonical (use for prompts).
    """
    words = RE_WORD_TOKEN.findall(text.lower())
    result = []
    seen: set[str] = set()
    for w in words:
        if w in STOPWORDS:
            continue
        if w not in seen:
            result.append(w)
            seen.add(w)
        stemmed = stem(w)
        if stemmed != w and stemmed not in seen:
            result.append(stemmed)
            seen.add(stemmed)
        canonical = SYNONYM_TABLE.get(w)
        if canonical and canonical not in seen:
            result.append(canonical)
            seen.add(canonical)
        if expand_reverse and w in _SYNONYM_GROUPS:
            for syn in _SYNONYM_GROUPS[w]:
                if syn not in seen:
                    result.append(syn)
                    seen.add(syn)
    return result
