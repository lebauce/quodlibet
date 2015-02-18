# -*- coding: utf-8 -*-
# Copyright 2014 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

# A simple top-down parser for the query grammar. It's basically textbook,
# but it could use some cleaning up. It builds the requisite match.*
# objects as it goes, which is where the interesting stuff will happen.

"""
Ways to let ASCII characters match other unicode characters which
can be decomposed into one ASCII character and one or more combining
diacritic marks. This allows to match e.g. "Múm" using "Mum".

re_add_diacritic_variants(u"Mum") =>
    u"[MḾṀṂ][uùúûüũūŭůűųưǔǖǘǚǜȕȗṳṵṷṹṻụủứừửữự][mḿṁṃ]"
"""

import sre_parse
import unicodedata
import sys

from quodlibet.util import re_escape


_DIACRITIC_CACHE = {
    u'\u0300': (u'AEINOUWYaeinouwy\u0391\u0395\u0397\u0399\u039f\u03a5\u03a9'
                u'\u03b1\u03b5\u03b7\u03b9\u03bf\u03c5\u03c9\u0415\u0418'
                u'\u0435\u0438'),
    u'\u0300\u0345': u'\u03b1\u03b7\u03c9',
    u'\u0301': (u'ACEGIKLMNOPRSUWYZacegiklmnoprsuwyz\xc6\xd8\xe6\xf8\u0391'
                u'\u0395\u0397\u0399\u039f\u03a5\u03a9\u03b1\u03b5\u03b7'
                u'\u03b9\u03bf\u03c5\u03c9\u0413\u041a\u0433\u043a'),
    u'\u0301\u0307': u'Ss',
    u'\u0301\u0345': u'\u03b1\u03b7\u03c9',
    u'\u0302': u'ACEGHIJOSUWYZaceghijosuwyz',
    u'\u0302\u0300': u'AEOaeo',
    u'\u0302\u0301': u'AEOaeo',
    u'\u0302\u0303': u'AEOaeo',
    u'\u0302\u0309': u'AEOaeo',
    u'\u0303': u'AEINOUVYaeinouvy',
    u'\u0303\u0301': u'OUou',
    u'\u0303\u0304': u'Oo',
    u'\u0303\u0308': u'Oo',
    u'\u0304': (u'AEGIOUYaegiouy\xc6\xe6\u0391\u0399\u03a5\u03b1\u03b9'
                u'\u03c5\u0418\u0423\u0438\u0443'),
    u'\u0304\u0300': u'EOeo',
    u'\u0304\u0301': u'EOeo',
    u'\u0304\u0308': u'Uu',
    u'\u0306': (u'AEGIOUaegiou\u0391\u0399\u03a5\u03b1\u03b9\u03c5\u0410'
                u'\u0415\u0416\u0418\u0423\u0430\u0435\u0436\u0438\u0443'),
    u'\u0306\u0300': u'Aa',
    u'\u0306\u0301': u'Aa',
    u'\u0306\u0303': u'Aa',
    u'\u0306\u0309': u'Aa',
    u'\u0307': u'ABCDEFGHIMNOPRSTWXYZabcdefghmnoprstwxyz',
    u'\u0307\u0304': u'AOao',
    u'\u0308': (u'AEHIOUWXYaehiotuwxy\u0399\u03a5\u03b9\u03c5\u0406\u0410'
                u'\u0415\u0416\u0417\u0418\u041e\u0423\u0427\u042b\u042d'
                u'\u0430\u0435\u0436\u0437\u0438\u043e\u0443\u0447\u044b'
                u'\u044d\u0456\u04d8\u04d9\u04e8\u04e9'),
    u'\u0308\u0300': u'Uu\u03b9\u03c5',
    u'\u0308\u0301': u'IUiu\u03b9\u03c5',
    u'\u0308\u0304': u'AOUaou',
    u'\u0308\u030c': u'Uu',
    u'\u0308\u0342': u'\u03b9\u03c5',
    u'\u0309': u'AEIOUYaeiouy',
    u'\u030a': u'AUauwy',
    u'\u030a\u0301': u'Aa',
    u'\u030b': u'OUou\u0423\u0443',
    u'\u030c': u'ACDEGHIKLNORSTUZacdeghijklnorstuz\u01b7\u0292',
    u'\u030c\u0307': u'Ss',
    u'\u030f': u'AEIORUaeioru\u0474\u0475',
    u'\u0311': u'AEIORUaeioru',
    u'\u0313': (u'\u0391\u0395\u0397\u0399\u039f\u03a9\u03b1\u03b5\u03b7'
                u'\u03b9\u03bf\u03c1\u03c5\u03c9'),
    u'\u0313\u0300': (u'\u0391\u0395\u0397\u0399\u039f\u03a9\u03b1\u03b5'
                      u'\u03b7\u03b9\u03bf\u03c5\u03c9'),
    u'\u0313\u0300\u0345': u'\u0391\u0397\u03a9\u03b1\u03b7\u03c9',
    u'\u0313\u0301': (u'\u0391\u0395\u0397\u0399\u039f\u03a9\u03b1\u03b5'
                      u'\u03b7\u03b9\u03bf\u03c5\u03c9'),
    u'\u0313\u0301\u0345': u'\u0391\u0397\u03a9\u03b1\u03b7\u03c9',
    u'\u0313\u0342': u'\u0391\u0397\u0399\u03a9\u03b1\u03b7\u03b9\u03c5\u03c9',
    u'\u0313\u0342\u0345': u'\u0391\u0397\u03a9\u03b1\u03b7\u03c9',
    u'\u0313\u0345': u'\u0391\u0397\u03a9\u03b1\u03b7\u03c9',
    u'\u0314': (u'\u0391\u0395\u0397\u0399\u039f\u03a1\u03a5\u03a9\u03b1'
                u'\u03b5\u03b7\u03b9\u03bf\u03c1\u03c5\u03c9'),
    u'\u0314\u0300': (u'\u0391\u0395\u0397\u0399\u039f\u03a5\u03a9\u03b1'
                      u'\u03b5\u03b7\u03b9\u03bf\u03c5\u03c9'),
    u'\u0314\u0300\u0345': u'\u0391\u0397\u03a9\u03b1\u03b7\u03c9',
    u'\u0314\u0301': (u'\u0391\u0395\u0397\u0399\u039f\u03a5\u03a9\u03b1'
                      u'\u03b5\u03b7\u03b9\u03bf\u03c5\u03c9'),
    u'\u0314\u0301\u0345': u'\u0391\u0397\u03a9\u03b1\u03b7\u03c9',
    u'\u0314\u0342': (u'\u0391\u0397\u0399\u03a5\u03a9\u03b1\u03b7\u03b9'
                      u'\u03c5\u03c9'),
    u'\u0314\u0342\u0345': u'\u0391\u0397\u03a9\u03b1\u03b7\u03c9',
    u'\u0314\u0345': u'\u0391\u0397\u03a9\u03b1\u03b7\u03c9',
    u'\u031b': u'OUou',
    u'\u031b\u0300': u'OUou',
    u'\u031b\u0301': u'OUou',
    u'\u031b\u0303': u'OUou',
    u'\u031b\u0309': u'OUou',
    u'\u031b\u0323': u'OUou',
    u'\u0323': u'ABDEHIKLMNORSTUVWYZabdehiklmnorstuvwyz',
    u'\u0323\u0302': u'AEOaeo',
    u'\u0323\u0304': u'LRlr',
    u'\u0323\u0306': u'Aa',
    u'\u0323\u0307': u'Ss',
    u'\u0324': u'Uu',
    u'\u0325': u'Aa',
    u'\u0326': u'STst',
    u'\u0327': u'CDEGHKLNRSTcdeghklnrst',
    u'\u0327\u0301': u'Cc',
    u'\u0327\u0306': u'Ee',
    u'\u0328': u'AEIOUaeiou',
    u'\u0328\u0304': u'Oo',
    u'\u032d': u'DELNTUdelntu',
    u'\u032e': u'Hh',
    u'\u0330': u'EIUeiu',
    u'\u0331': u'BDKLNRTZbdhklnrtz',
    u'\u0342': u'\u03b1\u03b7\u03b9\u03c5\u03c9',
    u'\u0342\u0345': u'\u03b1\u03b7\u03c9',
    u'\u0345': u'\u0391\u0397\u03a9\u03b1\u03b7\u03c9'
}


def diacritic_for_letters(regenerate=False):
    """Returns a mapping for combining diacritic mark to ascii characters
    for which they can be used to combine to a single unicode char.

    (actually not ascii, but unicode from the Lu/Ll/Lt categories,
    but mainly ascii)

    Since this is quite expensive to compute, the result is a cached version
    unless regenerate != True. regenerate = True is used for unittests
    to validate the cache.
    """

    if not regenerate:
        return _DIACRITIC_CACHE

    d = {}
    for i in xrange(sys.maxunicode):
        u = unichr(i)
        n = unicodedata.normalize("NFKD", u)
        if len(n) <= 1:
            continue
        if unicodedata.category(u) not in ("Lu", "Ll", "Lt"):
            continue
        if not all(map(unicodedata.combining, n[1:])):
            continue
        d.setdefault(n[1:], set()).add(n[0])

    for k, v in d.items():
        d[k] = u"".join(sorted(v))

    return d


def generate_re_diacritic_mapping(_diacritic_for_letters):
    letter_to_variants = {}

    # combine combining characters with the ascii chars
    for dia, letters in _diacritic_for_letters.iteritems():
        for c in letters:
            unichar = unicodedata.normalize("NFKC", c + dia)
            letter_to_variants.setdefault(c, []).append(unichar)

    # create strings to replace ascii with
    for k, v in letter_to_variants.items():
        letter_to_variants[k] = u"".join(sorted(v))

    return letter_to_variants


def _fixup_literal(literal, in_seq, mapping):
    u = unichr(literal)
    if u in mapping:
        u = u + mapping[u]
    need_seq = len(u) > 1
    u = re_escape(u)
    if need_seq and not in_seq:
        u = u"[%s]" % u
    return u


def _fixup_not_literal(literal, mapping):
    u = unichr(literal)
    if u in mapping:
        u = u + mapping[u]
    u = re_escape(u)
    return u"[^%s]" % u


def _fixup_range(start, end, mapping):
    extra = []
    for i in xrange(start, end + 1):
        u = unichr(i)
        if u in mapping:
            extra.append(re_escape(mapping[u]))
    start = re_escape(unichr(start))
    end = re_escape(unichr(end))
    return u"%s%s-%s" % ("".join(extra), start, end)


def _construct_regexp(pattern, mapping):
    """Raises NotImplementedError"""

    parts = []

    for op, av in pattern:
        if op == "not_literal":
            parts.append(_fixup_not_literal(av, mapping))
        elif op == "literal":
            parts.append(_fixup_literal(av, False, mapping))
        elif op == "category":
            cats = {
                "category_word": u"\\w",
                "category_not_word": u"\\W",
                "category_digit": u"\\d",
                "category_not_digit": u"\\D",
                "category_space": u"\\s",
                "category_not_space": u"\\S",
            }
            try:
                parts.append(cats[av])
            except KeyError:
                raise NotImplementedError(av)
        elif op == "any":
            parts.append(u".")
        elif op == "negate":
            parts.append(u"^")
        elif op == "in":
            in_parts = []
            for entry in av:
                op, eav = entry
                if op == "literal":
                    in_parts.append(_fixup_literal(eav, True, mapping))
                else:
                    in_parts.append(_construct_regexp([entry], mapping))
            parts.append(u"[%s]" % (u"".join(in_parts)))
        elif op == "range":
            start, end = av
            parts.append(_fixup_range(start, end, mapping))
        elif op == "max_repeat" or op == "min_repeat":
            min_, max_, pad = av
            pad = _construct_regexp(pad, mapping)
            if min_ == 1 and max_ == sre_parse.MAXREPEAT:
                parts.append(u"%s+" % pad)
            elif min_ == 0 and max_ == sre_parse.MAXREPEAT:
                parts.append(u"%s*" % pad)
            elif min_ == 0 and max_ == 1:
                parts.append(u"%s?" % pad)
            else:
                parts.append(u"%s{%d,%d}" % (pad, min_, max_))
            if op == "min_repeat":
                parts[-1] = parts[-1] + u"?"
        elif op == "at":
            ats = {
                "at_beginning": u"^",
                "at_end": u"$",
                "at_beginning_string": u"\\A",
                "at_boundary": u"\\b",
                "at_non_boundary": u"\\B",
                "at_end_string": u"\\Z",
            }
            try:
                parts.append(ats[av])
            except KeyError:
                raise NotImplementedError(av)
        elif op == "subpattern":
            group, pad = av
            pad = _construct_regexp(pad, mapping)
            if group is None:
                parts.append(u"(?:%s)" % pad)
            else:
                parts.append(u"(%s)" % pad)
        elif op == "assert":
            direction, pad = av
            pad = _construct_regexp(pad, mapping)
            if direction == 1:
                parts.append(u"(?=%s)" % pad)
            elif direction == -1:
                parts.append(u"(?<=%s)" % pad)
            else:
                raise NotImplementedError(direction)
        elif op == "assert_not":
            direction, pad = av
            pad = _construct_regexp(pad, mapping)
            if direction == 1:
                parts.append(u"(?!%s)" % pad)
            elif direction == -1:
                parts.append(u"(?<!%s)" % pad)
            else:
                raise NotImplementedError(direction)
        elif op == "branch":
            dummy, branches = av
            branches = map(lambda b: _construct_regexp(b, mapping), branches)
            parts.append(u"%s" % (u"|".join(branches)))
        else:
            raise NotImplementedError(op)

    return u"".join(parts)


def re_replace_literals(text, mapping):
    """Raises NotImplementedError or re.error"""

    assert isinstance(text, unicode)

    pattern = sre_parse.parse(text)
    return _construct_regexp(pattern, mapping)


# use _DIACRITIC_CACHE and create a lookup table
_diacritic_mapping = generate_re_diacritic_mapping(
    diacritic_for_letters(regenerate=False))


def re_add_diacritic_variants(text):
    """Will replace all occurrences of ascii chars
    by a bracket expression containing the character and all its
    variants with a diacritic mark.

    "föhn" -> "[fḟ]ö[hĥȟḣḥḧḩḫẖ][nñńņňǹṅṇṉṋ]"

    In case the passed in regex is invalid raises re.error.

    Supports all regexp except ones with group references. In
    case something is not supported NotImplementedError gets raised.
    """

    assert isinstance(text, unicode)

    return re_replace_literals(text, _diacritic_mapping)
