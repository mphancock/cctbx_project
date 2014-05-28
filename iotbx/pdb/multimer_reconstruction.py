from __future__ import divisionfrom iotbx import crystal_symmetry_from_anyimport iotbx.pdb.hierarchyfrom scitbx.array_family import flexfrom libtbx.utils import Sorryfrom libtbx.phil import parsefrom scitbx import matrixfrom iotbx import pdbimport stringimport mathimport osmaster_phil = parse("""  ncs_refinement {    apply_when_coordinates_present = False      .type = bool      .help='''      Can apply transformations even if coordinates are already present.      Need to provide NCS selection'''    ncs_selection = ''      .type = str      .help = '''      If apply_when_coordinates_present is True, ncs_selection must be given      and should include the complete ncs.      '''    ignore_mtrix_records = False    .type = bool    .help = ''' Ignore MTRIX records, if present in the PDB file'''    ncs_group      .multiple = True      {        transform        .multiple = True        {          rotation = None            .type = floats(size=9, value_min=-1, value_max=1)          translation = None            .type = floats(size=3)          coordinates_present = None            .type = bool        }        apply_to_selection = None          .help = '''Selection syntax similar to what is used in CNS or PyMOL.          multiple selection lines will be concatenates.'''          .type = str          .multiple = True      }    }  """)class multimer(object):  '''  Reconstruction of either the biological assembly or the crystallographic asymmetric unit  Reconstruction of the biological assembly multimer by applying  BIOMT transformation, from the pdb file, to all chains.  Reconstruction of the crystallographic asymmetric unit by applying  MTRIX transformations, from the pdb file, to all chains.  self.assembled_multimer is a pdb.hierarchy object with the multimer information  The method write generates a PDB file containing the multimer  since chain names string length is limited to two, this process does not maintain any  referance to the original chain names.  Several useful attributes:  --------------------------  self.write() : To write the new object to a pdb file  self.assembled_multimer : The assembled or reconstructed object is in  self.number_of_transforms : Number of transformations that where applied  @author: Youval Dar (LBL )  '''  def __init__(self,               reconstruction_type,               file_name=None,               pdb_str=None,               error_handle=True,               eps=1e-3,               round_coordinates=True,               params=None ):    '''    Arguments:    reconstruction_type -- 'ba' or 'cau'                           'ba': biological assembly                           'cau': crystallographic asymmetric unit    file_name -- the name of the pdb file we want to process.                 a string such as 'pdb_file_name.pdb'    pdb_str -- a string containing pdb information, when not using a pdb file    error_handle -- True: will stop execution on improper rotation matrices                    False: will continue execution but will replace the values                          in the rotation matrix with [0,0,0,0,0,0,0,0,0]    eps -- Rounding accuracy for avoiding numerical issue when when testing           proper rotation    round_coordinates -- round coordinates of new NCS copies, for sites_cart                         constancy    params -- information about how to apply transformations, with the              following phil structure:                ncs_refinement {                  apply_when_coordinates_present = (bool)                  ncs_selection = (str)                  ignore_mtrix_records = (bool)                  ncs_group {                    transform {                      rotation = tuple(float), size 9                      translation = tuple(float), size 3                      coordinates_present = (Bool / None)                    }                    apply_to_selection = (str)                  }                }    @author: Youval Dar (2013)    '''    assert file_name or pdb_str    # Read and process the pdb file    if file_name:      self.pdb_input_file_name = file_name      pdb_obj = pdb.hierarchy.input(file_name=file_name)    else:      self.pdb_input_file_name = pdb_str      pdb_obj = pdb.hierarchy.input(pdb_string=pdb_str)    pdb_obj_new = pdb_obj.hierarchy.deep_copy()    self.assembled_multimer = pdb_obj_new    self.transforms_obj = ncs_group_object()    # Read the relevant transformation matrices    if reconstruction_type == 'ba':      # Read BIOMT info      self.transforms_obj.populate_ncs_group_object(        ncs_refinement_params = params,        reconstruction_type= 'ba',        pdb_hierarchy_inp = pdb_obj)      self.transform_type = 'biological_assembly'    elif reconstruction_type == 'cau':      # Read MTRIX info      self.transforms_obj.populate_ncs_group_object(        ncs_refinement_params = params,        pdb_hierarchy_inp = pdb_obj)      self.transform_type = 'crystall_asymmetric_unit'    else:      raise Sorry('Worg reconstruction type is given \n' + \                  'Reconstruction type can be: \n' + \                  "'ba': biological assembly \n" + \                  "'cau': crystallographic asymmetric unit \n")    if len(pdb_obj_new.models()) > 1:      raise Sorry('Sorry, this feature currently supports on single models ' +                  'hierarchies')    # Calculate ASU (if there are any transforms to apply)    if self.transforms_obj.transform_to_be_used:      self.ncs_unique_chains_ids = self.transforms_obj.model_unique_chains_ids      self.number_of_transforms = len(self.transforms_obj.transform_to_be_used)      new_sites = self.transforms_obj.apply_transforms(        ncs_coordinates = pdb_obj.hierarchy.atoms().extract_xyz(),        round_coordinates = round_coordinates)      # apply the transformation      model = pdb_obj_new.models()[0]      for tr in self.transforms_obj.transform_chain_assignment:        key = tr.split('_')[0]        ncs_selection = self.transforms_obj.asu_to_ncs_map[key]        new_part = pdb_obj.hierarchy.select(ncs_selection).deep_copy()        new_chain = iotbx.pdb.hierarchy.ext.chain()        new_chain.id = self.transforms_obj.ncs_copies_chains_names[tr]        for res in new_part.residue_groups():          new_chain.append_residue_group(res.detached_copy())        model.append_chain(new_chain)      self.assembled_multimer.atoms().set_xyz(new_sites)  def get_source_hierarchy(self):    """    Retrieve the Original PDB hierarchy from the ASU    """    ncs_length = self.transforms_obj.total_length_extended_ncs    asu_length = self.transforms_obj.total_asu_length    source_atom_selection = flex.bool([True]*ncs_length)    temp = flex.bool([False]*(asu_length - ncs_length))    source_atom_selection.extend(temp)    return self.assembled_multimer.select(source_atom_selection)  def sites_cart(self):    """ () -> flex.vec3    Returns the reconstructed hierarchy sites cart (atom coordinates)    """    return self.assembled_multimer.atoms().extract_xyz()  def write(self,pdb_output_file_name='',crystal_symmetry=None):    ''' (string) -> text file    Writes the modified protein, with the added chains, obtained by the BIOMT/MTRIX    reconstruction, to a text file in a pdb format.    self.assembled_multimer is the modified pdb object with the added chains    Argumets:    pdb_output_file_name -- string. 'name.pdb'    if no pdn_output_file_name is given pdb_output_file_name=file_name    >>> v = multimer('name.pdb','ba')    >>> v.write('new_name.pdb')    Write a file 'new_name.pdb' to the current directory    >>> v.write(v.pdb_input_file_name)    Write a file 'copy_name.pdb' to the current directory    '''    input_file_name = os.path.basename(self.pdb_input_file_name)    if pdb_output_file_name == '':      pdb_output_file_name = input_file_name    # Aviod writing over the original file    if pdb_output_file_name == input_file_name:      # if file name of output is the same as the input, add 'copy_' in front of the name      self.pdb_output_file_name = self.transform_type + '_' + input_file_name    else:      self.pdb_output_file_name = pdb_output_file_name    # we need to add crystal symmetry to the new file since it is    # sometimes needed when calulating the R-work factor (r_factor_calc.py)    if not crystal_symmetry:      crystal_symmetry = crystal_symmetry_from_any.extract_from(        self.pdb_input_file_name)    # using the pdb hierarchy pdb file writing method    self.assembled_multimer.write_pdb_file(file_name=self.pdb_output_file_name,      crystal_symmetry=crystal_symmetry)class ncs_group_object(object):  def __init__(self):    """    process MTRIX, BOIMT and PHIL parameters and produce an object    with information for NCS refinement    Argument:    transform_info:  an object produced from the PDB MTRIX or BIOMT records    ncs_refinement_params: an object produced by the PHIL parameters    """    self.ncs_refinement_groups = None    self.apply_to_all_chains = False    # When ncs is known, reproduce asu even if the PDB file already contains    # the complete asu    self.apply_when_coordinates_present = False    # maps each chain in the ncs to its copies position in the asu, and the    # asu back to the ncs.    # the keys are chain-id_transform-serial-number, ie A_3    # values are list [start pos, end pos]    self.ncs_to_asu_map = {}    # values are flex iselection of the corresponding atoms in the ncs    self.asu_to_ncs_map = {}    self.ncs_copies_chains_names = {}    # map all dictionaries key to chain ID or ncs_selection    self.map_keys_to_selection = {}    # dictionary of transform names, same keys as ncs_to_asu_map    self.ncs_group = {}    self.ncs_group_pdb = {}    # map transform name (s1,s2,...) to transform object    self.ncs_transform = {}    self.ncs_transform_pdb = {}    # dictionary kes: selection names. values: number_of_copies_in_asu    self.number_of_ncs_copies = {}    # list of which transform is applied to which chain    # (the keys of ncs_to_asu_map, asu_to_ncs_map and ncs_group)    self.transform_chain_assignment = []    # map transformation to atoms in ncs. keys are s+transform serial number    # ie s1,s2.... values are list of ncs_to_asu_map keys    self.transform_to_ncs = {}    # sorted list of transformation    self.transform_order = []    # length of all chains in ncs    self.total_ncs_length = None    # ncs + all coordinates that no transform is applied to    self.total_length_extended_ncs = None    # length of all chains in asu    self.total_asu_length = None    # flex.bool ncs_atom_selection    self.ncs_atom_selection = None    self.ncs_selection_str = ''    # selection of all chains in NCS    self.all_pdb_selection = ''    self.pdb_chain_selection = []    # unique identifiers    self.model_unique_chains_ids = tuple()    self.selection_ids = set()    # transform application order    self.model_order_chain_ids = []    self.transform_to_be_used = set()    # Use to produce new unique names for atom selections    self.selection_names_index = [65,65]    # ignore MTRIX record if present in PDB file    self.ignore_mtrix_records = False  def populate_ncs_group_object(self,                                ncs_refinement_params = None,                                transform_info = None,                                pdb_hierarchy_inp = None,                                reconstruction_type = 'cau',                                rotations = None,                                translations = None):    """    Construct ncs_group_object    If rotations and translations are provided, they will be applied to all    selection groups (chains)    Arguments:    ncs_refinement_params : Phil parameters    transform_info : an object containing MTRIX or BIOMT transformation info    pdb_hierarchy_inp : iotbx.pdb.hierarchy.input    rotations : matrix.sqr 3x3 object    translations : matrix.col 3x1 object    """    self.collect_basic_info_from_pdb(pdb_hierarchy_inp=pdb_hierarchy_inp)    # process params    if ncs_refinement_params:      if isinstance(ncs_refinement_params,str):        ncs_refinement_params = parse(ncs_refinement_params)      working_phil = master_phil.fetch(source=ncs_refinement_params).extract()      self.ncs_refinement_groups = working_phil.ncs_refinement.ncs_group      self.ncs_selection_str = working_phil.ncs_refinement.ncs_selection      self.ignore_mtrix_records = \        working_phil.ncs_refinement.ignore_mtrix_records      self.apply_when_coordinates_present = \        working_phil.ncs_refinement.apply_when_coordinates_present      self.apply_to_all_chains = not \        (self.ncs_refinement_groups or working_phil.ncs_refinement.ncs_selection)    self.get_all_chains_from_phil_or_pdb()    if self.ncs_refinement_groups: self.process_phil_param()    # add rotations,translations to ncs_refinement_groups    self.add_transforms_to_ncs_refinement_groups(      rotations=rotations,      translations=translations)    # process PDB    self.process_pdb(      reconstruction_type=reconstruction_type,      transform_info=transform_info,      pdb_hierarchy_inp=pdb_hierarchy_inp)    # transformation application order    self.transform_order =sorted(      self.transform_to_ncs,key=lambda key: int(key[1:]))    for tr_id in self.transform_order:      for tr_selection in self.transform_to_ncs[tr_id]:        self.transform_chain_assignment.append(tr_selection)    self.ncs_copies_chains_names = self.make_chains_names(      transform_assignment=self.transform_chain_assignment,      unique_chain_names = self.model_unique_chains_ids)    if pdb_hierarchy_inp:      self.compute_ncs_asu_coordinates_map(pdb_hierarchy_inp=pdb_hierarchy_inp)    for k,v in self.ncs_group.iteritems():      key = k.split('_')[0]      if self.number_of_ncs_copies.has_key(key):        self.number_of_ncs_copies[key] += 1      else:         self.number_of_ncs_copies[key] = 1  def add_transforms_to_ncs_refinement_groups(self,                                              rotations=None,                                              translations=None):    """ Add  rotation matrices and translations vectors    to ncs_refinement_groups    """    if rotations:      # ncs selection      selection = self.ncs_selection_str      assert selection      #if phil parameters were provided,transforms serial number is changed      sn = {int(x[1:]) for x in self.ncs_transform.iterkeys()}      if not 1 in sn:        self.add_identity_transform()        sn.add(1)      n = max(sn)      assert len(rotations) == len(translations)      for (r,t) in zip(rotations,translations):        # check if transforms are the identity transform        identity = r.is_r3_identity_matrix() and t.is_col_zero()        if not identity:          n += 1          sn.add(n)          key = 's' + format_num_as_str(n)          tr = transform(            rotation = r,            translation = t,            serial_num = n,            coordinates_present = False)          assert not self.ncs_transform_pdb.has_key(key)          self.ncs_transform[key] = tr          self.build_transform_dict(            transform_id=key,            transform=tr,            selection_id=selection)          self.selection_ids.add(selection)  def collect_basic_info_from_pdb(self,pdb_hierarchy_inp):    """  Build chain selection string and collect chains IDs from pdb """    if pdb_hierarchy_inp:      model  = pdb_hierarchy_inp.hierarchy.models()[0]      chain_ids = {x.id for x in model.chains()}      # Collect order if chains IDs and unique IDs      self.model_unique_chains_ids = tuple(sorted(chain_ids))      self.model_order_chain_ids = [x.id for x in model.chains()]      s = ' or chain '.join(self.model_unique_chains_ids)      self.all_pdb_selection = 'chain ' + s      self.pdb_chain_selection =\        ['chain ' + s for s in self.model_unique_chains_ids]      self.pdb_chain_selection.sort()  def compute_ncs_asu_coordinates_map(self,pdb_hierarchy_inp):    """ Calculates coordinates maps from ncs to asu and from asu to ncs """    # in the case of regular pdb processing    if not self.apply_when_coordinates_present:      if self.apply_to_all_chains:        self.total_ncs_length = len(pdb_hierarchy_inp.hierarchy.atoms())      else:        self.total_ncs_length = len(self.ncs_atom_selection)    if not self.total_length_extended_ncs:      self.total_length_extended_ncs = self.total_ncs_length    assert bool(self.total_length_extended_ncs)    i = self.total_length_extended_ncs    temp = pdb_hierarchy_inp.hierarchy.atom_selection_cache()    for k in self.transform_chain_assignment:      key =  k.split('_')[0]      temp_selection = temp.selection(key)      self.asu_to_ncs_map[key] = temp_selection.iselection()      d = len(self.asu_to_ncs_map[key])      self.ncs_to_asu_map[k] = [i,i + d]      i += d    self.total_asu_length = i    # update ncs_atom_selection to the correct asu length    ncs_length = self.total_length_extended_ncs    asu_length = self.total_asu_length    temp = flex.bool([False]*(asu_length - ncs_length))    self.ncs_atom_selection.extend(temp)  def process_phil_param(self):    # TODO: add tests    """    Remarks:    - When using phil parameters, the selection string is used as a chain ID    """    if self.apply_when_coordinates_present:      assert bool(self.ncs_selection_str)    self.add_identity_transform()    serial_num = 2    for ncsg in self.ncs_refinement_groups:      #if no specific selection is made for the group,use the overall selection      if ncsg.apply_to_selection == ['']:        ncsg.apply_to_selection = [self.all_pdb_selection]      # create ncs selection      if ncsg.apply_to_selection:        selection_key = ' '.join(ncsg.apply_to_selection)      else:        selection_key = self.ncs_selection_str      for tr in ncsg.transform:        r = tr.rotation        t = tr.translation        cp = bool(tr.coordinates_present)        assert len(r) == 9        assert len(t) == 3        tranform_obj = transform(          rotation = matrix.sqr(r),          translation = matrix.col(t),          serial_num = serial_num,          coordinates_present = cp)        transform_key = 's' + format_num_as_str(serial_num)        serial_num += 1        self.ncs_transform[transform_key] = tranform_obj        self.build_transform_dict(          transform_id=transform_key,          transform=tranform_obj,          selection_id=selection_key)        self.selection_ids.add(selection_key)  def add_identity_transform(self):    """    Add identity transform    """    tranform_obj = transform(      rotation = matrix.sqr([1,0,0,0,1,0,0,0,1]),      translation = matrix.col([0,0,0]),      serial_num = 1,      coordinates_present = True)    self.ncs_transform['s001'] = tranform_obj    self.build_transform_dict(      transform_id='s001',      transform=tranform_obj,      selection_id=self.ncs_selection_str)    self.selection_ids.add(self.ncs_selection_str)  def process_pdb(self,transform_info,reconstruction_type,pdb_hierarchy_inp):    """    Process PDB Hierarchy object    Remarks:    The information on a chain in a PDB file does not have to be continuous.    Every time the chain name changes in the pdb file, a new chain is added    to the model, even if the chain ID already exist. so there model.    chains() might contain several chains that have the same chain ID    """    if pdb_hierarchy_inp and (not self.ignore_mtrix_records):        pdb_inp = pdb_hierarchy_inp.input        if not transform_info:          if reconstruction_type == 'ba':            transform_info  = pdb_inp.process_BIOMT_records()          else:             transform_info  = pdb_inp.process_mtrix_records()    transform_info_available = bool(transform_info) and bool(transform_info.r)    if transform_info_available and (not self.ignore_mtrix_records):      # ncs selection      if self.apply_when_coordinates_present:        selection = [self.ncs_selection_str]      else:        selection =   self.pdb_chain_selection      #if phil parameters were provided,transforms serial number is changed      sn = {int(x[1:]) for x in self.ncs_transform.iterkeys()}      ti = transform_info      # avoid repeated serial numbers, also if not in order      sn_pdb = {int(x) for x in ti.serial_number}      sn_intersection = sn.intersection(sn_pdb)      sn.update(sn_pdb)      max_sn = max(sn)      for (r,t,n,cp) in zip(ti.r,ti.t,ti.serial_number,ti.coordinates_present):        n = int(n)        if n in sn_intersection:          max_sn += 1          n = max_sn          sn.add(n)        key = 's' + format_num_as_str(n)        tr = transform(          rotation = r,          translation = t,          serial_num = n,          coordinates_present = cp)        assert not self.ncs_transform_pdb.has_key(key)        self.ncs_transform_pdb[key] = tr        for select in selection:          self.build_transform_dict(            transform_id=key,            transform=tr,            selection_id=select)          self.selection_ids.add(select)        # if ncs selection was not provided in phil parameter        assert not self.ncs_transform.has_key(key)        self.ncs_transform[key] = tr    if pdb_hierarchy_inp:      ncs_selection_str = self.ncs_selection_str      if not ncs_selection_str: ncs_selection_str = self.all_pdb_selection      assert ncs_selection_str      temp = pdb_hierarchy_inp.hierarchy.atom_selection_cache()      self.ncs_atom_selection = temp.selection(ncs_selection_str)      self.map_keys_to_selection = {k:k.split('_')[0] for k in self.ncs_group}  def get_all_chains_from_phil_or_pdb(self):    """    Collect all selection from all groups    """    selection_str = ''    selection_keys = set()    if self.ncs_refinement_groups:      for ncsg in self.ncs_refinement_groups:        if ncsg.apply_to_selection:          selection_key = ' '.join(ncsg.apply_to_selection)        else:          selection_key = 'all'        selection_keys.add(selection_key)    if self.ncs_selection_str: selection_keys.add(self.ncs_selection_str)    if 'all' in selection_keys:      selection_keys.discard('all')      if self.all_pdb_selection and (not self.ignore_mtrix_records):        selection_keys.add(self.all_pdb_selection)    selection_keys = list(selection_keys)    if selection_keys:      selection_str = '('+ selection_keys[0] +')'    for i in range(1,len(selection_keys)):      selection_str += ' or (' + selection_keys[i] + ')'    if selection_str:      self.ncs_selection_str = selection_str    elif not self.ignore_mtrix_records:      self.ncs_selection_str = self.all_pdb_selection    assert bool(self.ncs_selection_str)  def build_transform_dict(self,                           transform_id,                           transform,                           selection_id):    """    Arguments:    transform_id : (str) s001,s002...    transform : transform object, containing information on transformation    selection_id : (str) NCS selection string    """    if (not transform.coordinates_present) or \            self.apply_when_coordinates_present:      self.transform_to_be_used.add(transform.serial_num)      key = selection_id + '_' + format_num_as_str(transform.serial_num)      self.ncs_group[key] = transform_id      if self.transform_to_ncs.has_key(transform_id):        self.transform_to_ncs[transform_id].append(key)      else:        self.transform_to_ncs[transform_id] = [key]  def build_MTRIX_object(self):    """    Build a MTRIX object from ncs_group_object    Used for testing    """    result = iotbx.pdb._._mtrix_and_biomt_records_container()    tr_dict = self.ncs_transform_pdb    tr_sorted = sorted(tr_dict,key=lambda k:tr_dict[k].serial_num)    for key in tr_sorted:      transform = self.ncs_transform_pdb[key]      result.add(        r=transform.rotation,        t=transform.translation,        coordinates_present=transform.coordinates_present,        serial_number=transform.serial_num)    return result  def produce_selection_name(self):    """    Create a new unique name each time called, to name the NCS selections,    since they do not have to be the chain names    """    top_i = ord('Z')    i,j = self.selection_names_index    new_selection_name = 'S' + chr(i) + chr(j)    i += (j == ord('Z')) * 1    j = 65 + (j - 65 + 1) % 26    assert i <= top_i    self.selection_names_index = [i,j]    return new_selection_name  def make_chains_names(self,                        transform_assignment,                        unique_chain_names):    """    Create a dictionary names for the new NCS copies    keys: (str) chain_name + '_s' + serial_num    values: (str) (one or two chr long)    Chain names might repeat themselves several times in a pdb file    We want copies of chains with the same name to still have the    same name after similar BIOMT/MTRIX transformation    Arguments:    transform_assignment : (list) transformation assignment order    unique_chain_names : (tuple) a set of unique chain names    Returns:    new_names : a dictionary. {'A_1': 'G', 'A_2': 'H',....} map a chain    name and a transform number to a new chain name    >>> self.make_chains_names((1,2),['chain A_002','chain B_002'],('A','B'))    {'A_1': 'C', 'A_2': 'D', 'B_1': 'E', 'B_2': 'F'}    """    if not transform_assignment or not unique_chain_names: return {}    # create list of character from which to assemble the list of names    # total_chains_number = len(i_transforms)*len(unique_chain_names)    total_chains_number = len(transform_assignment)    # start naming chains with a single letter    chr_list1 = list(set(string.ascii_uppercase) - set(unique_chain_names))    chr_list2 = list(set(string.ascii_lowercase) - set(unique_chain_names))    chr_list1.sort()    chr_list2.sort()    new_names_list = chr_list1 + chr_list2    # check if we need more chain names    if len(new_names_list) < total_chains_number:      n_names =  total_chains_number - len(new_names_list)      # the number of character needed to produce new names      chr_number = int(math.sqrt(n_names)) + 1      # build character list      chr_list = list(string.ascii_uppercase) + \                 list(string.ascii_lowercase) + \                 list(string.digits)      # take only as many characters as needed      chr_list = chr_list[:chr_number]      extra_names = set([ x+y for x in chr_list for y in chr_list])      # make sure not using existing names      extra_names = list(extra_names - unique_chain_names)      extra_names.sort()      new_names_list.extend(extra_names)    assert len(new_names_list) >= total_chains_number    dictionary_values = new_names_list[:total_chains_number]    # create the dictionary    zippedlists = zip(transform_assignment,dictionary_values)    new_names_dictionary = {x:y for (x,y) in zippedlists}    return new_names_dictionary  def apply_transforms(self,                      ncs_coordinates,                      round_coordinates = True):    """    Apply transformation to the information in the transforms_obj to the    ncs_coordinates (flex.vec3), and round the results if    round_coordinates is True    Returns:    complete asymmetric or the biological unit    """    asu_xyz = flex.vec3_double(ncs_coordinates)    for trans in self.transform_chain_assignment:      s_asu,e_asu = self.ncs_to_asu_map[trans]      ncs_selection = self.asu_to_ncs_map[trans.split('_')[0]]      ncs_xyz = ncs_coordinates.select(ncs_selection)      tr_key = 's' + trans.split('_')[1]      assert self.ncs_transform.has_key(tr_key)      tr = self.ncs_transform[tr_key]      new_sites = tr.rotation.elems* ncs_xyz+tr.translation      asu_xyz.extend(new_sites)      # make sure that the new ncs copies are added in the expected order      assert len(new_sites) == (e_asu - s_asu)      assert len(asu_xyz) == e_asu    if round_coordinates:      return flex.vec3_double(asu_xyz).round(3)    else:      return flex.vec3_double(asu_xyz)class transform(object):  def __init__(self,               rotation,               translation,               serial_num,               coordinates_present):    """    Basic transformation properties    Argument:    rotation : Rotation matrix object    translation: Translation matrix object    serial_num : (int) Transform serial number    coordinates_present: equals 1 when coordinates are presents in PDB file    """    self.rotation = rotation    self.translation = translation    self.serial_num = serial_num    self.coordinates_present = bool(coordinates_present)def format_num_as_str(n):  """  return a 3 digit string of n  """  if n > 999 or n < 0:    raise IOError('Input out of the range 0 - 999.')  else:    s1 = n//100    s2 = (n%100)//10    s3 = n%10    return str(s1) + str(s2) + str(s3)