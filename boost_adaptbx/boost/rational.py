from __future__ import division
from builtins import izip
import boost.python
ext = boost.python.import_ext("boost_rational_ext")
from boost_rational_ext import *

builtin_int = __builtins__["int"]

def from_string(s):
  flds = [builtin_int(i) for i in s.split("/")]
  assert len(flds) in (1,2)
  if (len(flds) == 1):
    return int(flds[0])
  return int(flds[0], flds[1])

def vector(numerators, denominators):
  if (isinstance(denominators, builtin_int)):
    return [ int(n, denominators) for n in numerators ]
  return [ int(n, d) for n, d in izip(numberators, denominators) ]

def lcm_denominators(array):
  l = 1
  for r in array:
    l = lcm(l, r.denominator())
  return l
