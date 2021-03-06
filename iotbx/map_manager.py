from __future__ import absolute_import, division, print_function
from libtbx.utils import to_str, null_out
from libtbx import group_args
from libtbx import group_args, Auto
from libtbx.test_utils import approx_equal
import sys
import io
from cctbx import miller
from iotbx.mrcfile import map_reader, write_ccp4_map
from scitbx.array_family import flex
from scitbx.matrix import col
from cctbx import maptbx
from cctbx import miller
import mmtbx.ncs.ncs
from copy import deepcopy

class map_manager(map_reader, write_ccp4_map):

  '''
   map_manager, includes map_reader and write_ccp4_map

   This class is intended to be the principal mechanism for reading
   and writing map information.  It is intended to be used by the
   iotbx.data_manager for both of these purposes.

   Use map_manager to read, write, and carry information about
   one map.  Map_manager keeps track of the origin shifts and also the
   original full unit cell and cell dimensions.  It writes out the map
   in the same place as it was read in.

   Note on wrapping:  Wrapping means that the map value outside the map
   boundaries can be obtained as the value inside the boundaries, (translated
   by some multiple of the unit cell translations.)  Normally crystallographic
   maps can be wrapped and cryo EM maps cannot.

   Wrapping should be specified on initialization if not read from a file. If
   read from a file, the value from the file labels is used if available,
   otherwise it is assumed to be wrapping = False unless specified (normal
   for a cryo-EM map. If not specified at all, it will need to be specified
   before a map_model_manager is created or the map_manager is written out.

   Map_manager also keeps track of any changes in magnification. These
   are reflected in changes in unit_cell and crystal_symmetry cell dimensions
   and angles.

   You normally create a new map_manager by initializing map_manager with a
   file name.  Then you apply the shift_origin() method and the map is
   shifted to place the origin at (0, 0, 0) and the original origin is
   recorded as self.origin_shift_grid_units.

   You can also create a map_manager with a map_data object (3D flex.double()
   array) along with the meta-data below.

   NOTE: MRC Maps may not represent the entire unit cell.  Normally maps that
    have an origin (corner with minimum i, j, k) that is not zero will be
    shifted at a later stage to have the origin at (0, 0, 0), along with
    any models and ncs objects (typically done with iotbx.map_and_model).
    To be able to write out a map in the same place as it was read in
    after shifting the origin and/or boxing the map, you need to keep track
    of 3 things.  These are:
    1. unit_cell_grid: grid representing one full unit cell as read in.
        Saved in map_manager as self.unit_cell_grid
    2. unit_cell_crystal_symmetry: dimensions and space group of full unit cell
        Saved in map_manager as self._unit_cell_crystal_symmetry
    3. origin_shift_grid_units: the shift in grid units to apply to the
       working map to superimpose it on the original map. When you read the
       map in this is (0, 0, 0). If you shift the map origin from (i, j, k) to
       (0, 0, 0) then the origin_shift_grid_units is (i, j, k).
         Saved in map_manager as self.origin_shift_grid_units

   Magnification (pixel size scaling) of a map: there is no general parameter
   describing magnification of an MRC map.  Changes in scaling are
   recorded in map_manager as changes in the scaling matrix/translation that
   relates grid points in a map to real-space position.

   Normal usage (NOTE: read/write should normally be done through data_manager):

     Read in a map:
       mm = map_manager('input_map.mrc')
     Summarize:
       mm.show_summary()

     Normally shift origin of map to (0, 0, 0) (you can do this here
         or you can use iotbx.map_and_model to shift models and maps together):
       mm.shift_origin()

     Get the map_data (shifted if origin was shifted above):
       map_data = mm.map_data()

     Get the crystal_symmetry of the box of data that is present:
       cs = mm.crystal_symmetry()

     Get the crystal_symmetry of the whole unit cell (even if not present):
       unit_cell_cs = mm.unit_cell_crystal_symmetry()

     Write out the map in map_data() in original location:
       mm.write_map(file_name = 'output_map.ccp4')

   --------     CONVENTIONS  --------------
   See http://www.ccpem.ac.uk/mrc_format/mrc2014.php for MRC format
   See https://pypi.org/project/mrcfile/ for mrcfile library documentation

   Same conventions as iotbx.ccp4_map

   Default is to write maps with INTERNAL_STANDARD_ORDER of axes of [3, 2, 1]
     corresponding to columns in Z, rows in Y, sections in X to match
     flex array layout.  This can be modified by changing the values in
     output_axis_order.

   Hard-wired to convert input maps of any order to
     INTERNAL_STANDARD_ORDER = [3, 2, 1] before conversion to flex arrays
     This is not modifiable.

    INTERNAL_STANDARD_ORDER = [3, 2, 1]

  Standard limitations and associated message.
  These can be checked with: limitations = mrc.get_limitations()
    which returns a group_args object with a list of limitations and a list
    of corresponding error messages, or None if there are none
    see phenix.show_map_info for example
  These limitations can also be accessed with specific calls placed below:
   For example:
   mrc.can_be_sharpened()  returns False if "extract_unique" is present

  Map labels that are not limitations can be accessed with:
      additional_labels = mrc.get_additional_labels()

  STANDARD_LIMITATIONS_DICT = {
    "extract_unique":
     "This map is masked around unique region and not suitable for auto-sharpening.",
    "map_is_sharpened":
     "This map is auto-sharpened and not suitable for further auto-sharpening.",
    "map_is_density_modified": "This map has been density modified.",
     }


   NOTES ON ORDER OF AXES

    Phenix standard order is 3, 2, 1 (columns Z, rows Y, sections in X).
        Convert everything to this order.

    This is the order that allows direct conversion of a numpy 3D array
     with axis order (mapc, mapr, maps) to a flex array.

    For reverse = True, supply order that converts flex array to numpy 3D array
     with order (mapc, mapr, maps)

    Note that this does not mean input or output maps have to be in this order.
     It just means that before conversion of numpy to flex or vice-versa
     the array has to be in this order.

     Note that MRC standard order for input/ouput is 1, 2, 3.

     NOTE: numpy arrays indexed from 0 so this is equivalent to
      order of 2, 1, 0 in the numpy array

    NOTE:  MRC format allows data axes to be swapped using the header
      mapc mapr and maps fields. However the mrcfile library does not
      attempt to swap the axes and assigns the columns to X, rows to Y and
      sections to Z. The data array is indexed C-style, so data values can
      be accessed using mrc.data[z][y][x].

    NOTE: normal expectation is that phenix will read/write with the
      order 3, 2, 1. This means X-sections (index = 3), Y rows (index = 2),
      Z columns (index = 1). This correxponds to
       mapc (columns) =   3 or Z
       mapr (rows)    =   2 or Y
       maps (sections) =  1 or X

    In the numpy array (2, 1, 0 instead of 3, 2, 1):

    To transpose, specify i0, i1, i2 where:
        i0 = 2 means input axis 0 becomes output axis 2
        NOTE:  axes are 0, 1, 2 etc, not 1, 2, 3
      Examples:
        np.transpose(a, (0, 1, 2))  does nothing
        np.transpose(a, (1, 2, 0)) output axis 0 is input axis 1



    We want output axes to always be 2, 1, 0 and input axes for numpy array are
      (mapc-1, mapr-1, maps-1):

    For example, in typical phenix usage, the transposition is:
      i_mapc = 3    i_mapc_np = 2
      i_mapr = 2    i_mapr_np = 1
      i_maps = 1    i_maps_np = 0

   --------     END CONVENTIONS  --------------

  '''


  def __init__(self,
     file_name = None,  # USUAL: Initialize from file and specify wrapping
     map_data = None,   # OR map_data, unit_cell_grid, unit_cell_crystal_symmetry
     unit_cell_grid = None,
     unit_cell_crystal_symmetry = None,
     origin_shift_grid_units = None, # OPTIONAL first point in map in full cell
     ncs_object = None, # OPTIONAL ncs_object with map symmetry
     wrapping = Auto,   # OPTIONAL but recommended if not read from file
     log = None,
     ):

    '''
      Allows reading a map file or initialization with map_data

      Normally call with file_name to read map file in CCP4/MRC format.

      Alternative is initialize with map_data and metadata
       Required: specify map_data, unit_cell_grid, unit_cell_crystal_symmetry
       Optional: specify origin_shift_grid_units

      Optional in either case: supply ncs_object with map symmetry of full map

      NOTE on "crystal_symmetry" objects
      There are two objects that are "crystal_symmetry" objects:
      A.  unit_cell_crystal_symmetry():  This is the symmetry of the
        entire unit cell. It can be any space group. The dimensions
        correspond to the dimensions of unit_cell_grid.

      B.  crystal_symmetry():  This is the symmetry of the part of the map
        that is present.  If the entire map is present, this can be any
        space group. Otherwise it is set to P 1 (no symmetry other than unity).
        The dimensions correspond to the dimensions of the map_data.all().

      NOTE: As of 2020-05-22 both map_reader and map_manager ALWAYS convert
      map_data to flex.double.

      Map_manager does not save any extra information about
      the map except the details specified in this __init__.

      After reading you can access map data with self.map_data()
        and other attributes (see class utils in ccp4_map/__init__py)
    '''

    assert (file_name is not None) or [map_data,unit_cell_grid,
        unit_cell_crystal_symmetry].count(None)==0

    assert (ncs_object is None) or isinstance(ncs_object, mmtbx.ncs.ncs.ncs)
    assert (wrapping is Auto) or isinstance(wrapping, bool)

    if origin_shift_grid_units is not None:
      origin_shift_grid_units = tuple(origin_shift_grid_units)
      assert len(origin_shift_grid_units) ==3

    # Initialize log filestream
    self.set_log(log)


    # NOTE: If you add anything here to be initialized, add it to the
    #  customized_copy method

    # Initialize that we don't have crystal_symmetry:
    self._crystal_symmetry = None

    # Initialize mask to be not present
    self._created_mask = None

    # Initialize that this is not a mask
    self._is_mask = False

    # Initialize program_name, limitations, labels
    self.file_name = file_name # input file (source of this manager)
    self.program_name = None  # Name of program using this manager
    self.limitations = None  # Limitations from STANDARD_LIMITATIONS_DICT
    self.labels = None  # List of labels (usually from input file) to be written

    # Initialize wrapping
    self._wrapping = None
    self._cannot_figure_out_wrapping = None

    # Initialize ncs_object
    self._ncs_object = ncs_object

    # Initialize origin shift representing position of original origin in
    #  grid units.  If map is shifted, this is updated to reflect where
    #  to place current origin to superimpose map on original map.

    # Usual initialization with a file

    if self.file_name is not None:
      self._read_map()
      # Sets self.unit_cell_grid, self._unit_cell_crystal_symmetry, self.data,
      #  self._crystal_symmetry.  Sets also self.external_origin

      # read_map does not set self.origin_shift_grid_units. Set them here:

      # Set starting values:
      self.origin_shift_grid_units = (0, 0, 0)

      # Assume this map is not wrapped unless wrapping is set
      if isinstance(wrapping, bool):  # Take it...
        self._wrapping = wrapping
      elif self.wrapping_from_input_file() is not None:
        self._wrapping = self.wrapping_from_input_file()
      else:
        self._wrapping = False

    else:
      '''
         Initialization with map_data object and metadata
      '''

      assert map_data and unit_cell_grid and unit_cell_crystal_symmetry
      # wrapping must be specified

      assert wrapping in [True, False]

      # Required initialization information:
      self.data = map_data
      self.unit_cell_grid = unit_cell_grid
      self._unit_cell_crystal_symmetry = unit_cell_crystal_symmetry
      self._wrapping = wrapping

      # Calculate values for self._crystal_symmetry
      # Must always run this method after changing
      #    self._unit_cell_crystal_symmetry  or self.unit_cell_grid
      self.set_crystal_symmetry_of_partial_map()

      # Optional initialization information
      if origin_shift_grid_units is None:
        origin_shift_grid_units = (0, 0, 0)
      self.origin_shift_grid_units = origin_shift_grid_units

    # Initialization steps always done:

    # Make sure map is full size if wrapping is set
    if self._wrapping:
      assert self.is_full_size()

    # make sure labels are strings
    if self.labels is not None:
      self.labels = [to_str(label, codec = 'utf8') for label in self.labels]

  # prevent pickling error in Python 3 with self.log = sys.stdout
  # unpickling is limited to restoring sys.stdout
  def __getstate__(self):
    pickle_dict = self.__dict__.copy()
    if isinstance(self.log, io.TextIOWrapper):
      pickle_dict['log'] = None
    return pickle_dict

  def __setstate__(self, pickle_dict):
    self.__dict__ = pickle_dict
    if self.log is None:
      self.log = sys.stdout

  def __repr__(self):
    text = "Map manager (from %s)" %(self.file_name)+\
        "\n%s, \nUnit-cell grid: %s, (present: %s), origin shift %s " %(
      str(self.unit_cell_crystal_symmetry()).replace("\n"," "),
      str(self.unit_cell_grid),
      str(self.map_data().all()),
      str(self.origin_shift_grid_units)) + "\n"+\
      "Working coordinate shift %s" %( str(self.shift_cart()))
    if self._ncs_object:
      text += "\n%s" %str(self._ncs_object)
    return text


  def set_log(self, log = sys.stdout):
    '''
       Set output log file
    '''
    if log is None:
      self.log = null_out()
    else:
      self.log = log

  def _read_map(self):
      '''
       Read map using mrcfile/__init__.py
       Sets self.unit_cell_grid, self._unit_cell_crystal_symmetry, self.data
           self._crystal_symmetry
       Does not set self.origin_shift_grid_units
       Does set self.file_name
      '''
      self._print("Reading map from %s " %(self.file_name))

      self.read_map_file(file_name = self.file_name)  # mrcfile/__init__.py

  def _print(self, m):
    if (self.log is not None) and hasattr(self.log, 'closed') and (
        not self.log.closed):
      print(m, file = self.log)

  def set_unit_cell_crystal_symmetry(self, crystal_symmetry):
    '''
      Specify the dimensions and space group of unit cell.  This also changes
      the crystal_symmetry of the part that is present and the grid spacing.

      Purpose is to redefine the dimensions of the map without changing values
      of the map.  Normally used to correct the dimensions of a map
      where something was defined incorrectly.

      Does not change self.unit_cell_grid

       Fundamental parameters set:
        self._unit_cell_crystal_symmetry: dimensions of full unit cell
        self._crystal_symmetry: dimensions of part of unit cell that is present
    '''

    from cctbx import crystal
    assert isinstance(crystal_symmetry, crystal.symmetry)
    self._unit_cell_crystal_symmetry = crystal_symmetry

    # Always follow a set of _unit_cell_crystal_symmetry with this:
    self.set_crystal_symmetry_of_partial_map()

  def set_original_origin_and_gridding(self,
      original_origin = None,
      gridding = None):
    '''
       Specify the location in the full unit cell grid where the origin of
       the map that is present is to be placed to match its original position.
       This is referred to here as the "original" origin, as opposed to the
       current origin of this map.

       Note that this method does not actually shift the origin of the working
       map.  It just defines where that origin is going to be placed when
       restoring the map to its original position.

       Also optionally redefine the definition of the unit cell, keeping the
       grid spacing the same.

       This allows redefining the location of the map that is present
       within the full unit cell.  It also allows redefining the
       unit cell itself.  Only use this to create a new partial map
       in a defined location.

       Previous definition of the location of the map that is present
       is discarded.

       Fundamental parameters set:
        self.origin_shift_grid_units: shift to place origin in original location
        self._unit_cell_crystal_symmetry: dimensions of full unit cell
        self.unit_cell_grid: grid units of full unit cell

       At end, recheck wrapping
    '''
    if original_origin:
      if (self.origin_shift_grid_units !=  (0, 0, 0)) or (
          not self.origin_is_zero()):
        self.shift_origin()
        self._print("Previous origin shift of %s will be discarded" %(
          str(self.origin_shift_grid_units)))

      # Set the origin
      self.origin_shift_grid_units = original_origin
      self._print("New origin shift will be %s " %(
        str(self.origin_shift_grid_units)))

    if gridding: # reset definition of full unit cell.  Keep grid spacing

       # If gridding does not match original, set space group always to P1

       current_unit_cell_parameters = self.unit_cell_crystal_symmetry(
            ).unit_cell().parameters()
       current_unit_cell_grid = self.unit_cell_grid
       new_unit_cell_parameters = []
       for a, g, new_g in zip(
          current_unit_cell_parameters[:3], current_unit_cell_grid, gridding):
         new_a = a*new_g/g
         new_unit_cell_parameters.append(new_a)

       unit_cell_parameters = \
          new_unit_cell_parameters+list(current_unit_cell_parameters[3:])

       if current_unit_cell_grid !=  gridding:
         space_group_number_use = 1
       else:
         space_group_number_use = \
            self._unit_cell_crystal_symmetry.space_group_number()
       from cctbx import crystal
       self._unit_cell_crystal_symmetry = crystal.symmetry(
          unit_cell_parameters, space_group_number_use)

       self.unit_cell_grid = gridding
       if current_unit_cell_grid !=  gridding:
         self._print ("Resetting gridding of full unit cell from %s to %s" %(
           str(current_unit_cell_grid), str(gridding)))
         self._print ("Resetting dimensions of full unit cell from %s to %s" %(
           str(current_unit_cell_parameters),
            str(new_unit_cell_parameters)))

       # Always run after setting unit_cell_grid or _unit_cell_crystal_symmetry
       # This time it should not change anything
       original_crystal_symmetry = self.crystal_symmetry()
       self.set_crystal_symmetry_of_partial_map()
       new_crystal_symmetry = self.crystal_symmetry()
       assert original_crystal_symmetry.is_similar_symmetry(
         new_crystal_symmetry)

       if not self.is_full_size():
         self.set_wrapping(False)

  def is_mask(self):
    ''' Is this a mask '''
    return self._is_mask

  def set_is_mask(self, value=True):
    ''' define if this is a mask'''
    assert isinstance(value, bool)
    self._is_mask = value

  def origin_is_zero(self):
    if self.map_data().origin() == (0, 0, 0):
      return True
    else:
      return False

  def shift_origin(self, desired_origin = (0, 0, 0)):
    '''
    Shift the origin of the map to desired_origin
        (normally desired_origin = (0, 0, 0) and update origin_shift_grid_units

    Origin is the value of self.map_data().origin()
    origin_shift_grid_units is the shift to apply to self.map_data() to
      superimpose it on the original map.

    If you shift the origin by (i, j, k) then add -(i, j, k) to
      the current origin_shift_grid_units.

    If current origin is at (a, b, c) and
       desired origin = (d, e, f) and
       existing origin_shift_grid_units is (g, h, i):

    the shift to make is  (d, e, f) - (a, b, c)

    the new value of origin_shift_grid_units will be:
       (g, h, i)+(a, b, c)-(d, e, f)
       or new origin_shift_grid_units is: (g, h, i)- shift

    the new origin of map_data will be (d, e, f)

    '''

    if(self.map_data() is None): return

    # Figure out what the shifts are (in grid units)
    shift_info = self._get_shift_info(desired_origin = desired_origin)

    # Update the value of origin_shift_grid_units
    #  This is position of the origin of the new map in the full unit cell grid
    self.origin_shift_grid_units = shift_info.new_origin_shift_grid_units

    # Shift map_data if necessary
    if shift_info.shift_to_apply !=  (0, 0, 0):
      # map will start at desired_origin and have current size:
      acc = flex.grid(shift_info.desired_origin, shift_info.new_end)
      self.map_data().reshape(acc)

    # Checks
    new_current_origin = self.map_data().origin()
    assert new_current_origin == shift_info.desired_origin

    assert add_tuples_int(shift_info.current_origin, shift_info.shift_to_apply
        ) == shift_info.desired_origin

    # Original location of first element of map should agree with previous

    assert shift_info.map_corner_original_location  ==  add_tuples_int(
       new_current_origin, self.origin_shift_grid_units)

    # If there is an associated ncs_object, shift it too
    if self._ncs_object:
      self._ncs_object=self._ncs_object.coordinate_offset(shift_info.shift_to_apply_cart)

  def _get_shift_info(self, desired_origin = None):
    '''
      Utility to calculate the shift necessary (grid units)
      map to place the origin of the current map
      at the position defined by desired_origin.
      See definitions in shift_origin method.

    '''
    if(desired_origin is None):
      desired_origin = (0, 0, 0)
    desired_origin = tuple(desired_origin)

    if(self.origin_shift_grid_units is None):
      self.origin_shift_grid_units = (0, 0, 0)

    # Current origin and shift to apply
    current_origin = self.map_data().origin()

    # Original location of first element of map
    map_corner_original_location = add_tuples_int(current_origin,
         self.origin_shift_grid_units)

    shift_to_apply = subtract_tuples_int(desired_origin, current_origin)

    assert add_tuples_int(current_origin, shift_to_apply) == desired_origin

    new_origin_shift_grid_units = subtract_tuples_int(
        self.origin_shift_grid_units, shift_to_apply)

    current_end = add_tuples_int(current_origin, self.map_data().all())
    new_end = add_tuples_int(desired_origin, self.map_data().all())

    shift_to_apply_cart = self.grid_units_to_cart(shift_to_apply)

    shift_info = group_args(
      map_corner_original_location = map_corner_original_location,
      current_origin = current_origin,
      current_end = current_end,
      current_origin_shift_grid_units = self.origin_shift_grid_units,
      shift_to_apply = shift_to_apply,
      desired_origin = desired_origin,
      new_end = new_end,
      new_origin_shift_grid_units = new_origin_shift_grid_units,
      shift_to_apply_cart = shift_to_apply_cart,
       )
    return shift_info

  def shift_origin_to_match_original(self):
    '''
     Shift origin by self.origin_shift_grid_units to place origin in its
     original location
    '''
    original_origin = add_tuples_int(self.map_data().origin(),
                               self.origin_shift_grid_units)

    self.shift_origin(desired_origin = original_origin)

  def set_ncs_object(self, ncs_object):
    '''
      set the ncs object for this map_manager.  Incoming ncs_object must
     be compatible (shift_cart values must match).  Incoming ncs_object is
     deep_copied.
    '''
    assert isinstance(ncs_object, mmtbx.ncs.ncs.ncs)
    assert self.is_compatible_ncs_object(ncs_object)
    self._ncs_object = deepcopy(ncs_object)

  def set_program_name(self, program_name = None):
    '''
      Set name of program doing work on this map_manager for output
      (string)
    '''
    self.program_name = program_name
    self._print("Program name of %s added" %(program_name))

  def add_limitation(self, limitation = None):
    '''
      Add a limitation from STANDARD_LIMITATIONS_DICT
      Supply the key (such as "map_is_sharpened")
    '''
    from iotbx.mrcfile import STANDARD_LIMITATIONS_DICT
    assert limitation in list(STANDARD_LIMITATIONS_DICT.keys())

    if not self.limitations:
      self.limitations = []
    self.limitations.append(limitation)
    self._print("Limitation of %s ('%s') added to map_manager" %(
      limitation, STANDARD_LIMITATIONS_DICT[limitation]))

  def add_label(self, label = None, verbose = False):
    '''
     Add a label (up to 80-character string) to write to output map.
     Default is to specify the program name and date
    '''
    if not self.labels:
      self.labels = []
    if len(label)>80:  label = label[:80]
    self.labels.reverse()  # put at beginning
    self.labels.append(to_str(label, codec = 'utf8')) # make sure it is a string
    self.labels.reverse()
    if verbose:
      self._print("Label added: %s " %(label))

  def write_map(self, file_name):

    '''
      Simple version of write

      file_name is output file name
      map_data is map_data object with 3D values for map. If not supplied,
        use self.map_data()

      Normally call with file_name (file to be written)
      Output labels are generated from existing self.labels,
      self.program_name, and self.limitations

    '''

    # Make sure we have map_data
    assert self.map_data()

    map_data = self.map_data()

    assert isinstance(self.wrapping(), bool)  # need wrapping set to write file
    # remove any labels about wrapping
    for key in ["wrapping_outside_cell","no_wrapping_outside_cell"]:
      self.remove_limitation(key)
    # Add limitation on wrapping
    new_labels=[]
    if self.wrapping():
      self.add_limitation("wrapping_outside_cell")
    else:
      self.add_limitation("no_wrapping_outside_cell")


    from iotbx.mrcfile import create_output_labels
    labels = create_output_labels(
      program_name = self.program_name,
      input_file_name = self.file_name,
      input_labels = self.labels,
      limitations = self.limitations)

    crystal_symmetry = self.unit_cell_crystal_symmetry()
    unit_cell_grid = self.unit_cell_grid
    origin_shift_grid_units = self.origin_shift_grid_units

    if map_data.origin()  ==  (0, 0, 0):  # Usual
      self._print("Writing map with origin at %s and size of %s to %s" %(
        str(origin_shift_grid_units), str(map_data.all()), file_name))
      from six.moves import StringIO
      f=StringIO()
      write_ccp4_map(
        file_name   = file_name,
        crystal_symmetry = crystal_symmetry, # unit cell and space group
        map_data    = map_data,
        unit_cell_grid = unit_cell_grid,  # optional gridding of full unit cell
        origin_shift_grid_units = origin_shift_grid_units, # optional origin shift
        labels      = labels,
        out = f)
      self._print(f.getvalue())
    else: # map_data has not been shifted to (0, 0, 0).  Shift it and then write
          # and then shift back
      self._print("Writing map after shifting origin")
      if self.origin_shift_grid_units and origin_shift_grid_units!= (0, 0, 0):
        self._print (
          "WARNING: map_data has origin at %s " %(str(map_data.origin()))+
         " and this map_manager will apply additional origin shift of %s " %(
          str(self.origin_shift_grid_units)))

      # Save where we are
      current_origin = map_data.origin()

      # Set origin at (0, 0, 0)
      self.shift_origin(desired_origin = (0, 0, 0))
      self.write_map(file_name = file_name)
      self.shift_origin(desired_origin = current_origin)

  def create_mask_with_map_data(self, map_data):
    '''
      Set mask to be map_data

      Does not apply the mask (use apply_mask_to_map etc for that)

      Uses cctbx.maptbx.mask.create_mask_with_mask_data to do it

      Requires origin to be zero of both self and new mask
    '''

    assert isinstance(map_data, flex.double)
    assert self.map_data().all() == map_data.all()
    assert map_data.origin() == (0,0,0)
    assert self.origin_is_zero()

    from cctbx.maptbx.mask import create_mask_with_map_data as cm
    self._created_mask = cm(map_data = map_data,
      map_manager = self)


  def create_mask_around_density(self,
      resolution,
      molecular_mass = None,
      sequence = None,
      solvent_content = None):
    '''
      Use cctbx.maptbx.mask.create_mask_around_density to create a
       mask automatically

      Does not apply the mask (use apply_mask_to_map etc for that)

      Parameters are:
       resolution : required resolution of map
       molecular_mass: optional mass (Da) of object in density
       sequence: optional sequence of object in density
       solvent_content : optional solvent_content of map


    '''

    assert resolution is not None

    from cctbx.maptbx.mask import create_mask_around_density as cm
    self._created_mask = cm(map_manager = self,
        resolution = resolution,
        molecular_mass = molecular_mass,
        sequence = sequence,
        solvent_content = solvent_content, )

  def create_mask_around_edges(self, soft_mask_radius):
    '''
      Use cctbx.maptbx.mask.create_mask_around_edges to create a mask around
      edges of map.  Does not make a soft mask.  For a soft mask,
      follow with soft_mask(soft_mask_radius =soft_mask_radius)
      The radius is to define the boundary around the map.

      Does not apply the mask (use apply_mask_to_map etc for that)
    '''

    assert soft_mask_radius is not None

    from cctbx.maptbx.mask import create_mask_around_edges as cm
    self._created_mask = cm(map_manager = self,
      soft_mask_radius = soft_mask_radius)

  def create_mask_around_atoms(self, model, mask_atoms_atom_radius):
    '''
      Use cctbx.maptbx.mask.create_mask_around_atoms to create a mask around
      atoms in model

      Does not apply the mask (use apply_mask_to_map etc for that)
    '''

    assert model is not None
    assert mask_atoms_atom_radius is not None

    from cctbx.maptbx.mask import create_mask_around_atoms as cm
    self._created_mask = cm(map_manager = self,
      model = model,
      mask_atoms_atom_radius = mask_atoms_atom_radius)

  def soft_mask(self, soft_mask_radius = None):
    '''
      Make mask a soft mask. Just uses method in create_mask_around_atoms
    '''
    assert self._created_mask is not None
    self._created_mask.soft_mask(soft_mask_radius = soft_mask_radius)

  def apply_mask(self, set_outside_to_mean_inside = False):
    '''
      Replace map_data with masked version based on current mask
      Just uses method in create_mask_around_atoms
    '''

    assert self._created_mask is not None
    new_mm = self._created_mask.apply_mask_to_other_map_manager(
      other_map_manager = self,
      set_outside_to_mean_inside = set_outside_to_mean_inside)
    self.set_map_data(map_data = new_mm.map_data())  # replace map data

  def delete_mask(self):
    self._created_mask = None

  def get_mask_as_map_manager(self):
    assert self._created_mask is not None
    return self._created_mask.map_manager()

  def initialize_map_data(self, map_value = 0):
    '''
      Set all values of map_data to map_value
    '''
    s = (self.map_data() != map_value )
    self.map_data().set_selected(s, map_value)

  def set_map_data(self, map_data = None):
    '''
      Replace self.data with map_data. The two maps must have same gridding

      NOTE: This uses selections to copy all the data in map_data into
      self.data.  The map_data object is not associated with self.data, the
      data is simply copied.  Also as self.data is modified in place, any
      objects that currently are just pointers to self.data are affected.
    '''
    assert self.map_data().origin() == map_data.origin()
    assert self.map_data().all() == map_data.all()
    sel = flex.bool(map_data.size(), True)
    self.data.as_1d().set_selected(sel, map_data.as_1d())

  def as_full_size_map(self):
    '''
      Create a full-size map that with the current map inside it, padded by zero

      A little tricky because the starting map is going to have its origin at
      (0, 0, 0) but the map we are creating will have that point at
      self.origin_shift_grid_units.

      First use box.with_bounds to create map from -self.origin_shift_grid_units
       to -self.origin_shift_grid_units+self.unit_cell_grid-(1, 1, 1).  Then
      shift that map to place origin at (0, 0, 0)

      If the map is full size already, return the map as is
      If the map is bigger than full size stop as this is not suitable

    '''

    # Check to see if this is full size or bigger
    full_size_minus_working=subtract_tuples_int(self.unit_cell_grid,
      self.map_data().all())

    # Must not be bigger than full size already
    assert flex.double(full_size_minus_working).min_max_mean().min >= 0

    if full_size_minus_working == (0, 0, 0): # Exactly full size already. Done
      assert self.origin_shift_grid_units == (0, 0, 0)
      assert self.map_data().origin() == (0, 0, 0)
      return self
    working_lower_bounds = self.origin_shift_grid_units
    working_upper_bounds = tuple([i+j-1 for i, j in zip(working_lower_bounds,
      self.map_data().all())])
    lower_bounds = tuple([-i for i in self.origin_shift_grid_units])
    upper_bounds = tuple([i+j-1 for i, j in zip(lower_bounds, self.unit_cell_grid)])
    new_lower_bounds = tuple([i+j for i, j in zip(
      lower_bounds, self.origin_shift_grid_units)])
    new_upper_bounds = tuple([i+j for i, j in zip(
      upper_bounds, self.origin_shift_grid_units)])
    print("Creating full-size map padding outside of current map with zero",
      file = self.log)
    print("Bounds of current map: %s to %s" %(
     str(working_lower_bounds), str(working_upper_bounds)), file = self.log)
    print("Bounds of new map: %s to %s" %(
     str(new_lower_bounds), str(new_upper_bounds)), file = self.log)

    from cctbx.maptbx.box import with_bounds
    box = with_bounds(self,
       lower_bounds = lower_bounds,
       upper_bounds = upper_bounds,
       log = self.log)
    box.map_manager().set_original_origin_and_gridding(original_origin = (0, 0, 0))

    box.map_manager().add_label(
       "Restored full size from box %s - %s, pad with zero" %(
     str(working_lower_bounds), str(working_upper_bounds)))
    assert box.map_manager().origin_shift_grid_units == (0, 0, 0)
    assert box.map_manager().map_data().origin() == (0, 0, 0)
    assert box.map_manager().map_data().all() == box.map_manager().unit_cell_grid
    if box.map_manager().unit_cell_crystal_symmetry().space_group_number() == 1:
      assert box.map_manager().unit_cell_crystal_symmetry().is_similar_symmetry(
        box.map_manager().crystal_symmetry())
    else:
      assert box.map_manager().crystal_symmetry().space_group_number() == 1
      from cctbx import crystal
      assert box.map_manager().crystal_symmetry().is_similar_symmetry(
        crystal.symmetry(
           box.map_manager().unit_cell_crystal_symmetry().unit_cell(),
           1))
    return box.map_manager()


  def cc_to_other_map_manager(self, other_map_manager):
    assert self.is_similar(other_map_manager)

    return flex.linear_correlation(self.map_data().as_1d(),
     other_map_manager.map_data().as_1d()).coefficient()

  def density_at_sites_cart(self, sites_cart):
    '''
    Return flex.double list of density values corresponding to sites (cartesian
     coordinates in A)
    '''
    assert isinstance(sites_cart, flex.vec3_double)

    from cctbx.maptbx import real_space_target_simple_per_site
    return real_space_target_simple_per_site(
      unit_cell = self.crystal_symmetry().unit_cell(),
      density_map = self.map_data(),
      sites_cart = sites_cart)

  def get_density_along_line(self,
      start_site = None,
      end_site = None,
      n_along_line = 10,
      include_ends = True):

    '''
      Return group_args object with density values and coordinates
      along a line segment from start_site to end_site
      (cartesian coordinates in A) with n_along_line sampling points.
      Optionally include/exclude ends.
    '''
    along_sites = flex.vec3_double()
    if include_ends:
      start = 0
      end = n_along_line+1
    else:
      start = 1
      end = n_along_line

    for i in range(start, end):
      weight = (i/n_along_line)
      along_line_site = col(start_site)*weight+col(end_site)*(1-weight)
      along_sites.append(along_line_site)
    along_density_values = self.density_at_sites_cart(sites_cart = along_sites)
    return group_args(
     along_density_values = along_density_values,
       along_sites = along_sites)


  def resolution_filter(self, d_min = None, d_max = None):
    '''
      High- or low-pass filter the map in map_manager.
      Changes and overwrites contents of this map_manager.
      Remove all components with resolution < d_min or > d_max
      Either d_min or d_max or both can be None.
      To make a low_pass filter with cutoff at 3 A, set d_min=3
      To make a high_pass filter with cutoff at 2 A, set d_max=2

    '''
    map_coeffs = self.map_as_fourier_coefficients(d_min = d_min,
      d_max = d_max)
    mm = self.fourier_coefficients_as_map_manager( map_coeffs=map_coeffs)
    self.set_map_data(map_data = mm.map_data())  # replace map data


  def gaussian_filter(self, smoothing_radius):
    '''
      Gaussian blur the map in map_manager with given smoothing radius.
      Changes and overwrites contents of this map_manager.
    '''
    assert smoothing_radius is not None

    map_data = self.map_data()
    from cctbx.maptbx import smooth_map
    smoothed_map_data = smooth_map(
        map              = map_data,
        crystal_symmetry = self.crystal_symmetry(),
        rad_smooth       = smoothing_radius)
    self.set_map_data(map_data = smoothed_map_data)  # replace map data

  def binary_filter(self, threshold = 0.5):
    '''
      Apply a binary filter to the map (value at pixel i,j,k=1 if average
      of all 27 pixels within 1 of this one is > threshold, otherwise 0)
      Changes and overwrites contents of this map_manager.
    '''

    assert self.origin_is_zero()

    map_data=self.map_data()

    from cctbx.maptbx import binary_filter
    bf=binary_filter(map_data,threshold).result()
    self.set_map_data(map_data = bf)  # replace map data

  def deep_copy(self):
    '''
      Return a deep copy of this map_manager object
      Uses customized_copy to deepcopy everything including map_data

      Origin does not have to be at (0, 0, 0) to apply
    '''
    return self.customized_copy(map_data = self.map_data())

  def customized_copy(self, map_data = None, origin_shift_grid_units = None,
      use_deep_copy_for_map_data = True):
    '''
      Return a customized deep_copy of this map_manager, replacing map_data with
      supplied map_data.

      The map_data and any _created_mask will be deep_copied before using
      them unless use_deep_copy_for_map_data = False

      Normally this customized_copy is applied with a map_manager
      that has already shifted the origin to (0, 0, 0) with shift_origin.

      Normally the new map_data will have the same dimensions of the current
      map_data. Normally new map_data will also have origin at (0, 0, 0).

      NOTE: It is permissible for map_data to have different bounds or origin
      than the current self.map_data.  In this case you must specify a new
      value of origin_shift_grid_units corresponding to this new map_data.
      This new origin_shift_grid_units specifies the original position in the
      full unit cell grid of the most-negative corner grid point of the
      new map_data. The new map_manager will still have the same unit
      cell dimensions and grid as the original.

      NOTE: It is permissible to get a customized copy before shifting the
      origin.  Applying with non-zero origin requires that:
         self.origin_shift_grid_units == (0, 0, 0)
         origin_shift_grid_units = (0, 0, 0)
         map_data.all() (size in each direction)  of current and new maps
            are the same.
         origins of current and new maps are the same

       NOTE: wrapping is normally copied from original map, but if new map is
       not full size then wrapping is always set to False.

    '''

    # Make a deep_copy of map_data and _created_mask unless
    #    use_deep_copy_for_map_data = False

    if use_deep_copy_for_map_data:
      map_data = map_data.deep_copy()
      created_mask = deepcopy(self._created_mask)
    else:
      created_mask = self._created_mask

    assert map_data is not None # Require map data for the copy

    if map_data.origin() !=  (0, 0, 0):

      # Make sure all the assumptions are satisfied so we can just copy
      assert self.origin_shift_grid_units == (0, 0, 0)
      assert origin_shift_grid_units in [None, (0, 0, 0)]
      assert self.map_data().all() == map_data.all()
      assert self.map_data().origin() == map_data.origin()

      # Now just go ahead and copy using origin_shift_grid_units = (0, 0, 0)
      origin_shift_grid_units = (0, 0, 0)

    elif origin_shift_grid_units is None:  # use existing origin shift
      assert map_data.all()  ==  self.map_data().all() # bounds must be same
      origin_shift_grid_units = deepcopy(self.origin_shift_grid_units)

    # Keep track of change in shift_cart
    original_shift_cart=self.shift_cart()

    # Deepcopy this object and then set map_data and origin_shift_grid_units

    mm = deepcopy(self)

    # Set things that are not necessarily the same as in self:
    mm.log=self.log
    mm.origin_shift_grid_units = origin_shift_grid_units  # specified above
    mm.data = map_data  # using self.data or a deepcopy (specified above)
    mm._created_mask = created_mask  # using self._created_mask or a
                                     #deepcopy (specified above)
    if not mm.is_full_size():
      mm.set_wrapping(False)

    # Set up _crystal_symmetry for the new object
    mm.set_crystal_symmetry_of_partial_map() # Required and must be last

    # Keep track of change in shift_cart
    delta_origin_shift_grid_units = tuple([new - orig for new, orig in zip (
        origin_shift_grid_units, self.origin_shift_grid_units)])
    delta_shift_cart = tuple([-x for x in self.grid_units_to_cart(
       delta_origin_shift_grid_units)])
    new_shift_cart= tuple([
        o+d for o,d in zip(original_shift_cart,delta_shift_cart)])

    if self._ncs_object:
      mm._ncs_object = self._ncs_object.deep_copy(
        coordinate_offset=delta_shift_cart)
      assert approx_equal(mm.shift_cart(),mm._ncs_object.shift_cart())
    else:
      mm._ncs_object = None


    return mm

  def set_wrapping(self, wrapping_value):
    '''
       Set wrapping to be wrapping_value
    '''
    assert isinstance(wrapping_value, bool)
    self._wrapping = wrapping_value
    if self._wrapping:
      assert self.is_full_size()

  def wrapping(self):
    '''
      Report if map can be wrapped

    '''
    return self._wrapping

  def is_full_size(self):
    '''
      Report if map is full unit cell
    '''
    if self.map_data().all()  ==  self.unit_cell_grid:
      return True
    else:
      return False

  def is_consistent_with_wrapping(self, relative_sd_tol = 0.01):
    '''
      Report if this map looks like it is a crystallographic map and can be
      wrapped

      If it is not full size...no wrapping
      If origin is not at zero...no wrapping
      If it is not periodic, no wrapping
      If very small or resolution_factor for map is close to 0.5...cannot tell
      If has all zeroes (or some other constant on edges) ... no wrapping

      relative_sd_tol defines how close to constant values at edges must be
      to qualify as "constant"

      Returns True, False, or None (unsure)

    '''
    if not self.is_full_size():
      return False

    if self.map_data().origin() != (0, 0, 0):
      return False
    from cctbx.maptbx import is_periodic, is_bounded_by_constant
    if is_bounded_by_constant(self.map_data(),
       relative_sd_tol = relative_sd_tol):  # Looks like a cryo-EM map
      return False

    # Go with whether it looks periodic (cell translations give similar values
    #  or transform of high-res data is mostly at edges of cell)
    return is_periodic(self.map_data())  # Can be None if unsure


  def is_similar(self, other = None,
     absolute_angle_tolerance = 0.01,
     absolute_length_tolerance = 0.01,
     ):
    # Check to make sure origin, gridding and symmetry are similar
    self._warning_message=""

    if tuple(self.origin_shift_grid_units) !=  tuple(
        other.origin_shift_grid_units):
      self._warning_message="Origin shift grid units "+  \
        "(%s) does not match other (%s)" %(
        str(self.origin_shift_grid_units),str(other.origin_shift_grid_units))
      return False
    if not self.unit_cell_crystal_symmetry().is_similar_symmetry(
      other.unit_cell_crystal_symmetry(),
      absolute_angle_tolerance = absolute_angle_tolerance,
      absolute_length_tolerance = absolute_length_tolerance,):
      self._warning_message="Unit cell crystal symmetry:"+ \
        "\n%s\n does not match other:\n%s\n" %(
        str(self.unit_cell_crystal_symmetry()),
         str(other.unit_cell_crystal_symmetry()))
      return False
    if not self.crystal_symmetry().is_similar_symmetry(
      other.crystal_symmetry(),
      absolute_angle_tolerance = absolute_angle_tolerance,
      absolute_length_tolerance = absolute_length_tolerance):
      self._warning_message="Crystal symmetry:"+ \
        "\n%s\ndoes not match other: \n%s\n" %(
        str(self.crystal_symmetry()),
         str(other.crystal_symmetry()))
      return False
    if self.map_data().all()!=  other.map_data().all():
      self._warning_message="Existing map gridding "+ \
        "(%s) does not match other (%s)" %(
         str(self.map_data().all()),str(other.map_data().all()))
      return False
    if self.unit_cell_grid !=  other.unit_cell_grid:
      self._warning_message="Full map gridding "+ \
        "(%s) does not match other (%s)" %(
         str(self.map_data().all()),str(other.map_data().all()))
      return False

    # Make sure wrapping is same for all
    if ( self.wrapping() !=  other.wrapping()):
      self._warning_message="Wrapping "+ "(%s) does not match other (%s)" %(
         str(self.wrapping()),
         str(other.wrapping()))
      return False

    # Make sure ncs objects are similar if both have one
    if (self.ncs_object() is not None) and (
        other.ncs_object() is not None):
      if not other.ncs_object().is_similar_ncs_object(self.ncs_object()):
        text1=self.ncs_object().as_ncs_spec_string()
        text2=other.ncs_object().as_ncs_spec_string()
        self._warning_message="NCS objects do not match"+ \
           ":\n%s\n does not match other:\n%s" %( text1,text2)
        return False

    return True

  def grid_units_to_cart(self, grid_units):
    ''' Convert grid units to cartesian coordinates '''
    x = grid_units[0]/self.unit_cell_grid[0]
    y = grid_units[1]/self.unit_cell_grid[1]
    z = grid_units[2]/self.unit_cell_grid[2]
    return self.unit_cell().orthogonalize(tuple((x, y, z)))

  def ncs_object(self):
    return self._ncs_object

  def shift_cart(self):
    '''
     Return the shift_cart of this map from its original location.

     (the negative of the origin shift ) in cartesian coordinates
     '''
    return tuple(
       [-x for x in self.grid_units_to_cart(self.origin_shift_grid_units)])

  def set_ncs_object_shift_cart_to_match_map(self, ncs_object):
    '''
      Set the ncs_object shift_cart to match map

      Overwrites any information in ncs_object on shift_cart
      Modifies ncs_object in place

      Do not use this to try to shift the ncs object. That is done in
      the ncs object itself with ncs_object.coordinate_shift(shift_cart)
    '''

    # Set shift_cart (shift since readin) to match shift_cart for
    #   map (shift of origin is opposite of shift applied)
    ncs_object.set_shift_cart(self.shift_cart())

  def set_model_symmetries_and_shift_cart_to_match_map(self,model):
    '''
      Set the model original and working crystal_symmetry to match map.

      Overwrites any information in model on symmetry and shift_cart
      Modifies model in place

      NOTE: This does not shift the coordinates in model.  It is used
      to fix crystal symmetry and set shift_cart, not to actually shift
      a model.
      For shifting a model, use:
         model.shift_model_and_set_crystal_symmetry(shift_cart=shift_cart)
    '''

    # Check if we really need to do anything
    if self.is_compatible_model(model):
      return # already fine


    # Set crystal_symmetry to match map. This changes the xray_structure.
    model.set_crystal_symmetry(self.crystal_symmetry())

    # Set original crystal symmetry to match map unit_cell_crystal_symmetry
    # This just changes a specification in the map, nothing else changes
    model.set_unit_cell_crystal_symmetry(self.unit_cell_crystal_symmetry())

    # Set shift_cart (shift since readin) to match shift_cart for
    #   map (shift of origin is opposite of shift applied)
    model.set_shift_cart(self.shift_cart())

  def is_compatible_ncs_object(self, ncs_object, tol = 0.001):
    '''
      ncs_object is compatible with this map_manager if shift_cart is
      the same as map
    '''

    ok=True
    text=""

    map_shift=flex.double(self.shift_cart())
    ncs_object_shift=flex.double(ncs_object.shift_cart())
    delta=map_shift-ncs_object_shift
    mmm=delta.min_max_mean()
    if mmm.min < -tol or mmm.max > tol: # shifts do not match
      text="Shift of ncs object (%s) does not match shift of map (%s)" %(
         str(ncs_object_shift),str(map_shift))
      ok=False

    self._warning_message=text
    return ok

  def is_compatible_model(self, model,
       require_match_unit_cell_crystal_symmetry=True,
        absolute_angle_tolerance = 0.01,
        absolute_length_tolerance = 0.01,
        shift_tol = 0.001):
    '''
      Model is compatible with this map_manager if it is not specified as being
      different.

      They are different if:
        1. original and current symmetries are present and do not match
        2. model current symmetry does not match map original or current
        3. model has a shift_cart (shift applied) different than map shift_cart

      NOTE: a True result does not mean that the model crystal_symmetry matches
      the map crystal_symmetry.  It does mean that it is reasonable to set the
      model crystal_symmetry to match the map ones.

      If require_match_unit_cell_crystal_symmetry is True, then they are
      different if anything is different
    '''

    ok=None
    text=""

    model_uc=model.unit_cell_crystal_symmetry()
    model_sym=model.crystal_symmetry()
    map_uc=self.unit_cell_crystal_symmetry()
    map_sym=self.crystal_symmetry()

    text_model_uc="not defined"
    text_model_uc=str(model_uc).replace("\n"," ")
    text_model=str(model_sym).replace("\n"," ")
    text_map_uc=str(map_uc).replace("\n"," ")
    text_map=str(map_sym).replace("\n"," ")

    if require_match_unit_cell_crystal_symmetry and (not model_uc) and (
       not map_sym.is_similar_symmetry(map_uc,
        absolute_angle_tolerance = absolute_angle_tolerance,
        absolute_length_tolerance = absolute_length_tolerance,
         )):
      ok=False
      text="Model and map are different because "+\
          "require_match_unit_cell_crystal_symmetry is set and "+\
          "model does not have original_crystal_symmetry, and " +\
        "model symmetry: \n%s\n does not match map original symmetry:" %(
          model_sym) +\
        "\n%s\n. Current map symmetry is: \n%s\n " %(
         text_map_uc,text_map)

    elif  model_uc and (not map_uc.is_similar_symmetry(map_sym,
        absolute_angle_tolerance = absolute_angle_tolerance,
        absolute_length_tolerance = absolute_length_tolerance,
         ) and (
         (not model_uc.is_similar_symmetry(map_uc,
        absolute_angle_tolerance = absolute_angle_tolerance,
        absolute_length_tolerance = absolute_length_tolerance,
        )) or
         (not model_sym.is_similar_symmetry(map_sym,
        absolute_angle_tolerance = absolute_angle_tolerance,
        absolute_length_tolerance = absolute_length_tolerance,
         ) ) )):
       ok=False# model and map_manager symmetries present and do not match
       text="Model original symmetry: \n%s\n and current symmetry :\n%s\n" %(
          text_model_uc,text_model)+\
          "do not match map unit_cell symmetry:"+\
         " \n%s\n and map current symmetry: \n%s\n symmetry" %(
           text_map_uc,text_map)
    elif model_sym and (not model_sym.is_similar_symmetry(map_uc,
        absolute_angle_tolerance = absolute_angle_tolerance,
        absolute_length_tolerance = absolute_length_tolerance,
        )) and (not
              model_sym.is_similar_symmetry(map_sym,
        absolute_angle_tolerance = absolute_angle_tolerance,
        absolute_length_tolerance = absolute_length_tolerance,
        )):
       ok=False# model does not match either map symmetry
       text="Model current symmetry: \n%s\n" %(
          text_model)+\
          " does not match map unit_cell symmetry:"+\
           " \n%s\n or map current symmetry: \n%s\n" %(
           text_map_uc,text_map)

    elif require_match_unit_cell_crystal_symmetry and (
        not model_sym) and (not model_uc):
       ok=False # model does not have any symmetry so it does not match
       text="Model has no symmetry and cannot match any map"
    elif (not model_sym) and (not model_uc):
       ok=True # model does not have any symmetry so anything is ok
       text="Model has no symmetry and can match any map symmetry"

    else:  # match

       ok=True
       text="Model original symmetry: \n%s\n and current symmetry: \n%s\n" %(
          text_model_uc,text_model)+\
          "are compatible with "+\
          "map unit_cell symmetry:\n%s\n and current map symmetry:\n%s\n" %(
           text_map_uc,text_map)

    assert isinstance(ok, bool)  # must have chosen

    map_shift_cart=self.shift_cart()
    if ok and (map_shift_cart != (0,0,0)):
      if model.shift_cart() is None: # map is shifted but not model
        ok=False
        text+=" However map is shifted (shift_cart=%s) but model is not" %(
           str(map_shift_cart))
      else:
        map_shift=flex.double(map_shift_cart)
        model_shift=flex.double(model.shift_cart())
        delta=map_shift-model_shift
        mmm=delta.min_max_mean()
        if mmm.min<-shift_tol or mmm.max > shift_tol: # shifts do not match
          ok=False
          text+=" However map shift "+\
              "(shift_cart=%s) does not match model shift (%s)" %(
           str(map_shift),str(model_shift))
    self._warning_message=text
    return ok

  def warning_message(self):
    if hasattr(self,'_warning_message'):
       return self._warning_message

  def set_mean_zero_sd_one(self):
    ''' Normalize the map '''
    map_data = self.map_data()
    map_data = map_data - flex.mean(map_data)
    sd = map_data.sample_standard_deviation()
    assert sd != 0
    map_data = map_data/sd
    self.set_map_data(map_data)

  def ncs_cc(self):
    if hasattr(self,'_ncs_cc'):
       return self._ncs_cc

  def find_map_symmetry(self,
      include_helical_symmetry = False,
      symmetry_center = None,
      min_ncs_cc = None,
      symmetry = None):
    '''
       Use run_get_symmetry_from_map tool in segment_and_split_map to find
       map symmetry and save it as an mmtbx.ncs.ncs.ncs object

       Here map symmetry is the reconstruction symmetry used to generate the
       map. Normally it is essentially perfect symmetry and normally the
       principal axes are aligned with x,y,z and normally the center is at
       the original center of the map.

       Sets self._warning_message if failure, sets self._ncs_object and
           self._ncs_cc if success

       This procedure may fail if the above assumptions do not hold.
       Optional center of map can be supplied, and minimum NCS correlation
       can also be supplied

       Requires that map_manager is already shifted to place origin at (0, 0, 0)

       Assumes that center of symmetry is at (1/2, 1/2, 1/2) in the full map

       It is optional to include search for helical symmetry. Reason is that
       this is much slower than other symmetries.

       symmetry (symbol such as c1, O, D7) can be supplied and search will be
       limited to that symmetry
    '''

    assert self.origin_is_zero()

    self._warning_message = ""
    self._ncs_cc = None

    from cctbx.maptbx.segment_and_split_map import \
       run_get_ncs_from_map, get_params

    if symmetry is None:
      symmetry = 'ALL'

    if symmetry_center is None:
      # Most likely map center is (1/2,1/2,1/2) in full grid
      full_unit_cell=self.unit_cell_crystal_symmetry(
            ).unit_cell().parameters()[:3]
      symmetry_center=[]
      for x, sc in zip(full_unit_cell, self.shift_cart()):
        symmetry_center.append(0.5*x + sc)
      symmetry_center = tuple(symmetry_center)

    params = get_params(args=[],
      symmetry = symmetry,
      include_helical_symmetry = include_helical_symmetry,
      symmetry_center = symmetry_center,
      min_ncs_cc = min_ncs_cc,
      return_params_only = True,
      )


    new_ncs_obj, ncs_cc, ncs_score = run_get_ncs_from_map(params = params,
      map_data = self.map_data(),
      crystal_symmetry = self.crystal_symmetry(),
      out = self.log,
      )
    if new_ncs_obj:
      self._ncs_object = new_ncs_obj
      self._ncs_cc = ncs_cc
      self._ncs_object.set_shift_cart(self.shift_cart())
    else:
      self._warning_message = "No map symmetry found; ncs_cc cutoff of %s" %(
        min_ncs_cc)

  def map_as_fourier_coefficients(self, d_min = None,
     d_max = None):
    '''
       Convert a map to Fourier coefficients to a resolution of d_min,
       if d_min is provided, otherwise box full of map coefficients
       will be created.

       Filter results with low resolution of d_max if provided

       NOTE: Fourier coefficients are relative the working origin (not
       original origin).  A map calculated from the Fourier coefficients will
       superimpose on the working (current map) without origin shifts.

       This method and fourier_coefficients_as_map_manager interconvert map_data and
       map_coefficients without changin origin.  Both are intended for use
       with map_data that has an origin at (0, 0, 0).
    '''
    assert self.map_data()
    assert self.map_data().origin() == (0, 0, 0)
    ma = miller.structure_factor_box_from_map(
      crystal_symmetry = self.crystal_symmetry(),
      include_000      = True,
      map              = self.map_data(),
      d_min            = d_min )
    if d_max is not None:
      ma=ma.resolution_filter(d_min = d_min, d_max = d_max)
      # NOTE: miller array resolution_filter produces a new array.
      # Methods in map_manager that are _filter() change the existing array.
    return ma

  def fourier_coefficients_as_map_manager(self, map_coeffs):
    '''
       Convert Fourier coefficients into to a real-space map with gridding
        matching this existing map_manager.  Returns a map_manager object.

       Requires that this map_manager has origin at (0, 0, 0) (i.e.,
       shift_origin() has been applied if necessary)

       NOTE: Assumes that the map_coeffs are in the same frame of reference
       as this map_manager (i.e., similar to those that would be written out
       using map_as_fourier_coefficients).
    '''

    assert isinstance(map_coeffs, miller.array)
    assert isinstance(map_coeffs.data(), flex.complex_double)
    assert self.map_data() and self.map_data().origin() == (0, 0, 0)

    return self.customized_copy(
      map_data=maptbx.map_coefficients_to_map(
        map_coeffs       = map_coeffs,
        crystal_symmetry = self.crystal_symmetry(),
        n_real           = self.map_data().all())
      )

def subtract_tuples_int(t1, t2):
  return tuple(flex.int(t1)-flex.int(t2))

def add_tuples_int(t1, t2):
  return tuple(flex.int(t1)+flex.int(t2))
