import re

class TextCleaner:
    """
    Normalizes and cleans input text (English / Hinglish) for semantic extraction.
    Removes extraneous punctuation and standardizes common tactical terms.
    """
    
    # Mapping common variants to standardized forms
    SYNONYM_MAP = {
        "turant": "urgently",
        "jaldi": "urgently",
        "immediately": "urgently",
        "bhejo": "send",
        "bhej": "send",
        "dispatch": "send",
        "deploy": "send",
        "karo": "",
        "ko": "",
        "par": "at",
        "sir": "",
        "please": "",
    }

    @classmethod
    def clean_text(cls, text: str) -> str:
        if not text:
            return ""
        
        # Lowercase and strip
        cleaned = text.lower().strip()
        
        # Remove punctuation except alphanumeric and space
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        
        # Normalize whitespace
        tokens = cleaned.split()
        
        normalized_tokens = []
        for token in tokens:
            # Map synonyms if present
            mapped = cls.SYNONYM_MAP.get(token, token)
            if mapped:
                normalized_tokens.append(mapped)
                
        return " ".join(normalized_tokens)
