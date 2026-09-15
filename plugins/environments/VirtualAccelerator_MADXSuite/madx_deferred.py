"""Rewrite MAD-X immediate assignments ('=') as deferred ones (':=').

MAD-X evaluates '=' at parse time and keeps no expression, so cpymad reports
``mad.elements['q_dq206'].cmdpar['k1'].expr is None`` and the cpymad -> xtrack
conversion has nothing to build a dependency graph from.  Every lattice
quantity arrives in the Line as a frozen number, and changing a knob afterwards
moves nothing.

':=' is MAD-X's deferred assignment: the expression is stored and re-evaluated
on demand.  Those expressions survive ``Line.from_madx_sequence(...,
deferred_expressions=True)`` into xtrack's xdeps graph, which then recomputes
only the affected subtree when a knob moves.  Rewriting the source once at load
is therefore all it takes to turn a static Line into a live one.

The rewrite is deliberately conservative: anything it is not sure about keeps
its original '=' (see the guards in ``to_deferred``).  The caller is expected to
verify the result -- load both the original and the rewritten source into MAD-X
and compare every value -- before trusting it.
"""

import re

# A MAD-X identifier.  Dots appear in some generated element names.
IDENT = r'[A-Za-z_][\w.]*'

# Right-hand sides we refuse to defer.  ranf/gauss/tgauss would draw a new
# random number on every evaluation; table() reads whatever the last TWISS
# happened to leave behind.  Neither is a functional dependence.
VOLATILE = re.compile(r'\b(ranf|gauss|tgauss|table)\s*\(', re.I)

# Plain arithmetic only: identifiers, numbers, operators, parentheses.  Anything
# with a quote or a brace is a string or a keyword, and ':=' is invalid there.
ARITHMETIC = re.compile(r'^[\w.\s+\-*/^()%,]*$')

# MAD-X's boolean literals.  'MAKEDIPEDGE = FALSE;' is a flag, not a formula,
# and deferring it leaves 'false' itself undefined until something reads it.
BOOLEANS = frozenset({'true', 'false'})

# ':' declarations that are not element definitions and must not be touched.
NON_ELEMENT_TYPES = frozenset({'LINE', 'SEQUENCE', 'MACRO'})

# Element attributes whose value is a keyword or a string rather than a number.
# 'APERTYPE = ELLIPSE' is indistinguishable from 'K1 = G_DQ206' by shape alone,
# so these have to be named.
STRING_ATTRIBUTES = frozenset({'apertype', 'type', 'from', 'refpos', 'comments'})

# Element attributes are comma-separated; a comma inside parentheses belongs to
# a function call, not to the attribute list.
ATTRIBUTE = re.compile(rf'(,\s*{IDENT}\s*)=(?!=)([^,;]*)')

COMMENT = re.compile(r'//.*|!.*')


def _strip_comments(text: str) -> str:
    return COMMENT.sub('', text)


def _flatten(text: str) -> str:
    """Comment-free, whitespace-collapsed form of a statement, for matching."""
    return ' '.join(_strip_comments(text).split())


def _statements(src: str):
    """Yield (chunk, is_top_level_code) for each ';'-separated chunk.

    Chunks are yielded verbatim -- comments, newlines and indentation intact --
    so that reassembling them reproduces the source byte for byte.  Chunks
    inside braces are flagged as not top level: MACRO and IF/WHILE bodies are
    re-executed procedurally, so their assignments are steps, not dependencies.
    """
    depth = 0
    for chunk in re.split(r'(;)', src):
        if chunk == ';':
            yield chunk, False
            continue
        bare = _strip_comments(chunk)
        yield chunk, depth == 0 and bool(bare.strip())
        depth += bare.count('{') - bare.count('}')


def to_deferred(src: str) -> tuple[str, dict]:
    """Return (rewritten source, stats).

    Rewrites two forms:

    - global scalar assignment  ``NAME = rhs;``          -> ``NAME := rhs;``
    - element attribute         ``E: QUADRUPOLE, K1 = g`` -> ``K1 := g``

    Commands (OPTION, BEAM, USE, TWISS, SELECT, TRACK, ...), LINE and SEQUENCE
    definitions, macro and loop bodies, and statements already using ':=' are
    left alone.

    stats has 'vars' and 'attrs' counts, a 'skipped' list of
    '<name> (<reason>)' strings, and 'calls' -- CALLed files are not rewritten,
    so their assignments stay frozen and the caller should warn about them.
    """
    # A name assigned more than once is a procedural sequence of values, not a
    # formula; deferring it would make every occurrence mean the last one.
    assigned = {}
    for chunk, is_code in _statements(src):
        if not is_code:
            continue
        match = re.match(rf'^({IDENT})\s*:?=', _flatten(chunk))
        if match:
            name = match.group(1).lower()
            assigned[name] = assigned.get(name, 0) + 1

    stats = {'vars': 0, 'attrs': 0, 'skipped': [], 'calls': []}
    out = []

    for chunk, is_code in _statements(src):
        if not is_code:
            out.append(chunk)
            continue
        flat = _flatten(chunk)

        if re.match(r'^call\b', flat, re.I):
            stats['calls'].append(flat[:80])
            out.append(chunk)
            continue

        match = re.match(rf'^({IDENT})\s*=([^=].*)$', flat)
        if match:
            name, rhs = match.group(1), match.group(2)
            reason = _why_not_deferrable(name, rhs, assigned)
            if reason:
                stats['skipped'].append(f'{name} ({reason})')
                out.append(chunk)
            else:
                stats['vars'] += 1
                out.append(chunk.replace('=', ':=', 1))
            continue

        match = re.match(rf'^({IDENT}\$?)\s*:\s*({IDENT})\b', flat)
        if match and match.group(2).upper() not in NON_ELEMENT_TYPES:
            out.append(ATTRIBUTE.sub(lambda m: _defer_attribute(m, stats), chunk))
            continue

        out.append(chunk)

    return ''.join(out), stats


def _why_not_deferrable(name: str, rhs: str, assigned: dict) -> str:
    """Reason this assignment must stay immediate, or '' if it may be deferred."""
    if assigned.get(name.lower(), 0) > 1:
        return 'reassigned'
    if re.search(rf'\b{re.escape(name)}\b', rhs, re.I):
        return 'self-referential'
    if rhs.strip().lower() in BOOLEANS:
        return 'boolean rhs'
    if VOLATILE.search(rhs):
        return 'volatile rhs'
    if not ARITHMETIC.match(rhs):
        return 'non-arithmetic rhs'
    return ''


def _defer_attribute(match: re.Match, stats: dict) -> str:
    prefix, value = match.group(1), match.group(2)
    name = prefix.lstrip(', ').strip().lower()
    if name in STRING_ATTRIBUTES or value.strip().lower() in BOOLEANS:
        return match.group(0)
    if VOLATILE.search(value) or not ARITHMETIC.match(value):
        return match.group(0)
    stats['attrs'] += 1
    return f'{prefix}:={value}'


def _self_check():
    """Each guard, against the construct that motivated it."""
    text, stats = to_deferred('A = 1;\nB = A * 2;\n')
    assert text == 'A := 1;\nB := A * 2;\n', text
    assert stats['vars'] == 2 and not stats['skipped']

    # Element attributes are deferred; LINE and SEQUENCE are not.
    text, stats = to_deferred('Q1 : QUADRUPOLE, L = LQ, K1 = G1;')
    assert text == 'Q1 : QUADRUPOLE, L := LQ, K1 := G1;', text
    assert stats['attrs'] == 2
    for untouched in ('RING : LINE = (Q1, Q2);', 'S : SEQUENCE, L = 10;'):
        assert to_deferred(untouched)[0] == untouched

    # Commands keep their '=' -- ':=' is not valid syntax there.
    for command in ('OPTION, ECHO = FALSE;', 'USE, SEQUENCE = FULL;',
                    'BEAM, PC = E_MOMENTUM;', 'TWISS, BETX = 1.1, FILE = "o.dat";'):
        assert to_deferred(command)[0] == command, command

    # Loop and macro bodies are procedural, not functional.
    loop = 'N = 0;\nWHILE (N < 3) {\n  X = TGAUSS(4);\n  N = N + 1;\n}\n'
    text, _ = to_deferred(loop)
    assert 'X := TGAUSS' not in text and 'N := N + 1' not in text, text
    assert text.startswith('N := 0;'), text

    # Self-reference, volatility and reassignment, each at top level.
    _, stats = to_deferred('N = N + 1;')
    assert stats['skipped'] == ['N (self-referential)'], stats
    _, stats = to_deferred('X = TGAUSS(4);')
    assert stats['skipped'] == ['X (volatile rhs)'], stats
    _, stats = to_deferred('P = 1;\nP = 2;')
    assert stats['skipped'] == ['P (reassigned)', 'P (reassigned)'], stats

    # Boolean flags are not formulas, and look exactly like variable names.
    _, stats = to_deferred('MAKEDIPEDGE = FALSE;')
    assert stats['skipped'] == ['MAKEDIPEDGE (boolean rhs)'], stats

    # Non-arithmetic right-hand sides stay put, as values and as attributes.
    _, stats = to_deferred('TITLE = "a ring";')
    assert stats['skipped'] == ['TITLE (non-arithmetic rhs)'], stats
    # APERTYPE and FROM are keyword-valued and look exactly like variables.
    text, stats = to_deferred(
        'C1 : COLLIMATOR, APERTYPE = ELLIPSE, FROM = M1, TYPE = "x", L = LC;')
    assert 'APERTYPE = ELLIPSE' in text and 'FROM = M1' in text, text
    assert 'TYPE = "x"' in text and 'L := LC' in text, text
    assert stats['attrs'] == 1, stats

    # Already-deferred statements are left exactly as they are.
    assert to_deferred('SIG_X := SQRT(E_EX * BETX);')[0] == 'SIG_X := SQRT(E_EX * BETX);'

    # CALLed files are reported, not rewritten.
    _, stats = to_deferred('CALL, FILE = "other.madx";')
    assert len(stats['calls']) == 1, stats

    # Comments, blank lines and indentation survive verbatim.
    source = '// header\n\n  A = 1;  // trailing\n'
    assert to_deferred(source)[0] == '// header\n\n  A := 1;  // trailing\n'

    print('madx_deferred self-check passed')


if __name__ == '__main__':
    _self_check()
