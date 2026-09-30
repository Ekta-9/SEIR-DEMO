"""Real commit subjects from apache/commons-lang, used as regression examples."""

import pytest

from app.dataset.commit_filters import is_bug_fix, is_cosmetic

COSMETIC = [
    "Javadoc: Use {@code}",
    "Fix Javadoc typo.",
    "Fixing checkstyle issue - lack of braces after an if",
    "Fix formatting",
    "Fix weird formatting.",
    "Format tweaks",
    "Fix indentation",
    "Fix Checkstyle trailing whitespace.",
    "Fix SonarQube warning: The user-supplied array 'typeArguments' is stored directly.",
    "Fix some raw types",
    "(fix) unused imports",
    "Fix typos in comments",
    "添加注释",  # add comments
    "removed lots of finals",  # SZZ review sample (commons-io): blamed for a later fix, but cosmetic
    "Remove redundant final modifiers",
]
BUG_FIXES = [
    "[LANG-1637] Fix 2 digit week year formatting (#688)",
    "fix negative week year formatting in FastDatePrinter (#1762)",
    "fix indexOfAny matching an unpaired trailing high surrogate (#1687)",
    "Fix ArrayUtils.reverse range underflow on Integer.MIN_VALUE end (#1750)",
    "[LANG-1828] Fix OOM in StringUtils.leftPad/rightPad when size is Integer.MIN_VALUE (#1736).",
    "LANG-951: Fragments are wrong by 1 day when using fragment YEAR or MONTH",
    "Fix split to use whitespace, remove StringTokenizer",
    "Fix for LANG-477 OutOfMemory with custom format registry",
    # macrozheng/mall (Chinese subjects)
    "修复账号被禁用后，之前Token还能使用的问题。",  # fix: disabled account's token still usable
    "下单库存问题修复",  # order inventory problem fixed
    "跨域问题解决",  # CORS problem solved
]
NEITHER = [
    "Add ClassUtils.getAbbreviatedName",
    "Simplify code",
    "Bump commons-parent from 70 to 71",
    "Add messages when throwing NullPointerException.",  # found in SZZ review: not a fix
    "Update SmsCouponController.java",  # GitHub web-editor default message: tells us nothing
    "添加登录日志记录",  # add login logging (feature)
    "结构调整",  # structural adjustment
]


@pytest.mark.parametrize("subject", COSMETIC)
def test_cosmetic(subject):
    assert is_cosmetic(subject)
    assert not is_bug_fix(subject)


@pytest.mark.parametrize("subject", BUG_FIXES)
def test_bug_fix(subject):
    assert not is_cosmetic(subject)
    assert is_bug_fix(subject)


@pytest.mark.parametrize("subject", NEITHER)
def test_neither(subject):
    assert not is_cosmetic(subject)
    assert not is_bug_fix(subject)
