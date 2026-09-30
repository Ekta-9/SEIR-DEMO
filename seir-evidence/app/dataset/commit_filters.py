"""Classify commits by their subject line.

Keyword heuristics are the standard first step in mining-software-repositories
research (e.g. Mockus & Votta 2000; SZZ, Sliwerski et al. 2005). They are
imperfect, so the patterns are explicit, phrase-based and tested.

Lesson from commons-lang: single words are too blunt. "formatting",
"trailing" and "whitespace" also appear in real bug fixes ("Fix 2 digit week
year formatting", "unpaired trailing high surrogate"), so cosmetic words only
count inside cosmetic *phrases*.
"""

import re

_COSMETIC_PHRASES = (
    # documentation
    r"javadoc", r"doclint", r"@(see|since|link|param|throws|return|deprecated)\b",
    r"(fix(ed|es|ing)?|typos?\s+in|spelling\s+in|update[ds]?)\s+(the\s+|some\s+|inline\s+)?comments?",
    r"typos?", r"spelling", r"grammar",
    # static-analysis / style tools
    r"checkstyle", r"\bpmd\b", r"spotbugs", r"findbugs", r"sonar\w*", r"raw\s+types?", r"warnings?\b",
    # formatting-only phrases
    r"reformat\w*", r"code\s+(format\w*|style)", r"source\s+code\s+formatting",
    r"format(ting)?\s+(tweaks?|fix(es)?|changes?|only)",
    r"(fix(ed|es|ing)?|minor|some|weird)\s+(some\s+|weird\s+)?formatting\b(?!\s+(in|of|for)\b)",
    r"trailing\s+(white)?spaces?",
    r"(fix(ed|es)?|remove[ds]?|clean\s?up)\s+whitespaces?", r"whitespaces?\s+(fix(es)?|changes?|only|cleanup)",
    r"indent(ation|s)?\b", r"tabs?\s+to\s+spaces",
    # imports / licence / member order
    r"unused\s+imports?", r"organi[sz]e\s+imports", r"wildcard\s+imports?",
    r"(fix(ed)?|remove[ds]?)\s+imports?\b", r"licen[cs]e", r"sort(ed)?\s+members",
    r"use\s+final", r"final\s+(keyword|modifier)s?",
    # found in the SZZ review sample: "removed lots of finals"
    r"(remov(e[ds]?|ing)|add(ed|ing)?)\s+(lots\s+of\s+|some\s+|unnecessary\s+|redundant\s+)?finals?\b",
    r"(unnecessary|redundant)\s+finals?\b",
)
COSMETIC_PATTERN = re.compile(r"\b(" + "|".join(_COSMETIC_PHRASES) + r")", re.IGNORECASE)

# Bug-fix commits: the "fixing" side of SZZ. Exception names alone (NPE,
# NullPointerException) are deliberately absent: "Add messages when throwing
# NullPointerException" is a feature; "Fix NPE in X" is still caught by "fix".
BUG_FIX_PATTERN = re.compile(
    r"\b(fix(e[sd]|ing)?|bugs?|bugfix|regression|"
    r"broken|crash(es|ed)?|incorrect(ly)?|wrong(ly)?|defect|fault)\b",
    re.IGNORECASE,
)


# Chinese subjects (27 % of macrozheng/mall). `\b` word boundaries do not work
# for CJK text (no spaces between words), so these are plain substrings:
# 修复 fix/repair, 修正 correct, 解决 solve. 问题 "problem" and 异常 "exception"
# alone are excluded: mentioning a problem is not fixing one.
BUG_FIX_PATTERN_CJK = re.compile(r"修复|修正|解决")
COSMETIC_PATTERN_CJK = re.compile(r"注释|格式化|代码格式|错别字")  # comments, formatting, typos


def is_cosmetic(subject: str) -> bool:
    return bool(COSMETIC_PATTERN.search(subject) or COSMETIC_PATTERN_CJK.search(subject))


def is_bug_fix(subject: str) -> bool:
    """A bug fix mentions fixing something and is not a cosmetic change."""
    mentions_fix = BUG_FIX_PATTERN.search(subject) or BUG_FIX_PATTERN_CJK.search(subject)
    return bool(mentions_fix) and not is_cosmetic(subject)
