import re
import math
import numpy as np
from collections import Counter
from typing import Dict, List

def calculate_entropy(text: str) -> float:
    if not text:
        return 0.0
    probabilities = [count / len(text) for count in Counter(text).values()]
    return -sum(p * math.log2(p) for p in probabilities)

def extract_features(text: str) -> Dict:
    if not text:
        return {f"feature_{i}": 0.0 for i in range(1, 21)}
    
    text_lower = text.lower()
    text_upper = text.upper()
    words = text.split()
    chars = list(text)
    
    features = {}
    
    features["length_entropy"] = calculate_entropy(text)
    
    special_chars = sum(1 for c in chars if not c.isalnum() and not c.isspace())
    features["special_char_ratio"] = special_chars / len(text) if text else 0
    
    uppercase = sum(1 for c in chars if c.isupper())
    features["uppercase_ratio"] = uppercase / len(text) if text else 0
    
    cmd_patterns = ["rm -rf", "sudo", "chmod", "curl", "wget", "nc ", "bash", "sh "]
    features["command_pattern"] = 1.0 if any(p in text_lower for p in cmd_patterns) else 0.0
    
    override_keywords = ["override", "ignore", "bypass", "jailbreak", "DAN", "god mode"]
    features["override_keywords"] = 1.0 if any(kw in text_lower for kw in override_keywords) else 0.0
    
    sql_patterns = ["SELECT *", "DROP TABLE", "DELETE FROM", "UNION", "OR 1=1", "--"]
    features["sql_injection"] = 1.0 if any(p in text_upper for p in sql_patterns) else 0.0
    
    shell_patterns = ["/etc/", "/var/", "/usr/", "pipe", "grep", "exec"]
    features["shell_command"] = 1.0 if any(p in text_lower for p in shell_patterns) else 0.0
    
    unicode_chars = sum(1 for c in chars if ord(c) > 127)
    features["unicode_ratio"] = unicode_chars / len(text) if text else 0
    
    word_counts = Counter(words)
    max_repetition = max(word_counts.values()) if word_counts else 1
    features["repetition_score"] = min(max_repetition / 10, 1.0)
    
    avg_word_len = sum(len(w) for w in words) / len(words) if words else 0
    features["avg_word_length"] = min(avg_word_len / 10, 1.0)
    
    unique_words = len(set(words))
    features["vocab_diversity"] = unique_words / len(words) if words else 0
    
    imperative_starts = ["show", "give", "provide", "list", "output", "execute", "run", "create", "write", "generate"]
    features["imperative_mood"] = 1.0 if any(text_lower.startswith(s) for s in imperative_starts) else 0.0
    
    instruction_words = ["how to", "show me", "give me", "provide", "list", "output", "execute", "run"]
    features["instruction_count"] = min(sum(1 for w in instruction_words if w in text_lower) / 3, 1.0)
    
    escape_patterns = ["\\n", "\\t", "\\r", "\\x", "\\u"]
    features["escape_sequences"] = 1.0 if any(p in text for p in escape_patterns) else 0.0
    
    control_chars = sum(1 for c in chars if ord(c) < 32 and c not in "\n\r\t")
    features["control_chars"] = control_chars / len(text) if text else 0
    
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        "]+", flags=re.UNICODE)
    features["emoji_present"] = 1.0 if emoji_pattern.search(text) else 0.0
    
    punct_count = sum(1 for c in chars if c in "!@#$%^&*()_+-=[]{}|;:,.<>?")
    features["punctuation_density"] = punct_count / len(text) if text else 0
    
    if words:
        word_lens = [len(w) for w in words]
        features["word_length_variance"] = float(np.var(word_lens)) / 100 if len(word_lens) > 1 else 0
    else:
        features["word_length_variance"] = 0.0
    
    ngrams = [text[i:i+3] for i in range(len(text)-2)]
    features["ngram_entropy"] = calculate_entropy(" ".join(ngrams)) if ngrams else 0
    
    suspicious_phrases = [
        "system override", "ignore all", "bypass", "jailbreak", "god mode",
        "unrestricted", "training data", "system prompt", "API key",
        "connection string", "delete all", "drop table", "rm -rf"
    ]
    features["suspicious_phrase_count"] = min(sum(1 for p in suspicious_phrases if p in text_lower) / 2, 1.0)
    
    return features