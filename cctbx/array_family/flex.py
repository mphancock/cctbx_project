from __future__ import absolute_import, division, print_function
import scitbx.array_family.flex

import boost_adaptbx.python
ext_ = boost_adaptbx.python.import_ext("cctbx_array_family_flex_ext")
from scitbx_array_family_flex_ext import *
from cctbx_array_family_flex_ext import *
ext = ext_
del ext_

scitbx.array_family.flex.export_to("cctbx.array_family.flex")
